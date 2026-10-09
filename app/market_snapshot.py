"""Read current cached/public/local market observations without fetching."""
import json,sqlite3
from pathlib import Path
from .models import quote

def merge_observation(old,new):
    """Merge each side by observation time, never by the age of a UI result."""
    result=dict(old or new)
    for side in ('sell_price_min','sell_price_max','buy_price_min','buy_price_max'):
        value,age,status=quote(new,side,None)
        previous,old_age,old_status=quote(result,side,None)
        if value is None or 'будущем' in status:continue
        if previous is not None and 'будущем' not in old_status and old_age<age:continue
        for key in (side,side+'_date',side+'_source',side+'_amount',side+'_levels'):
            result.pop(key,None)
            if key in new:result[key]=new[key]
        for key in ('local_observations','nats_observations'):
            if key in new:result[key]=new[key]
    return result

def market_snapshot(owner,root,ids):
    root=Path(root)
    prices={};histories={};path=root/'prices.sqlite'
    if path.exists():
        db=sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True)
        try:
            for n in range(0,len(ids),400):
                chunk=list(ids)[n:n+400];marks=','.join('?' for _ in chunk)
                for payload, in db.execute('SELECT payload FROM observations WHERE item IN ('+marks+')',chunk):
                    p=json.loads(payload);prices[(p['item_id'],p['city'],p['quality'])]=p
            for key,payload in db.execute("SELECT cache_key,payload FROM requests WHERE cache_key LIKE '%history_item_all%' ORDER BY fetched"):
                if json.loads(key)[1] not in ids:continue
                for h in json.loads(payload):histories[(h['item_id'],h['location'],h['quality'])]=h
        finally:db.close()
    if owner.last:
        for p in owner.last['prices']:
            if p['item_id'] in ids:
                key=(p['item_id'],p['city'],p['quality']);prices[key]=merge_observation(prices.get(key,{}),p)
        for h in owner.last['histories']:
            if h['item_id'] in ids:histories[(h['item_id'],h['location'],h['quality'])]=h
    if owner.local_enabled.isChecked():
        from .local_market import LocalStore,merge_local
        store=LocalStore(path)
        try:
            prices={ (p['item_id'],p['city'],p['quality']):p for p in merge_local(list(prices.values()),[p for p in store.prices() if p['item_id'] in ids])}
            for h in store.histories(ids):histories[(h['item_id'],h['location'],h['quality'])]=h
        finally:store.close()
    return list(prices.values()),list(histories.values())
