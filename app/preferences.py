import json
import re


def save_settings(path,settings):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def exclusion_key(recipe):
    base=re.sub(r'_LEVEL[1-4]$','',recipe.item_id.split('@')[0])
    return re.sub(r'^T[1-8]_','',base)


def is_excluded(recipe,settings):
    return exclusion_key(recipe) in set(settings.get('excluded_items',[]))
