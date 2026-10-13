"""Use explicit game flags, never missing translations, to filter items."""
import re

def available(item):
    uid=item.get('@uniquename','')
    if item.get('@showinmarketplace')=='false':return False
    if 'PROTOTYPE' in uid.split('_'):return False
    # Unlock flags describe Destiny Board requirements, not availability.
    return True

def name_key(item):
    tag=item.get('@namelocatag','')
    return re.sub(r'^@ITEMS_','',tag) if tag.startswith('@ITEMS_') else item.get('@uniquename','')
