"""Conditional sale-time model, not a calibrated prediction of a player's orders.

Gamma-mixed Poisson opportunities give negative-binomial counts and beta-prime
completion times. A fixed market-share assumption thins opportunities; uncertainty
in that assumption is exposed as sensitivity scenarios, never fitted to volume.
"""
import math
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean, variance

MODEL_VERSION='gamma-poisson-v1'


def utc(value):
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def evidence(history,clock=None):
    clock=clock or datetime.now(timezone.utc)
    base=dict(status='insufficient',reason='Нет истории совершённых продаж',model=MODEL_VERSION,
        calibrated=False,coverage=0,observed_buckets=0,total=0,market_per_day=None,warnings=[])
    if not isinstance(history,dict):return base
    period=history.get('period_days',7)
    bucket=history.get('bucket_hours',6 if history.get('source','').startswith('Из твоей игры') else 24)
    if type(period) is not int or type(bucket) is not int or period not in (1,7,28) or bucket not in (1,6,24):return base
    end=clock.replace(hour=clock.hour//bucket*bucket,minute=0,second=0,microsecond=0)
    start=end-timedelta(days=period);unique={};discarded=0
    points=history.get('data',[])
    if not isinstance(points,list) or len(points)>1000:return base
    for p in points:
        try:
            dt=utc(p['timestamp']);count=p['item_count']
            if type(count) is not int or not 0<=count<=10**12 or not start<=dt or dt+timedelta(hours=bucket)>end:
                discarded+=1;continue
            if dt in unique:discarded+=1;continue
            unique[dt]=count
        except (ValueError,KeyError,TypeError,AttributeError,OverflowError):discarded+=1
    # Do not count overlapping intervals, even with distinct timestamps.
    accepted=[];previous=None
    for dt,count in sorted(unique.items()):
        if previous is not None and dt<previous:discarded+=1;continue
        accepted.append((dt,count));previous=dt+timedelta(hours=bucket)
    counts=[p[1] for p in accepted];expected=period*24//bucket;coverage=len(counts)/expected
    exposure=len(counts)*bucket/24;total=sum(counts)
    base.update(period_days=period,bucket_hours=bucket,expected_buckets=expected,
        observed_buckets=len(counts),coverage=coverage,exposure_days=exposure,total=total,
        source=history.get('source','API'),discarded=discarded,
        first=accepted[0][0].isoformat() if accepted else None,
        last_end=(accepted[-1][0]+timedelta(hours=bucket)).isoformat() if accepted else None,
        market_per_day=total/exposure if exposure else None)
    if not counts:return base
    if coverage<.75 or exposure<.75 or len(counts)<3:
        base['reason']='Недостаточное покрытие истории: нужны 75% интервалов, минимум 3 интервала и 18 часов наблюдений';return base
    if (clock-utc(base['last_end'])).total_seconds()>max(36,bucket*2)*3600:
        base['reason']='История устарела: открой свежую историю рынка';return base
    if total==0:
        base['reason']='В истории нет совершённых продаж для оценки темпа';return base
    if history.get('observed'):
        try:
            if utc(history['observed'])>clock+timedelta(minutes=2):
                base['reason']='Время наблюдения находится в будущем';return base
        except (ValueError,TypeError,AttributeError):
            base['reason']='Некорректное время наблюдения';return base
    # Jeffreys rate posterior, widened for observed extra-Poisson variation.
    # One latent rate is drawn for the whole future batch; this preserves a
    # coherent monotone completion-time CDF for every requested horizon.
    average=mean(counts);extra=max(0,(variance(counts)-average)/(average*average))
    alpha=1/(1/(total+.5)+extra)
    rate=(total+.5)/exposure;beta=alpha/rate
    warnings=[]
    if coverage<1:warnings.append('Пропуски не считаются нулями; наблюдавшиеся интервалы должны быть репрезентативными')
    if period==1:warnings.append('Суточный срез не описывает различия между днями недели')
    if total<20:warnings.append('Мало сделок: оценка чувствительна к новым наблюдениям')
    if extra>.25:warnings.append('Объёмы менялись скачками; диапазон модели расширен')
    base.update(status='ready',reason='',alpha=alpha,beta_days=beta,model_market_per_day=rate,
        extra_variation=extra,warnings=warnings)
    return base


def forecast(history,quantity,share=10,hours=12,clock=None):
    if type(quantity) is not int or not 1<=quantity<=10**9:raise ValueError('Количество должно быть целым числом от 1 до 1 000 000 000')
    if isinstance(share,bool) or not math.isfinite(float(share)) or not .01<=float(share)<=100:raise ValueError('Доля рынка должна быть от 0,01 до 100%')
    if isinstance(hours,bool) or not math.isfinite(float(hours)) or not 0<float(hours)<=8760:raise ValueError('Срок должен быть от 0 до 8760 часов')
    e=evidence(history,clock);result=dict(evidence=e,quantity=quantity,share=float(share),hours=float(hours),status=e['status'])
    if e['status']!='ready':return result
    from scipy.stats import nbinom,betaprime
    alpha=e['alpha'];beta=e['beta_days'];fraction=float(share)/100
    def horizon(h,s=fraction):
        if h==0:return dict(hours=0,probability=0.,expected_sold=0.,remaining=float(quantity),low_sold=0,high_sold=0)
        mu=alpha/beta*s*h/24;p=alpha/(alpha+mu)
        probability=float(nbinom.sf(quantity-1,alpha,p))
        expected=mu*float(nbinom.cdf(quantity-2,alpha+1,p))+quantity*probability
        expected=min(float(quantity),max(0.,expected))
        bounds=[min(quantity,max(0,int(nbinom.ppf(q,alpha,p)))) for q in (.1,.9)]
        return dict(hours=float(h),probability=min(1.,max(0.,probability)),expected_sold=expected,
            remaining=quantity-expected,low_sold=bounds[0],high_sold=bounds[1])
    def completion(q,s=fraction):
        value=float(betaprime.ppf(q,quantity,alpha,scale=beta/s))*24
        return value if math.isfinite(value) and value<=8760 else None
    selected=horizon(float(hours))
    result.update(selected=selected,median_hours=completion(.5),p10_hours=completion(.1),p80_hours=completion(.8),p90_hours=completion(.9),
        personal_per_day=e['model_market_per_day']*fraction,
        horizons=[horizon(h) for h in sorted(set([1,2,6,12,24,48,96,168,float(hours)]))],
        curve=[horizon(h) for h in [0]+[float(hours)*i/48 for i in range(1,49)]],
        sensitivity=[dict(share=s,probability=horizon(float(hours),s/100)['probability'],median_hours=completion(.5,s/100))
            for s in sorted(set([max(.01,float(share)/2),float(share),min(100,float(share)*2)]))])
    return result


def load_history(root,item,city,quality,period=None,histories=()):
    """One window/source per model. Never sum overlapping 1/7/28-day views."""
    candidates=[h for h in histories if h.get('item_id')==item and h.get('location')==city and h.get('quality',1)==quality
        and (period is None or h.get('period_days',7)==period)]
    path=Path(root)/'prices.sqlite'
    if path.exists():
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'local_history_windows' in tables:
                for payload, in db.execute('SELECT payload FROM local_history_windows WHERE item=? AND city=? AND quality=?',(item,city,quality)):
                    h=json.loads(payload)
                    if period is None or h.get('period_days',7)==period:candidates.append(h)
            if 'volume_windows' in tables:
                query='SELECT period,bucket,max(seen) FROM volume_windows WHERE item=? AND city=? AND quality=?'
                args=[item,city,quality]
                if period is not None:query+=' AND period=?';args.append(period)
                query+=' GROUP BY period,bucket ORDER BY max(seen) DESC LIMIT 3'
                for days,bucket,seen in db.execute(query,args):
                    unique={}
                    for t,count,price,source in db.execute('SELECT stamp,count,price,source FROM volume_windows WHERE item=? AND city=? AND quality=? AND period=? AND bucket=? ORDER BY seen DESC LIMIT 2000',(item,city,quality,days,bucket)):
                        if t not in unique:unique[t]=dict(timestamp=t,item_count=count,avg_price=price)
                    candidates.append(dict(item_id=item,location=city,quality=quality,period_days=days,bucket_hours=bucket,
                        observed=seen,source='Архив рынка',data=list(unique.values())))
        finally:db.close()
    def freshness(h):
        stamps=[utc(p['timestamp']) for p in h.get('data',[]) if isinstance(p,dict) and p.get('timestamp')]
        observed=utc(h['observed']) if h.get('observed') else (max(stamps) if stamps else datetime.min.replace(tzinfo=timezone.utc))
        return observed,len(stamps)
    return max(candidates,key=freshness) if candidates else None


def task(data):
    history=load_history(data['root'],data['item'],data['city'],data['quality'],data.get('period'),data.get('histories',()))
    return forecast(history,data['quantity'],data['share'],data['hours'])
