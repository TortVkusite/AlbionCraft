import unittest
import tempfile
from pathlib import Path
from app.cache import Cache
from app.catalog import load_catalog

class CacheTests(unittest.TestCase):
    def test_missing_retains_last_price_and_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            cache=Cache(Path(d)/'cache.sqlite')
            row=dict(item_id='X',city='A',quality=1,sell_price_min=100,sell_price_min_date='2020-01-01T00:00:00Z')
            cache.merge_prices([row],['X'],['A'],[1])
            result=cache.merge_prices([dict(item_id='X',city='A',quality=1,sell_price_min=0)],['X'],['A'],[1])[0]
            self.assertEqual(result['sell_price_min'],100)
            self.assertEqual(result['sell_price_min_date'],row['sell_price_min_date'])
            self.assertEqual(result['sell_price_min_source'],'Последняя сохранённая котировка')
            self.assertEqual(result['buy_price_max'],0)
            cache.close()

class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.recipes=load_catalog(Path(__file__).resolve().parents[1])
    def test_sword_recipe(self):
        r=next(r for r in self.recipes if r.item_id=='T4_MAIN_SWORD')
        self.assertEqual([(i.item_id,i.amount) for i in r.ingredients],[('T4_METALBAR',16),('T4_LEATHER',8)])
    def test_upgrade_not_fabricated(self):
        r=[r for r in self.recipes if r.item_id=='T4_MAIN_SWORD@4']
        self.assertTrue(r);self.assertTrue(all(r.path=='Прямой крафт' for r in r))
    def test_upgrade_chain(self):
        r=next(r for r in self.recipes if r.item_id=='T4_MAIN_SWORD@3' and r.path!='Прямой крафт')
        self.assertEqual([i.item_id for i in r.ingredients if not i.returnable],['T4_RUNE','T4_SOUL','T4_RELIC'])
    def test_artifact_alternatives(self):
        r=[r for r in self.recipes if r.item_id=='T4_MAIN_SCIMITAR_MORGANA' and r.path=='Прямой крафт']
        self.assertEqual(len(r),2)
        self.assertTrue(all(any(not i.returnable for i in x.ingredients) for x in r))
