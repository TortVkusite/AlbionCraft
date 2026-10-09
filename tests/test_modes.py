import unittest
from decimal import Decimal as D
from app.trading import trade_calculation, trading_scan, enchant_recipes
from app.models import Recipe,Ingredient

class ModeTests(unittest.TestCase):
    def test_buy_and_sell_orders(self):
        x=trade_calculation(D(1000),D(2000),D('.025'),D('.04'),D(0),True)
        self.assertEqual(x['cost'],D(1025));self.assertEqual(x['profit'],D(845));self.assertEqual(x['capital'],D(1075))
    def test_immediate_purchase_no_buy_setup(self):
        x=trade_calculation(D(1000),D(2000),D('.025'),D('.04'),D(100),False)
        self.assertEqual(x['profit'],D(770))
    def test_orders_one_city(self):
        r=Recipe('X','X',0,())
        p=[dict(item_id='X',city=c,quality=1,buy_price_max=100,sell_price_min=200,buy_price_max_date='2020-01-01T00:00:00Z',sell_price_min_date='2020-01-01T00:00:00Z') for c in ['A','B']]
        rows=trading_scan([r],p,[],['A','B'],['A','B'],{'setup':'2.5','tax':'4','other':'0'},1,30,'flip')
        self.assertEqual(len(rows),2);self.assertTrue(all(r['buy']==r['sell'] for r in rows))
    def test_intercity_separate(self):
        r=Recipe('X','X',0,())
        p=[dict(item_id='X',city=c,quality=1,sell_price_min=200,sell_price_min_date='2020-01-01T00:00:00Z') for c in ['A','B']]
        rows=trading_scan([r],p,[],['A','B'],['A','B'],{'setup':'2.5','tax':'4','other':'10'},1,30,'resale')
        self.assertEqual(len(rows),2);self.assertTrue(all(r['buy']!=r['sell'] for r in rows))
    def test_enchant_buys_base_item(self):
        r=Recipe('T4_X@1','X',0,(Ingredient('T4_BAR',16,True),Ingredient('T4_RUNE',288,False)),base_id='T4_X',enchantment=1,path='Крафт .0 → .1')
        x=enchant_recipes([r])[0]
        self.assertEqual([i.item_id for i in x.ingredients],['T4_X','T4_RUNE'])
        self.assertFalse(any(i.returnable for i in x.ingredients))
    def test_same_city_craft_and_global_profile(self):
        from app.scanner import scan
        r=Recipe('X','X',0,(Ingredient('BAR',10,True),))
        p=[dict(item_id=uid,city=c,quality=1,sell_price_min=value,sell_price_min_date='2020-01-01T00:00:00Z') for uid,value in [('X',2000),('BAR',100)] for c in ['A','B']]
        s={'same_city':True,'setup':'2.5','tax':'4','other':'0','general':{c:{'rrr':'0','focus_rrr':'36.7','station':'100'} for c in ['A','B']}}
        rows=scan([r],p,[],['A','B'],['A','B'],['A','B'],s,1,30)
        self.assertEqual(len(rows),2);self.assertTrue(all(x['buy']==x['craft']==x['sell'] for x in rows))
        self.assertEqual(rows[0]['base']['profit'],D(770))
    def test_enchant_selected_quality_and_no_focus(self):
        from app.scanner import scan
        r=Recipe('T4_X@1','X',0,(Ingredient('T4_BAR',16,True),Ingredient('T4_RUNE',288,False)),base_id='T4_X',enchantment=1,path='Крафт .0 → .1')
        r=enchant_recipes([r])[0]
        p=[dict(item_id=uid,city='A',quality=q,sell_price_min=value,sell_price_min_date='2020-01-01T00:00:00Z') for uid,q,value in [('T4_X',3,1000),('T4_RUNE',1,1),('T4_X@1',3,2000)]]
        s={'activity':'enchant','same_city':True,'setup':'2.5','tax':'4','other':'0'}
        x=scan([r],p,[],['A'],['A'],['A'],s,3,30)[0]
        self.assertEqual(x['base']['profit'],D(582));self.assertIsNone(x['focus'])
