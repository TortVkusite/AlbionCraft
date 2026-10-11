"""Complete scan/filter/sort pipeline, independent of Qt widgets."""
from decimal import Decimal
from .scanner import scan
from .trading import trading_scan
from .enchantment import prefer_enchanted
from .result_filters import in_bounds
from .item_names import has_known_price


def calculate_view(data):
    recipes=data['recipes'];settings=data['settings'];activity=data['activity']
    prices=data['prices'];history=data['histories'];quality=data['quality'];age=data['age']
    if activity in ('craft','enchant'):
        cities=data['craft']
        rows=scan(recipes,prices,history,cities,cities,cities,settings,quality,age)
    else:
        buy=data['buy'] if activity=='resale' else data['craft']
        sell=data['sell'] if activity=='resale' else buy
        rows=trading_scan(recipes,prices,history,buy,sell,settings,quality,age,activity)
    upgrades=[]
    if settings.get('prefer_upgrades',True):rows,upgrades=prefer_enchanted(rows,prices,age,quality)
    for row in rows:row.setdefault('quality',quality if isinstance(quality,int) else 1)
    recommendations=rows[:]
    if data['demand']:rows=[r for r in rows if r['demand']['kind']==data['demand']]
    before=len(rows);rows=[r for r in rows if in_bounds(r,settings)];limited=before-len(rows)
    hidden=0
    if data['with_prices']:
        priced=[r for r in rows if has_known_price(r)]
        hidden=len(rows)-len(priced);rows=priced
    sort=data['sort'];group='focus' if sort.startswith('focus_') else 'base';metric='roi' if sort.endswith('roi') else 'profit'
    present=[r for r in rows if r[group] is not None and r[group].get(metric) is not None]
    missing=[r for r in rows if r[group] is None or r[group].get(metric) is None]
    present.sort(key=lambda r:r[group][metric],reverse=data['descending'])
    return dict(rows=present+missing,recommendations=recommendations,upgrades=upgrades,hidden=hidden,limited=limited)
