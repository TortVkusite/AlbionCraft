"""Integer refining plans with optional reuse of expected resource returns.

The objective is net output revenue + retained materials at purchase value -
purchase - production fees. Inventory value is kept separate from cash revenue.
Focus coefficients are frozen at the starting profile (a conservative bound).
"""
import math
from dataclasses import dataclass
from decimal import Decimal as D, ROUND_CEILING
from fnmatch import fnmatchcase
from functools import lru_cache
from .catalog import many
from .models import CITIES, quote
from .scanner import scan, number
from .progression import advance

REFINING=('ore','wood','fiber','hide','rock')

def refining_recipes(recipes):
    return sorted((r for r in recipes if r.category=='materials' and r.crafting_category in REFINING
                   and r.path=='Прямой крафт' and r.variant==0),key=lambda r:(r.crafting_category,r.tier,r.enchantment))

def item_data(game,uid):
    return game.items.get(uid.split('@')[0],{})

@lru_cache(maxsize=4096)
def refining_nodes(game,recipe):
    base=recipe.item_id.split('@')[0]
    return [k for k,n in game.nodes.items() if n['@usetemplate'].startswith('REFINE_')
            and any(fnmatchcase(base,p['@pattern']) for p in many((n.get('itemlist') or {}).get('itempattern')))]

def unlocked(game,recipe,states):
    if recipe.tier<=3:return True
    return any(k.endswith('_T'+str(recipe.tier)) and states.get(k,{}).get('level',0)>0
               for k in refining_nodes(game,recipe))

def fame_per_item(game,uid,seen=None):
    """Refined fame sums consumed raw/previous-tier fame, not resource returns."""
    seen=set() if seen is None else seen
    if uid in seen:return None
    item=item_data(game,uid)
    if '@famevalue' in item:return D(item['@famevalue'])
    req=game.requirements(uid)
    parts=many(req.get('craftresource'))
    if not parts:return None
    total=D(0)
    for part in parts:
        mid=part['@uniquename'];ench=part.get('@enchantmentlevel','0')
        if ench!='0' and '@' not in mid:mid+='@'+ench
        fame=fame_per_item(game,mid,seen|{uid})
        if fame is None:return None
        total+=fame*D(part['@count'])
    return total/D(req.get('@amountcrafted','1'))

def focus_per_operation(game,recipe,states):
    req=game.requirements(recipe.item_id,recipe.variant)
    if '@craftingfocus' not in req:return None
    efficiency=sum(v*states.get(k,{}).get('level',0) for k,v in game.focus_coefficients(recipe.item_id).items())
    return math.ceil(int(req['@craftingfocus'])/float(game.game['ActionFocus']['@costreductionconstant'])**efficiency)

@dataclass
class Candidate:
    recipe:object
    purchase:D
    weight:D
    plain:dict
    focused:dict|None
    focus:int|None
    fame:D|None
    parts:list
    row:dict
    sales:dict
    limit:int|None=None

