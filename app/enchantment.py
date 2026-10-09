"""Exact per-item upgrade quantities and fees from the game's public dump."""
import json
from functools import lru_cache
from pathlib import Path
from .models import Ingredient


@lru_cache(maxsize=1)
def upgrade_paths():
    from .catalog import many
    root=Path(__file__).resolve().parents[1]
    items=json.loads((root/'research/items.json').read_text(encoding='utf-8-sig'))['items']
    paths={}
    for group in ('weapon','equipmentitem','transformationweapon'):
        for item in many(items.get(group)):
            uid=item.get('@uniquename','')
            steps={}
            for ench in many((item.get('enchantments') or {}).get('enchantment')):
                req=ench.get('upgraderequirements') or {}
                resources=many(req.get('upgraderesource'))
                if not resources:continue
                level=int(ench['@enchantmentlevel'])
                materials=tuple(Ingredient(m['@uniquename'],int(m['@count']),False) for m in resources)
                if any(i.amount<=0 for i in materials):continue
                steps[level]=(materials,int(req.get('@silver','0')))
            for start in range(4):
                materials=[];silver=0
                for end in range(start+1,5):
                    if end not in steps:break
                    resources,fee=steps[end];materials.extend(resources);silver+=fee
                    paths[(uid,start,end)]=(tuple(materials),silver)
    return paths


def comparison_price_ids(recipes,catalog):
    targets={}
    for r in recipes:
        if r.max_quality>1:
            base=r.item_id.split('@')[0]
            targets[base]=min(targets.get(base,r.enchantment),r.enchantment)
    paths=upgrade_paths();ids=set()
    for r in catalog:
        base=r.item_id.split('@')[0]
        if base not in targets or r.enchantment<=targets[base]:continue
        ids.add(r.item_id)
        for start in range(targets[base],r.enchantment):
            path=paths.get((base,start,r.enchantment))
            if path:ids.update(i.item_id for i in path[0])
    return ids


def prefer_enchanted(rows,prices,age_limit,quality=1):
    """Hide only when fresh same-city offers establish a cheaper upgrade alternative.

    Equal or better quality; .4 is compared only if an actual upgrade path exists,
    except that an outright cheaper higher-enchantment offer needs no reagents.
    """
    from decimal import Decimal
    from .models import quote
    from .item_names import item_name
    index={(p.get('item_id'),p.get('city'),p.get('quality')):p for p in prices}
    paths=upgrade_paths();kept=[];hidden=[]
    limit=30 if age_limit is None else age_limit
    for row in rows:
        r=row['recipe'];base=r.item_id.split('@')[0];q=row.get('quality',quality)
        if not isinstance(q,int):q=1
        offer=index.get((r.item_id,row['sell'],q),{})
        current,age,status=quote(offer,'sell_price_min',limit)
        if (r.max_quality<=1 or row['sale_side']!='sell_price_min' or current is None
                or age is None or age>limit or 'будущем' in status):
            kept.append(row);continue
        alternatives=[];missing=set()
        for end in range(r.enchantment+1,5):
            uid=base+'@'+str(end)
            for better_q in range(q,r.max_quality+1):
                candidate=index.get((uid,row['sell'],better_q),{})
                price,candidate_age,candidate_status=quote(candidate,'sell_price_min',limit)
                if price is None or candidate_age is None or candidate_age>limit or 'будущем' in candidate_status:continue
                cost=None
                if price>current:
                    path=paths.get((base,r.enchantment,end))
                    if path is None:continue
                    materials,fee=path;cost=Decimal(fee);complete=True
                    for i in materials:
                        unit,unit_age,unit_status=quote(index.get((i.item_id,row['sell'],1),{}),'sell_price_min',limit)
                        if unit is None or unit_age is None or unit_age>limit or 'будущем' in unit_status:
                            missing.add(item_name(i.item_id));complete=False
                        else:cost+=Decimal(unit)*i.amount
                    if not complete:continue
                if price<=current or Decimal(price)<=Decimal(current)+cost:
                    alternatives.append(dict(item_id=uid,quality=better_q,price=price,upgrade_cost=cost))
        if alternatives:
            alternative=min(alternatives,key=lambda a:(a['price'],-a['quality']))
            hidden.append(dict(row=row,alternative=alternative))
        else:
            if missing:row['issues'].append('Сравнение чар не завершено: нет свежих цен '+', '.join(sorted(missing)))
            kept.append(row)
    return kept,hidden
