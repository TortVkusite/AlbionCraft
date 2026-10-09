"""Game localization for components as well as catalog results."""
import json
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def names():
    path=Path(__file__).resolve().parents[1]/'research/names.json'
    try:
        entries=json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):
        return {}
    return {e['UniqueName']:(e.get('LocalizedNames') or {}).get('RU-RU')
        or (e.get('LocalizedNames') or {}).get('EN-US') or e['UniqueName'] for e in entries}


def item_name(uid,with_level=True):
    base=uid.split('@')[0]
    label=names().get(uid,names().get(base,uid))
    tier=re.match(r'T([1-8])_',uid)
    if with_level and tier and label!=uid:
        level=uid.split('@')[1] if '@' in uid else '0'
        label+=f' • T{tier[1]}.{level}'
    return label


def recipe_variant(recipe):
    special=[i for i in recipe.ingredients if not i.returnable and not i.item_id.endswith(('_RUNE','_SOUL','_RELIC'))]
    return (f'{item_name(special[0].item_id,False)} ×{special[0].amount}' if special else f'Рецепт {recipe.variant+1}')


def has_known_price(row):
    return row.get('sale') is not None or any(p.get('price') is not None for p in row['parts'])
