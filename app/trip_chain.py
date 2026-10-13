"""Joint purchasing, refining and selling with an auditable inventory ledger."""
from decimal import Decimal as D
from datetime import datetime,timezone
from .models import CITIES,quote
from .trip_optimizer import candidates
from .item_names import item_name

def dependency_recipes(selected,catalog):
    index={r.item_id:r for r in catalog};found={}
    def visit(r,stack):
        if r.item_id in stack:raise ValueError('Цикл рецептов: '+r.item_id)
        if r.item_id in found:return
        for i in r.ingredients:
            if i.item_id in index:visit(index[i.item_id],stack|{r.item_id})
        found[r.item_id]=r
    for r in selected:visit(r,set())
    return list(found.values())

def prepare_chain(recipes,prices,histories,buy,craft,settings,game,states,age_limit=None,
                  station_rate=None,other=D(0),fame_multiplier=D(1),respect_mastery=True,limits=None,roots=None,day_bonus=D(0),stock=()):
    """An intermediate need not have a market price if it can be manufactured.

    Temporary quotes only obtain recipe fees/profiles from the shared scanner.
    They are removed before optimization; unavailable purchases/sales get no
    variable in the model and never acquire a fictitious economic value.
    """
    index={(p['item_id'],p['city'],p.get('quality',1)):p for p in prices}
    def valid(uid,city,side):
        p=index.get((uid,city,1),{});v,age,status=quote(p,side,age_limit)
        if v is None or 'будущем' in status or age_limit is not None and age>age_limit:return None
        return v
    stamp=datetime.now(timezone.utc).isoformat();temporary=[dict(p) for p in prices]
    ids={r.item_id for r in recipes}|{i.item_id for r in recipes for i in r.ingredients}
    side='buy_price_max' if settings.get('sale_mode')=='instant' else 'sell_price_min'
    for uid in ids:
        for city,s in [(buy,'sell_price_min'),(craft,side)]:
            if valid(uid,city,s) is None:
                p=dict(index.get((uid,city,1),{}),item_id=uid,city=city,quality=1)
                p.update({s:1,s+'_date':stamp,s+'_source':'Внутренний расчёт рецепта'})
                temporary.append(p)
    options,rejected=candidates(recipes,temporary,histories,buy,craft,settings,game,states,None,station_rate,other,fame_multiplier,respect_mastery,limits,day_bonus)
    for c in options:
        c.row['net_sale_factor']=1-c.plain['fees']/c.plain['sale']
        c.row['setup_factor']=c.plain.get('setup_fee',D(0))/c.plain['sale']
        c.row['operation_other']=other*c.recipe.output_count+D(c.recipe.recipe_silver)
        c.row['root']=c.recipe.item_id in (roots or {r.item_id for r in recipes})
        c.sales={city:dict(price=D(v)) for city in CITIES if (v:=valid(c.recipe.item_id,city,side)) is not None}
        c.row['sale']=valid(c.recipe.item_id,craft,side)
        original=index.get((c.recipe.item_id,craft,1),{})
        c.row['sale_date']=original.get(side+'_date');c.row['sale_source']=original.get(side+'_source',settings.get('region_label','Europe')+' API')
        for part in c.parts:
            uid=part['ingredient'].item_id;p=index.get((uid,buy,1),{})
            _,age,status=quote(p,'sell_price_min',age_limit)
            part.update(price=valid(uid,buy,'sell_price_min'),date=p.get('sell_price_min_date'),source=p.get('sell_price_min_source',settings.get('region_label','Europe')+' API'),age=age,status=status)
        c.row['standalone']=c.row['sale'] is not None and all(p['price'] is not None for p in c.parts)
        if not c.row['standalone']:
            c.plain['profit']=D(0)
            if c.focused:c.focused['profit']=D(0)
        c.row['age']=max((p['age'] for p in c.parts if p['age'] is not None),default=0)
    available={p['ingredient'].item_id for c in options for p in c.parts if p['price'] is not None}|{s['item_id'] for s in stock if s['quantity']>0};usable=[]
    for c in ordered(options):
        missing=[p['ingredient'].item_id for p in c.parts if p['ingredient'].item_id not in available]
        if missing:rejected.append((c.recipe,'Нет покупки или доступного производства: '+', '.join(item_name(uid,False) for uid in missing)));continue
        usable.append(c);available.add(c.recipe.item_id)
    return usable,rejected

