import unittest
import tempfile
from pathlib import Path
from app.models import Recipe,Ingredient
from app.trading import trading_scan
from app.workers import Fetch
from PySide6.QtCore import QCoreApplication

class QualityLoadingTests(unittest.TestCase):
    def test_masterpiece_allowed_unless_higher_enchantment_cheaper(self):
        from app.scanner import scan
        r=Recipe('X','X',0,(Ingredient('BAR',1,True),))
        prices=[dict(item_id=uid,city='A',quality=q,sell_price_min=value,sell_price_min_date='2020-01-01T00:00:00Z')
            for uid,q,value in [('X',5,900000),('BAR',1,100)]]
        settings={'activity':'craft','same_city':True,'setup':'0','tax':'0','other':'0','general':{'A':{'rrr':'0','focus_rrr':'0','station':'0'}}}
        x=scan([r],prices,[],['A'],['A'],['A'],settings,'any',None)[0]
        self.assertEqual(x['sale'],900000);self.assertEqual(x['quality'],5)
        prices.append(dict(item_id='X@1',city='A',quality=1,sell_price_min=50,sell_price_min_date='2020-01-01T00:00:00Z'))
        x=scan([r],prices,[],['A'],['A'],['A'],settings,'any',None)[0]
        self.assertIsNone(x['sale']);self.assertIsNone(x['base'])
        self.assertEqual(scan([r],prices,[],['A'],['A'],['A'],settings,5,None),[])
        prices.append(dict(item_id='X',city='A',quality=4,sell_price_min=80,sell_price_min_date='2020-01-01T00:00:00Z'))
        prices.append(dict(item_id='X',city='A',quality=1,sell_price_min=90,sell_price_min_date='2020-01-01T00:00:00Z'))
        x=scan([r],prices,[],['A'],['A'],['A'],settings,'any',None)[0]
        self.assertEqual(x['quality'],4);self.assertEqual(x['sale'],80)
    def test_quality_mask_excludes_cheapest_disallowed_quality(self):
        r=Recipe('X','X',0,());date='2020-01-01T00:00:00Z'
        prices=[dict(item_id='X',city=city,quality=q,sell_price_min=value,sell_price_min_date=date)
            for city,q,value in [('A',1,90),('A',4,70),('A',5,10),('B',1,150),('B',4,140),('B',5,100)]]
        settings={'setup':'0','tax':'0','other':'0','quality_mask':[1,4]}
        rows=trading_scan([r],prices,[],['A'],['B'],settings,'any',None,'resale')
        self.assertEqual(rows[0]['quality'],4);self.assertEqual(rows[0]['purchase_cost'],70)
        rows=trading_scan([r],prices,[],['A'],['B'],settings,None,None,'resale')
        self.assertEqual({r['quality'] for r in rows},{1,4})
    def test_any_uses_cheapest_available_and_same_sale_quality(self):
        r=Recipe('X','X',0,())
        date='2020-01-01T00:00:00Z'
        prices=[dict(item_id='X',city=city,quality=q,sell_price_min=value,sell_price_min_date=date)
            for city,q,value in [('A',2,100),('A',4,70),('B',2,200),('B',4,150)]]
        rows=trading_scan([r],prices,[],['A'],['B'],{'setup':'0','tax':'0','other':'0'},'any',None,'resale')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['quality'],4)
        self.assertEqual(rows[0]['purchase_cost'],70);self.assertEqual(rows[0]['sale'],150)
    def test_new_filter_only_requests_missing_ids(self):
        app=QCoreApplication.instance() or QCoreApplication([])
        class API:
            cancel=lambda:False
            def __init__(self):self.calls=[]
            def prices(self,ids,cities,quality):
                self.calls.append(('prices',tuple(ids),quality))
                return [dict(item_id=uid,city=cities[0],quality=1,sell_price_min=100,sell_price_min_date='2020-01-01T00:00:00Z') for uid in ids]
            def history(self,ids,cities,quality):self.calls.append(('history',tuple(ids),quality));return []
        with tempfile.TemporaryDirectory() as d:
            api=API();root=Path(d)
            a=Recipe('A','A',0,(Ingredient('BAR',1,True),))
            b=Recipe('B','B',0,(Ingredient('BAR',2,True),))
            Fetch(api,[a],None,root,False,'craft').run()
            Fetch(api,[a],None,root,False,'resale').run()
            Fetch(api,[b],None,root,False,'craft').run()
            self.assertEqual([c[1] for c in api.calls if c[0]=='prices'],[('A','BAR'),('B',)])
            self.assertEqual([c[1] for c in api.calls if c[0]=='history'],[('A',),('B',)])
            self.assertTrue(all(c[2] is None for c in api.calls))
