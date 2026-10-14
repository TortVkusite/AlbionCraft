from datetime import datetime,timezone
from decimal import Decimal
from .result_filters import in_bounds


def age_minutes(stamp):
    try:
        value=datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if value.year<=1:return None
        value=value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return (datetime.now(timezone.utc)-value).total_seconds()/60
    except (ValueError,TypeError,AttributeError):return None


def build_recommendations(rows,settings,prices=(),histories=()):
    prefs=settings.get('recommendations',{});limit=int(prefs.get('stale_hours',6))*60
    low=Decimal(str(prefs.get('roi_min',5)));high=Decimal(str(prefs.get('roi_max',200)))
    items={};candidates={}
    for row in rows:
        recipe=row['recipe'];q=row.get('quality',1)
        observations=[dict(item_id=p['ingredient'].item_id,city=row['buy'],quality=p.get('quality',q if row.get('activity') in ('resale','flip','enchant') else 1),
            price=p['price'],date=p['date'],source=p.get('source',settings.get('region_label','Europe')+' API'),status=p['status'],role='Покупка' if row.get('activity') in ('resale','flip') else 'Компонент') for p in row['parts']]
        observations.append(dict(item_id=recipe.item_id,city=row['sell'],quality=q,price=row['sale'],date=row['sale_date'],
            source=row.get('sale_source',settings.get('region_label','Europe')+' API'),status=row['sale_status'],role='Продажа' if row.get('activity') in ('resale','flip') else 'Результат'))
        for p in observations:
            key=(p['item_id'],p['city'],p['quality'],p['role'])
            if key not in items:items[key]=dict(p,used_by=set())
            items[key]['used_by'].add(recipe.item_id)
        for scenario in ('base','focus'):
            if not in_bounds(row,settings):continue
            x=row.get(scenario)
            if x is None or x['profit']<=0 or not low<=x['roi']<=high:continue
            key=(recipe.item_id,recipe.path,recipe.variant,row['buy'],row['sell'],q)
            if key not in candidates:candidates[key]=dict(row=row,scenario=scenario,result=x)
    missing=[];known=[]
    for p in items.values():
        p['age']=age_minutes(p['date']);p['recipes']=len(p.pop('used_by'))
        p['state']='Нет цены' if p['price'] is None or p['age'] is None else 'Дата в будущем' if p['age']< -2 else 'Сильно устарело' if p['age']>limit else 'Цена есть'
        if p['state']!='Цена есть':missing.append(p)
        if p['price'] is not None:known.append(p)
    missing.sort(key=lambda p:(p['state']=='Нет цены',p['role']=='Компонент',p['recipes'],p['age'] or 0),reverse=True)
    known.sort(key=lambda p:(not p['source'].startswith('Из твоей игры'),p['age'] if p['age'] is not None else float('inf')))
    candidates=sorted(candidates.values(),key=lambda c:c['result']['profit'],reverse=True)
    from .price_gaps import find_gaps
    return dict(update=missing,known=known,candidates=candidates,price_count=len(items),with_price=len(known),gaps=find_gaps(prices,histories,settings))
