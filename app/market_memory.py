"""Local observations, never an inferred record of executed trades."""
import json,math,sqlite3
from datetime import datetime,timezone
from decimal import Decimal as D

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS price_history (item TEXT,city TEXT,quality INTEGER,side TEXT,stamp TEXT,price REAL,source TEXT,PRIMARY KEY(item,city,quality,side,stamp,source))')
    db.execute('CREATE INDEX IF NOT EXISTS price_timeline ON price_history(item,city,quality,stamp)')
    db.execute('CREATE TABLE IF NOT EXISTS volume_history (item TEXT,city TEXT,quality INTEGER,stamp TEXT,count INTEGER,price REAL,source TEXT,PRIMARY KEY(item,city,quality,stamp,source))')
    db.execute('CREATE TABLE IF NOT EXISTS order_history (id TEXT,item TEXT,city TEXT,quality INTEGER,side TEXT,price INTEGER,amount INTEGER,stamp TEXT,PRIMARY KEY(id,stamp))')
    db.execute('CREATE TABLE IF NOT EXISTS production_bonuses (id INTEGER PRIMARY KEY,category TEXT,percent REAL,starts TEXT,ends TEXT,source TEXT,confirmed INTEGER)')

def archive_prices(db,rows,source='API'):
    initialize(db);values=[]
    for row in rows:
        if not isinstance(row,dict) or not row.get('item_id') or not row.get('city'):continue
        for side in ('sell_price_min','buy_price_max'):
            value=row.get(side);stamp=row.get(side+'_date')
            try:dt=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            except (AttributeError,TypeError,ValueError):continue
            if isinstance(value,bool) or not isinstance(value,(int,float)) or value<=0 or not math.isfinite(value) or dt.year<2000:continue
            dt=dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
            if dt>datetime.now(timezone.utc):continue
            values.append((row['item_id'],row['city'],row.get('quality',1),side,dt.isoformat(),value,source))
    db.executemany('INSERT OR IGNORE INTO price_history VALUES(?,?,?,?,?,?,?)',values)

def archive_volumes(db,rows,source='API'):
    initialize(db);values=[]
    for row in rows:
        if not isinstance(row,dict) or not row.get('item_id') or not row.get('location'):continue
        for p in row.get('data',[]):
            if not isinstance(p,dict):continue
            count=p.get('item_count');price=p.get('avg_price',0)
            if type(count) is not int or count<0 or not isinstance(price,(int,float)) or not math.isfinite(price) or price<0:continue
            try:dt=datetime.fromisoformat(p['timestamp'].replace('Z','+00:00'))
            except (KeyError,AttributeError,TypeError,ValueError):continue
            dt=dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
            if dt.year<2000 or dt>datetime.now(timezone.utc):continue
            values.append((row['item_id'],row['location'],row.get('quality',1),dt.isoformat(),count,price,source))
    db.executemany('INSERT OR REPLACE INTO volume_history VALUES(?,?,?,?,?,?,?)',values)

