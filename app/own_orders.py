import json,re
import sqlite3
from datetime import datetime,timezone,timedelta
from decimal import Decimal,InvalidOperation
from .market_stream import LOCATIONS
from .item_ids import market_item_id
from .item_names import item_name


def amount(value,optional=False):
    if optional and value in (None,''):return None
    try:
        result=Decimal(str(value).replace(' ','').replace('\u00a0','').replace(',','.'))
        if not result.is_finite() or result<0:raise ValueError()
        return result
    except (InvalidOperation,ValueError):raise ValueError('Введите неотрицательную сумму серебра')


def order_totals(orders,tax):
    tax=amount(tax)/100
    if tax>1:raise ValueError('Налог должен быть от 0 до 100%')
    buy=Decimal(0);sell=Decimal(0);cost=Decimal(0);unknown=0;active=0
    for order in orders:
        if order.get('status','active')!='active':continue
        qty=order['quantity'];price=amount(order['price']);unit_cost=amount(order.get('cost'),True)
        if type(qty) is not int or qty<0:raise ValueError('Остаток должен быть целым неотрицательным числом')
        if not qty:continue
        active+=1
        if order['side']=='buy':buy+=price*qty
        elif order['side']=='sell':
            sell+=price*qty
            if unit_cost is None:unknown+=1
            else:cost+=unit_cost*qty
        else:raise ValueError('Неизвестный тип заказа')
    return dict(buy=buy,sell=sell,net=sell*(1-tax),cost=cost,invested=buy+cost,
        unknown_cost=unknown,order_value=buy+sell,active=active)


