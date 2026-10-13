"""Prepare and solve an entire trip in the isolated calculation process."""
from decimal import Decimal as D
from .crafter_dialog import progression
from .trip_inventory import route_stock
from .trip_optimizer import candidates,solve
from .trip_chain import prepare_chain,solve_chain
from .trip_market import configure_market


def calculate_trip(data):
    game=progression(data['root'])
    stock,missing=route_stock(data['stock_rows'],data['buy'],data['city'],data['prices'],data['age'])
    joint=data['joint'] or data.get('full_budget',False) or bool(data.get('trip_fixed'))
    engine=prepare_chain if joint else candidates
    extra=dict(roots=data['roots'],stock=stock) if joint else {}
    extra['day_bonus']=data['day_bonus']
    options,rejected=engine(data['recipes'],data['prices'],data['histories'],data['buy'],data['city'],
        data['settings'],game,data['states'],data['age'],data['rate'],data['other'],data['multiplier'],
        data['mastery'],data['limits'],**extra)
    warnings=configure_market(options,data['prices'],data['depth'],data['horizon'],data['share'],data['age'])
    plans=[]
    if options:
        solver=solve_chain if joint else solve
        arguments=dict(stock=stock) if joint else {}
        if joint:arguments['trip_fixed']=D(str(data.get('trip_fixed',0)))
        if data.get('full_budget'):
            available=D(str(data['budget']))-D(str(data.get('reserve',0)))
            if available<0:raise ValueError('Резерв превышает доступное серебро')
            arguments.update(cash_budget=available,trip_fixed=D(str(data.get('trip_fixed',0))))
        for focus in (0,data['focus']):
            plan=solver(options,data['budget'],data['weight'],focus,repeat=data['repeat'],
                objective_mode=data['objective'],**arguments)
            plan['objective_mode']=data['objective'];plans.append(plan)
            from .trip_decisions import plan_evidence
            plan.update(plan_evidence(plan,data))
    return dict(plans=plans,options=options,rejected=rejected,stock_missing=missing,depth_warnings=warnings)