class MarketMemory:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10);initialize(self.db);self.db.commit()
    def timeline(self,item,city,quality=1,limit=500):
        return [dict(stamp=s,side=side,price=p,source=source) for s,side,p,source in self.db.execute('SELECT stamp,side,price,source FROM price_history WHERE item=? AND city=? AND quality=? ORDER BY stamp DESC LIMIT ?',(item,city,quality,limit))]
    def volumes(self,item,city,quality=1,limit=365):
        # A local/API observation of the same day must not double sales volume.
        rows=self.db.execute('SELECT stamp,count,price,source FROM volume_history WHERE item=? AND city=? AND quality=? ORDER BY stamp DESC,source DESC LIMIT ?',(item,city,quality,limit*2))
        unique={}
        for stamp,count,price,source in rows:
            if stamp not in unique:unique[stamp]=dict(stamp=stamp,count=count,price=price,source=source)
        return list(unique.values())[:limit]
    def bonuses(self):
        return [dict(id=i,category=c,percent=p,starts=s,ends=e,source=src,confirmed=bool(ok)) for i,c,p,s,e,src,ok in self.db.execute('SELECT * FROM production_bonuses ORDER BY starts DESC LIMIT 100')]
    def add_bonus(self,category,percent,starts,ends,source,confirmed=True):
        start=datetime.fromisoformat(starts);end=datetime.fromisoformat(ends)
        if not start.tzinfo or not end.tzinfo or end<=start or not 0<float(percent)<=200 or not category or not source.strip():raise ValueError('Проверь категорию, процент, источник и время бонуса')
        starts=start.astimezone(timezone.utc).isoformat();ends=end.astimezone(timezone.utc).isoformat()
        with self.db:
            self.db.execute('DELETE FROM production_bonuses WHERE category=? AND starts=? AND ends=?',(category,starts,ends))
            self.db.execute('INSERT INTO production_bonuses(category,percent,starts,ends,source,confirmed) VALUES(?,?,?,?,?,?)',(category,float(percent),starts,ends,source.strip(),int(confirmed)))
    def remove_bonus(self,uid):
        with self.db:self.db.execute('DELETE FROM production_bonuses WHERE id=?',(uid,))
    def active(self,now=None):
        now=now or datetime.now(timezone.utc)
        result={}
        for b in reversed(self.bonuses()):
            if b['confirmed'] and datetime.fromisoformat(b['starts'])<=now<datetime.fromisoformat(b['ends']):
                previous=result.get(b['category']);result[b['category']]=dict(b)
                if previous:
                    result[b['category']]['percent']+=previous['percent']
                    result[b['category']]['starts']=max(b['starts'],previous['starts'])
                    result[b['category']]['ends']=min(b['ends'],previous['ends'])
        return result
    def arrivals(self,item,city,side,quality=1):
        points=self.db.execute('SELECT id,stamp,price FROM order_history WHERE item=? AND city=? AND quality=? AND side=? ORDER BY stamp DESC LIMIT 10000',(item,city,quality,side))
        first={};stamps=set()
        for uid,stamp,price in points:stamps.add(stamp);first[uid]=(stamp,price)
        if len(stamps)<2:return None
        ordered=sorted(stamps);hours=(datetime.fromisoformat(ordered[-1])-datetime.fromisoformat(ordered[0])).total_seconds()/3600
        new=[p for s,p in first.values() if s>ordered[0]]
        return dict(samples=len(stamps),hours=hours,new=len(new),per_hour=len(new)/hours if hours>0 else None)
    def close(self):self.db.close()

def sale_scenario(quantity,per_day,share=10,next_check_hours=12):
    if per_day is None or per_day<=0:return dict(days=None,fast_days=None,slow_days=None,remaining=None)
    if quantity<0 or not 0<share<=100 or next_check_hours<0:raise ValueError('Неверные параметры сценария продаж')
    rate=D(str(per_day))*D(str(share))/100;qty=D(str(quantity));days=qty/rate
    return dict(days=days,fast_days=days/2,slow_days=days*2,remaining=max(D(0),qty-rate*D(str(next_check_hours))/24))

def bonus_settings(root,settings):
    result=dict(settings);result['production_bonuses']={}
    if settings.get('use_bonuses',True):
        store=MarketMemory(root/'prices.sqlite')
        try:result['production_bonuses']=store.active()
        finally:store.close()
    return result

def calibration(entries,buy=None,craft=None):
    from .trip_ledger import actual_summary
    import statistics
    samples=[]
    for entry in entries:
        snap=entry['snapshot']
        if buy and snap['buy']!=buy or craft and snap['craft']!=craft:continue
        try:
            actual=actual_summary(snap,entry['facts'])
            if actual['closed'] and D(snap['profit'])>0:samples.append(dict(id=entry['id'],completed=entry['facts'].get('completed_at',entry.get('stamp','')),estimate=D(snap['profit']),profit=actual['profit'],changes=actual['changes']))
        except (ValueError,ArithmeticError):continue
    samples.sort(key=lambda r:(r['completed'],r['id']));ratios=[s['profit']/s['estimate'] for s in samples]
    factor=statistics.median(ratios) if len(ratios)>=10 else None
    # Sequential backtest uses only earlier completed trips for each prediction.
    errors=[abs(samples[n]['profit']-samples[n]['estimate']*statistics.median(ratios[:n])) for n in range(10,len(samples))]
    return dict(count=len(samples),factor=factor,backtest_count=len(errors),backtest_mae=sum(errors,D(0))/len(errors) if errors else None,
        changes={key:sum((s['changes'][key] for s in samples),D(0)) for key in ('sale','purchase','stock','station','other','sale_fees')})
