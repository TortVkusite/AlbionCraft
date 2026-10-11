"""Translate presentation text while retaining stable game IDs and stored values."""
import json
import re
from functools import lru_cache
from .paths import resource_root

LANGUAGES={'ru':'Русский','en':'English'}
_language='ru'

def get_language():
    return _language

def set_language(language):
    global _language
    _language=language if language in LANGUAGES else 'ru'

def game_locale():
    return 'EN-US' if _language=='en' else 'RU-RU'

def default_language():
    from PySide6.QtCore import QLocale
    return 'ru' if QLocale.system().language()==QLocale.Russian else 'en'

@lru_cache(maxsize=1)
def translations():
    return json.loads((resource_root()/'app/config/locales/en.json').read_text(encoding='utf-8'))

@lru_cache(maxsize=1)
def _fragments():
    # Longest phrases win. Boundaries protect unknown names and partial words.
    units={' д ',' ч ',' мин ',' с',' ч',' ч.',' кг',' шт.',' дн.','от','до'}
    keys=[key for key in translations() if (len(key.strip())>2 or key in units) and re.search('[А-Яа-яЁё]',key)]
    def pattern(key):
        return (r'(?<![А-Яа-яЁё])' if re.match('[А-Яа-яЁё]',key) else '')+re.escape(key)+(r'(?![А-Яа-яЁё])' if re.search('[А-Яа-яЁё]$',key) else '')
    return re.compile('|'.join(pattern(key) for key in sorted(keys,key=len,reverse=True)))

def tr(text):
    if not isinstance(text,str):return text
    return _translate(_language,text)

@lru_cache(maxsize=16384)
def _translate(language,text):
    if language=='ru' or not re.search('[А-Яа-яЁё]',text):return text
    mapping=translations()
    if text in mapping:return mapping[text]
    # Old manually entered orders can still contain official Russian item names.
    if text in _item_translations():return _item_translations()[text]
    # Item labels embedded in multiline messages retain their tier/quality suffix.
    text=_item_pattern().sub(lambda match:_item_translations()[match[0]],text)
    return _fragments().sub(lambda match:mapping[match[0]],text)

@lru_cache(maxsize=1)
def _item_translations():
    from .item_names import localized_names
    ru=localized_names('RU-RU');en=localized_names('EN-US')
    return {name:en.get(uid,name) for uid,name in ru.items() if re.search('[А-Яа-яЁё]',name)}

@lru_cache(maxsize=1)
def _item_pattern():
    return re.compile(r'(?<![А-Яа-яЁё])(?:'+'|'.join(re.escape(key) for key in sorted(_item_translations(),key=len,reverse=True))+r')(?![А-Яа-яЁё])')
