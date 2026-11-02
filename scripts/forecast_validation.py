"""Deterministic numerical validation, NOT evidence of real-market accuracy."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def validate():
    from datetime import datetime,timezone,timedelta
    import numpy as np
    from app.sale_forecast import forecast
    rng=np.random.default_rng(20261102);clock=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    h=dict(period_days=7,bucket_hours=24,source='Synthetic numerical validation',
        data=[dict(timestamp=(clock-timedelta(days=n)).isoformat(),item_count=c,avg_price=1) for n,c in enumerate([80,90,100,110,95,105,120],1)])
    result=forecast(h,10,10,24,clock);e=result['evidence'];samples=100000
    rates=rng.gamma(e['alpha'],1/e['beta_days'],samples)
    counts=rng.poisson(rates*.1)
    completion=rng.gamma(10,1/(rates*.1))*24
    empirical=float(np.mean(counts>=10));analytic=result['selected']['probability']
    coverage=float(np.mean((completion>=result['p10_hours'])&(completion<=result['p90_hours'])))
    assert abs(empirical-analytic)<.01,(empirical,analytic)
    assert abs(coverage-.8)<.01,coverage
    assert abs(float(np.mean(np.minimum(counts,10)))-result['selected']['expected_sold'])<.05
    return dict(seed=20261102,samples=samples,analytic_probability=analytic,simulated_probability=empirical,
        interval_coverage_under_assumed_model=coverage,scope='Numerical agreement only; not real-player calibration')


if __name__=='__main__':
    result=validate()
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
