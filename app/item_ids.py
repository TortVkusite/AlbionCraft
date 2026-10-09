"""Normalize client material IDs to the game's market IDs without mixing enchants."""
import re
from functools import lru_cache


@lru_cache(maxsize=1)
def material_ids():
    from .item_names import names
    aliases={}
    for uid in names():
        match=re.fullmatch(r'(.+)_LEVEL([1-4])@([1-4])',uid)
        if match and match[2]==match[3]:
            base,level=match[1],int(match[2])
            aliases[(base,level)]=uid
            aliases[(base+'_LEVEL'+str(level),level)]=uid
    return aliases


def market_item_id(uid,enchantment=0):
    base,separator,suffix=uid.partition('@')
    level=int(suffix) if separator and suffix.isdigit() else int(enchantment)
    encoded=re.search(r'_LEVEL([1-4])$',base)
    if not separator and encoded:level=int(encoded[1])
    canonical=material_ids().get((base,level))
    return canonical or base+('@'+str(level) if level else '')