def candidates(recipes,prices,histories,buy,craft,settings,game,states,age_limit=None,
               station_rate=None,other=D(0),fame_multiplier=D(1),respect_mastery=True,limits=None,day_bonus=D(0)):
    """Missing prices/fees/weights do not silently become zero coefficients."""
    day_bonus=D(str(day_bonus))
    if not day_bonus.is_finite() or day_bonus<0:raise ValueError('Дневной бонус не может быть отрицательным')
    config=dict(settings,activity='craft',same_city=False,auto_rules=True,other=str(other))
    config['quality_mask']=[1]
    # Explicit station rate has priority over saved city/recipe station profiles.
    config['station_rates']={**settings.get('station_rates',{}),**({craft:str(station_rate)} if station_rate is not None else {})}
    from dataclasses import replace
    prepared=[];rejected=[]
    for r in recipes:
        if respect_mastery and not unlocked(game,r,states):
            rejected.append((r,'Тир не открыт в сохранённом профиле'));continue
        value=number(item_data(game,r.item_id).get('@itemvalue'))
        if r.nutrition is None and value is not None:
            r=replace(r,nutrition=str(value*D(game.game['ItemValueToNutrition']['@factor'])))
        if r.tier<=int(game.game['FreeCrafting']['@maxTier']):r=replace(r,nutrition='0')
        prepared.append(r)
    if station_rate is not None:
        config['profiles']={k:{city:dict(v) for city,v in cities.items()} for k,cities in settings.get('profiles',{}).items()}
        for r in prepared:
            key=r.item_id+'|'+r.path+'|'+str(r.variant)
            config['profiles'].setdefault(key,{}).setdefault(craft,{})['station']=str(station_rate*D(r.nutrition)/100) if r.nutrition is not None else ''
    if day_bonus:
        from .rules import automatic_profile
        config['profiles']={k:{city:dict(v) for city,v in cities.items()} for k,cities in config.get('profiles',{}).items()}
        for r in prepared:
            key=r.item_id+'|'+r.path+'|'+str(r.variant)
            specific=dict(config.get('profiles',{}).get(key,{}).get(craft,{}))
            profile={**automatic_profile(r,craft,config),**{k:v for k,v in config.get('general',{}).get(craft,{}).items() if str(v).strip()},**{k:v for k,v in specific.items() if str(v).strip()}}
            for name in ('rrr','focus_rrr'):
                rr=number(profile.get(name),True)
                if rr is None or not 0<=rr<1:raise ValueError('Для дневного бонуса нужен корректный возврат ресурсов')
                bonus=rr/(1-rr)+day_bonus/100;specific[name]=str(bonus/(1+bonus)*100)
            config['profiles'].setdefault(key,{})[craft]=specific
    # Only this route's sale determines the objective. Other cities are comparisons.
    rows=scan(prepared,prices,histories,[buy],[craft],[craft],config,1,age_limit)
    index={(p.get('item_id'),p.get('city'),p.get('quality')):p for p in prices}
    side='buy_price_max' if config.get('sale_mode')=='instant' else 'sell_price_min'
    result=[]
    for row in rows:
        r=row['recipe'];key=r.item_id
        if age_limit is not None and row['age'] is not None and row['age']>age_limit:
            rejected.append((r,f'Есть цена старше {age_limit} минут; обнови ингредиенты и результат'));continue
        if row['base'] is None or row['pending_costs']:
            rejected.append((r,'; '.join(row['reasons']) or 'Не задан тариф станции'));continue
        weight=D(0);missing=False
        for i in r.ingredients:
            w=number(item_data(game,i.item_id).get('@weight'))
            if w is None:missing=True;break
            weight+=w*i.amount
        if missing or weight<=0:
            rejected.append((r,'Нет веса ингредиентов'));continue
        sales={}
        for city in CITIES:
            p=index.get((key,city,1),{});v,age,status=quote(p,side,age_limit)
            if v is not None and 'будущем' not in status and (age_limit is None or age is not None and age<=age_limit):sales[city]=dict(price=D(v),age=age,status=status)
        # scan expresses money per output unit; solver variables are whole operations.
        out=r.output_count
        plain={k:v*out if isinstance(v,D) else v for k,v in row['base'].items()}
        focused={k:v*out if isinstance(v,D) else v for k,v in row['focus'].items()} if row['focus'] else None
        fame=fame_per_item(game,key)
        row['input_weights']={i.item_id:number(item_data(game,i.item_id).get('@weight')) for i in r.ingredients}
        result.append(Candidate(r,row['purchase_cost']*out,weight,plain,focused,
            focus_per_operation(game,r,states),fame*fame_multiplier if fame is not None else None,
            row['parts'],row,sales,(limits or {}).get(key)))
    return result,rejected

