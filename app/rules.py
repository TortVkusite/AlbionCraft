import json
from functools import lru_cache
from pathlib import Path
from decimal import Decimal as D

@lru_cache(maxsize=1)
def rules():
    return json.loads((Path(__file__).resolve().parents[1]/'app/config/game_rules.json').read_text(encoding='utf-8'))

def effective_settings(settings):
    result=dict(settings)
    if not settings.get('auto_rules'):return result
    table=rules()['market']
    if not str(result.get('setup','')).strip():result['setup']=table['setup_percent']
    if not str(result.get('tax','')).strip():result['tax']=table['premium_tax_percent'] if settings.get('premium') else table['normal_tax_percent']
    return result

def automatic_profile(recipe,city,settings):
    table=rules();location=table['cities'].get(city)
    if location is None:return {}
    bonus=D(location['base'])+D(location['bonuses'].get(recipe.crafting_category, '0'))
    from datetime import datetime,timezone
    active=settings.get('production_bonuses',{}).get(recipe.crafting_category)
    if active and datetime.fromisoformat(active['starts'])<=datetime.now(timezone.utc)<datetime.fromisoformat(active['ends']):bonus+=D(str(active['percent']))/100
    focus=D(table['focus_bonus'])
    rate=settings.get('station_rates',{}).get(city)
    result=dict(rrr=str(bonus/(1+bonus)*100),focus_rrr=str((bonus+focus)/(1+bonus+focus)*100),production_bonus=str(bonus*100))
    if rate is not None and str(rate).strip() and recipe.nutrition is not None:
        result['station']=str(D(str(rate))*D(recipe.nutrition)/100)
    return result
