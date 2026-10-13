"""Cash requirements, break-even scenarios and existing-stock alternatives."""
from decimal import Decimal as D
from .models import quote

def plan_evidence(plan,data):
    lines=plan['lines'];station=sum((l['calc']['station']*l['operations'] for l in lines),D(0))
    other=sum((l['calc']['fixed']*l['operations'] for l in lines),D(0))
    setup=plan.get('setup_fee',sum((l['calc'].get('setup_fee',D(0))*l['operations'] for l in lines),D(0)))
    required=plan.get('cash_required',plan['purchase']+station+other+setup)
    reserve=D(str(data.get('reserve',0)));budget=D(str(data['budget']));profit=plan['profit']
    net=plan.get('revenue',sum(((l['calc']['sale']-l['calc']['fees'])*l['operations'] for l in lines),D(0)))
    purchase=plan['purchase'];index={(p['item_id'],p['city']):p for p in data['prices'] if p.get('quality',1)==1}
    alternative=D(0);complete=True
    from .rules import effective_settings
    raw_tax=effective_settings(data['settings']).get('tax')
    tax=D(str(raw_tax))/100 if raw_tax is not None and str(raw_tax).strip() else None
    for lot in plan.get('existing',[]):
        value,age,status=quote(index.get((lot['item_id'],lot['city']),{}),'buy_price_max',data['age'])
        if tax is None or value is None or 'будущем' in status or data['age'] is not None and (age is None or age>data['age']):complete=False;continue
        alternative+=D(value)*lot['used']*(1-tax)
    limits=[]
    if D(str(data['weight']))-plan['weight']<=max(D('.01'),D(str(data['weight']))/100):limits.append('Вес')
    if budget-reserve-required<=max(D(1),budget/100):limits.append('Серебро')
    if data['focus'] and data['focus']-plan['focus']<max(1,data['focus']/100):limits.append('Фокус')
    if any(l['candidate'].limit is not None for l in lines):limits.append('Лимиты выпуска')
    return dict(cash_required=required,cash_left=budget-required,reserve=reserve,limiting=limits,break_even_sale_factor=(net-profit)/net if net else None,
        purchase_margin=profit/purchase*100 if purchase else None,sale_margin=profit/net*100 if net else None,
        adverse_profit=profit-purchase*D('.05')-net*D('.05'),
        stock_alternative=alternative if complete else None,
        versus_stock_sale=profit+plan.get('stock_value',D(0))-alternative if complete and plan.get('existing') else None)