def solve(options,budget,weight,focus_budget=0,time_limit=10,repeat=False,objective_mode='profit'):
    """Maximise modeled profit with integral operations and hard full-load limits."""
    if repeat:return solve_repeated(options,budget,weight,focus_budget,time_limit,objective_mode)
    import numpy as np
    from scipy.optimize import milp,Bounds,LinearConstraint
    budget=D(str(budget));weight=D(str(weight));focus_budget=int(focus_budget)
    if not budget.is_finite() or not weight.is_finite() or budget<=0 or weight<=0 or focus_budget<0:
        raise ValueError('Введите положительные бюджет и вес; фокус не может быть отрицательным')
    variables=[]
    for idx,c in enumerate(options):
        for focused,calc in [(False,c.plain),(True,c.focused)]:
            if calc is None or (focused and (not focus_budget or c.focus is None or c.focus<=0)):continue
            if calc['profit']<=0:continue
            maximum=min(int(budget//c.purchase),int(weight//c.weight)) if c.purchase else int(weight//c.weight)
            if c.limit is not None:maximum=min(maximum,c.limit)
            if focused:maximum=min(maximum,focus_budget//c.focus)
            if maximum>0:variables.append((idx,focused,calc,maximum))
    if not variables:return dict(lines=[],profit=D(0),purchase=D(0),weight=D(0),focus=0,optimal=True,message='Нет прибыльных вариантов в заданных ограничениях')
    matrix=[[float(options[i].purchase/budget) for i,f,c,m in variables],
            [float(options[i].weight/weight) for i,f,c,m in variables],
            [options[i].focus/focus_budget if f else 0 for i,f,c,m in variables]]
    upper=[1,1,1]
    for i,c in enumerate(options):
        if c.limit is not None:
            matrix.append([int(j==i) for j,f,calc,m in variables]);upper.append(c.limit)
    from .trip_objective import optimize
    result,scale=optimize(milp,[-float(c['profit']) for i,f,c,m in variables],
        [float(options[i].purchase) for i,f,c,m in variables],
        Bounds(np.zeros(len(variables)),[m for i,f,c,m in variables]),
        LinearConstraint(matrix,-np.inf,upper),time_limit,objective_mode)
    if result.x is None:raise ValueError('Решатель не нашёл допустимый план: '+result.message)
    lines=[];cost=D(0);load=D(0);used=0;profit=D(0)
    for (i,focused,calc,maximum),raw in zip(variables,result.x):
        qty=int(round(raw))
        if qty<=0:continue
        c=options[i];cost+=c.purchase*qty;load+=c.weight*qty;used+=(c.focus or 0)*qty if focused else 0;profit+=calc['profit']*qty
        lines.append(dict(candidate=c,focused=focused,operations=qty,quantity=qty*c.recipe.output_count,calc=calc))
    # Reject numerical-tolerance violations; never display an overloaded load.
    if cost>budget or load>weight or used>focus_budget:raise ValueError('План превысил ограничение из-за точности решателя. Уменьшите лимит и пересчитайте.')
    return dict(lines=lines,profit=profit,purchase=cost,weight=load,focus=used,optimal=result.status==0,message=result.message)

def solve_repeated(options,budget,weight,focus_budget=0,time_limit=10,objective_mode='profit'):
    """Integer initial purchases and operations; expected returns are reused.

    Initial stock must cover every recipe, including the final operation's
    reserve. Plain operations precede focused ones. Returns are expectations,
    so integral operations do not promise an exact in-game random outcome.
    """
    import numpy as np
    from scipy.optimize import milp,Bounds,LinearConstraint
    budget=D(str(budget));weight=D(str(weight));focus_budget=int(focus_budget)
    if not budget.is_finite() or not weight.is_finite() or budget<=0 or weight<=0 or focus_budget<0:
        raise ValueError('Введите положительные бюджет и вес; фокус не может быть отрицательным')
    objectives=[];bounds=[];budget_row={};weight_row={};focus_row={};constraints=[];groups=[]
    def var(upper,profit=D(0)):
        n=len(bounds);bounds.append(upper);objectives.append(float(-profit));return n
    def constraint(coeff,low=-np.inf,high=np.inf):constraints.append((coeff,low,high))
    for c in options:
        rp=D(c.row['profile']['rrr'])/100;rf=D(c.row['profile']['focus_rrr'])/100
        if not D(0)<=rp<D(1) or not D(0)<=rf<D(1):raise ValueError('Возврат должен быть от 0 до менее 100%')
        parts=c.parts
        net_plain=sum((D(p['price'])*p['ingredient'].amount*(1-rp if p['ingredient'].returnable else 1) for p in parts),D(0))
        net_focus=sum((D(p['price'])*p['ingredient'].amount*(1-rf if p['ingredient'].returnable else 1) for p in parts),D(0))
        wp=sum((c.row['input_weights'][p['ingredient'].item_id]*p['ingredient'].amount*(1-rp if p['ingredient'].returnable else 1) for p in parts),D(0))
        wf=sum((c.row['input_weights'][p['ingredient'].item_id]*p['ingredient'].amount*(1-rf if p['ingredient'].returnable else 1) for p in parts),D(0))
        def maximum(cost,load):
            m=int(weight//load)
            if cost>0:m=min(m,int(budget//cost))
            if c.limit is not None:m=min(m,c.limit//c.recipe.output_count)
            return m
        mp=maximum(net_plain,wp) if c.plain['profit']>0 else 0
        mf=min(maximum(net_focus,wf),focus_budget//c.focus) if c.focused and c.focused['profit']>0 and c.focus and focus_budget else 0
        if not mp and not mf:continue
        p=var(mp,c.plain['profit']);f=var(mf,c.focused['profit'] if c.focused else D(0));active=var(1);fa=var(1 if mf else 0)
        constraint({p:1,f:1,active:-(mp+mf)},high=0);constraint({active:1,p:-1,f:-1},high=0)
        constraint({f:1,fa:-mf},high=0);constraint({fa:1,f:-1},high=0)
        if c.limit is not None:constraint({p:1,f:1},high=c.limit//c.recipe.output_count)
        focus_row[f]=(c.focus or 0)/focus_budget if focus_budget else 0
        buys=[]
        for part in parts:
            i=part['ingredient'];price=D(part['price']);w=c.row['input_weights'][i.item_id];count=D(i.amount)
            cap=int(weight//w)
            if price>0:cap=min(cap,int(budget//price))
            b=var(cap);budget_row[b]=float(price/budget);weight_row[b]=float(w/weight)
            # Cover the final recipe before its return arrives, not merely its
            # net consumption. Nonreturnable inputs are purchased for all ops.
            coeff={b:1,p:-float(count*(1-rp if i.returnable else 1)),f:-float(count*(1-rf if i.returnable else 1))}
            if i.returnable:coeff.update({active:-float(count*rp),fa:-float(count*(rf-rp))})
            constraint(coeff,low=0);buys.append((part,price,w))
        groups.append((c,p,f,rp,rf,buys))
    if not groups:return dict(lines=[],profit=D(0),purchase=D(0),weight=D(0),focus=0,optimal=True,message='Нет прибыльных вариантов в заданных ограничениях',repeat=True,goods={})
    for coeff in [budget_row,weight_row,focus_row]:constraint(coeff,high=1)
    matrix=np.zeros((len(constraints),len(bounds)))
    for n,(coeff,lo,hi) in enumerate(constraints):
        for col,value in coeff.items():matrix[n,col]=value
    from .trip_objective import optimize
    purchase_vector=np.zeros(len(bounds))
    for col,value in budget_row.items():purchase_vector[col]=value*float(budget)
    result,scale=optimize(milp,objectives,purchase_vector,Bounds(np.zeros(len(bounds)),bounds),
        LinearConstraint(matrix,[r[1] for r in constraints],[r[2] for r in constraints]),time_limit,objective_mode)
    if result.x is None:raise ValueError('Решатель не нашёл допустимый план: '+result.message)
    lines=[];goods={};cost=D(0);load=D(0);profit=D(0);used=0
    for c,p,f,rp,rf,buys in groups:
        plain=int(round(result.x[p]));focused=int(round(result.x[f]));total=plain+focused
        if not total:continue
        initial_cost=D(0);initial_weight=D(0);leftover=D(0)
        for part,price,w in buys:
            i=part['ingredient'];count=D(i.amount)
            consumed=count*(plain*(1-rp if i.returnable else 1)+focused*(1-rf if i.returnable else 1))
            reserve=count*(rf if focused else rp) if i.returnable else D(0)
            qty=int((consumed+reserve).to_integral_value(rounding=ROUND_CEILING));remaining=D(qty)-consumed
            entry=goods.setdefault(i.item_id,dict(quantity=0,returned=D(0),price=part['price']))
            entry['quantity']+=qty;entry['returned']+=remaining
            initial_cost+=price*qty;initial_weight+=w*qty;leftover+=price*remaining
        # Allocate actual initial load between the two displayed operation rows.
        proportions=[D(plain)*sum((D(p['price'])*p['ingredient'].amount*(1-rp if p['ingredient'].returnable else 1) for p in c.parts),D(0))]
        proportions.append(D(focused)*sum((D(p['price'])*p['ingredient'].amount*(1-rf if p['ingredient'].returnable else 1) for p in c.parts),D(0)))
        denominator=sum(proportions) or D(total)
        for flag,qty,share in [(False,plain,proportions[0]),(True,focused,proportions[1])]:
            if not qty:continue
            fraction=(share/denominator) if sum(proportions) else D(qty)/D(total)
            calc=dict(c.focused if flag else c.plain);calc['returned']=leftover*fraction/qty
            lines.append(dict(candidate=c,focused=flag,operations=qty,quantity=qty*c.recipe.output_count,calc=calc,purchase=initial_cost*fraction,weight=initial_weight*fraction))
            profit+=calc['profit']*qty;used+=(c.focus or 0)*qty if flag else 0
        cost+=initial_cost;load+=initial_weight
    if cost>budget or load>weight or used>focus_budget:raise ValueError('План превысил ограничение из-за точности решателя. Уменьшите лимит и пересчитайте.')
    return dict(lines=lines,profit=profit,purchase=cost,weight=load,focus=used,optimal=result.status==0,message=result.message,repeat=True,goods=goods)

def shopping(plan):
    if plan.get('repeat') or plan.get('chain'):return plan['goods']
    result={}
    for line in plan['lines']:
        c=line['candidate'];rrr=c.row['profile']['focus_rrr' if line['focused'] else 'rrr'];rrr=D(rrr)/100
        for part in c.parts:
            i=part['ingredient'];qty=i.amount*line['operations'];entry=result.setdefault(i.item_id,dict(quantity=0,returned=D(0),price=part['price']))
            entry['quantity']+=qty
            if i.returnable:entry['returned']+=qty*rrr
    return result

def sale_comparisons(plan,craft,settings):
    from .rules import effective_settings
    settings=effective_settings(settings);setup=D(0) if settings.get('sale_mode')=='instant' else number(settings.get('setup'),True);tax=number(settings.get('tax'),True)
    results=[]
    if plan.get('chain'):
        byid={l['candidate'].recipe.item_id:l['candidate'] for l in plan['lines']}
        for city in CITIES:
            profit=plan['profit'];missing=[]
            for uid,qty in plan['sold'].items():
                c=byid[uid];sale=c.sales.get(city)
                if sale is None:missing.append(uid);continue
                from .trip_market import proceeds
                gross=plan.get('gross_sales',{}).get(uid,c.sales[craft]['price']*qty) if city==craft else proceeds(sale,qty)
                if gross is None:missing.append(uid);continue
                profit+=(gross-plan.get('gross_sales',{}).get(uid,c.sales[craft]['price']*qty))*c.row['net_sale_factor']
            results.append(dict(city=city,profit=profit if not missing else None,delta=profit-plan['profit'] if not missing else None,missing=missing))
        return results
    for city in CITIES:
        profit=D(0);missing=[]
        for line in plan['lines']:
            c=line['candidate'];sale=c.sales.get(city)
            if sale is None:missing.append(c.recipe.item_id);continue
            profit+=line['calc']['profit']*line['operations']+(sale['price']-c.sales[craft]['price'])*line['quantity']*(1-setup-tax)
        results.append(dict(city=city,profit=profit if not missing else None,delta=profit-plan['profit'] if not missing else None,missing=missing))
    return results

def simulate_progress(game,plan,states):
    before={k:dict(v) for k,v in states.items()};states={k:dict(v) for k,v in states.items()};total_focus=0;fame=D(0)
    # Lowest-tier operations first; then plain before focused to show a reproducible order.
    lines=plan['lines'] if plan.get('chain') else sorted(plan['lines'],key=lambda l:(l['candidate'].recipe.tier,l['candidate'].recipe.enchantment,l['focused']))
    for line in lines:
        c=line['candidate'];r=c.recipe
        if c.fame is None:raise ValueError('Неизвестен опыт для '+r.name)
        remaining=line['operations'];gain=c.fame*r.output_count
        while remaining:
            active=[];chunk=remaining
            for key in refining_nodes(game,r):
                current=states.get(key,dict(level=0,xp=0));level=current['level'];costs=game.costs(key)
                if level>=len(costs):continue
                parents=game.nodes[key].get('parentachievements',{})
                prerequisites=[p['@id'] for p in many(parents.get('achievement'))]
                if level==0 and prerequisites:
                    enabled=[p not in game.nodes or states.get(p,{}).get('level',0)>0 for p in prerequisites]
                    if not (all(enabled) if parents.get('@allrequired')=='true' else any(enabled)):continue
                levels=[s.strip().split(';') for s in game.templates[game.nodes[key]['@usetemplate']]['baselevels']['#text'].splitlines() if s.strip()]
                # Mission tier range is part of each level's template row.
                low,high=int(levels[level][2]),int(levels[level][3])
                if low<=r.tier<=high:
                    active.append((key,current,costs))
                    if gain>0:chunk=min(chunk,max(1,math.ceil((D(str(costs[level]))-D(str(current['xp'])))/gain)))
            if line['focused']:total_focus+=focus_per_operation(game,r,states)*chunk
            for key,current,costs in active:
                new,xp=advance(current['level'],current['xp'],float(gain*chunk),costs);states[key]=dict(level=new,xp=xp)
            fame+=gain*chunk;remaining-=chunk
    return dict(states=states,before=before,focus=total_focus,fame=fame)
