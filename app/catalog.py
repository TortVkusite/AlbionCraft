import json
import logging
import re
from decimal import Decimal as D
from pathlib import Path
from .models import Ingredient, Recipe
from .rules import rules
from .i18n import game_locale
from functools import lru_cache
from .catalog_visibility import available,name_key

def many(value):
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []

def load_catalog(root: Path):
    from .paths import catalog_root
    root = catalog_root(root).resolve()
    files=[root/'research/items.json',root/'research/names.json']
    stamps=tuple((p.stat().st_mtime_ns,p.stat().st_size) if p.exists() else None for p in files)
    return list(_load_catalog(root,game_locale(),stamps))

@lru_cache(maxsize=4)
def _load_catalog(root,locale,stamps):
    data = json.loads((root / 'research/items.json').read_text(encoding='utf-8-sig'))['items']
    values={}
    for entries in data.values():
        for entry in many(entries):
            if '@uniquename' in entry and '@itemvalue' in entry:
                uid=entry['@uniquename'];level=entry.get('@enchantmentlevel','0')
                values[uid+('@'+level if level!='0' and '@' not in uid else '')]=D(entry['@itemvalue'])
    names_file = root / 'research/names.json'
    names = {}
    if names_file.exists():
        for entry in json.loads(names_file.read_text(encoding='utf-8-sig')):
            loc = entry.get('LocalizedNames') or {}
            names[entry['UniqueName']] = loc.get(locale) or loc.get('EN-US') or entry['UniqueName']
    recipes = []
    nutrition_by_output={}
    for group in ('weapon', 'equipmentitem', 'transformationweapon', 'simpleitem', 'consumableitem', 'farmableitem'):
        for item in many(data.get(group)):
            first_recipe=len(recipes)
            uid = item.get('@uniquename', '')
            if not available(item) or item.get('@tier') not in tuple(str(n) for n in range(1,9)):
                continue
            if names.get(uid,uid)==uid and name_key(item) in names:names[uid]=names[name_key(item)]
            shop=item.get('@shopcategory','');sub=item.get('@shopsubcategory1','')
            category={'head':'armors','shoes':'armors'}.get(shop,shop)
            if shop=='crafting':category={'resources':'resources','refinedresources':'materials','alchemy':'reagents','fish':'fish','cityresources':'reagents'}.get(sub,'')
            if shop=='consumables':category={'food':'food','potions':'potions'}.get(sub,'')
            if category not in ('weapons','armors','offhands','bags','capes','gathering','resources','materials','reagents','fish','food','potions','farming','artefacts'):
                continue
            level=item.get('@enchantmentlevel','0')
            full_uid=uid+('@'+level if level!='0' and '@' not in uid else '')
            base_uid=re.sub(r'_LEVEL[1-4]$','',uid)
            family=item.get('@shopsubcategory2',sub) if category in ('resources','materials','food','potions','farming','fish','reagents') else sub
            max_quality=int(item.get('@maxqualitylevel','1'))
            market_only=category in ('resources','artefacts','farming') and not (category=='farming' and sub=='farmingproducts' and item.get('craftingrequirements'))
            requirements=None if market_only else item.get('craftingrequirements')
            versions = [(full_uid, requirements)]
            for ench in many((item.get('enchantments') or {}).get('enchantment')):
                level = ench.get('@enchantmentlevel')
                if level in ('1','2','3','4'):
                    versions.append((uid+'@'+level, ench.get('craftingrequirements')))
            for full_id, requirements in versions:
                if not many(requirements):
                    recipes.append(Recipe(full_id,names.get(full_id,names.get(uid,uid)),0,(),category,family,base_uid,int(item['@tier']),
                        int(full_id.split('@')[1]) if '@' in full_id else 0,'Рынок',max_quality=max_quality))
                for variant, req in enumerate(many(requirements)):
                    ingredients = []
                    try:
                        for material in many(req.get('craftresource')):
                            mid = material['@uniquename']
                            level = material.get('@enchantmentlevel', '0')
                            if level != '0' and '@' not in mid:
                                mid += '@' + level
                            count = int(material['@count'])
                            if count <= 0:
                                raise ValueError('invalid quantity')
                            ingredients.append(Ingredient(mid, count, material.get('@maxreturnamount') != '0',material.get('@preservequality')=='true'))
                        if ingredients:
                            nutrition=None
                            if max_quality>1 and all(i.item_id in values for i in ingredients):
                                nutrition=str(sum(values[i.item_id]*i.amount for i in ingredients)*D(rules()['nutrition_factor']))
                            if variant==0:nutrition_by_output[full_id]=nutrition
                            else:nutrition=nutrition_by_output.get(full_id)
                            warnings=tuple('Особый предел возврата '+m['@uniquename'] for m in many(req.get('craftresource')) if m.get('@maxreturnamount') not in (None,'0'))
                            recipes.append(Recipe(full_id, names.get(full_id, names.get(uid, uid)), variant, tuple(ingredients),
                                category,family,base_uid,int(item['@tier']),
                                int(full_id.split('@')[1]) if '@' in full_id else 0,'Прямой крафт',
                                int(req.get('@silver','0')),int(req.get('@amountcrafted','1')),warnings,
                                item.get('@craftingcategory',item.get('@shopsubcategory1','')),nutrition,max_quality))
                    except (KeyError, ValueError, TypeError):
                        logging.exception('Rejected recipe %s variant %s', full_id, variant)
            # Enchant ordinary crafted gear step by step only when every step is in the dump.
            if max_quality==1:continue
            base_recipes=[r for r in recipes[first_recipe:] if r.item_id==uid and r.path=='Прямой крафт']
            upgrades=[]
            for ench in sorted(many((item.get('enchantments') or {}).get('enchantment')),key=lambda e:int(e['@enchantmentlevel'])):
                level=int(ench['@enchantmentlevel'])
                req=ench.get('upgraderequirements')
                if level!=len(upgrades)+1 or not isinstance(req,dict) or not many(req.get('upgraderesource')):
                    break
                upgrades.append(req)
                extra=[]
                for step in upgrades:
                    for mat in many(step.get('upgraderesource')):
                        extra.append(Ingredient(mat['@uniquename'],int(mat['@count']),False))
                for base in base_recipes:
                    from dataclasses import replace
                    full_id=uid+'@'+str(level)
                    recipes.append(replace(base,item_id=full_id,name=names.get(full_id,base.name),enchantment=level,
                        path='Крафт .0 → .'+str(level),ingredients=base.ingredients+tuple(extra),
                        recipe_silver=base.recipe_silver+sum(int(s.get('@silver','0')) for s in upgrades)))
    return tuple(recipes)
