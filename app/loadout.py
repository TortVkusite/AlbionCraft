"""Compare real variants of the same equipment, with a minimum reference IP."""
import re
from fnmatch import fnmatchcase
from .catalog import many
from .models import quote

SLOTS={'weapon_id':('Оружие',('mainhand','2h')), 'offhand_id':('Левая рука',('offhand',)),
       'helmet_id':('Шлем',('head',)), 'chest_id':('Броня',('armor',)),
       'boots_id':('Обувь',('shoes',)), 'bag_id':('Сумка',('bag',)), 'cape_id':('Плащ',('cape',))}

def family(uid):return re.sub(r'^T[1-8]_','',uid.split('@')[0])

def equipment(game,uid):
    base,_,level=uid.partition('@');item=game.items.get(base)
    if not item:return None
    if not level:return item
    enchanted=next((e for e in many((item.get('enchantments') or {}).get('enchantment')) if e.get('@enchantmentlevel')==level),None)
    return dict(item,**enchanted) if enchanted else None

def variants(game,uid):
    result=[]
    for tier in range(4,9):
        base=f'T{tier}_'+family(uid)
        if base not in game.items:continue
        result.append(base)
        result.extend(base+'@'+e['@enchantmentlevel'] for e in many((game.items[base].get('enchantments') or {}).get('enchantment')))
    return result

def bonus_per_level(game,node,uid):
    base=uid.split('@')[0];tier=int(base[1]);value=0
    for bonus in many((game.nodes[node].get('baserewards') or {}).get('bonus')):
        if bonus.get('@type')!='itemwearbonus' or bonus.get('@attribute')!='itempower':continue
        if not int(bonus.get('@mintier',0))<=tier<=int(bonus.get('@maxtier',99)):continue
        if any(fnmatchcase(base,p['@pattern']) for p in many(bonus.get('itempattern'))):value+=float(bonus['@bonus'])
    return value

def item_power(game,uid,quality=1,states=None):
    item=equipment(game,uid)
    if item is None or '@itempower' not in item:raise ValueError('Неизвестная сила предмета: '+uid)
    qualities={1:0,**{int(q['@level']):float(q['@itempowerbonus']) for q in many(game.game['Items']['QualityLevels']['qualitylevel'])}}
    if quality not in qualities:raise ValueError('Неизвестное качество')
    bonus=sum(bonus_per_level(game,k,uid)*v['level'] for k,v in (states or {}).items() if k in game.nodes)
    return float(item['@itempower'])+qualities[quality]+bonus*(1+float(item.get('@masterymodifier',0)))

def cheapest(game,uid,prices,city,states=None,quality=1,max_age=30,include_pristine=False):
    target=item_power(game,uid,quality or 1,states);available=variants(game,uid);index={(p['item_id'],p['city'],p['quality']):p for p in prices}
    choices=[];missing=[]
    for candidate in available:
        if candidate.endswith('@4') and not include_pristine:continue
        for q in (range(1,6) if quality is None else [quality]):
            power=item_power(game,candidate,q,states)
            if power+1e-7<target:continue
            p=index.get((candidate,city,q),{});price,age,status=quote(p,'sell_price_min',max_age)
            if price is None or 'будущем' in status or (max_age is not None and age>max_age):missing.append((candidate,q));continue
            choices.append(dict(item_id=candidate,quality=q,power=power,price=price,age=age,status=status,date=p.get('sell_price_min_date'),source=p.get('sell_price_min_source','Рынок')))
    choices.sort(key=lambda p:(p['price'],-p['power'],p['item_id'],p['quality']))
    return dict(target=target,choices=choices,missing=missing,best=choices[0] if choices else None)
