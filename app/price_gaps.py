"""Observed offer gaps are resale scenarios, never guaranteed market value."""
from decimal import Decimal as D
from datetime import datetime,timezone
from .calculator import demand
from .rules import effective_settings
from .scanner import number


def find_gaps(prices,histories,settings,now=None):
    now=now or datetime.now(timezone.utc);prefs=settings.get('price_gaps',{})
    threshold=D(str(prefs.get('minimum',10)));budget=D(str(prefs.get('budget',0)));minutes=float(prefs.get('minutes',15))
    if not threshold.is_finite() or threshold<0 or not budget.is_finite() or budget<0 or not 0<minutes<=1440:raise ValueError('Неверные ограничения дешёвых партий')
    rules=effective_settings(settings);setup=number(rules.get('setup'),True);tax=number(rules.get('tax'),True);other=number(rules.get('other'))
    if setup is None or tax is None or setup<0 or tax<0 or setup+tax>=1:return []
    missing=other is None;other=other or D(0)
    history={(h.get('item_id'),h.get('location'),h.get('quality')):h for h in histories};results=[]
    for row in prices:
        obs=row.get('local_observations')
        if not obs:continue
        try:
            stamp=datetime.fromisoformat(obs['sell_price_min_date'].replace('Z','+00:00'))
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
            age=(now-stamp).total_seconds()/60
            if not 0<=age<=minutes:continue
            levels={}
            for level in obs.get('sell_price_min_levels',[]):
                price=D(str(level['price']));qty=level['quantity']
                if not price.is_finite() or price<=0 or type(qty) is not int or qty<=0:continue
                levels[price]=levels.get(price,0)+qty
        except (KeyError,ValueError,TypeError,ArithmeticError):continue
        levels=sorted(levels.items())
        quantity=0;purchase=D(0);best=None;info=None
        for n,(price,amount) in enumerate(levels[:-1]):
            quantity+=amount;purchase+=price*amount;reference,remaining=levels[n+1]
            # Buy the whole cheap prefix, then list one silver below the next
            # seen level. An unfilled partial prefix leaves cheaper competitors.
            target=reference-1;gap=(reference/price-1)*100
            proceeds=target*quantity;fees=proceeds*(setup+tax);costs=other*quantity
            profit=proceeds-fees-purchase-costs;cash=purchase+proceeds*setup+costs
            if gap<threshold or target<=0 or profit<=0 or budget and cash>budget:continue
            if best is not None and profit<=best['profit']:continue
            if info is None:info=demand(history.get((row['item_id'],row['city'],row['quality']),{}),now)
            best=dict(item_id=row['item_id'],city=row['city'],quality=row['quality'],quantity=quantity,
                purchase=purchase,average=purchase/quantity,reference=reference,remaining_quantity=remaining,
                target=target,gap=gap,revenue=proceeds,fees=fees,other=costs,profit=profit,cash=cash,
                pending=missing,demand=info,stamp=stamp.isoformat(),bought_levels=n+1)
        # One actionable prefix per item/city/quality, rather than dozens of
        # overlapping plans using the same cheap orders.
        if best:
            best['levels']=[dict(price=p,quantity=q) for p,q in levels];results.append(best)
    return sorted(results,key=lambda c:c['profit'],reverse=True)
