def remove_overpriced_masterpieces(rows,prices,age_limit):
    from .models import quote
    index={}
    for p in prices:
        uid=p.get('item_id','');base=uid.split('@')[0]
        try:level=int(uid.split('@')[1]) if '@' in uid else 0
        except ValueError:continue
        index.setdefault((base,p.get('city')),[]).append((level,p))
    result=[]
    for row in rows:
        if row.get('quality')==5 and row['sale'] is not None:
            r=row['recipe'];base=r.item_id.split('@')[0]
            cheaper=False
            for level,p in index.get((base,row['sell']),[]):
                if level<=r.enchantment:continue
                price,_,status=quote(p,row['sale_side'],age_limit)
                if price is not None and 'будущем' not in status and price<row['sale']:
                    cheaper=True;break
            if cheaper:continue
        result.append(row)
    return result

def choose_quality(rows,activity):
    """One observed quality per route; never combine buy and sell qualities."""
    groups={}
    for row in rows:
        r=row['recipe'];key=(r.item_id,r.path,r.variant,row['buy'],row['craft'],row['sell'])
        groups.setdefault(key,[]).append(row)
    result=[]
    for candidates in groups.values():
        preserves=any(i.preserve_quality for i in candidates[0]['recipe'].ingredients)
        ordinary_craft=activity=='craft' and not preserves
        if ordinary_craft:
            priced=[r for r in candidates if r['sale'] is not None and 'будущем' not in r['sale_status']]
            selected=min(priced,key=lambda r:(r['sale'],r['quality'])) if priced else candidates[0]
        else:
            priced=[r for r in candidates if r.get('purchase_complete') and r.get('purchase_cost') is not None
                and not any('будущем' in p['status'] for p in r['parts'])]
            if preserves:
                complete=[r for r in priced if r['sale'] is not None and 'будущем' not in r['sale_status']]
                if complete:priced=complete
            observed=[r for r in candidates if r['sale'] is not None and 'будущем' not in r['sale_status']]
            selected=min(priced,key=lambda r:(r['purchase_cost'],r['quality'])) if priced else min(observed,key=lambda r:(r['sale'],r['quality'])) if observed else candidates[0]
        selected['issues'].append('Качество неважно: самое дешёвое доступное '+('предложение продажи результата' if ordinary_craft else 'при покупке')+'; продажа того же качества')
        result.append(selected)
    return result
