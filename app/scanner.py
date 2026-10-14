from decimal import Decimal as D, InvalidOperation
from .models import quote
from .calculator import calculate, classify, demand
from .rules import effective_settings,automatic_profile
from .item_names import item_name

def number(value, percent=False):
    if value is None or str(value).strip()=='': return None
    try:
        n=D(str(value).replace(',','.'))
        if not n.is_finite() or n<0: return None
        return n/100 if percent else n
    except InvalidOperation: return None

def scan(recipes, prices, histories, buy_cities, craft_cities, sell_cities, settings, quality, age_limit):
    if quality=='any':
        from .quality import choose_quality
        return choose_quality(scan(recipes,prices,histories,buy_cities,craft_cities,sell_cities,settings,None,age_limit),settings.get('activity','craft'))
    if quality is None:
        from .quality import remove_overpriced_masterpieces
        mask=settings.get('quality_mask',range(1,6))
        rows=[dict(row,quality=q) for q in mask for row in scan(recipes,prices,histories,buy_cities,craft_cities,sell_cities,settings,q,age_limit)]
        if 1 not in mask:rows.extend(dict(row,quality=1) for row in scan([r for r in recipes if r.max_quality==1],prices,histories,buy_cities,craft_cities,sell_cities,settings,1,age_limit))
        return remove_overpriced_masterpieces(rows,prices,age_limit)
    settings=effective_settings(settings)
    index={(p.get('item_id'),p.get('city'),p.get('quality')):p for p in prices if isinstance(p,dict)}
    hist={(h.get('item_id'),h.get('location'),h.get('quality')):h for h in histories if isinstance(h,dict)}
    results=[]
    mode=settings.get('sale_mode','order')
    side='buy_price_max' if mode=='instant' else 'sell_price_min'
    setup=D(0) if mode=='instant' else number(settings.get('setup'),True)
    tax=number(settings.get('tax'),True)
    other=number(settings.get('other'))
    for recipe in recipes:
        if quality>recipe.max_quality or not recipe.ingredients:continue
        activity=settings.get('activity','craft')
        for buy_city in buy_cities:
            parts=[]; raw=D(0); fixed=D(recipe.recipe_silver)
            issues=list(recipe.warnings); missing=[]
            if activity=='craft' and recipe.max_quality>1:
                issues.append(f'Качество {quality}: сохраняется от исходного предмета' if any(i.preserve_quality for i in recipe.ingredients) else f'Качество {quality}: сценарий продажи; получение такого качества при крафте не гарантировано')
            for i in recipe.ingredients:
                q=quality if i.preserve_quality or (activity=='enchant' and i.item_id==recipe.base_id) else 1
                p=index.get((i.item_id,buy_city,q),{})
                value,age,status=quote(p,'sell_price_min',age_limit)
                source=p.get('sell_price_min_source',settings.get('region_label','Europe')+' API')
                if source.startswith('Из твоей игры'):issues.append(item_name(i.item_id)+': '+source+'; просмотренные ордера не гарантируют полный рынок')
                parts.append(dict(ingredient=i,quality=q,price=value,age=age,status=status,date=p.get('sell_price_min_date'),source=source,nats=p.get('nats_observations'),local=p.get('local_observations')))
                if source.startswith('AODP NATS'):issues.append(item_name(i.item_id)+': наблюдавшийся ордер NATS; полнота рынка не гарантирована')
                if source=='Последняя сохранённая котировка':issues.append(item_name(i.item_id)+': последняя сохранённая котировка')
                if value is None or 'будущем' in status:
                    missing.append(item_name(i.item_id))
                else:
                    cost=D(value)*i.amount
                    if i.returnable: raw+=cost
                    else: fixed+=cost
                if status!='свежее': issues.append(item_name(i.item_id)+': '+status)
            for craft_city in craft_cities:
                if settings.get('same_city') and buy_city!=craft_city:continue
                profile_key=recipe.item_id+'|'+recipe.path+'|'+str(recipe.variant)
                general=settings.get('general',{}).get(craft_city,{})
                specific=settings.get('profiles',{}).get(profile_key,settings.get('cities',{})).get(craft_city,{})
                automatic=automatic_profile(recipe,craft_city,settings) if settings.get('auto_rules') else {}
                profile={**automatic,**{k:v for k,v in general.items() if str(v).strip()},**{k:v for k,v in specific.items() if str(v).strip()}}
                plain=number(profile.get('rrr'),True)
                focused=number(profile.get('focus_rrr'),True)
                station=number(profile.get('station'))
                if activity=='enchant':plain=D(0);focused=D(0);station=D(0)
                for sell_city in sell_cities:
                    if settings.get('same_city') and sell_city!=buy_city:continue
                    p=index.get((recipe.item_id,sell_city,quality),{})
                    value,sale_age,status=quote(p,side,age_limit)
                    row_issues=list(issues)
                    if general and not specific:row_issues.append('Общий профиль RRR / станции: проверьте соответствие рецепту')
                    sale_source=p.get(side+'_source',settings.get('region_label','Europe')+' API')
                    if sale_source.startswith('Из твоей игры'):row_issues.append('Продажа: '+sale_source+'; доступность ордера требует проверки')
                    if sale_source.startswith('AODP NATS'):row_issues.append('Продажа: наблюдавшийся ордер NATS; полнота рынка не гарантирована')
                    if sale_source=='Последняя сохранённая котировка':row_issues.append('Продажа: последняя сохранённая котировка')
                    if status!='свежее': row_issues.append('Продажа: '+status)
                    hist_data=hist.get((recipe.item_id,sell_city,quality),[])
                    demand_info=demand(hist_data)
                    if demand_info['kind']=='unknown': row_issues.append('Нет истории продаж')
                    base=None; focus=None
                    pending=[]
                    if automatic:row_issues.append('Городские бонусы из игровой выгрузки; дневной бонус не включён')
                    if automatic and recipe.nutrition is None:row_issues.append('Расход питания станции для этого рецепта не подтверждён; задайте стоимость станции в ручном профиле рецепта')
                    if settings.get('auto_rules'):row_issues.append('Рыночные комиссии: справочный профиль; проверьте в игре')
                    reasons=[]
                    if missing: reasons.append('Нет цен: '+', '.join(missing))
                    if value is None or 'будущем' in status: reasons.append('Нет допустимой цены продажи')
                    if recipe.output_count<1: reasons.append('Некорректный выход рецепта')
                    if recipe.warnings: reasons.extend(recipe.warnings)
                    if not reasons:
                        for rrr,which in [(plain,'base'),(focused,'focus')]:
                            cost_station=station;cost_other=other
                            if settings.get('auto_rules'):
                                if cost_station is None:
                                    cost_station=D(0)
                                    if 'станция' not in pending:pending.append('станция')
                                if cost_other is None:
                                    cost_other=D(0)
                                    if 'прочие расходы' not in pending:pending.append('прочие расходы')
                            if any(v is None for v in (rrr,cost_station,setup,tax,cost_other)):
                                reasons.append('Заполните RRR / станцию / комиссии ('+which+')')
                                continue
                            try:
                                result=calculate(raw/recipe.output_count,fixed/recipe.output_count+cost_other,D(value),rrr,cost_station/recipe.output_count,setup,tax)
                                if which=='base': base=result
                                else: focus=result
                            except ValueError as exc: reasons.append(str(exc))
                    if base and focus:
                        if focused<plain: row_issues.append('RRR с Focus ниже RRR без Focus')
                    average=demand_info['average']
                    if value and average and D(value)>D(str(average))*D('2'):
                        row_issues.append('Цена выше исторической средней более чем в 2 раза')
                    ages=[a['age'] for a in parts if a['age'] is not None]
                    if sale_age is not None: ages.append(sale_age)
                    color=classify(base['roi'] if base else None,focus['roi'] if focus else None)
                    if pending:
                        row_issues.append('Верхняя граница прибыли: не вычтены '+', '.join(pending))
                        if color!='red':color='unknown'
                    if activity=='enchant':focus=None
                    results.append(dict(recipe=recipe,buy=buy_city,craft=craft_city,sell=sell_city,
                        parts=parts,sale=value,sale_date=p.get(side+'_date'),sale_side=side,sale_status=status,
                        base=base,focus=focus,color=color,demand=demand_info,issues=row_issues,reasons=reasons,
                        age=max(ages) if ages else None,profile=profile,sale_source=sale_source,activity=activity,sale_nats=p.get('nats_observations'),
                        pending_costs=pending,purchase_cost=(raw+fixed)/recipe.output_count,purchase_complete=not missing,sale_local=p.get('local_observations'),
                        max_station_fee=base['profit']+base['station'] if base else None,
                        max_station_rate=(base['profit']+base['station'])*recipe.output_count*100/D(recipe.nutrition) if base and recipe.nutrition and D(recipe.nutrition)>0 else None,
                        gross_margin=D(value)-(raw+fixed)/recipe.output_count if value is not None and not missing else None))
    if quality==5:
        from .quality import remove_overpriced_masterpieces
        return remove_overpriced_masterpieces([dict(row,quality=5) for row in results],prices,age_limit)
    return results
