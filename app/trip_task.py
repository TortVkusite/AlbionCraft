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
    joint=data['joint']
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
        for focus in (0,data['focus']):
            plan=solver(options,data['budget'],data['weight'],focus,repeat=data['repeat'],
                objective_mode=data['objective'],**arguments)
            plan['objective_mode']=data['objective'];plans.append(plan)
    return dict(plans=plans,options=options,rejected=rejected,stock_missing=missing,depth_warnings=warnings)
