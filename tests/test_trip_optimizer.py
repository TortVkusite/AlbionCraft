import unittest,itertools,tempfile
from pathlib import Path
from decimal import Decimal as D
from datetime import datetime,timezone
from app.trip_optimizer import Candidate,solve,candidates,refining_recipes,fame_per_item,focus_per_operation,shopping,sale_comparisons,simulate_progress
from app.catalog import load_catalog
from app.progression import GameProgression,PlayerStore
from app.models import Recipe,Ingredient

class TripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1];cls.game=GameProgression(cls.root);cls.recipes=refining_recipes(load_catalog(cls.root))
    def option(self,uid,price,weight,profit,focused,focus,limit=None):
        return Candidate(Recipe(uid,uid,0,()),D(price),D(weight),dict(profit=D(profit)),dict(profit=D(focused)),focus,D(0),[],{}, {},limit)
    def test_integer_plan_matches_exhaustive_not_greedy(self):
        options=[self.option('A',7,3,9,12,3,3),self.option('B',4,4,7,11,2,4)]
        p=solve(options,25,17,5)
        best=D(0)
        for a,af,b,bf in itertools.product(range(5),repeat=4):
            if a+af>3 or b+bf>4 or 7*(a+af)+4*(b+bf)>25 or 3*(a+af)+4*(b+bf)>17 or 3*af+2*bf>5:continue
            best=max(best,D(9*a+12*af+7*b+11*bf))
        self.assertEqual(p['profit'],best);self.assertTrue(p['optimal']);self.assertLessEqual(p['focus'],5)
    def test_focus_optimizes_increment_not_total_profit_per_focus(self):
        p=solve([self.option('A',1,1,100,101,1),self.option('B',1,1,1,10,1)],2,2,1)
        # With per-item caps, extra focus belongs to B despite its lower total margin.
        options=[self.option('A',1,1,100,101,1,1),self.option('B',1,1,1,10,1,1)]
        p=solve(options,2,2,1)
        self.assertEqual(p['profit'],D(110));self.assertEqual([l['candidate'].recipe.item_id for l in p['lines'] if l['focused']],['B'])
    def test_no_focus_negative_profit_empty(self):
        p=solve([self.option('A',5,2,-1,2,4)],20,10)
        self.assertFalse(p['lines']);self.assertEqual(p['focus'],0)
        with self.assertRaises(ValueError):solve([],0,10)
    def test_roi_and_cash_choose_different_lots(self):
        options=[self.option('A',10,1,10,10,1),self.option('B',100,1,50,50,1)]
        cash=solve(options,1000,5)
        percent=solve(options,1000,5,objective_mode='roi')
        self.assertEqual(cash['profit'],250)
        self.assertEqual(percent['profit'],50)
        self.assertEqual(percent['purchase'],50)
        self.assertTrue(percent['optimal'])
    def test_roi_matches_exhaustive_and_ties_prefer_cash(self):
        options=[self.option('A',7,3,9,12,3,3),self.option('B',4,4,7,11,2,4)]
        best=(D(0),D(0))
        for a,af,b,bf in itertools.product(range(5),repeat=4):
            cost=7*(a+af)+4*(b+bf);profit=9*a+12*af+7*b+11*bf
            if not cost or cost>25 or 3*(a+af)+4*(b+bf)>17 or 3*af+2*bf>5 or a+af>3 or b+bf>4:continue
            best=max(best,(D(profit)/cost,D(profit)))
        p=solve(options,25,17,5,objective_mode='roi')
        self.assertEqual((p['profit']/p['purchase'],p['profit']),best)
        self.assertTrue(p['optimal'])
    def prices(self,r):
        now=datetime.now(timezone.utc).isoformat();ids={i.item_id for i in r.ingredients}|{r.item_id}
        return [dict(item_id=uid,city=city,quality=1,sell_price_min=100 if uid!=r.item_id else 400+(20 if city=='Martlock' else 0),buy_price_max=80,sell_price_min_date=now,buy_price_max_date=now) for uid in ids for city in ['Fort Sterling','Thetford','Martlock']]
    def prepared(self):
        r=next(r for r in self.recipes if r.item_id=='T4_METALBAR');settings=dict(auto_rules=True,premium=False,sale_mode='order')
        options,rejected=candidates([r],self.prices(r),[],'Fort Sterling','Thetford',settings,self.game,{'CRAFT_REFINE_ORE_T4':dict(level=1,xp=0)},station_rate=D(400))
        self.assertFalse(rejected);return options,settings
    def test_repeated_roi_matches_enumerated_initial_purchases(self):
        from decimal import ROUND_CEILING
        options,_=self.prepared();c=options[0];c.limit=3
        rp=D(c.row['profile']['rrr'])/100;rf=D(c.row['profile']['focus_rrr'])/100
        best=(D(0),D(0))
        for plain,focused in itertools.product(range(4),repeat=2):
            if not plain+focused or plain+focused>3 or focused*c.focus>500:continue
            cost=D(0);weight=D(0)
            for part in c.parts:
                i=part['ingredient'];count=D(i.amount)
                net=count*(plain*(1-rp if i.returnable else 1)+focused*(1-rf if i.returnable else 1))
                reserve=count*(rf if focused else rp) if i.returnable else D(0)
                qty=(net+reserve).to_integral_value(rounding=ROUND_CEILING)
                cost+=D(part['price'])*qty;weight+=c.row['input_weights'][i.item_id]*qty
            profit=c.plain['profit']*plain+c.focused['profit']*focused
            if cost<=1000 and weight<=10:best=max(best,(profit/cost,profit))
        p=solve(options,1000,10,500,repeat=True,objective_mode='roi')
        self.assertEqual((p['profit']/p['purchase'],p['profit']),best)
        self.assertTrue(p['optimal'])
    def test_full_load_and_inputs_not_net_consumption(self):
        options,settings=self.prepared();c=options[0]
        self.assertEqual(c.purchase,D(300));self.assertEqual(c.weight,D('1.36'));self.assertEqual(c.plain['station'],D('7.2'))
        p=solve(options,600,D('2.72'));self.assertEqual(sum(l['quantity'] for l in p['lines']),2)
        goods=shopping(p);self.assertEqual(goods['T4_ORE']['quantity'],4);self.assertEqual(goods['T3_METALBAR']['quantity'],2)
        self.assertGreater(goods['T4_ORE']['returned'],0)
        cities=sale_comparisons(p,'Thetford',settings)
        self.assertEqual(next(c for c in cities if c['city']=='Martlock')['delta'],D('35.8'))
        self.assertIsNone(next(c for c in cities if c['city']=='Caerleon')['profit'])
    def test_missing_inputs_fees_and_locked_tier_rejected(self):
        r=next(r for r in self.recipes if r.item_id=='T4_METALBAR');s=dict(auto_rules=True,premium=False)
        for prices,states,rate in [(self.prices(r),{},D(0)),([],{'CRAFT_REFINE_ORE_T4':dict(level=1,xp=0)},D(0)),(self.prices(r),{'CRAFT_REFINE_ORE_T4':dict(level=1,xp=0)},None)]:
            rows,rejected=candidates([r],prices,[],'Fort Sterling','Thetford',s,self.game,states,station_rate=rate)
            self.assertFalse(rows);self.assertTrue(rejected)
    def test_station_tariff_and_extra_cost_are_separate(self):
        r=next(r for r in self.recipes if r.item_id=='T4_METALBAR')
        args=([r],self.prices(r),[],'Fort Sterling','Thetford',dict(auto_rules=True,premium=False,sale_mode='order'),self.game,{'CRAFT_REFINE_ORE_T4':dict(level=1,xp=0)})
        normal,_=candidates(*args,station_rate=D(395),other=D(0))
        duplicate,_=candidates(*args,station_rate=D(395),other=D(395))
        self.assertEqual(normal[0].plain['station'],D('7.11'))
        self.assertEqual(normal[0].plain['profit']-duplicate[0].plain['profit'],D(395))
        self.assertFalse(solve(duplicate,1000000,1000)['lines'])
    def test_trip_stale_price_switch_is_enforced(self):
        from datetime import timedelta
        r=next(r for r in self.recipes if r.item_id=='T4_METALBAR');prices=self.prices(r)
        for p in prices:
            if p['item_id']=='T4_ORE' and p['city']=='Fort Sterling':p['sell_price_min_date']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        args=([r],prices,[],'Fort Sterling','Thetford',dict(auto_rules=True,premium=False),self.game,{'CRAFT_REFINE_ORE_T4':dict(level=1,xp=0)})
        options,rejected=candidates(*args,age_limit=30,station_rate=D(350))
        self.assertFalse(options);self.assertIn('старше',rejected[0][1])
        options,_=candidates(*args,age_limit=None,station_rate=D(350));self.assertTrue(options)
        for p in prices:
            p['sell_price_min_date']=datetime.now(timezone.utc).isoformat()
            if p['city']=='Martlock':p['sell_price_min_date']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        options,_=candidates(*args,age_limit=30,station_rate=D(350));self.assertTrue(options)
        self.assertNotIn('Martlock',options[0].sales)
    def test_day_bonus_does_not_mutate_saved_profiles(self):
        import json
        r=next(r for r in self.recipes if r.item_id=='T4_METALBAR')
        settings=dict(auto_rules=True,premium=False,profiles={'T4_METALBAR|Прямой крафт|0':{'Thetford':dict(rrr='30',focus_rrr='50',station='5')}})
        before=json.dumps(settings)
        rows,_=candidates([r],self.prices(r),[],'Fort Sterling','Thetford',settings,self.game,{},respect_mastery=False,day_bonus=D(20))
        self.assertTrue(rows);self.assertEqual(json.dumps(settings),before)
    def repeated_option(self,count=1,price=16,weight='0.2',sale=22,rrr='40',focus_rrr='60',station=0,focus=2):
        i=Ingredient('ORE',count,True);r=Recipe('BAR','Слиток',0,(i,),tier=2)
        def calc(rate):
            consumed=D(price)*count*(1-D(rate)/100)
            return dict(profit=D(sale)-consumed-D(station),sale=D(sale),fees=D(0),station=D(station),fixed=D(0),returned=D(price)*count*D(rate)/100,cost=consumed+D(station))
        return Candidate(r,D(price)*count,D(weight)*count,calc(rrr),calc(focus_rrr),focus,D(1),[dict(ingredient=i,price=price)],dict(profile=dict(rrr=rrr,focus_rrr=focus_rrr),input_weights={'ORE':D(weight)}),{'Thetford':dict(price=D(sale))})
    def test_repeated_copper_example_and_cash_identity(self):
        c=self.repeated_option();p=solve([c],1000000,1000,repeat=True)
        self.assertEqual(p['purchase'],D(80000));self.assertEqual(p['weight'],D(1000))
        self.assertEqual(sum(l['quantity'] for l in p['lines']),8332)
        self.assertEqual(shopping(p)['ORE']['quantity'],5000)
        remaining=shopping(p)['ORE']['returned'];self.assertEqual(remaining,D('0.8'))
        self.assertEqual(p['profit'],D(22)*8332-D(80000)+D(16)*remaining)
        self.assertGreater(p['profit'],D(103000))
    def test_repeat_does_not_buy_less_than_first_recipe(self):
        c=self.repeated_option(count=6,price=1,sale=30)
        p=solve([c],5,100,repeat=True);self.assertFalse(p['lines'])
        p=solve([c],6,100,repeat=True);self.assertEqual(sum(l['operations'] for l in p['lines']),1)
    def test_repeated_focus_all_operations_and_station(self):
        c=self.repeated_option(price=1,sale=10,station=2,focus=3)
        p=solve([c],10,100,focus_budget=12,repeat=True)
        self.assertLessEqual(p['focus'],12)
        self.assertEqual(p['focus'],sum(l['operations']*3 for l in p['lines'] if l['focused']))
        ops=sum(l['operations'] for l in p['lines']);stock=shopping(p)['ORE']
        self.assertEqual(p['profit'],D(10)*ops-p['purchase']-D(2)*ops+stock['returned'])
        for city in sale_comparisons(p,'Thetford',dict(auto_rules=True,premium=False,sale_mode='instant')):
            if city['city']=='Thetford':self.assertEqual(city['delta'],0)
    def test_repeated_solver_matches_small_exhaustive(self):
        c=self.repeated_option(price=3,sale=8,station=1,focus=2)
        best=D(0)
        for plain,focused in itertools.product(range(15),repeat=2):
            if not plain+focused or focused*2>6:continue
            consumed=D(plain)*D('.6')+D(focused)*D('.4')
            from decimal import ROUND_CEILING
            bought=int((consumed+(D('.6') if focused else D('.4'))).to_integral_value(rounding=ROUND_CEILING))
            if bought*3>18 or D(bought)*D('.2')>D('1.2'):continue
            best=max(best,c.plain['profit']*plain+c.focused['profit']*focused)
        self.assertEqual(solve([c],18,D('1.2'),6,repeat=True)['profit'],best)
    def test_repeat_mixed_recipes_matches_independent_inventory_simulation(self):
        from dataclasses import replace
        a=self.repeated_option(price=3,sale=8,station=1,focus=2)
        b=self.repeated_option(count=2,price=2,weight='.3',sale=11,station=2,focus=3)
        i=Ingredient('OTHER_ORE',2,True);b.recipe=replace(b.recipe,item_id='OTHER_BAR',ingredients=(i,));b.parts=[dict(ingredient=i,price=2)];b.row['input_weights']={'OTHER_ORE':D('.3')}
        best=D(0)
        for counts in itertools.product(range(8),repeat=4):
            if counts[1]*2+counts[3]*3>6:continue
            cost=load=profit=D(0)
            for c,plain,focused in [(a,*counts[:2]),(b,*counts[2:])]:
                # Find the minimum starting integer stock by forward simulation.
                if not plain+focused:continue
                ing=c.parts[0]['ingredient'];required=ing.amount
                for initial in range(required,100):
                    inventory=D(initial);feasible=True
                    for mode in [False]*plain+[True]*focused:
                        if inventory<required:feasible=False;break
                        inventory-=D(required)*(D('.4') if mode else D('.6'))
                    if feasible:break
                cost+=initial*c.parts[0]['price'];load+=initial*c.row['input_weights'][ing.item_id]
                profit+=plain*c.plain['profit']+focused*c.focused['profit']
            if cost<=18 and load<=D('1.5'):best=max(best,profit)
        plan=solve([a,b],18,D('1.5'),6,repeat=True)
        self.assertEqual(plan['profit'],best)
        self.assertLessEqual(plan['purchase'],18);self.assertLessEqual(plan['weight'],D('1.5'))
    def test_refining_fame_and_tier_specific_efficiency(self):
        for t,fame in [(4,'22.5'),(5,'90'),(6,'270'),(7,'645'),(8,'1395')]:self.assertEqual(fame_per_item(self.game,f'T{t}_METALBAR'),D(fame))
        self.assertEqual(fame_per_item(self.game,'T4_METALBAR_LEVEL3@3'),D(180))
        coeff=self.game.focus_coefficients('T4_METALBAR')
        self.assertEqual(coeff['CRAFT_REFINE_ORE_T4'],2.8);self.assertEqual(coeff['CRAFT_REFINE_ORE_T8'],.3)
    def test_progress_preserves_combat_focus_safe_and_undo(self):
        options,s=self.prepared();r=options[0].recipe
        states={'CRAFT_REFINE_ORE_T4':dict(level=1,xp=self.game.costs('CRAFT_REFINE_ORE_T4')[1]-1),'COMBAT_SWORDS':dict(level=5,xp=2)}
        p=solve(options,60000,1000,10000);result=simulate_progress(self.game,p,states)
        self.assertGreater(result['states']['CRAFT_REFINE_ORE_T4']['level'],1);self.assertEqual(result['states']['COMBAT_SWORDS'],states['COMBAT_SWORDS']);self.assertLessEqual(result['focus'],p['focus'])
        # T6 cannot gain unlock XP while the parent T5 is still locked.
        short=solve(options,300,2);short_result=simulate_progress(self.game,short,states)
        self.assertNotIn('CRAFT_REFINE_ORE_T6',short_result['states'])
        with tempfile.TemporaryDirectory() as folder:
            store=PlayerStore(Path(folder)/'player.sqlite');store.save('A',states)
            store.record('A',dict(type='Выполнено',states_before=states,states_after=result['states']),result['states']);store.undo_last('A')
            self.assertEqual(store.states('A'),states);store.close()
