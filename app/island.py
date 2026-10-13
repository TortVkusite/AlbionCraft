"""Expected farming economics. Returned seeds are inventory, not sale revenue."""
import json
from decimal import Decimal as D,ROUND_CEILING
from functools import lru_cache
from .paths import resource_root
from .models import quote

@lru_cache(maxsize=1)
def farming_data():return json.loads((resource_root()/'app/config/island_data.json').read_text(encoding='utf-8'))

def focus_cost(product,mastery,specialization):
    if not 0<=mastery<=100 or not 0<=specialization<=100:raise ValueError('Уровни должны быть от 0 до 100')
    return int((D(product['focus_base'])/(D(2)**(D(mastery*100+specialization*200)/10000))).to_integral_value(rounding=ROUND_CEILING))

def estimate(product,settings,prices,focused=0):
    plots=int(settings['plots']);count=plots*9
    if not 1<=plots<=16 or not 0<=focused<=count:raise ValueError('Некорректное число участков или полива')
    city=settings['city'];premium=bool(settings['premium']);side='buy_price_max' if settings.get('sale')=='instant' else 'sell_price_min'
    tax=D('.04') if premium else D('.08');setup=D(0) if side=='buy_price_max' else D('.025')
    index={(p['item_id'],p['city']):p for p in prices if p.get('quality',1)==1}
    def price(uid,which):
        p=index.get((uid,city),{});value,age,status=quote(p,which,None if settings.get('any_age',True) else 30)
        if value is None or 'будущем' in status or (not settings.get('any_age',True) and 'устарело' in status):return None,status
        return D(value),status
    seed,seed_status=price(product['id'],'sell_price_min');sale,sale_status=price(product['product'],side)
    food=None;food_amount=D(0)
    missing=[]
    if seed is None:missing.append(product['id'])
    if sale is None:missing.append(product['product'])
    if product['kind'] in ('animals','wild'):
        food,food_status=price(product['food'],'sell_price_min');food_amount=D(str(settings.get('food_amount',product['food_amount'])))
        if not food_amount.is_finite() or food_amount<0:raise ValueError('Некорректное количество корма')
        if food is None and food_amount:missing.append(product['food'])
    cost=focus_cost(product,int(settings.get('mastery',0)),int(settings.get('specialization',0)))
    # Animals can be nurtured several times. Selected animals receive all allowed actions.
    actions=product['actions'];focus=focused*cost*actions
    bonus=D('.1') if product['product'] in farming_data()['bonuses'].get(city,[]) else D(0)
    output=D(count)*D(product['yield_min']+product['yield_max'])/2
    if product['kind'] not in ('animals','wild'):output*=D(2) if premium else D(1);output*=1+bonus
    returned=D(count)*D(product['seed_return'])+D(focused)*D(product['focus_bonus'])*actions
    replacement=max(D(count)-returned,D(0));surplus=max(returned-D(count),D(0))
    hours=D(str(product['hours']))/(2 if premium and product['kind'] in ('animals','wild') else 1)
    base=dict(count=count,output=output,returned=returned,replacement=replacement,surplus=surplus,hours=hours,
        focus=focus,focused=focused,focus_each=cost*actions,bonus=bonus,missing=missing,
        seed_price=seed,sale_price=sale,food_amount=food_amount*count,seed_status=seed_status,sale_status=sale_status,
        seed_date=index.get((product['id'],city),{}).get('sell_price_min_date'),sale_date=index.get((product['product'],city),{}).get(side+'_date'))
    if missing:return dict(base,profit=None,investment=None,revenue=None,feed_cost=None,net_cost=None,extra_per_focus=None)
    feed_cost=(food or D(0))*food_amount*count;revenue=output*sale*(1-tax-setup)
    # Retain seeds for the next cycle. Sell only the surplus, at its own market side.
    surplus_price,_=price(product['id'],side)
    if surplus and surplus_price is None:return dict(base,missing=[product['id']],profit=None,investment=None,revenue=None,feed_cost=None,net_cost=None,extra_per_focus=None)
    surplus_revenue=surplus*(surplus_price or D(0))*(1-tax-setup)
    profit=revenue+surplus_revenue-replacement*seed-feed_cost
    return dict(base,profit=profit,investment=count*seed+feed_cost,revenue=revenue+surplus_revenue,
        feed_cost=feed_cost,net_cost=replacement*seed+feed_cost)

def calculate_islands(data):
    products={p['id']:p for p in farming_data()['products']};rows=[]
    for settings in data['islands']:
        p=products[settings['product']];settings=dict(settings,premium=data['premium'],sale=data['sale'],any_age=data['any_age'])
        plain=estimate(p,settings,data['prices']);full=estimate(p,settings,data['prices'],plain['count'])
        rows.append(dict(settings=settings,product=p,plain=plain,full=full))
    # Enumerate complete per-island choices, preserving seed replacement/surplus breakpoints.
    from scipy.optimize import milp,Bounds,LinearConstraint
    import numpy as np
    available=int(data['focus'])
    if not 0<=available<=30000:raise ValueError('Некорректное количество фокуса')
    valid=[r for r in rows if r['plain']['profit'] is not None]
    allocated={}
    if valid and available:
        choices=[]
        for n,row in enumerate(valid):
            plain=row['plain']
            for amount in range(min(plain['count'],available//plain['focus_each'])+1):
                current=estimate(row['product'],row['settings'],data['prices'],amount)
                if current['profit'] is None:continue
                choices.append((n,amount,current['profit']-plain['profit'],current['focus']))
        matrix=np.zeros((len(valid)+1,len(choices)))
        for column,(n,amount,gain,cost) in enumerate(choices):matrix[0,column]=cost;matrix[n+1,column]=1
        result=milp(-np.array([float(c[2]) for c in choices]),integrality=np.ones(len(choices)),
            bounds=Bounds(np.zeros(len(choices)),np.ones(len(choices))),
            constraints=LinearConstraint(matrix,np.array([0]+[1]*len(valid)),np.array([available]+[1]*len(valid))),options={'time_limit':5})
        if result.x is None:raise ValueError('Не удалось распределить фокус')
        for choice,value in zip(choices,result.x):
            if value>.5:allocated[id(valid[choice[0]])]=choice[1]
    for row in rows:row['selected']=estimate(row['product'],row['settings'],data['prices'],allocated.get(id(row),0))
    from .island_planner import animal_risk
    for row in rows:row['risk']=animal_risk(row['product'],row['selected'])
    return rows
