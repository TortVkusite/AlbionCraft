import unittest,itertools
from decimal import Decimal as D
from pathlib import Path
from datetime import datetime,timezone,timedelta
from app.models import Recipe,Ingredient
from app.trip_optimizer import Candidate,refining_recipes,sale_comparisons,simulate_progress
from app.trip_chain import dependency_recipes,prepare_chain,solve_chain
from app.catalog import load_catalog
from app.progression import GameProgression

class ChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1];cls.game=GameProgression(cls.root);cls.catalog=refining_recipes(load_catalog(cls.root))

    def real_options(self,missing_intermediates=False,locked=False,day_bonus=D(0)):
        selected=[r for r in self.catalog if r.item_id=='T4_METALBAR_LEVEL1@1'];recipes=dependency_recipes(selected,self.catalog)
        now=datetime.now(timezone.utc).isoformat();prices=[]
        purchases={'T2_ORE':15,'T3_ORE':76,'T4_ORE_LEVEL1@1':109,'T2_METALBAR':15,'T3_METALBAR':151}
        if missing_intermediates:
            purchases.pop('T2_METALBAR');purchases.pop('T3_METALBAR')
        for uid,p in purchases.items():prices.append(dict(item_id=uid,city='Fort Sterling',quality=1,sell_price_min=p,sell_price_min_date=now))
        prices.append(dict(item_id=selected[0].item_id,city='Thetford',quality=1,sell_price_min=409,sell_price_min_date=now))
        options,rejected=prepare_chain(recipes,prices,[],'Fort Sterling','Thetford',dict(auto_rules=True,premium=False,sale_mode='order'),self.game,{},
            station_rate=D(350),respect_mastery=locked,roots={selected[0].item_id},day_bonus=day_bonus)
        return options,rejected

    def test_user_manual_chain_is_in_search_space_and_cash_balances(self):
        options,rejected=self.real_options();self.assertFalse(rejected)
        p=solve_chain(options,2000000,2000)
        self.assertGreaterEqual(p['profit'],D('304319.985'));self.assertTrue(p['optimal'])
        self.assertIn('T2_ORE',p['goods']);self.assertIn('T3_ORE',p['goods'])
        self.assertEqual(set(p['sold']),{'T4_METALBAR_LEVEL1@1'})
        fees=sum(((l['calc']['station']+l['calc']['fixed'])*l['operations'] for l in p['lines']),D(0))
        self.assertEqual(p['profit'],p['revenue']-p['purchase']-fees)
        self.assertLessEqual(p['weight'],2000);self.assertLessEqual(p['purchase'],2000000)
        self.assertTrue(all(v>=D('-0.0000001') for v in p['stocks'].values()))
        comparisons=sale_comparisons(p,'Thetford',dict(auto_rules=True,premium=False))
        self.assertEqual(next(c for c in comparisons if c['city']=='Thetford')['delta'],0)
        self.assertIsNone(next(c for c in comparisons if c['city']=='Caerleon')['profit'])

    def test_intermediate_can_be_produced_without_any_market_quote(self):
        options,rejected=self.real_options(missing_intermediates=True);self.assertFalse(rejected)
        p=solve_chain(options,2000000,2000)
        self.assertGreaterEqual(p['profit'],D('304319.985'))
        self.assertNotIn('T2_METALBAR',p['goods']);self.assertNotIn('T3_METALBAR',p['goods'])
        self.assertTrue(all(p['price'] is not None for c in options for p in c.parts if p['ingredient'].item_id.endswith('ORE')))

    def test_locked_root_is_not_automatically_opened(self):
        options,rejected=self.real_options(locked=True)
        self.assertTrue(any(r.item_id=='T4_METALBAR_LEVEL1@1' for r,why in rejected))
        p=solve_chain(options,2000000,2000);self.assertFalse(p['lines'])

    def tiny_options(self,mid_price=7):
        a=Ingredient('RAW_A',1,True);b=Ingredient('RAW_B',1,True);mid=Ingredient('MID',1,True)
        def candidate(uid,ingredients,prices,root):
            recipe=Recipe(uid,uid,0,tuple(ingredients))
            return Candidate(recipe,D(0),D(len(ingredients)),dict(profit=D(-999),station=D(1),sale=D(0),fees=D(0),fixed=D(0)),
                dict(profit=D(-999)),2,D(1),[dict(ingredient=i,price=p) for i,p in zip(ingredients,prices)],
                dict(profile=dict(rrr='25',focus_rrr='50'),input_weights={i.item_id:D(1) for i in ingredients},root=root,sell='Thetford',net_sale_factor=D(1),operation_other=D(0)),
                {'Thetford':dict(price=D(20))} if root else {})
        return [candidate('MID',[a],[3],False),candidate('FINAL',[mid,b],[mid_price,1],True)]

    def test_joint_focus_and_inventory_match_independent_exhaustive_simulation(self):
        best=D(0)
        def minimum_stock(plain,focused):
            if not plain+focused:return 0
            for initial in range(plain+focused+1):
                stock=D(initial);valid=True
                for flag in [True]*focused+[False]*plain:
                    if stock<1:valid=False;break
                    stock-=D('.5') if flag else D('.75')
                if valid:return initial
        for ap,af,bp,bf in itertools.product(range(8),repeat=4):
            if (af+bf)*2>6:continue
            raw_a=minimum_stock(ap,af);raw_b=minimum_stock(bp,bf)
            for bought_mid in range(6):
                if raw_a+raw_b+bought_mid>5 or raw_a*3+raw_b+bought_mid*7>12:continue
                stock=D(ap+af+bought_mid);valid=True
                for flag in [True]*bf+[False]*bp:
                    if stock<1:valid=False;break
                    stock-=D('.5') if flag else D('.75')
                if valid:best=max(best,D((bp+bf)*20-raw_a*3-raw_b-bought_mid*7-ap-af-bp-bf))
        p=solve_chain(self.tiny_options(),12,5,6)
        self.assertEqual(p['profit'],best);self.assertLessEqual(p['focus'],6)
        self.assertTrue(p['optimal'])

    def test_do_not_discard_unprofitable_intermediate_or_count_it_as_sale(self):
        p=solve_chain(self.tiny_options(mid_price=None),12,5)
        self.assertTrue(p['lines']);self.assertNotIn('MID',p['sold']);self.assertNotIn('MID',p['goods'])
        mid_line=next(l for l in p['lines'] if l['candidate'].recipe.item_id=='MID')
        self.assertEqual(mid_line['sold'],0);self.assertGreater(mid_line['internal'],0)
        self.assertLess(mid_line['calc']['profit'],0);self.assertGreater(p['profit'],0)
    def test_roi_chain_matches_exhaustive_inventory_balance(self):
        best=(D(0),D(0))
        for ap,af,bp,bf,raw_a,raw_b,bought_mid in itertools.product(range(4),range(4),range(4),range(4),range(5),range(5),range(5)):
            cost=raw_a*3+raw_b+bought_mid*7
            if not cost or cost>12 or raw_a+raw_b+bought_mid>5 or (af+bf)*2>6:continue
            stock={'RAW_A':D(raw_a),'RAW_B':D(raw_b),'MID':D(bought_mid)};valid=True
            for uid,plain,focused in [('MID',ap,af),('FINAL',bp,bf)]:
                for flag in [True]*focused+[False]*plain:
                    inputs=['RAW_A'] if uid=='MID' else ['RAW_B','MID']
                    if any(stock[i]<1 for i in inputs):valid=False;break
                    for i in inputs:stock[i]-=D('.5') if flag else D('.75')
                    stock[uid]=stock.get(uid,D(0))+1
                if not valid:break
            profit=D((bp+bf)*20-cost-ap-af-bp-bf)
            if valid and profit>0:best=max(best,(profit/cost,profit))
        p=solve_chain(self.tiny_options(),12,5,6,objective_mode='roi')
        self.assertEqual((p['profit']/p['purchase'],p['profit']),best)
        self.assertTrue(p['optimal']);self.assertIsNone(p['upper_bound'])

    def test_output_cap_and_no_repeat_remain_feasible(self):
        options=self.tiny_options();options[-1].limit=2
        p=solve_chain(options,100,100,repeat=False)
        self.assertLessEqual(p['sold'].get('FINAL',0),2)
        self.assertTrue(all(v>=0 for v in p['stocks'].values()))

    def test_unavailable_raw_input_cannot_become_free(self):
        options=self.tiny_options(mid_price=None);options[0].parts[0]['price']=None
        p=solve_chain(options,100,100);self.assertFalse(p['lines']);self.assertEqual(p['profit'],0)

    def test_day_bonus_changes_all_stages_and_profit(self):
        plain,_=self.real_options();bonus,_=self.real_options(day_bonus=D(20))
        for c in bonus:self.assertAlmostEqual(float(D(c.row['profile']['rrr'])/100),.78/1.78)
        self.assertGreater(solve_chain(bonus,2000000,2000)['profit'],solve_chain(plain,2000000,2000)['profit'])

    def test_shared_intermediate_purchase_and_sales_are_counted_once(self):
        from copy import deepcopy
        from dataclasses import replace
        options=self.tiny_options();second=deepcopy(options[-1]);second.recipe=replace(second.recipe,item_id='FINAL_2');second.sales['Thetford']['price']=D(19)
        options[-1].limit=2;second.limit=2
        p=solve_chain(options+[second],100,20,6)
        self.assertLessEqual(p['sold'].get('FINAL',0),2);self.assertLessEqual(p['sold'].get('FINAL_2',0),2)
        self.assertLess(abs(sum((l['purchase'] for l in p['lines']),D(0))-p['purchase']),D('1e-20'))
        self.assertLess(abs(sum((l['weight'] for l in p['lines']),D(0))-p['weight']),D('1e-20'))
        self.assertEqual(p['revenue'],sum(D(p['sold'].get(uid,0))*price for uid,price in [('FINAL',20),('FINAL_2',19)]))

    def test_time_limit_zero_incumbent_is_not_a_proof_of_no_profit(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        def stopped(*args,**kwargs):
            return SimpleNamespace(x=[0]*len(kwargs['bounds'].ub),status=1,mip_dual_bound=-1,message='Time limit reached')
        with patch('scipy.optimize.milp',side_effect=stopped):p=solve_chain(self.tiny_options(),12,5)
        self.assertFalse(p['optimal']);self.assertGreater(p['upper_bound'],0);self.assertFalse(p['lines'])
