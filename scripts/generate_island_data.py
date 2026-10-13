"""Small, reproducible farming manifest from bundled game dump."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
items=json.loads((ROOT/'research/items.json').read_text(encoding='utf-8-sig'))['items']
loot={r['@name']:r for r in json.loads((ROOT/'research/loot.json').read_text(encoding='utf-8-sig'))['LootDefinition']['Lootlist']}
products=[]
for item in items['farmableitem']:
    uid=item['@uniquename'];harvest=item.get('harvest',{});grown=item.get('grownitem',{})
    if item.get('@kind')=='plant' and harvest:
        drops=loot[harvest['@lootlist']]['Item'];drops=drops if isinstance(drops,list) else [drops]
        crop=next(d for d in drops if d['@type']!='T1_WORM');low,high=map(int,crop['@amount'].split('-'))
        row=dict(id=uid,product=crop['@type'],kind='herbs' if item['@shopsubcategory1']=='herbgarden' else 'crops',
            yield_min=low,yield_max=high,hours=int(harvest['@growtime'])/3600,seed_return=harvest['seed']['@chance'],
            focus_bonus=item['@activefarmbonus'],focus_base=int(item['@activefarmfocuscost']),actions=1)
    elif grown and item.get('@shopsubcategory1')=='pasture':
        food=item['consumption']['food'];accepted=food['acceptedfood']
        if accepted.get('@foodcategory')!='plants':continue
        row=dict(id=uid,product=grown['@uniquename'],kind='animals',yield_min=1,yield_max=1,
            hours=int(grown['@growtime'])/3600,seed_return=grown['offspring']['@chance'],focus_bonus=item['@activefarmbonus'],
            focus_base=int(item['@activefarmfocuscost']),actions=int(item['@activefarmmaxcycles']),
            food=accepted.get('@favorite','T1_CARROT'),food_amount=str(float(food['@nutritionmax'])/48/(2 if accepted.get('@favorite') else 1)))
    else:continue
    row['tier']=int(item['@tier']);products.append(row)
bonuses={'Fort Sterling':['T4_TURNIP','T8_YARROW'],'Thetford':['T5_CABBAGE','T7_MULLEIN'],
    'Martlock':['T6_POTATO','T6_FOXGLOVE'],'Bridgewatch':['T7_CORN','T5_TEASEL'],
    'Lymhurst':['T8_PUMPKIN','T4_BURDOCK'],'Caerleon':['T3_WHEAT','T2_AGARIC']}
data=dict(sources=['https://albiononline.com/news/guide-farming','https://github.com/ao-data/ao-bin-dumps'],products=products,bonuses=bonuses)
(ROOT/'app/config/island_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(len(products),'products')
