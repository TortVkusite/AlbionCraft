"""Observed page depth and explicit, conservative turnover assumptions."""
from decimal import Decimal as D
from .models import quote


def observed_levels(row,side,max_age=None):
    observation=row.get('local_observations',row)
    value,age,status=quote(observation,side,max_age)
    if value is None or 'будущем' in status or max_age is not None and (age is None or age>max_age):return None
    raw=observation.get(side+'_levels')
    if raw is None:return None
    levels={}
    for entry in raw:
        price=D(str(entry['price']));qty=entry['quantity']
        if not price.is_finite() or price<=0 or type(qty) is not int or qty<0:raise ValueError('Неверный объём ордера')
        if qty:levels[price]=levels.get(price,0)+qty
    return [dict(price=p,quantity=q) for p,q in sorted(levels.items(),reverse=side=='buy_price_max')]


def configure_market(options,prices,mode='observed',days=0,share=10,max_age=None):
    if mode not in ('quote','observed','strict'):raise ValueError('Неверный режим объёмов рынка')
    if days<0 or not 0<share<=100:raise ValueError('Неверный срок или доля продаж')
    index={(p['item_id'],p['city'],p.get('quality',1)):p for p in prices};warnings=set()
    for c in options:
        c.row['sale_mode']='instant' if c.row.get('sale_side')=='buy_price_max' else 'order'
        for part in c.parts:
            uid=part['ingredient'].item_id
            levels=observed_levels(index.get((uid,c.row['buy'],1),{}),'sell_price_min',max_age) if mode!='quote' else None
            part['buy_levels']=levels if levels is not None else [] if mode=='strict' else None
            if mode!='quote' and levels is None:warnings.add(('purchase',uid,c.row['buy']))
        for city,sale in c.sales.items():
            if c.row.get('sale_mode')=='instant' and mode!='quote':
                levels=observed_levels(index.get((c.recipe.item_id,city,1),{}),'buy_price_max',max_age)
                sale['levels']=levels if levels is not None else [] if mode=='strict' else None
                if levels is None and c.row.get('root',True):warnings.add(('sale',c.recipe.item_id,city))
        c.row['market_mode']=mode;c.row['turnover_days']=days;c.row['turnover_share']=share
        if days and c.row.get('sale_mode')!='instant':
            demand=c.row.get('demand',{})
            c.row['sale_limit']=int(D(str(demand.get('per_day',0)))*D(str(days))*D(str(share))/100)
            if demand.get('kind','unknown')=='unknown' and c.row.get('root',True):warnings.add(('history',c.recipe.item_id,c.row['sell']))
        else:c.row.pop('sale_limit',None)
    return sorted(warnings)


def proceeds(sale,quantity):
    """Gross revenue at observed bid levels; None means insufficient seen depth."""
    if sale.get('levels') is None:return sale['price']*quantity
    remaining=quantity;total=D(0)
    for level in sale['levels']:
        used=min(remaining,level['quantity']);total+=level['price']*used;remaining-=used
        if not remaining:break
    return None if remaining else total


def turnover(quantity,demand,share=10):
    if demand.get('kind','unknown')=='unknown':return dict(per_day=None,days=None)
    rate=D(str(demand.get('per_day',0)));personal=rate*D(str(share))/100
    return dict(per_day=rate,days=D(quantity)/personal if personal else None)
