import unittest
from decimal import Decimal as D
from pathlib import Path
from app.catalog import load_catalog
from app.rules import automatic_profile,effective_settings
from app.scanner import scan

class RulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=next(r for r in load_catalog(Path(__file__).resolve().parents[1]) if r.item_id=='T4_MAIN_SWORD')
    def test_city_crafting_not_refining(self):
        x=automatic_profile(self.r,'Lymhurst',{})
        self.assertAlmostEqual(float(x['rrr']),24.812030075,places=6)
        self.assertAlmostEqual(float(x['focus_rrr']),47.91666667,places=6)
    def test_no_specialty(self):
        x=automatic_profile(self.r,'Thetford',{})
        self.assertAlmostEqual(float(x['rrr']),15.25423728,places=6)
    def test_nutrition_station(self):
        self.assertEqual(D(self.r.nutrition),D('43.2'))
        x=automatic_profile(self.r,'Lymhurst',{'station_rates':{'Lymhurst':'500'}})
        self.assertEqual(D(x['station']),D(216))
    def test_missing_tariff_not_invented(self):
        self.assertNotIn('station',automatic_profile(self.r,'Lymhurst',{}))
    def test_tax_scenarios_and_override(self):
        self.assertEqual(effective_settings({'auto_rules':True})['tax'],'8')
        self.assertEqual(effective_settings({'auto_rules':True,'premium':True})['tax'],'4')
        self.assertEqual(effective_settings({'auto_rules':True,'tax':'7'})['tax'],'7')
    def test_useful_numbers_with_unknown_station(self):
        p=[dict(item_id=uid,city='Lymhurst',quality=1,sell_price_min=value,sell_price_min_date='2020-01-01T00:00:00Z') for uid,value in [('T4_MAIN_SWORD',10000),('T4_METALBAR',100),('T4_LEATHER',100)]]
        x=scan([self.r],p,[],['Lymhurst'],['Lymhurst'],['Lymhurst'],{'auto_rules':True},1,None)[0]
        self.assertEqual(x['purchase_cost'],2400)
        self.assertIsNotNone(x['base'])
        self.assertIn('станция',x['pending_costs'])
        self.assertEqual(x['color'],'unknown')
        self.assertEqual(x['max_station_fee'],x['base']['profit'])
    def test_confirmed_tariff_all_costs(self):
        p=[dict(item_id=uid,city='Lymhurst',quality=1,sell_price_min=value,sell_price_min_date='2020-01-01T00:00:00Z') for uid,value in [('T4_MAIN_SWORD',10000),('T4_METALBAR',100),('T4_LEATHER',100)]]
        x=scan([self.r],p,[],['Lymhurst'],['Lymhurst'],['Lymhurst'],{'auto_rules':True,'station_rates':{'Lymhurst':'500'},'other':'0'},1,None)[0]
        self.assertEqual(x['pending_costs'],[])
        self.assertEqual(x['base']['station'],216)
