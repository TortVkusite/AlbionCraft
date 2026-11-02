"""Explicit allowlist between local capture, peer mailbox and calculators."""
import hashlib
import json
import sqlite3
from datetime import timedelta
from pathlib import Path

from .peer_store import canonical, now, stamp, TTL


class CapturePublisher:
    def __init__(self, store, path, region):
        self.store=store;self.path=Path(path);self.region=region
        self.cursors={'local_quotes':0,'local_history_windows':0}

    def poll(self):
        if not self.path.exists():return 0
        db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=0.025)
        count=0
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in self.cursors:
                if table not in tables:continue
                rows=db.execute('SELECT rowid,* FROM '+table+' WHERE rowid>? ORDER BY rowid LIMIT 32',(self.cursors[table],)).fetchall()
                for row in rows:
                    cursor=row[0]
                    try:
                        if table=='local_quotes':
                            _,item,city,q,side,payload=row;entries=json.loads(payload)
                            if not entries:continue
                            observed=max(stamp(o['observed']) for o in entries)
                            orders=[dict(id=str(o['id']),price=o['price'] if o.get('unit')=='silver' else o['price']//10000,
                                amount=o['amount'],expires=o['expires']) for o in entries if stamp(o['expires'])>observed]
                            if not orders:continue
                            kind='orders';data=dict(item=item,city=city,quality=q,side=side,orders=orders)
                        else:
                            _,item,city,q,period,payload=row;p=json.loads(payload);observed=stamp(p['observed'])
                            kind='history';data=dict(item=item,city=city,quality=q,period_days=period,bucket_hours=p['bucket_hours'],
                                points=[{k:v[k] for k in ('timestamp','item_count','avg_price')} for v in p['data']])
                        if not now()-TTL <= observed <= now()+timedelta(minutes=2):continue
                        slot=self.region+':'+table+':'+':'.join(map(str,(item,city,q,side if table=='local_quotes' else period)))
                        digest=hashlib.sha256(canonical([data,observed.isoformat()])).hexdigest()
                        old=self.store.db.execute('SELECT digest FROM captured WHERE slot=?',(slot,)).fetchone()
                        if not old or old[0]!=digest:
                            self.store.publish(self.region,kind,data,observed.isoformat())
                            with self.store.db:self.store.db.execute('INSERT OR REPLACE INTO captured VALUES(?,?)',(slot,digest))
                            count+=1
                    except (ValueError,TypeError,KeyError,OverflowError):
                        continue
                    finally:
                        self.cursors[table]=cursor
            return count
        finally:db.close()


def shared_market(path,region):
    """Read committed peer observations without loading keys or starting networking."""
    path=Path(path)
    if not path.exists():return [],[]
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=0.025)
    prices={};histories={};current=now()
    try:
        identity=db.execute("SELECT value FROM config WHERE key='identity_public'").fetchone()
        own=json.loads(identity[0]) if identity else ''
        for raw, in db.execute('''SELECT body FROM (SELECT body,observed,ROW_NUMBER() OVER(PARTITION BY slot ORDER BY observed DESC,id DESC) n
            FROM events WHERE observed>=? AND slot LIKE ? AND origin<>?) WHERE n=1''',((current-TTL).isoformat(),region+':%',own)):
            e=json.loads(raw);d=e['data'];observed=e['observed'];source='P2P: '+e['origin'][:10]
            key=(d['item'],d['city'],d['quality'])
            if e['kind']=='orders':
                valid=[o for o in d['orders'] if stamp(o['expires'])>current]
                if not valid:continue
                side=d['side'];best=(min if side=='sell_price_min' else max)(valid,key=lambda o:o['price'])
                levels={}
                for o in valid:levels[o['price']]=levels.get(o['price'],0)+o['amount']
                row=prices.setdefault(key,dict(item_id=key[0],city=key[1],quality=key[2]))
                row.update({side:best['price'],side+'_date':observed,side+'_source':source,side+'_amount':best['amount'],
                    side+'_levels':[dict(price=p,quantity=q) for p,q in sorted(levels.items(),reverse=side=='buy_price_max')]})
            else:
                h=dict(item_id=key[0],location=key[1],quality=key[2],data=[dict(p,bucket_hours=d['bucket_hours']) for p in d['points']],
                    period_days=d['period_days'],bucket_hours=d['bucket_hours'],source=source,observed=observed)
                if key not in histories or stamp(histories[key]['observed'])<stamp(observed):histories[key]=h
        return list(prices.values()),list(histories.values())
    finally:db.close()


def merge_shared(primary,shared):
    result={(p['item_id'],p['city'],p['quality']):dict(p) for p in primary}
    for p in shared:
        row=result.setdefault((p['item_id'],p['city'],p['quality']),dict(item_id=p['item_id'],city=p['city'],quality=p['quality']))
        row['peer_observations']=p
        for side in ('sell_price_min','buy_price_max'):
            if side not in p:continue
            try:old=stamp(row.get(side+'_date',''))
            except ValueError:old=None
            if row.get(side) and old is not None and old<=now()+timedelta(minutes=2) and old>=stamp(p[side+'_date']):continue
            for suffix in ('','_date','_source','_amount','_levels'):
                field=side+suffix;row.pop(field,None)
                if field in p:row[field]=p[field]
    return list(result.values())
