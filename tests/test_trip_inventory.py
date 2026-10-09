import unittest,tempfile,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from app.trip_inventory import StockStore,route_stock,purchase_from_mail
from app.trip_chain import solve_chain,prepare_chain
from app.models import Recipe,Ingredient
from app.trip_optimizer import Candidate


def options(price=D(100)):
    i=Ingredient('T2_ORE',1,True);r=Recipe('T2_METALBAR','Copper',2,(i,))
    return [Candidate(r,D(0),D(1),dict(profit=D(0),station=D(1),sale=D(0),fees=D(0),fixed=D(0)),None,None,D(1),
        [dict(ingredient=i,price=price)],dict(profile=dict(rrr='25',focus_rrr='25'),input_weights={'T2_ORE':D(1)},root=True,sell='Thetford',net_sale_factor=D(1),operation_other=D(0)),
        {'Thetford':dict(price=D(20))})]


class StockOptimizerTests(unittest.TestCase):
    def test_base_has_no_transport_weight_or_new_purchase_cost(self):
        p=solve_chain(options(),0,1,stock=[dict(item_id='T2_ORE',quantity=10,price=3,transport=False)])
        self.assertTrue(p['optimal']);self.assertEqual(p['sold']['T2_METALBAR'],13)
        self.assertEqual(p['weight'],0);self.assertEqual(p['purchase'],0);self.assertEqual(p['stock_value'],30)
        self.assertEqual(p['profit'],260-30-13);self.assertEqual(p['basis'],30)
        self.assertEqual(p['existing'][0]['used'],10)
    def test_bought_lot_uses_locked_cost_not_changed_market_quote(self):
        p=solve_chain(options(),0,5,stock=[dict(item_id='T2_ORE',quantity=10,price=3,transport=True)])
        self.assertEqual(p['weight'],5);self.assertEqual(p['purchase'],0)
        self.assertEqual(p['stock_value'],15);self.assertEqual(p['sold']['T2_METALBAR'],6)
        self.assertEqual(p['profit'],120-15-6)
    def test_missing_market_buy_price_can_be_replaced_by_existing_stock(self):
        p=solve_chain(options(None),0,1,stock=[dict(item_id='T2_ORE',quantity=10,price=3,transport=False)])
        self.assertEqual(p['profit'],217);self.assertFalse(p['goods'])
    def test_expensive_stock_is_not_treated_as_free_profit(self):
        p=solve_chain(options(),0,1,stock=[dict(item_id='T2_ORE',quantity=10,price=100,transport=False)])
        self.assertFalse(p['lines']);self.assertEqual(p['profit'],0)
    def test_roi_basis_includes_stock(self):
        p=solve_chain(options(),0,1,objective_mode='roi',stock=[dict(item_id='T2_ORE',quantity=10,price=3,transport=False)])
        self.assertEqual(p['basis'],p['stock_value']);self.assertGreater(p['profit'],0)
    def test_mixed_stock_and_new_purchases_respect_both_constraints(self):
        lots=[dict(item_id='T2_ORE',quantity=3,price=2,transport=False),dict(item_id='T2_ORE',quantity=8,price=3,transport=True)]
        p=solve_chain(options(D(4)),12,4,stock=lots)
        best=D(0)
        for base in range(4):
            for bought in range(9):
                for new in range(4):
                    if new*4>12 or new+bought>4:continue
                    available=D(base+bought+new);operations=0
                    while available>=1:operations+=1;available-=D('.75')
                    best=max(best,operations*19-base*2-bought*3-new*4)
        self.assertEqual(p['profit'],best);self.assertLessEqual(p['purchase'],12);self.assertLessEqual(p['weight'],4)
    def test_negative_stock_is_rejected(self):
        with self.assertRaises(ValueError):solve_chain(options(),1,1,stock=[dict(item_id='T2_ORE',quantity=-1,price=3)])


class StockStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.s=StockStore(Path(self.folder.name)/'player.sqlite')
    def tearDown(self):self.s.close();self.folder.cleanup()
    def test_screen_is_replaced_and_identical_stacks_are_distinct(self):
        rows=[dict(item_id='T2_METALBAR',quantity=999,cell=0),dict(item_id='T2_METALBAR',quantity=999,cell=1)]
        self.s.replace_page('me','Thetford','base',rows);self.s.replace_page('me','Thetford','base',rows)
        self.assertEqual(sum(r['quantity'] for r in self.s.rows('me')),1998)
        self.s.replace_page('me','Thetford','base',rows[:1]);self.assertEqual(len(self.s.rows('me')),1)
    def test_locked_price_resets_if_stack_quantity_changes(self):
        self.s.replace_page('me','Fort Sterling','bought',[dict(item_id='T2_ORE',quantity=10,cell=0)],'bought')
        row=self.s.rows('me')[0];self.s.put('me',row['city'],row['key'],dict(row,price='3'))
        self.s.replace_page('me','Fort Sterling','bought',[dict(item_id='T2_ORE',quantity=20,cell=0)],'bought')
        self.assertIsNone(self.s.rows('me')[0]['price']);self.assertEqual(self.s.rows('me')[0]['kind'],'bought')
    def test_route_filters_locations_and_distinguishes_estimate(self):
        now=datetime.now(timezone.utc).isoformat()
        rows=[dict(item_id='T2_ORE',city='Thetford',kind='base',quantity=5,price=None),dict(item_id='T2_ORE',city='Fort Sterling',kind='bought',quantity=4,price='3'),dict(item_id='T2_ORE',city='Martlock',kind='base',quantity=500,price='1')]
        r,m=route_stock(rows,'Fort Sterling','Thetford',[dict(item_id='T2_ORE',city='Thetford',quality=1,sell_price_min=8,sell_price_min_date=now)])
        self.assertEqual(len(r),2);self.assertFalse(m);self.assertTrue(r[0]['estimated']);self.assertFalse(r[0]['transport']);self.assertEqual(r[1]['price'],3);self.assertTrue(r[1]['transport'])
        r,m=route_stock(rows,'Fort Sterling','Thetford',[]);self.assertEqual(len(r),1);self.assertEqual(len(m),1)
    def receipt(self,stamp,mail=1,city='4002'):
        return dict(Action='mail',Confirmed=True,CharacterId='owner',CharacterName='DemoCharacter',Mail=dict(Id=mail,Type='MARKETPLACE_BUYORDER_FINISHED_SUMMARY',Received=stamp,LocationId=city,Body='10|T2_ORE|300000|30000'))
    def test_purchase_requires_watch_new_letter_correct_city_and_is_idempotent(self):
        self.s.watch('me','DemoCharacter','Fort Sterling',True)
        old=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat();fresh=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        self.assertEqual(self.s.capture(self.receipt(old),{'T2_ORE'}),0)
        self.assertEqual(self.s.capture(self.receipt(fresh),{'T2_ORE'}),1)
        self.assertEqual(self.s.capture(self.receipt(fresh),{'T2_ORE'}),0)
        self.assertEqual(len(self.s.rows('me')),1);self.assertEqual(D(self.s.rows('me')[0]['price']),3)
        self.assertEqual(self.s.capture(self.receipt(fresh,2,'0007'),{'T2_ORE'}),0)
    def test_screen_and_receipt_are_never_added_twice(self):
        self.s.watch('me','DemoCharacter','Fort Sterling',True)
        fresh=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat();self.s.capture(self.receipt(fresh),{'T2_ORE'})
        self.s.replace_page('me','Fort Sterling','bought',[dict(item_id='T2_ORE',quantity=10,cell=0)],'bought')
        rows=self.s.rows('me');self.assertEqual(len(rows),1);self.assertEqual(D(rows[0]['price']),3)
        self.assertEqual(self.s.capture(self.receipt(fresh,2),{'T2_ORE'}),0)
    def test_consumption_and_profile_record_undo_are_atomic(self):
        from app.progression import PlayerStore
        from app.trip_inventory import consumption_changes
        self.s.put('me','Thetford','manual:1',dict(item_id='T2_ORE',quantity=10,price='3',kind='base'))
        before=self.s.rows('me')[0];player=PlayerStore(Path(self.folder.name)/'player.sqlite')
        try:
            changes=consumption_changes(player.db,'me',[dict(before,used=7)])
            payload=dict(states_before={},states_after={'A':dict(level=1,xp=0)},stock_changes=changes)
            player.record('me',payload,payload['states_after']);self.assertEqual(self.s.rows('me')[0]['quantity'],3)
            player.undo_last('me');self.assertEqual(self.s.rows('me')[0]['quantity'],10);self.assertFalse(player.states('me'))
            player.record('me',payload,payload['states_after'])
            self.s.put('me','Thetford','manual:1',dict(before,quantity=20))
            with self.assertRaises(ValueError):player.undo_last('me')
            self.assertEqual(self.s.rows('me')[0]['quantity'],20);self.assertEqual(player.states('me'),payload['states_after'])
        finally:player.close()


if __name__=='__main__':unittest.main()
