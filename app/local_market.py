"""Loopback HTTP ingest compatible with Albion Data Client's public uploader."""
import json
import re
import sqlite3
from datetime import datetime,timezone,timedelta
from http.server import HTTPServer,BaseHTTPRequestHandler
from PySide6.QtCore import QThread,Signal
from .market_stream import normalized_order
from .models import quote
from .market_stream import LOCATIONS
from pathlib import Path
from functools import lru_cache
from .item_ids import market_item_id
from .regions import REGIONS,region_key

PORT=43871
SOURCE='Из твоей игры: наблюдавшийся ордер'

@lru_cache(maxsize=1)
def item_indexes():
    names=json.loads((Path(__file__).resolve().parents[1]/'research/names.json').read_text(encoding='utf-8-sig'))
    return {int(n['Index']):n['UniqueName'] for n in names if str(n.get('Index','')).isdigit()}

def decode_history(payload,indexes=None,now=None):
    if not isinstance(payload,dict):raise ValueError('Неверная история')
    scale=payload.get('Timescale')
    if type(scale) is not int or scale not in (0,1,2):return None
    period,bucket=((1,1),(7,6),(28,24))[scale]
    uid=(indexes if indexes is not None else item_indexes()).get(payload.get('AlbionId'))
    city=LOCATIONS.get(str(payload.get('LocationId')));quality=payload.get('QualityLevel')
    if not uid or not city or type(quality) is not int or quality not in range(1,6):raise ValueError('Неизвестный предмет / город / качество')
    points=payload.get('MarketHistories')
    if not isinstance(points,list) or len(points)>1000:raise ValueError('Неверные точки истории')
    now=now or datetime.now(timezone.utc)
    end=now.replace(hour=now.hour//bucket*bucket,minute=0,second=0,microsecond=0);rows={}
    for p in points:
        if not isinstance(p,dict) or any(type(p.get(k)) is not int for k in ('Timestamp','ItemAmount','SilverAmount')):continue
        if p['ItemAmount']<0 or p['SilverAmount']<0:continue
        try:dt=datetime(1,1,1,tzinfo=timezone.utc)+timedelta(microseconds=p['Timestamp']//10)
        except (ValueError,OverflowError):continue
        if not end-timedelta(days=period)<=dt or dt+timedelta(hours=bucket)>end:continue
        rows[dt.isoformat()]=dict(timestamp=dt.isoformat(),item_count=p['ItemAmount'],avg_price=p['SilverAmount']/10000/p['ItemAmount'] if p['ItemAmount'] else 0,bucket_hours=bucket)
    return dict(item_id=uid,location=city,quality=quality,data=list(rows.values()),period_days=period,bucket_hours=bucket,
        source='Из твоей игры: история '+{1:'24 ч.',7:'7 дней',28:'4 недели'}[period],observed=now.isoformat())

def decode_orders(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('Orders'),list):raise ValueError('Ожидается Orders')
    if len(payload['Orders'])>5000:raise ValueError('Слишком много ордеров')
    orders=[]
    for entry in payload['Orders']:
        if not isinstance(entry,dict):continue
        if not isinstance(entry.get('ItemTypeId'),str) or not re.fullmatch(r'[A-Z0-9_@]+',entry['ItemTypeId']):continue
        if any(type(entry.get(k)) is not int for k in ('UnitPriceSilver','Amount','QualityLevel','EnchantmentLevel')):continue
        if not 0<=entry['EnchantmentLevel']<=4:continue
        # Direct client uploads carry fixed-point prices: 10000 units = 1 silver.
        converted=dict(entry,UnitPriceSilver=entry['UnitPriceSilver']//10000)
        order=normalized_order(converted)
        if order:orders.append(order)
    return orders

class LocalStore:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS local_quotes (item TEXT,city TEXT,quality INTEGER,side TEXT,payload TEXT,PRIMARY KEY(item,city,quality,side))')
        self.db.execute('CREATE TABLE IF NOT EXISTS local_histories (item TEXT,city TEXT,quality INTEGER,payload TEXT,PRIMARY KEY(item,city,quality))')
        self.db.execute('CREATE TABLE IF NOT EXISTS local_history_windows (item TEXT,city TEXT,quality INTEGER,period INTEGER,payload TEXT,PRIMARY KEY(item,city,quality,period))')
        self.db.commit()
    def save(self,orders):
        from .market_memory import initialize,archive_prices
        initialize(self.db)
        self.db.executemany('INSERT OR IGNORE INTO order_history VALUES(?,?,?,?,?,?,?,?)',[(o[0],o[1],o[2],o[3],o[4],o[5],o[6],o[7]) for o in orders])
        # Replace the previously seen page for each item/side; never keep a cheaper old page forever.
        groups={}
        for order in orders:
            key=order[1:5];groups.setdefault(key,[]).append(order)
        for (uid,city,q,side),entries in groups.items():
            unique={o[0]:o for o in entries}
            payload=[dict(id=o[0],price=o[5],amount=o[6],observed=o[7],expires=o[8],unit='silver') for o in unique.values()]
            self.db.execute('INSERT OR REPLACE INTO local_quotes VALUES(?,?,?,?,?)',(uid,city,q,side,json.dumps(payload)))
            best=(min if side=='sell_price_min' else max)(entries,key=lambda o:o[5])
            archive_prices(self.db,[dict(item_id=uid,city=city,quality=q,**{side:best[5],side+'_date':best[7]})],'Local')
        self.db.commit()
    def prices(self,ids=None,now=None):
        now=now or datetime.now(timezone.utc);result={};ids=set(ids) if ids is not None else None
        for uid,city,q,side,payload in self.db.execute('SELECT * FROM local_quotes'):
            uid=market_item_id(uid)
            if ids is not None and uid not in ids:continue
            entries=[dict(o,price=o['price'] if o.get('unit')=='silver' else o['price']//10000) for o in json.loads(payload)]
            valid=[o for o in entries if o['price']>0 and o['amount']>0 and datetime.fromisoformat(o['expires'])>now and timedelta(0)<=now-datetime.fromisoformat(o['observed'])<timedelta(days=1)]
            if not valid:continue
            best=(min if side=='sell_price_min' else max)(valid,key=lambda o:o['price'])
            row=result.setdefault((uid,city,q),dict(item_id=uid,city=city,quality=q))
            # Old aliases may coexist: use the newest observed page, not an older cheap one.
            if side in row and datetime.fromisoformat(row[side+'_date'])>=datetime.fromisoformat(best['observed']):continue
            row.update({side:best['price'],side+'_date':best['observed'],side+'_amount':best['amount'],side+'_source':SOURCE})
            levels={}
            for o in valid:levels[o['price']]=levels.get(o['price'],0)+o['amount']
            if all(o.get('id') is not None for o in valid):row[side+'_levels']=[dict(price=p,quantity=q) for p,q in sorted(levels.items(),reverse=side=='buy_price_max')]
        return list(result.values())
    def close(self):self.db.close()
    def save_history(self,history):
        from .market_memory import archive_volumes
        archive_volumes(self.db,[history],'Local')
        self.db.execute('INSERT OR REPLACE INTO local_history_windows VALUES(?,?,?,?,?)',(history['item_id'],history['location'],history['quality'],history.get('period_days',7),json.dumps(history)));self.db.commit()
    def histories(self,ids):
        ids=set(ids);cutoff=datetime.now(timezone.utc)-timedelta(days=1)
        result={}
        for uid,payload in self.db.execute('SELECT item,payload FROM local_histories UNION ALL SELECT item,payload FROM local_history_windows'):
            if uid not in ids:continue
            p=json.loads(payload);stamp=datetime.fromisoformat(p['observed']);key=(uid,p['location'],p['quality'])
            if not p['data'] or not cutoff<=stamp<=datetime.now(timezone.utc):continue
            if key not in result or stamp>=datetime.fromisoformat(result[key]['observed']):result[key]=p
        return list(result.values())

def merge_local(primary,local):
    result={(r['item_id'],r['city'],r['quality']):dict(r) for r in primary}
    for p in local:
        key=(p['item_id'],p['city'],p['quality']);row=result.setdefault(key,dict(item_id=key[0],city=key[1],quality=key[2]))
        row['local_observations']=p
        for side in ('sell_price_min','buy_price_max'):
            if not p.get(side):continue
            old,old_age,status=quote(row,side,None);value,age,new_status=quote(p,side,None)
            if value is None or 'будущем' in new_status:continue
            if old is None or 'будущем' in status or old_age is not None and age<old_age:
                row.update({side:value,side+'_date':p[side+'_date'],side+'_source':SOURCE})
                row.pop(side+'_amount',None)
                if side+'_amount' in p:row[side+'_amount']=p[side+'_amount']
    return list(result.values())

def make_server(path,token,on_update,port=PORT,region=None,on_status=lambda text:None):
    expected=region_key(region) if region is not None else None
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            history_request=self.path==f'/{token}/markethistories.ingest'
            own_request=self.path==f'/{token}/ownorders.ingest'
            if self.path!=f'/{token}/marketorders.ingest' and not history_request and not own_request:
                # Client may also send public non-market topics; acknowledge without storing them.
                if self.path.startswith('/'+token+'/'):self.send_error(200,'Ignored topic')
                else:self.send_error(404)
                self.close_connection=True;return
            try:
                if expected is not None:
                    try:actual=region_key(self.headers.get('X-Albion-Server',''))
                    except ValueError:
                        on_status('Из игры: сервер не определён. Запусти обновлённый клиент через приложение.')
                        self.send_error(422,'Missing Albion server');self.close_connection=True;return
                    if actual!=expected:
                        on_status('Из игры: выбери сервер '+REGIONS[actual]['label']+'; данные другого сервера не сохранены.')
                        self.send_error(409,'Wrong Albion server');self.close_connection=True;return
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=2_000_000:self.send_error(413);return
                payload=json.loads(self.rfile.read(size))
                if own_request:
                    from .own_orders import OwnOrderStore
                    own=OwnOrderStore(Path(path).with_name('player.sqlite'))
                    try:count=own.observe(payload)
                    finally:own.close()
                    from .trip_inventory import StockStore
                    stock=StockStore(Path(path).with_name('player.sqlite'))
                    try:stock.capture(payload,set(item_indexes().values()))
                    finally:stock.close()
                    self.send_response(200);self.end_headers();self.wfile.write(b'OK');return
                history=decode_history(payload) if history_request else None
                orders=[] if history_request else decode_orders(payload)
                store=LocalStore(path)
                try:
                    if history and history['data']:store.save_history(history)
                    elif not history_request:store.save(orders)
                finally:store.close()
                on_update(-len(history['data']) if history and history['data'] else len(orders))
                self.send_response(200);self.end_headers();self.wfile.write(b'OK')
            except (ValueError,TypeError,ArithmeticError):self.send_error(400)
            except sqlite3.Error:self.send_error(503)
        def setup(self):
            super().setup();self.connection.settimeout(5)
    server=HTTPServer(('127.0.0.1',port),Handler);server.timeout=.3
    return server

class LocalReceiver(QThread):
    updated=Signal(int)
    status=Signal(str)
    def __init__(self,path,token,port=PORT,region='europe'):
        super().__init__();self.path=path;self.token=token;self.port=port;self.region=region_key(region)
    def run(self):
        try:
            server=make_server(self.path,self.token,self.updated.emit,self.port,self.region,self.status.emit)
            self.port=server.server_port
        except OSError as exc:self.status.emit('Локальный приём недоступен: '+str(exc));return
        self.status.emit('Из игры: приём включён, ожидаю ордера • '+REGIONS[self.region]['label'])
        try:
            while not self.isInterruptionRequested():server.handle_request()
        finally:server.server_close()
