"""Route inventory snapshots and dated purchase lots, separate from market quotes."""
import json,sqlite3,re
from datetime import datetime,timezone
from decimal import Decimal as D
from .models import quote

class StockStore:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS trip_stock (player TEXT,city TEXT,key TEXT,payload TEXT,PRIMARY KEY(player,city,key))')
        self.db.execute('CREATE TABLE IF NOT EXISTS trip_stock_watch (player TEXT PRIMARY KEY,character TEXT,started TEXT,city TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS trip_stock_receipts (owner TEXT,id TEXT,PRIMARY KEY(owner,id))');self.db.commit()
        self.db.execute('CREATE TABLE IF NOT EXISTS trip_bank_scans (player TEXT,city TEXT,page TEXT,payload TEXT,PRIMARY KEY(player,city,page))');self.db.commit()
    def rows(self,player):
        return [dict(json.loads(p),key=k,city=c) for c,k,p in self.db.execute('SELECT city,key,payload FROM trip_stock WHERE player=? ORDER BY city,key',(player,))]
    def put(self,player,city,key,row):
        if not re.fullmatch(r'[A-Z0-9_@]+',row['item_id']) or type(row['quantity']) is not int or row['quantity']<0:raise ValueError('Неверный ресурс или количество')
        if row.get('price') is not None:
            price=D(str(row['price']))
            if not price.is_finite() or price<0:raise ValueError('Неверная цена запаса')
        value=dict(row,observed=datetime.now(timezone.utc).isoformat())
        self.db.execute('INSERT OR REPLACE INTO trip_stock VALUES(?,?,?,?)',(player,city,key,json.dumps(value,ensure_ascii=False)));self.db.commit()
    def replace_page(self,player,city,page,rows,kind='base'):
        if kind not in ('base','bought'):raise ValueError('Неверный вид запаса')
        if any(type(r.get('quantity')) is not int or r['quantity']<1 or not re.fullmatch(r'[A-Z0-9_@]+',r.get('item_id','')) for r in rows):raise ValueError('Неверные данные снимка')
        if len({r.get('cell',n) for n,r in enumerate(rows)})!=len(rows):raise ValueError('Повтор ячейки в снимке')
        # The same visible grid is a replacement, never an additive import.
        prefix='screen:'+str(page)+':'
        old={r['key']:r for r in self.rows(player) if r['city']==city and r['key'].startswith(prefix)}
        with self.db:
            receipt_rows=[r for r in self.rows(player) if r['city']==city and r['key'].startswith('mail:')] if kind=='bought' else []
            totals={}
            for r in rows:totals[r['item_id']]=totals.get(r['item_id'],0)+r['quantity']
            receipt_prices={}
            for uid,qty in totals.items():
                matched=[r for r in receipt_rows if r['item_id']==uid]
                if matched and sum(r['quantity'] for r in matched)==qty:
                    receipt_prices[uid]=str(sum(D(r['price'])*r['quantity'] for r in matched)/qty)
            for r in receipt_rows:self.db.execute('DELETE FROM trip_stock WHERE player=? AND city=? AND key=?',(player,city,r['key']))
            self.db.execute('DELETE FROM trip_stock WHERE player=? AND city=? AND key LIKE ?',(player,city,prefix+'%'))
            for n,row in enumerate(rows):
                key=prefix+str(row.get('cell',n));before=old.get(key,{})
                preserve=before.get('item_id')==row['item_id'] and before.get('quantity')==row['quantity']
                value=dict(row,kind=kind,source='Экран банка',price=receipt_prices.get(row['item_id'],before.get('price') if preserve else None),valuation_estimated=bool(preserve and before.get('valuation_estimated') and row['item_id'] not in receipt_prices),observed=datetime.now(timezone.utc).isoformat())
                self.db.execute('INSERT INTO trip_stock VALUES(?,?,?,?)',(player,city,key,json.dumps(value,ensure_ascii=False)))
    def delete(self,player,city,key):self.db.execute('DELETE FROM trip_stock WHERE player=? AND city=? AND key=?',(player,city,key));self.db.commit()
    def bank_scans(self,player):
        return [dict(json.loads(payload),city=city,page=page) for city,page,payload in self.db.execute('SELECT city,page,payload FROM trip_bank_scans WHERE player=?',(player,))]
    def start_bank(self,player,city,kind,container):
        from .bank_pages import page_key
        page=page_key(kind,container);prefix='screen:'+page+':'
        with self.db:
            keys=[r['key'] for r in self.rows(player) if r['city']==city and r['key'].startswith(prefix) and r['key'][len(prefix):].isdecimal()]
            for key in keys:self.db.execute('DELETE FROM trip_stock WHERE player=? AND city=? AND key=?',(player,city,key))
            self.db.execute('DELETE FROM trip_bank_scans WHERE player=? AND city=? AND page=?',(player,city,page))
    def merge_bank(self,player,city,kind,container,rows,columns,cells,first_row=None,warnings=()):
        from .bank_pages import page_key,page_vector,locate_page,joined_state
        if kind not in ('base','bought'):raise ValueError('Неверный вид запаса')
        container=container.strip()
        other_kind='bought' if kind=='base' else 'base'
        other_page=page_key(other_kind,container)
        if any(s['city']==city and s['page']==other_page for s in self.bank_scans(player)):raise ValueError('Этот контейнер в этом городе уже прочитан в другом источнике запасов. Используй прежний источник; один банк нельзя учитывать одновременно как базу и уже купленное.')
        page=page_key(kind,container);prefix='screen:'+page+':'
        previous=next((s for s in self.bank_scans(player) if s['city']==city and s['page']==page),None)
        vector=page_vector(rows,cells);offset=locate_page(previous,vector,columns,first_row)
        state=joined_state(previous,vector,columns,offset,container,warnings);state['kind']=kind;state['observed']=datetime.now(timezone.utc).isoformat()
        prior={r['key']:r for r in self.rows(player) if r['city']==city and r['key'].startswith(prefix) and r['key'][len(prefix):].isdecimal()}
        # Legacy snapshots have unknown coverage: retain only when the first anchored region replaces them.
        with self.db:
            if previous is None:
                for key in prior:self.db.execute('DELETE FROM trip_stock WHERE player=? AND city=? AND key=?',(player,city,key))
            for n in range(cells):
                slot=offset+n
                if str(slot) not in state['uncertain']:self.db.execute('DELETE FROM trip_stock WHERE player=? AND city=? AND key=?',(player,city,prefix+str(slot)))
            receipt_rows=[r for r in self.rows(player) if r['city']==city and r['key'].startswith('mail:')] if kind=='bought' else []
            pool={r['key']:r for scan in self.bank_scans(player) if scan['city']==city and scan.get('kind')=='bought' for r in scan.get('receipt_lots',[])} if kind=='bought' else {}
            pool.update({r['key']:r for r in receipt_rows})
            if pool:state['receipt_lots']=list(pool.values())
            for r in receipt_rows:self.db.execute('DELETE FROM trip_stock WHERE player=? AND city=? AND key=?',(player,city,r['key']))
            totals={}
            for r in self.rows(player):
                if r['city']==city and r.get('kind')=='bought' and r.get('source')=='Экран банка':totals[r['item_id']]=totals.get(r['item_id'],0)+r['quantity']
            for row in rows:totals[row['item_id']]=totals.get(row['item_id'],0)+row['quantity']
            receipt_prices={}
            for uid,qty in totals.items():
                matched=[r for r in pool.values() if r['item_id']==uid]
                if matched and sum(r['quantity'] for r in matched)==qty:receipt_prices[uid]=str(sum(D(r['price'])*r['quantity'] for r in matched)/qty)
            for row in rows:
                key=prefix+str(offset+row['cell']);before=prior.get(key,{})
                preserve=before.get('item_id')==row['item_id'] and before.get('quantity')==row['quantity']
                price=before.get('price') if preserve and before.get('price') is not None and not before.get('valuation_estimated') else receipt_prices.get(row['item_id'],before.get('price') if preserve else None)
                value=dict(row,cell=offset+row['cell'],container=container,kind=kind,source='Экран банка',price=price,valuation_estimated=bool(preserve and before.get('valuation_estimated') and row['item_id'] not in receipt_prices),observed=state['observed'])
                self.db.execute('INSERT OR REPLACE INTO trip_stock VALUES(?,?,?,?)',(player,city,key,json.dumps(value,ensure_ascii=False)))
            for r in self.rows(player):
                if r['city']==city and r.get('kind')=='bought' and r.get('source')=='Экран банка' and r['item_id'] in receipt_prices and (r.get('price') is None or r.get('valuation_estimated')):
                    value=dict(r,price=receipt_prices[r['item_id']],valuation_estimated=False)
                    self.db.execute('UPDATE trip_stock SET payload=? WHERE player=? AND city=? AND key=?',(json.dumps(value,ensure_ascii=False),player,city,r['key']))
            self.db.execute('INSERT OR REPLACE INTO trip_bank_scans VALUES(?,?,?,?)',(player,city,page,json.dumps(state,ensure_ascii=False)))
        return offset,state
    def finish_bank(self,player,city,kind,container):
        from .bank_pages import page_key,complete_state
        page=page_key(kind,container);state=next((s for s in self.bank_scans(player) if s['city']==city and s['page']==page),None)
        state=complete_state(state)
        with self.db:self.db.execute('UPDATE trip_bank_scans SET payload=? WHERE player=? AND city=? AND page=?',(json.dumps(state,ensure_ascii=False),player,city,page))
    def watch(self,player,character,city,enabled):
        with self.db:
            self.db.execute('DELETE FROM trip_stock_watch WHERE player=?',(player,))
            if enabled:
                if not character.strip():raise ValueError('Укажи имя персонажа в игре')
                self.db.execute('INSERT INTO trip_stock_watch VALUES(?,?,?,?)',(player,character.strip(),datetime.now(timezone.utc).isoformat(),city))
    def watcher(self,player):
        return self.db.execute('SELECT character,started,city FROM trip_stock_watch WHERE player=?',(player,)).fetchone()
    def capture(self,payload,allowed):
        receipt=purchase_from_mail(payload,allowed)
        if not receipt:return 0
        from .order_time import utc_time
        received=utc_time(receipt['received']);owner=payload.get('CharacterId');name=payload.get('CharacterName')
        if not received or not owner or not name:return 0
        watchers=self.db.execute('SELECT player,started,city FROM trip_stock_watch WHERE character=?',(name,)).fetchall()
        count=0
        with self.db:
            if self.db.execute('SELECT 1 FROM trip_stock_receipts WHERE owner=? AND id=?',(owner,receipt['key'])).fetchone():return 0
            for player,started,city in watchers:
                if received<utc_time(started) or city!=receipt['city']:continue
                # Screen quantities and receipts must never be added together.
                if any(r.get('kind')=='bought' and r.get('source')=='Экран банка' for r in self.rows(player) if r['city']==city):continue
                value=dict(receipt,observed=datetime.now(timezone.utc).isoformat())
                self.db.execute('INSERT OR REPLACE INTO trip_stock VALUES(?,?,?,?)',(player,city,receipt['key'],json.dumps(value,ensure_ascii=False)));count+=1
            if count:self.db.execute('INSERT INTO trip_stock_receipts VALUES(?,?)',(owner,receipt['key']))
        return count
    def close(self):self.db.close()