def ordered(options):
    """Topological order also used for execution, XP and prefix stock checks."""
    byid={c.recipe.item_id:c for c in options};done={};visiting=set()
    def visit(c):
        uid=c.recipe.item_id
        if uid in visiting:raise ValueError('Цикл производственной цепочки')
        if uid in done:return
        visiting.add(uid)
        for p in c.parts:
            if p['ingredient'].item_id in byid:visit(byid[p['ingredient'].item_id])
        visiting.remove(uid);done[uid]=c
    for c in sorted(options,key=lambda c:(c.recipe.tier,c.recipe.enchantment,c.recipe.item_id)):visit(c)
    return list(done.values())

def solve_chain(options,budget,weight,focus_budget=0,time_limit=10,repeat=True,objective_mode='profit',stock=(),cash_budget=None,trip_fixed=D(0)):
    import numpy as np
    from scipy.optimize import milp,Bounds,LinearConstraint
    budget=D(str(budget));weight=D(str(weight));focus_budget=int(focus_budget)
    if not budget.is_finite() or not weight.is_finite() or budget<0 or (budget==0 and not stock) or weight<=0 or focus_budget<0:
        raise ValueError('Введите положительные бюджет и вес; фокус не может быть отрицательным')
    options=ordered(options);byid={c.recipe.item_id:c for c in options}
    inputs={};weights={};levels={}
    for c in options:
        for p in c.parts:
            uid=p['ingredient'].item_id;weights[uid]=c.row['input_weights'][uid]
            inputs[uid]=p['price']
            levels[uid]=p.get('buy_levels')
    stock=[dict(s,price=D(str(s['price']))) for s in stock if s['item_id'] in inputs]
    for s in stock:
        if type(s['quantity']) is not int or s['quantity']<0 or not s['price'].is_finite() or s['price']<0:raise ValueError('Неверное количество или стоимость запаса')
    bounds=[];objective=[];constraints=[];buys={};ops={};sales={};owned=[]
    def var(cap,coefficient=D(0)):
        n=len(bounds);bounds.append(max(0,int(cap)));objective.append(float(coefficient));return n
    def add(coeff,low=-np.inf,high=np.inf):constraints.append((dict(coeff),float(low),float(high)))
    for uid,price in inputs.items():
        tiers=levels[uid] if levels[uid] is not None else [dict(price=price,quantity=None)] if price is not None else []
        for tier in tiers:
            price=D(tier['price']);cap=min(int(weight//weights[uid]),int(budget//price))
            if tier['quantity'] is not None:cap=min(cap,tier['quantity'])
            buys.setdefault(uid,[]).append((var(cap,price),price))
    for s in stock:owned.append((s,var(s['quantity'],s['price'])))
    # Valid upper bounds include the cheapest/lightest possible manufacturing
    # path; a purchased previous-tier bar is never mandatory for this bound.
    memo={}
    def min_mass(uid):
        if uid in memo:return memo[uid]
        value=weights.get(uid,D('Infinity'))
        if uid in byid:
            c=byid[uid];rr=max(D(c.row['profile']['rrr'])/100,D(c.row['profile']['focus_rrr'])/100 if c.focused and c.focus else D(0))
            production=sum((min_mass(p['ingredient'].item_id)*p['ingredient'].amount*(1-rr if p['ingredient'].returnable and repeat else 1) for p in c.parts),D(0))/c.recipe.output_count
            value=min(value,production)
        memo[uid]=value;return value
    total_mass=weight+sum((weights[s['item_id']]*s['quantity'] for s in stock),D(0))
    focus_coeff={}
    for c in options:
        uid=c.recipe.item_id;rp=D(c.row['profile']['rrr'])/100;rf=D(c.row['profile']['focus_rrr'])/100 if c.focused else rp
        if not 0<=rp<1 or not 0<=rf<1:raise ValueError('Возврат должен быть меньше 100%')
        if rf<rp:raise ValueError('Возврат с фокусом ниже возврата без фокуса; проверь профиль')
        rr=max(rp,rf if focus_budget and c.focus else rp)
        mass=sum((min_mass(p['ingredient'].item_id)*p['ingredient'].amount*(1-rr if p['ingredient'].returnable and repeat else 1) for p in c.parts),D(0))
        maximum=int(total_mass//mass) if mass.is_finite() and mass>0 else 0
        if c.limit is not None:maximum=min(maximum,c.limit//c.recipe.output_count)
        mf=min(maximum,focus_budget//c.focus) if focus_budget and c.focus and c.focused else 0
        fee=c.plain['station']+c.row.get('operation_other',D(0))
        p=var(maximum,fee);f=var(mf,fee);active=var(1 if maximum else 0);fa=var(1 if mf else 0);pa=var(1 if maximum else 0)
        add({p:1,f:1,active:-maximum},high=0);add({active:1,p:-1,f:-1},high=0)
        add({f:1,fa:-mf},high=0);add({fa:1,f:-1},high=0)
        add({p:1,pa:-maximum},high=0);add({pa:1,p:-1},high=0)
        focus_coeff[f]=(c.focus or 0)/focus_budget if focus_budget else 0
        ops[uid]=(p,f,active,fa,rp,rf,pa)
        if c.row.get('root',True) and c.sales.get(c.row['sell']):
            sale=c.sales[c.row['sell']];tiers=sale.get('levels')
            if tiers is None:tiers=[dict(price=sale['price'],quantity=maximum*c.recipe.output_count)]
            sales[uid]=[(var(min(maximum*c.recipe.output_count,t['quantity']),-D(t['price'])*c.row['net_sale_factor']),D(t['price'])) for t in tiers]
            coeff={col:1 for col,price in sales[uid]};coeff.update({p:-c.recipe.output_count,f:-c.recipe.output_count});add(coeff,high=0)
            if c.row.get('sale_limit') is not None:add({col:1 for col,price in sales[uid]},high=c.row['sale_limit'])
    trip_fixed=D(str(trip_fixed));trip_active=None
    if not trip_fixed.is_finite() or trip_fixed<0:raise ValueError('Неверные расходы ходки')
    if trip_fixed:
        trip_active=var(1,trip_fixed);all_ops={col:1 for values in ops.values() for col in values[:2]}
        add(all_ops|{trip_active:-sum(bounds[col] for col in all_ops)},high=0)
        add({trip_active:1}|{col:-1 for col in all_ops},high=0)
    add({b:float(price/max(budget,D(1))) for uid,tiers in buys.items() for b,price in tiers},high=1 if budget else 0)
    if cash_budget is not None:
        cash_budget=D(str(cash_budget));trip_fixed=D(str(trip_fixed))
        if not cash_budget.is_finite() or not trip_fixed.is_finite() or cash_budget<0 or trip_fixed<0:raise ValueError('Неверный бюджет всей операции')
        cash={b:price for tiers in buys.values() for b,price in tiers}
        for c in options:
            p,f=ops[c.recipe.item_id][:2];fee=c.plain['station']+c.row.get('operation_other',D(0))
            cash[p]=fee;cash[f]=fee
            for col,price in sales.get(c.recipe.item_id,[]):cash[col]=price*c.row.get('setup_factor',D(0))
        if trip_active is not None:cash[trip_active]=trip_fixed
        add(cash,high=cash_budget)
    load_coeff={b:float(weights[uid]/weight) for uid,tiers in buys.items() for b,price in tiers}
    for s,col in owned:
        if s.get('transport'):load_coeff[col]=float(weights[s['item_id']]/weight)
    add(load_coeff,high=1);add(focus_coeff,high=1)
    ledger={uid:{b:D(1) for b,price in buys.get(uid,[])} for uid in set(inputs)|set(byid)}
    def change(uid,col,value):ledger[uid][col]=ledger[uid].get(col,D(0))+value
    for s,col in owned:change(s['item_id'],col,D(1))
    for c in options:
        uid=c.recipe.item_id;p,f,active,fa,rp,rf,pa=ops[uid]
        for part in c.parts:
            i=part['ingredient'];count=D(i.amount)
            if not repeat:
                before=dict(ledger[i.item_id]);before[p]=before.get(p,D(0))-count;before[f]=before.get(f,D(0))-count
                add(before,low=0)
            change(i.item_id,p,-count*(1-rp if i.returnable else 1));change(i.item_id,f,-count*(1-rf if i.returnable else 1))
            if repeat:
                prefix=dict(ledger[i.item_id])
                if i.returnable:
                    # Focused operations go first. With fixed focus costs and
                    # rf >= rp, finishing with plain minimizes required stock.
                    prefix[active]=prefix.get(active,D(0))-count*rf;prefix[pa]=prefix.get(pa,D(0))-count*(rp-rf)
                add(prefix,low=0)
        change(uid,p,D(c.recipe.output_count));change(uid,f,D(c.recipe.output_count))
    for uid,coeff in ledger.items():
        end=dict(coeff)
        for col,price in sales.get(uid,[]):end[col]=end.get(col,D(0))-1
        add(end,low=0)
    if not bounds:return empty_plan()
    matrix=np.zeros((len(constraints),len(bounds)))
    for n,(coeff,lo,hi) in enumerate(constraints):
        for col,v in coeff.items():matrix[n,col]=float(v)
    from .trip_objective import optimize
    purchase_vector=np.zeros(len(bounds))
    for tiers in buys.values():
        for col,price in tiers:purchase_vector[col]=float(price)
    for s,col in owned:purchase_vector[col]=float(s['price'])
    result,scale=optimize(milp,objective,purchase_vector,Bounds(np.zeros(len(bounds)),bounds),
        LinearConstraint(matrix,[r[1] for r in constraints],[r[2] for r in constraints]),time_limit,objective_mode)
    if result.x is None:raise ValueError('Решатель не нашёл план цепочки: '+result.message)
    quantities=[int(round(v)) for v in result.x]
    # Check all integer constraints before accepting a solver result.
    for coeff,lo,hi in constraints:
        val=sum((D(str(v))*quantities[col] for col,v in coeff.items()),D(0))
        if val<D(str(lo))-D('0.0000001') or val>D(str(hi))+D('0.0000001'):raise ValueError('Нарушен баланс цепочки из-за точности решателя; пересчитай')
    purchased={uid:sum(quantities[b] for b,price in tiers) for uid,tiers in buys.items() if any(quantities[b] for b,price in tiers)}
    costs={uid:sum((price*quantities[b] for b,price in tiers),D(0)) for uid,tiers in buys.items()}
    existing=[dict(s,used=quantities[col]) for s,col in owned if quantities[col]]
    counts={uid:(quantities[v[0]],quantities[v[1]]) for uid,v in ops.items()}
    sold={uid:sum(quantities[col] for col,price in tiers) for uid,tiers in sales.items() if any(quantities[col] for col,price in tiers)}
    gross_sales={uid:sum((price*quantities[col] for col,price in tiers),D(0)) for uid,tiers in sales.items()}
    consumed={}
    for c in options:
        plain,focused=counts[c.recipe.item_id];rp=ops[c.recipe.item_id][4];rf=ops[c.recipe.item_id][5]
        for part in c.parts:
            i=part['ingredient'];consumed[i.item_id]=consumed.get(i.item_id,D(0))+i.amount*(plain*(1-rp if i.returnable else 1)+focused*(1-rf if i.returnable else 1))
    # Forward inventory simulation is independent of the constraint matrix.
    stock={uid:D(n) for uid,n in purchased.items()};execution=[]
    for s in existing:stock[s['item_id']]=stock.get(s['item_id'],D(0))+s['used']
    for c in options:
        plain,focused=counts[c.recipe.item_id]
        for flag,n in [(True,focused),(False,plain)]:
            if not n:continue
            rr=ops[c.recipe.item_id][5 if flag else 4]
            for part in c.parts:
                i=part['ingredient'];count=D(i.amount);net=count*(1-rr if i.returnable else 1)
                required=net*n+(count*rr if i.returnable else 0) if repeat else count*n
                if stock.get(i.item_id,D(0))+D('0.0000001')<required:raise ValueError('Недостаточно ингредиентов для выполнения цепочки')
                stock[i.item_id]=stock.get(i.item_id,D(0))-net*n
            stock[c.recipe.item_id]=stock.get(c.recipe.item_id,D(0))+n*c.recipe.output_count
            execution.append((c,flag,n))
    for uid,n in sold.items():stock[uid]-=n
    if any(v<D('-0.0000001') for v in stock.values()):raise ValueError('Отрицательный остаток цепочки')
    purchase=sum(costs.values(),D(0));load=sum((weights[uid]*n for uid,n in purchased.items()),D(0))
    stock_value=sum((s['price']*s['used'] for s in existing),D(0))
    load+=sum((weights[s['item_id']]*s['used'] for s in existing if s.get('transport')),D(0))
    used=sum((byid[uid].focus or 0)*f for uid,(p,f) in counts.items())
    if purchase>budget or load>weight or used>focus_budget:raise ValueError('Цепочка превысила бюджет, вес или фокус')
    lines=[];revenue=D(0);fees=D(0)
    for c,flag,n in execution:
        uid=c.recipe.item_id;total=sum(counts[uid]);out=n*c.recipe.output_count;fraction=D(n)/total
        sell_qty=max(0,sold.get(uid,0)-counts[uid][0]*c.recipe.output_count) if flag else min(sold.get(uid,0),out)
        allocated=D(0);allocated_weight=D(0)
        rr=ops[uid][5 if flag else 4]
        for part in c.parts:
            i=part['ingredient'];use=i.amount*n*(1-rr if i.returnable else 1)
            ratio=use/consumed[i.item_id] if consumed[i.item_id] else D(0)
            allocated+=costs.get(i.item_id,D(0))*ratio
            allocated_weight+=weights[i.item_id]*purchased.get(i.item_id,0)*ratio
            allocated+=sum((s['price']*s['used']*ratio for s in existing if s['item_id']==i.item_id),D(0))
            allocated_weight+=sum((weights[i.item_id]*s['used']*ratio for s in existing if s['item_id']==i.item_id and s.get('transport')),D(0))
        gross=gross_sales.get(uid,D(0))*D(sell_qty)/sold[uid] if sell_qty else D(0);net=gross*c.row['net_sale_factor'];station=c.plain['station']*n;other=c.row.get('operation_other',D(0))*n
        contribution=net-allocated-station-other
        calc=dict(c.plain);calc.update(sale=gross/n,fees=(gross-net)/n,station=station/n,fixed=other/n,returned=D(0),profit=contribution/n)
        lines.append(dict(candidate=c,focused=flag,operations=n,quantity=out,calc=calc,purchase=allocated,weight=allocated_weight,sold=sell_qty,internal=consumed.get(uid,D(0))*fraction))
        revenue+=net;fees+=station+other
    profit=revenue-purchase-stock_value-fees
    setup=sum((gross_sales.get(c.recipe.item_id,D(0))*c.row.get('setup_factor',D(0)) for c in options),D(0))
    required=purchase+fees+setup+(trip_fixed if lines else D(0))
    if cash_budget is not None and required>cash_budget+D('.0001'):raise ValueError('План превышает доступное серебро')
    profit-=trip_fixed if lines else D(0)
    if abs(sum((l['calc']['profit']*l['operations'] for l in lines),D(0))-profit-(trip_fixed if lines else D(0)))>D('0.000001'):raise ValueError('Не сходится денежный баланс цепочки')
    if profit<=0:
        empty=empty_plan();empty['optimal']=result.status==0
        empty['upper_bound']=max(D(0),D(str(-result.mip_dual_bound*scale))) if getattr(result,'mip_dual_bound',None) is not None else None
        return empty
    goods={uid:dict(quantity=n,price=costs[uid]/n,cost=costs[uid],levels=[dict(price=price,quantity=quantities[col]) for col,price in buys[uid] if quantities[col]],depth_known=levels[uid] is not None,returned=max(D(0),stock.get(uid,D(0)))) for uid,n in purchased.items()}
    bound=D(str(-result.mip_dual_bound*scale)) if getattr(result,'mip_dual_bound',None) is not None else None
    return dict(chain=True,repeat=repeat,lines=lines,goods=goods,sold=sold,gross_sales=gross_sales,stocks=stock,purchase=purchase,stock_value=stock_value,basis=purchase+stock_value,existing=existing,weight=load,focus=used,profit=profit,revenue=revenue,cash_required=required,setup_fee=setup,trip_fixed=trip_fixed,
        optimal=result.status==0,upper_bound=max(profit,bound) if bound is not None else None,message=result.message)

def empty_plan():
    return dict(chain=True,repeat=True,lines=[],goods={},sold={},stocks={},purchase=D(0),weight=D(0),focus=0,profit=D(0),revenue=D(0),optimal=True,upper_bound=D(0),message='Нет прибыльной цепочки')
