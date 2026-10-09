import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from app.market_stream import normalized_order,supplement
from app.cache import Cache
from app.trading import allowed_route,enchant_recipes
from app.models import Recipe,Ingredient
from app.scanner import scan

class AdditionalMarketsTests(unittest.TestCase):
    def order(self,**updates):
        data=dict(Id=1,ItemTypeId='T4_MAIN_SWORD',LocationId=3008,QualityLevel=2,EnchantmentLevel=1,
            UnitPriceSilver=23499,Amount=3,AuctionType='offer',Expires=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
        data.update(updates);return data
    def test_wire_price_location_and_enchantment(self):
        row=normalized_order(self.order())
        self.assertEqual(row[1:7],('T4_MAIN_SWORD@1','Martlock',2,'sell_price_min',23499,3))
        self.assertEqual(normalized_order(self.order(LocationId=7))[2],'Thetford')
        self.assertIsNone(normalized_order(self.order(LocationId=5003))) # Brecilien is a different market.
    def test_expired_and_invalid_orders_are_rejected(self):
        self.assertIsNone(normalized_order(self.order(Amount=0)))
        self.assertIsNone(normalized_order(self.order(Expires='2000-01-01T00:00:00Z')))
    def test_rest_preserved_and_missing_side_filled(self):
        date=datetime.now(timezone.utc).isoformat()
        p=dict(item_id='X',city='A',quality=1,sell_price_min=100,sell_price_min_date=date)
        n=dict(item_id='X',city='A',quality=1,sell_price_min=80,sell_price_min_date=date,buy_price_max=70,buy_price_max_date=date)
        r=supplement([p],[n])[0]
        self.assertEqual(r['sell_price_min'],100);self.assertEqual(r['buy_price_max'],70)
        self.assertEqual(r['nats_observations']['sell_price_min'],80)
        self.assertIn('NATS',r['buy_price_max_source'])
    def test_snapshot_extrema_expiry_and_quantities(self):
        with tempfile.TemporaryDirectory() as d:
            c=Cache(Path(d)/'p.sqlite')
            c.save_stream_orders([normalized_order(self.order(Id=1,UnitPriceSilver=200)),normalized_order(self.order(Id=2,UnitPriceSilver=100,Amount=8))])
            r=c.stream_prices(['T4_MAIN_SWORD@1'])[0]
            self.assertEqual(r['sell_price_min'],100);self.assertEqual(r['sell_price_min_amount'],8)
            self.assertEqual(c.stream_prices(['UNKNOWN']),[]);c.close()
    def test_routes_nearest_and_caerleon(self):
        self.assertTrue(allowed_route('Thetford','Martlock'));self.assertTrue(allowed_route('Thetford','Fort Sterling'))
        self.assertFalse(allowed_route('Thetford','Lymhurst'));self.assertFalse(allowed_route('Thetford','Bridgewatch'))
        self.assertFalse(allowed_route('Thetford','Caerleon'));self.assertTrue(allowed_route('Thetford','Caerleon',True))
        self.assertFalse(allowed_route('Caerleon','Caerleon',True))
    def test_upgrade_from_already_enchanted_item(self):
        r=Recipe('T4_X@3','X',0,tuple(Ingredient('T4_'+x,288,False) for x in ['RUNE','SOUL','RELIC']),base_id='T4_X',enchantment=3,path='Крафт .0 → .3')
        variants=enchant_recipes([r]);self.assertEqual(len(variants),3)
        x=variants[2];self.assertEqual(x.base_id,'T4_X@2')
        self.assertEqual([(i.item_id,i.amount) for i in x.ingredients],[('T4_X@2',1),('T4_RELIC',288)])
        date=datetime.now(timezone.utc).isoformat()
        prices=[dict(item_id=uid,city='A',quality=q,sell_price_min=value,sell_price_min_date=date)
            for uid,q,value in [('T4_X@2',3,1000),('T4_X@2',1,10),('T4_RELIC',1,1),('T4_X@3',3,2000)]]
        settings={'activity':'enchant','same_city':True,'setup':'2.5','tax':'4','other':'0'}
        row=scan([x],prices,[],['A'],['A'],['A'],settings,3,30)[0]
        self.assertEqual(row['purchase_cost'],1288);self.assertEqual(row['base']['profit'],582)
        self.assertIsNone(row['focus'])
    def test_all_qualities_not_mixed(self):
        r=Recipe('X','X',0,(Ingredient('BAR',1,True),))
        date=datetime.now(timezone.utc).isoformat()
        p=[dict(item_id='X',city='A',quality=q,sell_price_min=q*100,sell_price_min_date=date) for q in range(1,6)]
        p.append(dict(item_id='BAR',city='A',quality=1,sell_price_min=10,sell_price_min_date=date))
        s={'same_city':True,'setup':'0','tax':'0','other':'0','general':{'A':{'rrr':'0','focus_rrr':'0','station':'0'}}}
        rows=scan([r],p,[],['A'],['A'],['A'],s,None,30)
        self.assertEqual([x['quality'] for x in rows],list(range(1,6)))
        self.assertEqual([x['base']['profit'] for x in rows],[90,190,290,390,490])
