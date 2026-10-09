from datetime import datetime, timezone, timedelta
from decimal import Decimal as D

def calculate(raw, fixed, sale, rrr, station, setup, tax, focus=None):
    values=(raw,fixed,sale,rrr,station,setup,tax)
    if any(not v.is_finite() or v<0 for v in values) or rrr>=1 or setup+tax>=1:
        raise ValueError('Некорректные расходы, RRR или комиссии')
    if focus is not None and (not focus.is_finite() or focus<=0):
        raise ValueError('Focus должен быть положительным')
    returned=raw*rrr
    cost=raw-returned+fixed+station
    fees=sale*(setup+tax)
    profit=sale-fees-cost
    capital=raw+fixed+station+sale*setup
    return dict(raw=raw,returned=returned,effective=raw-returned,fixed=fixed,station=station,
                setup_fee=sale*setup,sales_tax=sale*tax,
                cost=cost,sale=sale,fees=fees,profit=profit,capital=capital,
                roi=profit/cost*100 if cost else None,
                per_million=profit/capital*1000000 if capital else None,
                per_focus=profit/focus if focus else None)

def classify(plain, focused, band=D('5')):
    if plain is None or focused is None: return 'unknown'
    if plain>band: return 'green'
    if focused>band: return 'blue'
    if plain < -band and focused < -band: return 'red'
    return 'neutral'

DEMAND_LABELS={
    'unknown':'Нет истории', 'none':'Продажи не зафиксированы',
    'very_low':'Очень мало', 'low':'Мало', 'medium':'Умеренно',
    'high':'Много', 'very_high':'Очень много', 'mass':'Массовые продажи',
    'huge':'Огромный объём'}
DEMAND_BANDS=((3,'very_low'),(10,'low'),(50,'medium'),(200,'high'),
              (1000,'very_high'),(10000,'mass'))
DEMAND_SCALE=('Средний объём за 7 завершённых дней, единиц в сутки:\n'
    'Очень мало: больше 0, но меньше 3; мало: 3–<10; умеренно: 10–<50;\n'
    'много: 50–<200; очень много: 200–<1 000; массовые продажи: 1 000–<10 000;\n'
    'огромный объём: от 10 000. Пороги одинаковы для всех типов предметов.\n'
    'Ноль в полученной истории: продажи не зафиксированы; нет истории: объём неизвестен.')


def demand_text(info):
    if info['kind']=='unknown':return 'Нет истории'
    volume=f'{info["per_day"]:,.1f}'.replace(',', ' ').replace('.', ',')
    unit=f'({volume} шт./день)'
    if info['per_day']>=1000:
        hourly=f'{info["per_day"]/24:,.1f}'.replace(',', ' ')
        unit+=f'\n≈ {hourly} ед./час'
    return DEMAND_LABELS[info['kind']]+'\n'+unit


def demand_tip(info):
    text=DEMAND_SCALE+'\n\nИстория относится к городу, зачарованию и качеству этой строки.\n'
    text+=f'Дней с полученными данными: {info["observed_days"]}/7; с продажами: {info["active_days"]}/7.\n'
    text+='Пропуски не считаются подтверждёнными нулями; неполная история может занижать объём.\n'
    if info['per_day']>0:
        text+=f'30 единиц / весь объём рынка ≈ {30/info["per_day"]:.1f} суток. Это ориентир масштаба партии, а не срок продажи вашего заказа: есть конкуренты.\n'
    return text+'Среднее в час = объём в сутки / 24, а не измеренный темп каждого часа.'


def demand(data, now=None):
    now=now or datetime.now(timezone.utc)
    # Seven complete UTC days; the current incomplete day is excluded.
    end=now.replace(hour=0,minute=0,second=0,microsecond=0)
    start=end-timedelta(days=7)
    days={}; total=0; weighted=0
    seen=set()
    for row in data:
        try:
            dt=datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
            dt=dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
            count=row['item_count']; price=row['avg_price']
            if not isinstance(count,int) or isinstance(count,bool) or count<0 or not isinstance(price,(int,float)) or price<0:
                continue
            if not start<=dt<end or dt in seen: continue
            seen.add(dt); days[dt.date()]=days.get(dt.date(),0)+count
            total+=count; weighted+=count*price
        except (KeyError,ValueError,TypeError,AttributeError): continue
    active=sum(v>0 for v in days.values())
    per_day=total/7
    kind='unknown' if not days else 'none' if total==0 else next((kind for upper,kind in DEMAND_BANDS if per_day<upper),'huge')
    return dict(kind=kind,total=total,per_day=total/7,active_days=active,observed_days=len(days),
                average=weighted/total if total else None)
