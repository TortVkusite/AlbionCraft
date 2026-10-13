"""Small, reproducible farming manifest from bundled game dump."""
import json
import hashlib
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
    elif grown and item.get('@shopsubcategory1') in ('pasture','kennel'):
        food=item['consumption']['food'];accepted=food['acceptedfood']
        food_id=accepted.get('@favorite',{'plants':'T1_CARROT','meat':'T3_MEAT','mount':'T3_FARM_HORSE_GROWN'}.get(accepted.get('@foodcategory')))
        if not food_id:continue
        nutrition=next((float(x['@nutrition']) for group in items.values() for x in (group if isinstance(group,list) else [group]) if isinstance(x,dict) and x.get('@uniquename')==food_id),None)
        if not nutrition:continue
        row=dict(id=uid,product=grown['@uniquename'],kind='wild' if item['@shopsubcategory1']=='kennel' else 'animals',yield_min=1,yield_max=1,
            hours=int(grown['@growtime'])/3600,seed_return=grown['offspring']['@chance'],focus_bonus=item['@activefarmbonus'],
            focus_base=int(item['@activefarmfocuscost']),actions=int(item['@activefarmmaxcycles']),
            food=food_id,food_amount=str(float(food['@nutritionmax'])/nutrition/(2 if accepted.get('@favorite') else 1)),offspring_amount=int(grown['offspring']['@amount']))
    else:continue
    row['tier']=int(item['@tier']);products.append(row)
modifier_path=ROOT/'research/farmingmodifiers.json'
modifiers=json.loads(modifier_path.read_text(encoding='utf-8'))['farmingmodifiers']['location']
cities={'0000':'Thetford','1000':'Lymhurst','2000':'Bridgewatch','3004':'Martlock','4000':'Fort Sterling','3003':'Caerleon','5000':'Brecilien'}
by_id={p['id']:p for p in products};bonuses={}
for location in modifiers:
    city=cities.get(location.get('@clusterid'))
    if not city:continue
    bonuses[city]=[by_id[m['@farmable']]['product'] for m in location['farmingyieldmodifier'] if m['@farmable'] in by_id and float(m['@islandvalue'])==.1]
data=dict(sources=['https://albiononline.com/news/guide-farming','https://github.com/ao-data/ao-bin-dumps/blob/master/farmingmodifiers.json'],products=products,bonuses=bonuses,farming_modifiers_sha256=hashlib.sha256(modifier_path.read_bytes()).hexdigest())
(ROOT/'app/config/island_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(len(products),'products')