def route_stock(rows,buy,craft,prices,max_age=None):
    index={(p['item_id'],p['city'],p.get('quality',1)):p for p in prices};result=[];missing=[]
    for row in rows:
        city=craft if row.get('kind')=='base' else buy
        if row['city']!=city or not row['quantity']:continue
        value=row.get('price');estimated=bool(row.get('valuation_estimated'))
        if value is None and row.get('kind')=='base':
            price,age,status=quote(index.get((row['item_id'],craft,1),{}),'sell_price_min',max_age)
            if price is not None and 'будущем' not in status and (max_age is None or age<=max_age):value=price;estimated=True
        if value is None:missing.append(row);continue
        result.append(dict(row,price=D(str(value)),transport=row.get('kind')!='base' and buy!=craft,estimated=estimated))
    return result,missing

def purchase_from_mail(payload,allowed):
    """A receipt proves historical cost, but an old letter proves no current stock."""
    mail=payload.get('Mail',{})
    if payload.get('Action')!='mail' or payload.get('Confirmed') is not True or mail.get('Type')!='MARKETPLACE_BUYORDER_FINISHED_SUMMARY':return None
    parts=str(mail.get('Body','')).split('|')
    if len(parts)!=4 or parts[1] not in allowed or not re.fullmatch(r'T[1-8]_(ORE|WOOD|FIBER|HIDE|ROCK|METALBAR|PLANKS|CLOTH|LEATHER|STONEBLOCK)(?:_LEVEL[1-4]@[1-4])?',parts[1]):return None
    qty=int(parts[0]);total=D(parts[2])/10000
    if qty<=0 or not total.is_finite() or total<0:raise ValueError('Неверная покупка')
    from .market_stream import LOCATIONS
    city=LOCATIONS.get(str(mail.get('LocationId')))
    if not city or not mail.get('Received') or type(mail.get('Id')) not in (str,int):return None
    return dict(item_id=parts[1],quantity=qty,price=str(total/qty),kind='bought',city=city,received=mail['Received'],source='Письмо рынка: фактическая сумма покупки',key='mail:'+str(mail['Id']))


