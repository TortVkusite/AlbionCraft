import copy
import json
import math
import sqlite3
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

from app.sale_forecast import evidence,forecast,load_history

CLOCK=datetime(2026,11,2,12,tzinfo=timezone.utc)


def history(counts=None,period=7,bucket=24):
    counts=counts if counts is not None else [100]*7
    end=CLOCK.replace(hour=CLOCK.hour//bucket*bucket)
    return dict(item_id='T4_MAIN_SWORD',location='Thetford',quality=1,period_days=period,bucket_hours=bucket,
        observed=CLOCK.isoformat(),source='Synthetic fixture',data=[dict(timestamp=(end-timedelta(hours=bucket*(i+1))).isoformat(),item_count=n,avg_price=1200) for i,n in enumerate(counts)])


class SaleForecastTests(unittest.TestCase):
    def test_count_probability_matches_closed_form_gamma_poisson(self):
        r=forecast(history(),1,10,24,CLOCK);e=r['evidence']
        expected=1-(e['beta_days']/(e['beta_days']+.1))**e['alpha']
        self.assertAlmostEqual(r['selected']['probability'],expected,12)

    def test_median_and_interval_are_quantiles_of_same_completion_cdf(self):
        h=history([4,6,4,5,6,5,5]);r=forecast(h,3,10,24,CLOCK)
        for key,q in [('p10_hours',.1),('median_hours',.5),('p80_hours',.8),('p90_hours',.9)]:
            hvalue=r[key];self.assertIsNotNone(hvalue)
            check=forecast(h,3,10,hvalue,CLOCK)
            self.assertAlmostEqual(check['selected']['probability'],q,8)

    def test_probabilities_increase_with_time_and_share_and_decrease_with_batch(self):
        r=forecast(history(),10,10,24,CLOCK)
        ps=[h['probability'] for h in r['curve']]
        self.assertEqual(ps,sorted(ps))
        self.assertLess(forecast(history(),10,5,24,CLOCK)['selected']['probability'],r['selected']['probability'])
        self.assertLess(forecast(history(),20,10,24,CLOCK)['selected']['probability'],r['selected']['probability'])

    def test_expected_sold_uses_capped_count_not_probability_times_quantity(self):
        from scipy.stats import nbinom
        r=forecast(history([5]*7),10,20,24,CLOCK);e=r['evidence'];mu=e['model_market_per_day']*.2
        p=e['alpha']/(e['alpha']+mu)
        expected=sum(min(n,10)*nbinom.pmf(n,e['alpha'],p) for n in range(200))
        self.assertAlmostEqual(r['selected']['expected_sold'],expected,10)
        self.assertAlmostEqual(r['selected']['expected_sold']+r['selected']['remaining'],10)

    def test_one_daily_sword_does_not_sell_thirty_in_one_day(self):
        r=forecast(history([1]*7),30,10,24,CLOCK)
        self.assertLess(r['selected']['probability'],1e-10)
        self.assertGreater(r['median_hours'],24*200)

    def test_observed_dispersion_widens_rate_uncertainty(self):
        smooth=evidence(history([100]*7),CLOCK);bursty=evidence(history([0,0,0,700,0,0,0]),CLOCK)
        self.assertEqual(smooth['total'],bursty['total'])
        self.assertLess(bursty['alpha'],smooth['alpha']);self.assertTrue(bursty['warnings'])

    def test_day_week_and_four_week_use_hours_not_bucket_count_as_days(self):
        for period,bucket in [(1,1),(7,6),(28,24)]:
            e=evidence(history([100]*(period*24//bucket),period,bucket),CLOCK)
            self.assertEqual(e['status'],'ready');self.assertEqual(e['coverage'],1)
            self.assertEqual(e['market_per_day'],100*24/bucket)

    def test_missing_buckets_are_not_invented_zero_sales(self):
        e=evidence(history([100]*21,7,6),CLOCK)
        self.assertEqual(e['coverage'],.75);self.assertEqual(e['market_per_day'],400)
        self.assertEqual(e['exposure_days'],5.25);self.assertTrue(e['warnings'])

    def test_sparse_empty_or_zero_history_suppresses_probabilities(self):
        for h in [None,history([]),history([100]),history([0]*7)]:
            r=forecast(h,30,10,24,CLOCK)
            self.assertEqual(r['status'],'insufficient');self.assertNotIn('selected',r)

    def test_duplicate_incomplete_future_and_overlapping_buckets_do_not_inflate_volume(self):
        h=history();h['data'].append(copy.deepcopy(h['data'][0]))
        h['data'].append(dict(timestamp=CLOCK.isoformat(),item_count=10000,avg_price=1))
        h['data'].append(dict(timestamp=(CLOCK-timedelta(hours=14)).isoformat(),item_count=10000,avg_price=1))
        e=evidence(h,CLOCK)
        self.assertEqual(e['total'],700);self.assertGreaterEqual(e['discarded'],3)

    def test_stale_history_and_future_observation_are_unavailable(self):
        h=history([100]*28,28,24);h['data']=h['data'][4:]
        self.assertEqual(evidence(h,CLOCK)['status'],'insufficient')
        h=history();h['observed']=(CLOCK+timedelta(hours=2)).isoformat()
        self.assertEqual(evidence(h,CLOCK)['status'],'insufficient')

    def test_invalid_parameters_fail_before_numerical_work(self):
        for quantity,share,hours in [(0,10,24),(True,10,24),(1,float('nan'),24),(1,0,24),(1,10,float('inf')),(1,10,0)]:
            with self.assertRaises(ValueError):forecast(history(),quantity,share,hours,CLOCK)

    def test_large_values_are_bounded_and_serializable(self):
        r=forecast(history([10**10]*7),10**9,100,8760,CLOCK)
        self.assertTrue(0<=r['selected']['probability']<=1)
        self.assertTrue(0<=r['selected']['expected_sold']<=10**9)
        json.dumps(r,allow_nan=False)

    def test_history_selection_keeps_period_city_and_quality_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            a=history();b=history([100]*24,1,1);other=copy.deepcopy(a);other['quality']=2
            self.assertEqual(load_history(folder,'T4_MAIN_SWORD','Thetford',1,7,[a,b,other]),a)
            self.assertEqual(load_history(folder,'T4_MAIN_SWORD','Thetford',1,1,[a,b,other]),b)
            self.assertIsNone(load_history(folder,'T4_MAIN_SWORD','Martlock',1,7,[a,b,other]))
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_archive_deduplicates_sources_and_preserves_window(self):
        from app.market_memory import archive_volumes
        with tempfile.TemporaryDirectory() as folder:
            db=sqlite3.connect(Path(folder)/'prices.sqlite');h=history()
            end=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
            h['observed']=datetime.now(timezone.utc).isoformat()
            for n,p in enumerate(h['data'],1):p['timestamp']=(end-timedelta(days=n)).isoformat()
            archive_volumes(db,[h],'API');archive_volumes(db,[h],'Local');db.commit();db.close()
            loaded=load_history(folder,'T4_MAIN_SWORD','Thetford',1,7)
            self.assertEqual(len(loaded['data']),7);self.assertEqual(loaded['bucket_hours'],24)


if __name__=='__main__':unittest.main()
