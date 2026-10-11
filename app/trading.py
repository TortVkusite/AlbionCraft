from dataclasses import replace
from decimal import Decimal as D
from .models import Ingredient,quote
from .calculator import calculate,classify,demand
from .scanner import number
from .rules import effective_settings

# Royal ring; Caerleon is a separate opt-in destination.
NEIGHBORS={'Thetford':{'Fort Sterling','Martlock'},'Fort Sterling':{'Thetford','Lymhurst'},
    'Lymhurst':{'Fort Sterling','Bridgewatch'},'Bridgewatch':{'Lymhurst','Martlock'},'Martlock':{'Bridgewatch','Thetford'}}

def allowed_route(buy,sell,caerleon=False,brecilien=False):
    if buy==sell:return False
    if 'Brecilien' in (buy,sell):return brecilien
    if 'Caerleon' in (buy,sell):return caerleon
    return sell in NEIGHBORS.get(buy,set())

def enchant_recipes(recipes):
    result={}
    for r in recipes:
        if r.path=='Прямой крафт':continue
        reagents=tuple(i for i in r.ingredients if i.item_id.endswith(('_RUNE','_SOUL','_RELIC')))
        if not reagents:continue
        for start in range(r.enchantment):
            source=r.base_id+('@'+str(start) if start else '')
            remaining=reagents[start:]
            result.setdefault((r.item_id,start),replace(r,path=f'Зачарование .{start} → .{r.enchantment}',variant=start,base_id=source,
                ingredients=(Ingredient(source,1,False),)+remaining,recipe_silver=0,warnings=()))
    return list(result.values())

def trade_calculation(buy,sale,setup,tax,other,buy_order,sale_order=True):
    buy_fee=buy*setup if buy_order else D(0)
    x=calculate(D(0),buy+buy_fee+other,sale,D(0),D(0),setup if sale_order else D(0),tax)
    x.update(buy_price=buy,buy_setup_fee=buy_fee,other=other)
    return x

def trading_scan(recipes,prices,histories,buy_cities,sell_cities,settings,quality,age_limit,activity):
    if quality=='any':
        from .quality import choose_quality
        return choose_quality(trading_scan(recipes,prices,histories,buy_cities,sell_cities,settings,None,age_limit,activity),activity)
    if quality is None:
        mask=settings.get('quality_mask',range(1,6))
        rows=[dict(row,quality=q) for q in mask for row in trading_scan(recipes,prices,histories,buy_cities,sell_cities,settings,q,age_limit,activity)]
        if 1 not in mask:rows.extend(dict(row,quality=1) for row in trading_scan([r for r in recipes if r.max_quality==1],prices,histories,buy_cities,sell_cities,settings,1,age_limit,activity))
        return rows
    settings=effective_settings(settings)
    index={(p.get('item_id'),p.get('city'),p.get('quality')):p for p in prices if isinstance(p,dict)}
    hist={(h.get('item_id'),h.get('location'),h.get('quality')):h.get('data',[]) for h in histories if isinstance(h,dict)}
    unique={r.item_id:r for r in recipes};result=[]
    setup=number(settings.get('setup'),True);tax=number(settings.get('tax'),True);other=number(settings.get('other'))
    pending=['прочие расходы'] if other is None and settings.get('auto_rules') else []
    if pending:other=D(0)
    sell_side='sell_price_min' if activity=='flip' or settings.get('sale_mode','order')=='order' else 'buy_price_max'
    buy_side='buy_price_max' if activity=='flip' else 'sell_price_min'
    for r in unique.values():
        if quality>r.max_quality:continue
        for buy_city in buy_cities:
            for sell_city in sell_cities:
                if activity=='flip' and buy_city!=sell_city:continue
                if activity=='resale' and buy_city==sell_city:continue
                if activity=='resale' and settings.get('nearby_only',False) and not allowed_route(buy_city,sell_city,settings.get('include_caerleon',False),settings.get('include_brecilien',False)):continue
                bp=index.get((r.item_id,buy_city,quality),{});sp=index.get((r.item_id,sell_city,quality),{})
                bv,ba,bs=quote(bp,buy_side,age_limit);sv,sa,ss=quote(sp,sell_side,age_limit)
                reasons=[];issues=[];x=None
                if bv is None or sv is None:reasons.append('Нет цены покупки / продажи')
                if 'будущем' in bs+ss:reasons.append('Timestamp в будущем')
                if any(v is None for v in (setup,tax,other)):reasons.append('Задайте комиссии и прочие расходы в общем профиле')
                if bs!='свежее':issues.append('Покупка: '+bs)
                if ss!='свежее':issues.append('Продажа: '+ss)
                if pending:issues.append('Верхняя граница прибыли: прочие расходы не вычтены')
                if settings.get('auto_rules'):issues.append('Рыночные комиссии: справочный профиль; проверьте в игре')
                if not reasons:
                    try:x=trade_calculation(D(bv),D(sv),setup,tax,other,activity=='flip',sell_side=='sell_price_min')
                    except ValueError as exc:reasons.append(str(exc))
                if activity=='flip':issues.append('Ориентир buy/sell orders: объём и срок исполнения не известны; два размещения')
                if activity=='resale':issues.append('Расходы транспорта включены только в указанные прочие расходы')
                d=demand(hist.get((r.item_id,sell_city,quality),[]))
                if d['kind']=='unknown':issues.append('Нет истории за 7 дней')
                part=dict(ingredient=Ingredient(r.item_id,1,False),price=bv,age=ba,status=bs,date=bp.get(buy_side+'_date'),source=bp.get(buy_side+'_source',settings.get('region_label','Europe')+' API'),side=buy_side,nats=bp.get('nats_observations'),local=bp.get('local_observations'))
                if part['source'].startswith('Из твоей игры') or sp.get(sell_side+'_source','').startswith('Из твоей игры'):issues.append('Получено из твоей игры: только просмотренные ордера; исполнение и полнота рынка не гарантированы')
                if part['source'].startswith('AODP NATS') or sp.get(sell_side+'_source','').startswith('AODP NATS'):issues.append('Наблюдавшиеся ордера NATS; полнота рынка не гарантирована')
                result.append(dict(recipe=r,buy=buy_city,craft='—',sell=sell_city,parts=[part],sale=sv,sale_date=sp.get(sell_side+'_date'),sale_side=sell_side,sale_status=ss,
                    sale_source=sp.get(sell_side+'_source',settings.get('region_label','Europe')+' API'),sale_nats=sp.get('nats_observations'),base=x,focus=None,color=classify(x['roi'],x['roi']) if x else 'unknown',
                    demand=d,issues=issues,reasons=reasons,profile={},age=max(v for v in (ba,sa) if v is not None) if ba is not None or sa is not None else None,
                    activity=activity,gross_margin=D(sv-bv) if sv is not None and bv is not None else None,
                    pending_costs=pending,purchase_cost=D(bv) if bv is not None else None,purchase_complete=bv is not None,sale_local=sp.get('local_observations')))
                if pending and result[-1]['color']!='red':result[-1]['color']='unknown'
    if quality==5:
        from .quality import remove_overpriced_masterpieces
        return remove_overpriced_masterpieces([dict(row,quality=5) for row in result],prices,age_limit)
    return result