class OwnOrderStore:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS own_orders (id INTEGER PRIMARY KEY,payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS personal_meta (key TEXT PRIMARY KEY,value TEXT)');self.db.commit()
        self.db.execute('CREATE TABLE IF NOT EXISTS captured_own_orders (owner TEXT,city TEXT,side TEXT,order_id TEXT,payload TEXT,cost TEXT,PRIMARY KEY(owner,city,side,order_id))');self.db.commit()
        self.db.execute('CREATE TABLE IF NOT EXISTS own_order_events (owner TEXT,event_id TEXT,payload TEXT,PRIMARY KEY(owner,event_id))');self.db.commit()
        self.db.execute('CREATE TABLE IF NOT EXISTS own_order_terminal (owner TEXT,order_id TEXT,status TEXT,PRIMARY KEY(owner,order_id))');self.db.commit()
    def version(self):
        row=self.db.execute("SELECT value FROM personal_meta WHERE key='own_version'").fetchone()
        return row[0] if row else ''
    def orders(self,owner=None):
        rows=[dict(json.loads(payload),id=key,source='manual') for key,payload in self.db.execute('SELECT id,payload FROM own_orders ORDER BY id')]
        now=datetime.now(timezone.utc)
        for who,city,side,key,payload,cost in self.db.execute('SELECT * FROM captured_own_orders ORDER BY owner,city,side,order_id'):
            if owner is not None and owner!=who:continue
            order=json.loads(payload);order.update(auto_key=[who,city,side,key],source='auto',cost=cost)
            if order.get('status') in ('active','unconfirmed') and order.get('expires') and datetime.fromisoformat(order['expires'])<=now:order['status']='finished'
            rows.append(order)
        return rows
    def capture_status(self):
        row=self.db.execute("SELECT value FROM personal_meta WHERE key='own_capture_status'").fetchone()
        return row[0] if row else 'Для первого снимка просмотри свои заказы без фильтра.'
    def observe(self,payload):
        if isinstance(payload,dict) and payload.get('Action'):
            from .own_order_events import observe_event
            return observe_event(self,payload)
        if isinstance(payload,dict) and payload.get('Finished') is True:
            if not isinstance(payload.get('CharacterId'),str) or not payload['CharacterId'] or not isinstance(payload.get('Orders'),list):raise ValueError('Неверные завершённые заказы')
            ids=[]
            for entry in payload['Orders']:
                if not isinstance(entry,dict) or not isinstance(entry.get('Id'),(int,str)) or isinstance(entry['Id'],bool):raise ValueError('Неверный ID завершённого заказа')
                ids.append(str(entry['Id']))
            with self.db:
                for key in ids:
                    self.db.execute('INSERT OR REPLACE INTO own_order_terminal VALUES(?,?,?)',(payload['CharacterId'],key,'finished'))
                    for who,city,side,ident,raw,cost in self.db.execute('SELECT * FROM captured_own_orders WHERE owner=? AND order_id=?',(payload['CharacterId'],key)).fetchall():
                        record=json.loads(raw);record['status']='finished'
                        record['terminal']=True
                        self.db.execute('UPDATE captured_own_orders SET payload=? WHERE owner=? AND city=? AND side=? AND order_id=?',(json.dumps(record,ensure_ascii=False),who,city,side,ident))
                self.db.execute('INSERT OR REPLACE INTO personal_meta VALUES(?,?)',('own_version',datetime.now(timezone.utc).isoformat()))
            return len(ids)
        orders=decode_own_orders(payload)
        stamp=datetime.now(timezone.utc).isoformat()
        with self.db:
            for order in orders:
                key=(payload['CharacterId'],order['city'],order['side'],order['order_id'])
                terminal=self.db.execute('SELECT status FROM own_order_terminal WHERE owner=? AND order_id=?',(key[0],key[3])).fetchone()
                if terminal:order.update(status=terminal[0],terminal=True)
                previous=self.db.execute('SELECT payload FROM captured_own_orders WHERE owner=? AND city=? AND side=? AND order_id=?',key).fetchone()
                if previous:
                    old=json.loads(previous[0])
                    if old.get('terminal'):continue
                    if old.get('observed','')>order['observed']:continue
                    order['original_quantity']=max(old.get('original_quantity',old['quantity']),order['quantity'])
                    order['created']=old.get('created') or order.get('created')
                self.db.execute('INSERT INTO captured_own_orders VALUES(?,?,?,?,?,NULL) ON CONFLICT(owner,city,side,order_id) DO UPDATE SET payload=excluded.payload',(*key,json.dumps(order,ensure_ascii=False)))
            # Supersede only the illustrative screenshot rows, once per page.
            touched={(o['city'],o['side']) for o in orders}
            for ident,raw in self.db.execute('SELECT id,payload FROM own_orders').fetchall():
                old=json.loads(raw)
                if (old.get('city'),old.get('side')) in touched and old.get('note','').startswith('Только видимые строки пользовательского скриншота'):
                    self.db.execute('DELETE FROM own_orders WHERE id=?',(ident,))
            self.db.execute('INSERT OR REPLACE INTO personal_meta VALUES(?,?)',('own_version',stamp))
            if orders:self.db.execute('INSERT OR REPLACE INTO personal_meta VALUES(?,?)',('own_capture_status',f'Получено с последней страницы: {len(orders)}. Старые непроверенные строки в текущий список не входят.'))
        return len(orders)
    def new_snapshot(self):
        with self.db:
            for who,city,side,key,raw,cost in self.db.execute('SELECT * FROM captured_own_orders').fetchall():
                record=json.loads(raw)
                if record.get('terminal') or record['status'] in ('finished','cancelled'):continue
                record['status']='unconfirmed'
                self.db.execute('UPDATE captured_own_orders SET payload=? WHERE owner=? AND city=? AND side=? AND order_id=?',(json.dumps(record,ensure_ascii=False),who,city,side,key))
            self.db.execute('INSERT OR REPLACE INTO personal_meta VALUES(?,?)',('own_version',datetime.now(timezone.utc).isoformat()))
    def save(self,orders):
        # Validate the complete edited list before replacing any persisted data.
        for order in orders:
            if not order.get('name','').strip():raise ValueError('Укажите название предмета')
            if type(order['quantity']) is not int or order['quantity']<0:raise ValueError('Остаток должен быть целым неотрицательным числом')
            if order.get('status','active') not in ('active','finished','cancelled','unconfirmed'):raise ValueError('Неизвестное состояние заказа')
            amount(order['price']);amount(order.get('cost'),True)
        order_totals(orders,0)
        with self.db:
            self.db.execute('DELETE FROM own_orders')
            for order in orders:
                if order.get('source')=='auto':
                    self.db.execute('UPDATE captured_own_orders SET cost=? WHERE owner=? AND city=? AND side=? AND order_id=?',(order.get('cost'),*order['auto_key']))
                    continue
                record=dict(order);record.pop('id',None);record['updated']=datetime.now(timezone.utc).isoformat()
                self.db.execute('INSERT INTO own_orders(payload) VALUES(?)',(json.dumps(record,ensure_ascii=False),))
    def close(self):self.db.close()


def decode_own_orders(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('Orders'),list) or len(payload['Orders'])>5000:raise ValueError('Неверный список собственных заказов')
    owner=payload.get('CharacterId');player=payload.get('CharacterName','')
    if not isinstance(owner,str) or not owner or len(owner)>128 or not isinstance(player,str):raise ValueError('Неизвестный владелец заказов')
    side=payload.get('Side');fallback=LOCATIONS.get(str(payload.get('LocationId')))
    if side not in ('buy','sell','mixed'):raise ValueError('Неверная сторона собственных заказов')
    result=[]
    for entry in payload['Orders']:
        if not isinstance(entry,dict):raise ValueError('Неверный собственный заказ')
        uid=entry.get('ItemTypeId');key=entry.get('Id')
        if not isinstance(uid,str) or not re.fullmatch('[A-Z0-9_@]+',uid) or not isinstance(key,(int,str)) or isinstance(key,bool) or not str(key):raise ValueError('Нет ID собственного заказа')
        price=entry.get('UnitPriceSilver');qty=entry.get('Amount');q=entry.get('QualityLevel');ench=entry.get('EnchantmentLevel',0)
        if any(type(v) is not int or v<0 for v in (price,qty)) or type(q) is not int or not 1<=q<=5 or type(ench) is not int or not 0<=ench<=4:raise ValueError('Неверные значения собственного заказа')
        city=LOCATIONS.get(str(entry.get('LocationId'))) or fallback
        if not city:raise ValueError('Неизвестный город собственных заказов')
        order_side=side
        if side=='mixed':order_side={'offer':'sell','request':'buy'}.get(str(entry.get('AuctionType','')).lower())
        if order_side not in ('sell','buy'):raise ValueError('Неизвестный тип собственного заказа')
        uid=market_item_id(uid,ench);expires=entry.get('Expires');dt=None
        if expires:
            try:dt=datetime.fromisoformat(expires.replace('Z','+00:00'));dt=dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
            except (AttributeError,ValueError):raise ValueError('Неверный срок собственного заказа')
        from .order_time import utc_time
        observed=utc_time(payload.get('Observed')) or datetime.now(timezone.utc)
        result.append(dict(city=city,side=order_side,name=item_name(uid),quantity=qty,original_quantity=qty,price=str(Decimal(price)/10000),cost=None,status='active' if qty else 'finished',
            order_id=str(key),item_id=uid,quality=q,player=player,observed=observed.isoformat(),expires=dt.isoformat() if dt else None,created=(dt-timedelta(days=30)).isoformat() if dt else None,
            note='Из игры • '+player+' • полученная страница; другие страницы могут быть не просмотрены'))
    return result


def import_user_snapshot(path):
    """Visible orders from the user's 2026-10-03 Thetford screenshot, once only."""
    store=OwnOrderStore(path)
    try:
        if store.db.execute('SELECT 1 FROM personal_meta WHERE key=?',('screenshot_2026_10_03',)).fetchone():return False
        if store.orders():return False
        entries=[('buy','Огненный посох (странник)',10,515),
            ('buy','Плащ контрабандиста (знаток)',1,62153),
            ('buy','Плащ контрабандиста (знаток)',1,42551),
            ('buy','Плащ контрабандиста (знаток)',1,75004),
            ('sell','Березовые брусья',115,32),
            ('sell','Каштановые брусья',361,439),
            ('sell','Каштановые брусья',211,444),
            ('sell','Огненный посох (странник)',6,900)]
        store.save([dict(city='Thetford',side=side,name=name,quantity=qty,price=str(price),cost=None,status='active',
            note='Только видимые строки пользовательского скриншота 03.10.26; остатки требуют обновления') for side,name,qty,price in entries])
        store.db.execute('INSERT INTO personal_meta VALUES(?,?)',('screenshot_2026_10_03','visible rows only'));store.db.commit()
        return True
    finally:store.close()
