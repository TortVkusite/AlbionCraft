import json
import sqlite3
import time

class Cache:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, cache_key TEXT, fetched REAL, payload TEXT)')
        self.db.execute('CREATE INDEX IF NOT EXISTS lookup ON requests(cache_key, fetched)')
        self.db.execute('CREATE TABLE IF NOT EXISTS observations (item TEXT, city TEXT, quality INTEGER, payload TEXT, PRIMARY KEY(item,city,quality))')
        self.db.execute('CREATE TABLE IF NOT EXISTS stream_orders (id TEXT PRIMARY KEY,item TEXT,city TEXT,quality INTEGER,side TEXT,price INTEGER,amount INTEGER,observed TEXT,expires TEXT)')
        self.db.commit()

    def get(self, key, ttl=120):
        row = self.db.execute('SELECT fetched,payload FROM requests WHERE cache_key=? ORDER BY fetched DESC LIMIT 1',(key,)).fetchone()
        return json.loads(row[1]) if row and time.time()-row[0]<ttl else None

    def put(self, key, rows):
        from .market_memory import archive_volumes
        if isinstance(rows,list):archive_volumes(self.db,[r for r in rows if isinstance(r,dict) and 'data' in r])
        self.db.execute('INSERT INTO requests(cache_key,fetched,payload) VALUES (?,?,?)',(key,time.time(),json.dumps(rows)))
        self.db.commit()

    def close(self):
        self.db.close()

    def save_stream_orders(self,orders):
        from .market_memory import initialize
        initialize(self.db)
        self.db.executemany('INSERT OR IGNORE INTO order_history VALUES(?,?,?,?,?,?,?,?)',[(o[0],o[1],o[2],o[3],o[4],o[5],o[6],o[7]) for o in orders])
        from datetime import datetime,timezone,timedelta
        cutoff=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        self.db.executemany('INSERT OR REPLACE INTO stream_orders VALUES(?,?,?,?,?,?,?,?,?)',orders)
        self.db.execute('DELETE FROM stream_orders WHERE observed<?',(cutoff,));self.db.commit()

    def stream_prices(self,ids):
        from datetime import datetime,timezone,timedelta
        now=datetime.now(timezone.utc);cutoff=(now-timedelta(days=1)).isoformat();result={};allowed=set(ids)
        for uid,city,q,side,price,amount,stamp in self.db.execute('SELECT item,city,quality,side,price,amount,observed FROM stream_orders WHERE observed>=? AND expires>?',(cutoff,now.isoformat())):
            if uid not in allowed:continue
            p=result.setdefault((uid,city,q),dict(item_id=uid,city=city,quality=q))
            if side not in p or (price<p[side] if side=='sell_price_min' else price>p[side]):
                p[side]=price;p[side+'_date']=stamp;p[side+'_amount']=amount
        return list(result.values())

    def merge_prices(self, rows, ids, cities, qualities):
        from .market_memory import archive_prices
        archive_prices(self.db,rows)
        from .models import quote
        from datetime import datetime
        incoming={(r.get('item_id'),r.get('city'),r.get('quality')):r for r in rows if isinstance(r,dict)}
        merged=[]
        for uid in sorted(set(ids)):
            for city in cities:
                for quality in sorted(set(qualities)):
                    key=(uid,city,quality)
                    stored=self.db.execute('SELECT payload FROM observations WHERE item=? AND city=? AND quality=?',key).fetchone()
                    old=json.loads(stored[0]) if stored else {}
                    new=incoming.get(key,{})
                    result=dict(item_id=uid,city=city,quality=quality)
                    for side in ('sell_price_min','sell_price_max','buy_price_min','buy_price_max'):
                        new_value,_,status=quote(new,side)
                        old_value,_,_=quote(old,side)
                        use_new=new_value is not None and 'будущем' not in status
                        if use_new and old_value is not None:
                            # ISO timestamp observations are compared as UTC-aware datetimes.
                            from datetime import timezone
                            def dt(v):
                                x=datetime.fromisoformat(v.replace('Z','+00:00'))
                                return x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x.astimezone(timezone.utc)
                            use_new=dt(new[side+'_date'])>=dt(old[side+'_date'])
                        selected=new if use_new else old
                        result[side]=selected.get(side,0)
                        result[side+'_date']=selected.get(side+'_date','0001-01-01T00:00:00')
                        result[side+'_source']=new.get(side+'_source','AODP API') if use_new else 'Последняя сохранённая котировка' if old_value is not None else 'Нет данных'
                    if new or old:
                        merged.append(result)
                        self.db.execute('INSERT OR REPLACE INTO observations VALUES(?,?,?,?)',(*key,json.dumps(result)))
        self.db.commit()
        return merged
