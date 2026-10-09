import unittest
from app.models import Ingredient,Recipe
from app.scanner import scan
from app.formatting import timestamp

class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.r=Recipe('T4_TEST','Тест',0,(Ingredient('T4_BAR',10,True),Ingredient('T4_ART',1,False)))
        self.p=[dict(item_id=uid,city=city,quality=1,sell_price_min=value,sell_price_min_date='2020-01-01T00:00:00Z') for uid,value in [('T4_TEST',2000),('T4_BAR',100),('T4_ART',100)] for city in ['A','B']]
        self.s={'setup':'2.5','tax':'4','other':'0','cities':{'A':{'rrr':'0','focus_rrr':'36.7','station':'100'}}}
    def rows(self): return scan([self.r],self.p,[],['A','B'],['A'],['A','B'],self.s,1,30)
    def test_multiple_cities(self): self.assertEqual(len(self.rows()),4)
    def test_stale_kept(self):
        x=self.rows()[0]; self.assertIsNotNone(x['base']); self.assertTrue(x['issues'])
    def test_missing_not_zero(self):
        self.p=[p for p in self.p if p['item_id']!='T4_BAR']
        self.assertIsNone(self.rows()[0]['base'])
    def test_artifact_return(self): self.assertEqual(self.rows()[0]['focus']['fixed'],100)
    def test_unknown_settings(self):
        self.s['tax']=''; self.assertIsNone(self.rows()[0]['base'])
    def test_format(self):
        self.assertEqual(timestamp('2026-10-02T15:45:00'),'02.10.26 15:45')
        self.assertEqual(timestamp('0001-01-01T00:00:00'),'—')
