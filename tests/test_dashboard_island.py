import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,tempfile,time,json
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from app.island import farming_data,estimate,focus_cost,calculate_islands
from app.models import Recipe,Ingredient

def prices(product,seed=2000,sale=100):
    stamp=datetime.now(timezone.utc).isoformat()
    entries=[(product['id'],seed),(product['product'],sale)]
    if product.get('food'):entries.append((product['food'],100))
    return [dict(item_id=uid,city='Thetford',quality=1,sell_price_min=value,buy_price_max=value-1,sell_price_min_date=stamp,buy_price_max_date=stamp) for uid,value in entries]

class FarmingTests(unittest.TestCase):
    def setUp(self):
        self.p=farming_data()['products'][0];self.settings=dict(city='Thetford',plots=1,premium=True,sale='order',any_age=True)
    def test_carrot_seeds_retained_surplus_sold_and_taxes_applied(self):
        p=[q for q in prices(self.p) if q['item_id']!='T1_CARROT']+prices(self.p)[1:2]
        base=estimate(self.p,self.settings,p);full=estimate(self.p,self.settings,p,9)
        self.assertEqual(base['output'],81);self.assertEqual(base['replacement'],9)
        self.assertEqual(full['output'],81);self.assertEqual(full['returned'],18);self.assertEqual(full['replacement'],0)
        self.assertEqual(full['surplus'],9);self.assertEqual(full['investment'],18000)
        self.assertEqual(full['profit'],D(81)*100*D('.935')+D(9)*2000*D('.935'))
        self.assertEqual(base['profit'],D(81)*100*D('.935')-18000)
    def test_no_premium_halves_crop_yield_but_not_plant_timer(self):
        a=estimate(self.p,self.settings,prices(self.p));b=estimate(self.p,dict(self.settings,premium=False),prices(self.p))
        self.assertEqual(a['output'],b['output']*2);self.assertEqual(a['hours'],22);self.assertEqual(b['hours'],22)
    def test_city_bonus_changes_crop_only(self):
        p=next(p for p in farming_data()['products'] if p['id']=='T5_FARM_CABBAGE_SEED')
        result=estimate(p,self.settings,prices(p),1)
        self.assertEqual(result['output'],D('89.1'));self.assertEqual(result['returned'],D(9)*D('.8')+D('.4'))
    def test_unknown_zero_and_stale_prices_never_become_zero_revenue(self):
        p=prices(self.p);p[1]['sell_price_min']=0
        self.assertIsNone(estimate(self.p,self.settings,p)['profit'])
        p=prices(self.p);p[1]['sell_price_min_date']=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
        self.assertIsNone(estimate(self.p,dict(self.settings,any_age=False),p)['profit'])
    def test_animal_time_feed_and_nurturing_all_actions(self):
        p=next(p for p in farming_data()['products'] if p['id']=='T3_FARM_OX_BABY');settings=dict(self.settings,food_amount='10')
        premium=estimate(p,settings,prices(p,25000,40000),3);normal=estimate(p,dict(settings,premium=False),prices(p,25000,40000),3)
        self.assertEqual(premium['output'],9);self.assertEqual(normal['output'],9)
        self.assertEqual(premium['hours'],22);self.assertEqual(normal['hours'],44)
        self.assertEqual(premium['feed_cost'],9000);self.assertEqual(premium['focus'],3000)
    def test_focus_matches_levels_and_rejects_invalid(self):
        self.assertEqual(focus_cost(self.p,0,0),1000);self.assertEqual(focus_cost(self.p,100,100),125)
        with self.assertRaises(ValueError):focus_cost(self.p,101,0)
    def test_allocation_matches_exhaustive_profit_under_shared_focus(self):
        herb=next(p for p in farming_data()['products'] if p['id']=='T2_FARM_AGARIC_SEED')
        islands=[dict(self.settings,product=self.p['id'],mastery=0,specialization=0),dict(self.settings,product=herb['id'],mastery=100,specialization=100)]
        pp=prices(self.p)+prices(herb,5000,100)
        data=dict(islands=islands,premium=True,sale='order',any_age=True,focus=2500,prices=pp)
        result=calculate_islands(data);actual=sum(r['selected']['profit'] for r in result)
        expected=max(estimate(self.p,islands[0],pp,i)['profit']+estimate(herb,islands[1],pp,j)['profit'] for i in range(10) for j in range(10) if i*1000+j*125<=2500)
        self.assertEqual(actual,expected);self.assertLessEqual(sum(r['selected']['focus'] for r in result),2500)
    def test_missing_surplus_quote_still_allows_seed_replacement(self):
        pp=prices(self.p);pp[0]['buy_price_max']=0
        data=dict(islands=[dict(self.settings,product=self.p['id'])],premium=True,sale='instant',any_age=True,focus=4000,prices=pp)
        result=calculate_islands(data)[0]['selected'];self.assertIsNotNone(result['profit']);self.assertEqual(result['focused'],4)
    def test_material_breakdown_artifact_output_and_missing_price(self):
        from app.material_cells import breakdown
        ore=Ingredient('T4_METALBAR',16,True);artifact=Ingredient('T4_ARTEFACT_TEST',1,False)
        row=dict(recipe=Recipe('T4_TEST','Test',0,(ore,artifact),output_count=2),parts=[dict(ingredient=ore,price=100),dict(ingredient=artifact,price=None)])
        material=breakdown(row);art=breakdown(row,True)
        self.assertEqual(material['total'],800);self.assertEqual(material['parts'][0]['amount'],8)
        self.assertFalse(art['complete']);self.assertEqual(art['parts'][0]['amount'],D('.5'))

class DashboardTests(unittest.TestCase):
    def test_pages_navigation_retains_edits_and_isolated_settings(self):
        from app.i18n_widgets import QApplication
        from app.main import Window
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder,patch('app.main.ROOT',Path(folder)),patch.object(Window,'stream_changed'),patch.object(Window,'local_changed'),patch.object(Window,'fetch'):
            window=Window();window.load_timer.stop();window.stream_timer.stop();window.show()
            window.open_trip();trip=window.trip_page;trip.budget.setValue(765432)
            window.open_island();island=window.island_page;island.rows[0]['plots'].setValue(4)
            window.show_market();window.open_trip();self.assertIs(window.trip_page,trip);self.assertEqual(trip.budget.value(),765432)
            window.open_island();self.assertIs(window.island_page,island)
            self.assertEqual(window.settings['islands']['rows'][0]['plots'],4)
            window.resize(1100,720);app.processEvents();self.assertEqual(window.width(),1100)
            window.open_orders();self.assertIs(window.page_stack.currentWidget(),window.orders_page)
            window.orders_page.reject();app.processEvents();self.assertIs(window.page_stack.currentWidget(),window.market_page)
            window.close();app.processEvents()

if __name__=='__main__':unittest.main()
