import unittest,tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from tests.test_trip_inventory import options
from app.trip_market import configure_market,turnover,proceeds
from app.trip_chain import solve_chain
from app.local_market import LocalStore,merge_local


class DepthTests(unittest.TestCase):
    def candidate(self):
        c=options(D(3))[0];c.row.update(buy='Fort Sterling',sale_side='sell_price_min');return c
    def test_expensive_next_level_changes_optimum_and_cash_balance(self):
        c=self.candidate();c.parts[0]['buy_levels']=[dict(price=D(3),quantity=2),dict(price=D(30),quantity=20)]
        p=solve_chain([c],1000,30,repeat=False)
        self.assertEqual(p['profit'],32);self.assertEqual(p['goods']['T2_ORE']['quantity'],2)
        self.assertEqual(p['purchase'],6)
    def test_bid_depth_and_multiple_purchase_prices_match_exhaustive_search(self):
        c=self.candidate();c.parts[0]['buy_levels']=[dict(price=D(3),quantity=2),dict(price=D(9),quantity=8)]
        c.sales['Thetford']['levels']=[dict(price=D(20),quantity=2),dict(price=D(8),quantity=8)]
        p=solve_chain([c],30,5,repeat=False)
        best=max(D(min(n,2)*20+max(0,n-2)*8-min(n,2)*3-max(0,n-2)*9-n) for n in range(6) if min(n,2)*3+max(0,n-2)*9<=30)
        self.assertEqual(p['profit'],best);self.assertEqual(p['revenue'],40)
        self.assertEqual(proceeds(c.sales['Thetford'],11),None)
    def test_shared_ingredient_depth_is_not_reused_for_each_recipe(self):
        from copy import deepcopy
        from dataclasses import replace
        c=self.candidate();c.parts[0]['buy_levels']=[dict(price=D(3),quantity=2)]
        other=deepcopy(c);other.recipe=replace(c.recipe,item_id='OTHER');other.sales['Thetford']['price']=D(19)
        p=solve_chain([c,other],100,100,repeat=False)
        self.assertEqual(p['goods']['T2_ORE']['quantity'],2);self.assertEqual(sum(p['sold'].values()),2)
    def test_missing_depth_fallback_and_strict_stock_only(self):
        c=self.candidate();warnings=configure_market([c],[],mode='strict')
        self.assertTrue(warnings);self.assertFalse(solve_chain([c],100,100)['lines'])
        p=solve_chain([c],0,1,stock=[dict(item_id='T2_ORE',quantity=2,price=3,transport=False)])
        self.assertTrue(p['lines']);configure_market([c],[],mode='observed')
        self.assertTrue(solve_chain([c],100,100)['lines'])
    def test_turnover_limit_and_unknown_are_explicit(self):
        c=self.candidate();c.row['demand']=dict(kind='low',per_day=10)
        configure_market([c],[],days=3,share=10);p=solve_chain([c],100,100)
        self.assertLessEqual(sum(p['sold'].values()),3)
        self.assertEqual(turnover(30,c.row['demand'],10)['days'],30)
        c.row['demand']=dict(kind='unknown');configure_market([c],[],days=3,share=10)
        self.assertFalse(solve_chain([c],100,100)['lines']);self.assertIsNone(turnover(30,c.row['demand'])['per_day'])
    def test_local_snapshot_deduplicates_ids_and_survives_merge(self):
        now=datetime.now(timezone.utc);stamp=now.isoformat();expiry=(now+timedelta(days=1)).isoformat()
        a=('id','T2_ORE','Fort Sterling',1,'sell_price_min',3,2,stamp,expiry)
        with tempfile.TemporaryDirectory() as folder:
            s=LocalStore(Path(folder)/'prices.sqlite');s.save([a,a,('id2',*a[1:5],9,4,stamp,expiry)])
            rows=merge_local([],s.prices());s.close()
        c=self.candidate();configure_market([c],rows)
        self.assertEqual(c.parts[0]['buy_levels'],[dict(price=3,quantity=2),dict(price=9,quantity=4)])
