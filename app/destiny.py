"""Compact, navigable branches backed by achievement nodes, never by item tiers."""
import re
from dataclasses import dataclass
from .item_names import item_name

RESOURCE={'FIBER':'Волокно / ткань','HIDE':'Шкуры / кожа','ORE':'Руда / слитки','ROCK':'Камень','WOOD':'Древесина','FISH':'Рыболовство'}
SPECIAL={'FARM_ALCHEMIST':'Алхимия','FARM_COOK':'Кулинария','FARM_ANIMALS':'Животные','FARM_CROPS':'Овощи','FARM_HERBS':'Травы'}
GROUP_COLORS={'WARRIOR':'#cf7770','HUNTER':'#7dbb80','MAGE':'#7ca6dc'}
MODES={'CRAFT':'Крафт','COMBAT':'Ношение / бой','REFINE':'Переработка','GATHER':'Сбор','FARM':'Фермерство'}

@dataclass
class Branch:
    key:str
    label:str
    mode:str
    category:str
    nodes:list
    root:str|None
    icon:str
    group:str=""

def node_name(game,key):
    node=game.nodes[key];uid=node.get('@itemforsprite','')
    label=item_name(uid,False).split(' (')[0] if uid else key
    tier=re.search(r'_T([4-8])$',key)
    return f'{label} • T{tier[1]}' if tier else label

def build_branches(game,recipes):
    from .main import FAMILIES
    meta={r.item_id.split('@')[0]:r for r in sorted(recipes,key=lambda r:r.enchantment,reverse=True)}
    roots={key for key,n in game.nodes.items() if n['@usetemplate'].endswith('_BASE') or n['@usetemplate'] in ('CRAFT_OFF','COMBAT_OFF','GATHER_FISH')}
    ordered=sorted(roots,key=len,reverse=True);groups={}
    for key,node in game.nodes.items():
        t=node['@usetemplate']
        if t.startswith('REFINE'):mode='REFINE';group=re.sub(r'_T[4-8]$','',key)
        elif key.startswith('GATHER_'):mode='GATHER';group=re.sub(r'_T[4-8]$','',key);group='GATHER_FISH' if 'FISH' in group else group
        elif key.startswith('TRACKING_'):mode='GATHER';group=next((root for root in ordered if key==root or key.startswith(root+'_')),key)
        else:
            mode='CRAFT' if key.startswith('CRAFT_') or key in ('FARM_COOK','FARM_ALCHEMIST') or key.startswith(('FARM_COOK_','FARM_ALCHEMIST_')) else 'COMBAT' if key.startswith('COMBAT_') else 'FARM'
            group=next((root for root in ordered if key==root or key.startswith(root+'_')),key)
        groups.setdefault((mode,group),[]).append(key)
    result=[]
    for (mode,key),nodes in groups.items():
        root=key if key in game.nodes and key in roots else None
        representative=root or nodes[0];uid=game.nodes[representative].get('@itemforsprite','');recipe=meta.get(uid)
        if mode in ('REFINE','GATHER'):
            label=next((title for code,title in RESOURCE.items() if code in key),node_name(game,representative));category=MODES[mode]
        elif key in SPECIAL:label=SPECIAL[key];category='Еда / зелья' if mode=='CRAFT' else 'Фермерство'
        else:
            label=FAMILIES.get(recipe.family,node_name(game,representative)) if recipe else node_name(game,representative)
            category={'weapons':'Оружие','armors':'Броня','offhands':'Левая рука','bags':'Сумки / плащи','capes':'Сумки / плащи','gathering':'Собиратель'}.get(recipe.category if recipe else '', 'Другие ветки')
        nodes.sort(key=lambda n:(n!=root,node_name(game,n)))
        tag=game.nodes[representative].get('@subcategorylocatag','')
        group=next((g for g in GROUP_COLORS if tag.endswith('_'+g)), '')
        result.append(Branch(key,label,mode,category,nodes,root,uid,group))
    return sorted(result,key=lambda b:(b.mode,b.category,list(GROUP_COLORS).index(b.group) if b.group else 3,b.label))
