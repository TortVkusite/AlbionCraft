import unittest
from pathlib import Path
from decimal import Decimal as D
from app.catalog import load_catalog
from app.scanner import scan
from app.trading import trading_scan
from app.progression import GameProgression
from app.rules import automatic_profile

ROOT=Path(__file__).resolve().parents[1]

class CommodityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=load_catalog(ROOT)
        cls.game=GameProgression(ROOT)
    def recipe(self,uid,variant=0):
        return next(r for r in self.catalog if r.item_id==uid and r.variant==variant and r.path=='Прямой крафт')
    def test_raw_resource_market_and_enchanted_refining_ids(self):
        raw=next(r for r in self.catalog if r.item_id=='T4_ORE_LEVEL1@1')
        self.assertEqual((raw.category,raw.base_id,raw.enchantment,raw.path,raw.max_quality),('resources','T4_ORE',1,'Рынок',1))
        refined=self.recipe('T4_METALBAR_LEVEL1@1')
        self.assertEqual(refined.ingredients[0].item_id,'T4_ORE_LEVEL1@1')
        self.assertAlmostEqual(float(automatic_profile(refined,'Thetford',{})['rrr']),100*.58/1.58)
    def test_multi_output_costs_and_station_per_unit(self):
        r=self.recipe('T4_POTION_HEAL')
        self.assertEqual(r.output_count,5)
        p=[dict(item_id=uid,city='A',quality=1,sell_price_min=price,sell_price_min_date='2020-01-01T00:00:00Z') for uid,price in [(r.item_id,200),('T4_BURDOCK',10),('T3_EGG',10)]]
        s=dict(setup='0',tax='0',other='7',general={'A':dict(rrr='0',focus_rrr='50',station='50')})
        row=scan([r],p,[],['A'],['A'],['A'],s,'any',None)[0]
        self.assertEqual(row['purchase_cost'],60)
        self.assertEqual(row['base']['raw'],60)
        self.assertEqual(row['base']['station'],10)
        self.assertEqual(row['base']['profit'],123)
        self.assertEqual(row['focus']['profit'],153)
    def test_food_and_stone_output(self):
        self.assertEqual(self.recipe('T4_MEAL_STEW').output_count,10)
        self.assertEqual(self.recipe('T4_STONEBLOCK',4).output_count,8)
    def test_nonquality_market_once_even_when_gear_mask_excludes_normal(self):
        r=next(r for r in self.catalog if r.item_id=='T4_ORE')
        p=[dict(item_id=r.item_id,city='A',quality=1,sell_price_min=100,buy_price_max=90,sell_price_min_date='2020-01-01T00:00:00Z',buy_price_max_date='2020-01-01T00:00:00Z')]
        rows=trading_scan([r],p,[],['A'],['A'],dict(setup='0',tax='0',other='0',quality_mask=[4,5]),None,None,'flip')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['quality'],1)
        self.assertEqual(rows[0]['base']['profit'],D(10))
    def test_focus_counts_craft_events_not_each_potion(self):
        r=self.recipe('T4_POTION_HEAL')
        self.assertEqual(self.game.simulate(r.item_id,10,{},0,recipe=r)['focus'],420)
        self.assertEqual(self.game.simulate(r.item_id,10,{},0,focus_each=12,recipe=r)['focus'],120)
        with self.assertRaises(ValueError):self.game.simulate(r.item_id,6,{},0,recipe=r)
    def test_separate_enchanted_material_focus(self):
        r=self.recipe('T4_METALBAR_LEVEL1@1')
        self.assertEqual(self.game.simulate(r.item_id,1,{},0,recipe=r)['focus'],94)
    def test_market_only_has_no_crafting_profit(self):
        r=next(r for r in self.catalog if r.item_id=='T4_ORE')
        self.assertEqual(scan([r],[],[],['A'],['A'],['A'],{},1,None),[])

if __name__=='__main__':unittest.main()
