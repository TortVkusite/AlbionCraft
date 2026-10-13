"""Plot decisions and exact offspring scenarios from verified game parameters."""
from decimal import Decimal as D

def animal_risk(product,result):
    if product['kind']!='wild' or result['profit'] is None or product.get('offspring_amount',1)!=1:return None
    p=D(product['seed_return']);focused=min(D(1),p+D(product['focus_bonus'])*product['actions'])
    if not 0<=p<=1:return None
    distribution=[D(1)]
    for i in range(result['count']):
        chance=focused if i<result['focused'] else p;new=[D(0)]*(len(distribution)+1)
        for k,value in enumerate(distribution):new[k]+=value*(1-chance);new[k+1]+=value*chance
        distribution=new
    base=result['revenue']-result['feed_cost']-result['count']*result['seed_price']
    outcomes=[dict(offspring=k,profit=base+k*result['seed_price'],probability=p) for k,p in enumerate(distribution)]
    def percentile(target):
        cumulative=D(0)
        for row in outcomes:
            cumulative+=row['probability']
            if cumulative>=target:return row['profit']
        return outcomes[-1]['profit']
    return dict(positive=sum((r['probability'] for r in outcomes if r['profit']>0),D(0)),expected=sum((r['probability']*r['profit'] for r in outcomes),D(0)),p10=percentile(D('.1')),p50=percentile(D('.5')),p90=percentile(D('.9')),outcomes=outcomes)

def profile_levels(game,states,uid):
    keys=game.matching(uid,'FARM');base=[k for k in keys if game.nodes[k]['@usetemplate']=='FARM_BASE'];spec=[k for k in keys if game.nodes[k]['@usetemplate']=='FARM_SPEC']
    return dict(mastery=max((states.get(k,{}).get('level',0) for k in base),default=0),specialization=max((states.get(k,{}).get('level',0) for k in spec),default=0))

def payback(investment,profit,hours,horizon=30):
    investment=D(str(investment));profit=D(str(profit));hours=D(str(hours))
    if investment<0 or hours<=0:raise ValueError('Неверная стоимость постройки или длительность')
    daily=profit*24/max(hours,D(24))
    return dict(days=investment/daily if daily>0 else None,net_horizon=daily*D(str(horizon))-investment,daily=daily)

def alternatives(data):
    from .island import farming_data,estimate
    rows=[]
    for product in farming_data()['products']:
        if product['kind']!=data['kind']:continue
        settings=dict(data['settings'],product=product['id'])
        if data.get('levels'):settings.update(data['levels'].get(product['id'],{}))
        settings['food_amount']=product.get('food_amount',0)
        result=estimate(product,settings,data['prices'])
        if result['profit'] is None:continue
        financial=payback(D(str(data.get('construction',0)))+result['investment'],result['profit'],result['hours'])
        rows.append(dict(product=product,result=result,financial=financial))
    return sorted(rows,key=lambda row:row['financial']['daily'],reverse=True)