def consumption_changes(db,player,existing):
    changes=[];scans=set()
    for lot in existing:
        record=db.execute('SELECT payload FROM trip_stock WHERE player=? AND city=? AND key=?',(player,lot['city'],lot['key'])).fetchone()
        before=json.loads(record[0]) if record else None
        if not before or any(before.get(k)!=lot.get(k) for k in ('item_id','quantity','observed')):
            raise ValueError('Запасы изменились после расчёта. Пересчитай ходку перед записью партии.')
        if not 0<=lot['used']<=before['quantity']:raise ValueError('Недостаточно запасов для списания')
        after=dict(before,quantity=before['quantity']-lot['used'],observed=datetime.now(timezone.utc).isoformat())
        change=dict(city=lot['city'],key=lot['key'],before=record[0],after=json.dumps(after,ensure_ascii=False))
        if lot['key'].startswith('screen:'):
            page=lot['key'].rsplit(':',1)[0][len('screen:'):];scan_key=(lot['city'],page)
            if scan_key not in scans:
                scans.add(scan_key);scan=db.execute('SELECT payload FROM trip_bank_scans WHERE player=? AND city=? AND page=?',(player,lot['city'],page)).fetchone()
                if scan:
                    state=json.loads(scan[0]);state['complete']=False
                    change.update(scan_page=page,scan_before=scan[0],scan_after=json.dumps(state,ensure_ascii=False))
        changes.append(change)
    return changes


def apply_consumption(db,player,changes,reverse=False):
    for change in changes:
        expected=change['after' if reverse else 'before'];value=change['before' if reverse else 'after']
        record=db.execute('SELECT payload FROM trip_stock WHERE player=? AND city=? AND key=?',(player,change['city'],change['key'])).fetchone()
        if not record or record[0]!=expected:raise ValueError('Запасы изменились. Запись или отмена не должна перезаписывать новый снимок банка.')
        db.execute('UPDATE trip_stock SET payload=? WHERE player=? AND city=? AND key=?',(value,player,change['city'],change['key']))
        if change.get('scan_page'):
            scan_expected=change['scan_after' if reverse else 'scan_before'];scan_value=change['scan_before' if reverse else 'scan_after']
            scan=db.execute('SELECT payload FROM trip_bank_scans WHERE player=? AND city=? AND page=?',(player,change['city'],change['scan_page'])).fetchone()
            if not scan or scan[0]!=scan_expected:raise ValueError('Снимок банка изменился после записи партии. Отмена не должна перезаписывать новое покрытие.')
            db.execute('UPDATE trip_bank_scans SET payload=? WHERE player=? AND city=? AND page=?',(scan_value,player,change['city'],change['scan_page']))
