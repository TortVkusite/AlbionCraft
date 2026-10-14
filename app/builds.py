"""Public build metadata and market evaluation; site votes are not sale counts."""
import json,re,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from .models import quote
from .calculator import demand
from .item_names import item_name

SOURCE='Albion Online Grind'
ACTIVITIES={'ALL':'Все активности','CORRUPTED_DUNGEON':'Коррапты','MISTS_SOLO':'Мисты соло','MISTS_DUO':'Мисты дуо',
 'HELLGATE_2V2':'Хеллгейты 2×2','HELLGATE_5V5':'Хеллгейты 5×5','HELLGATE_10V10':'Хеллгейты 10×10',
 'OPEN_WORLD':'Открытый мир','SMALL_SCALE':'Малые группы','ZVZ':'ZvZ','CRYSTAL_ARENA':'Арена',
 'FAME_FARM_SOLO':'PvE соло','FAME_FARM_GROUP':'PvE группа','FAME_FARM_GROUP_AVALON':'Авалонские подземелья',
 'GANK_SOLO':'Ганк соло','GANK_DUO':'Ганк дуо','GANK_GROUP':'Ганк группа','GATHERING':'Сбор',
 'TRACKING_SOLO':'Выслеживание соло','TRACKING_GROUP':'Выслеживание группа','ABYSSAL_DEPTHS_2V2':'Глубины 2×2'}
SLOTS={'weapon_id':'Оружие','offhand_id':'Левая рука','helmet_id':'Шлем','chest_id':'Броня','boots_id':'Обувь','cape_id':'Плащ','food_id':'Еда','potion_id':'Зелье'}


def parse_grind(html):
    match=re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',html,re.S)
    if not match:raise ValueError('Сайт изменил формат: предыдущие билды сохранены')
    props=json.loads(match[1])['props']['pageProps'];rows=props.get('initialBuilds')
    if not isinstance(rows,list):raise ValueError('Не получен список билдов')
    result=[];seen=set()
    for row in rows:
        slug=row.get('slug','')
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',slug) or slug in seen:continue
        items={slot:uid for slot in SLOTS if isinstance(uid:=row.get(slot),str) and re.fullmatch(r'T[1-8]_[A-Z0-9_]+(?:@[1-4])?',uid)}
        if not items.get('weapon_id'):continue
        votes=row.get('upvote_count',0)
        result.append(dict(id=slug,url='https://albiononlinegrind.com/build/'+slug,source=SOURCE,
            title=str(row.get('title',''))[:200],activity=str(row.get('category','')),items=items,
            votes=max(0,votes) if isinstance(votes,int) else 0,updated=str(row.get('updated_at',''))))
        seen.add(slug)
    if rows and not result:raise ValueError('Составы билдов не распознаны; предыдущие данные сохранены')
    return dict(builds=result,has_more=bool(props.get('initialHasMore')),fetched=time.time(),activity=props.get('initialFilters',{}).get('content','ALL'))


def fetch_grind(activity):
    slug=activity.lower().replace('_','-')
    url='https://albiononlinegrind.com/builds'+('/'+slug if activity!='ALL' else '')+'?sort=POPULAR'
    with urlopen(Request(url,headers={'User-Agent':'AlbionCraft/0.1','Accept':'text/html'}),timeout=20) as response:
        raw=response.read(4_000_001)
    if len(raw)>4_000_000:raise ValueError('Ответ сайта слишком большой')
    data=parse_grind(raw.decode('utf-8'))
    if data['activity']!=activity:raise ValueError('Сайт не применил фильтр активности; предыдущие данные сохранены')
    return data


def variant(uid,slot,tier,enchantment):
    if slot in ('food_id','potion_id'):return uid
    base=re.sub(r'^T[1-8]_','T'+str(tier)+'_',uid.split('@')[0])
    return base+('@'+str(enchantment) if enchantment else '')


def build_variants(build,tier,enchantment,available):
    tiers=range(1,9) if tier is None else (tier,)
    charms=range(5) if enchantment is None else (enchantment,)
    return [(t,e) for t in tiers for e in charms if all(variant(uid,slot,t,e) in available
        for slot,uid in build['items'].items() if slot not in ('food_id','potion_id'))]


def evaluate(build,prices,histories,city,tier,enchantment,quality,recipes,settings,context=None):
    from .scanner import scan
    from .trading import trading_scan
    if context is None:context={}
    if not context:
        context.update(index={(p.get('item_id'),p.get('city'),p.get('quality')):p for p in prices},
            hist={(h.get('item_id'),h.get('location'),h.get('quality')):h for h in histories},parts={},recipes={})
        for recipe in recipes:context['recipes'].setdefault(recipe.item_id,[]).append(recipe)
    index=context['index'];hist=context['hist']
    parts=[];total=0;missing=[]
    for slot,original in build['items'].items():
        uid=variant(original,slot,tier,enchantment)
        cache_key=(uid,city,quality)
        if cache_key in context['parts']:
            part=dict(context['parts'][cache_key],slot=slot);parts.append(part)
            if part['price'] is None:missing.append(uid)
            else:total+=part['price']
            continue
        qs=range(1,6) if quality is None else [quality]
        candidates=[]
        for q in qs:
            p=index.get((uid,city,q),{});price,age,status=quote(p,'sell_price_min',None)
            if price is not None and 'будущем' not in status:candidates.append((price,q,p,age,status))
        price,q,p,age,status=min(candidates,key=lambda x:(x[0],x[1])) if candidates else (None,quality or 1,{},None,'нет цены')
        if price is None:missing.append(uid)
        else:total+=price
        demand_info=demand(hist.get((uid,city,q),[]))
        rs=context['recipes'].get(uid,[]) if price is not None else []
        candidates=scan(rs,prices,histories,[city],[city],[city],settings,q,None) if rs else []
        trades=trading_scan(rs,prices,histories,[city],[city],settings,q,None,'flip') if rs else []
        def best(rows):
            options=[r for r in rows if r.get('base')]
            return max(options,key=lambda r:r['base']['profit']) if options else None
        parts.append(dict(slot=slot,item_id=uid,name=item_name(uid),price=price,quality=q,age=age,status=status,
            date=p.get('sell_price_min_date'),source=p.get('sell_price_min_source','Нет данных'),demand=demand_info,
            craft=best(candidates),flip=best(trades)))
        context['parts'][cache_key]=parts[-1]
    return dict(build=build,tier=tier,enchantment=enchantment,key=(build['id'] if 'id' in build else '',tier,enchantment),parts=parts,cost=total,complete=not missing,missing=missing)
