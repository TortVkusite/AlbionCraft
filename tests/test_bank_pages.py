import unittest,tempfile
from pathlib import Path
from app.trip_inventory import StockStore
from app.bank_pages import page_vector,locate_page,joined_state,complete_state


def viewport(values,columns=2):
    return [dict(cell=n,item_id=uid,quantity=qty) for n,(uid,qty) in enumerate(values)]


class BankTests(unittest.TestCase):
    def setUp(self):self.folder=tempfile.TemporaryDirectory();self.store=StockStore(Path(self.folder.name)/'player.sqlite')
    def tearDown(self):self.store.close();self.folder.cleanup()
    def merge(self,values,container='Банк',first=None,warnings=()):return self.store.merge_bank('me','Thetford','base',container,viewport(values),2,len(values),first,warnings)
    def test_overlapping_pages_count_identical_stacks_once_and_survive_reopen(self):
        full=[('T2_ORE',3),('T3_ORE',4),('T2_METALBAR',999),('T2_METALBAR',999),('T3_METALBAR',7),('T4_ORE',8),('T2_PLANKS',9),('T3_PLANKS',10)]
        self.merge(full[:6]);offset,state=self.merge(full[2:]);self.assertEqual(offset,2)
        self.merge(full[2:]);rows=self.store.rows('me');self.assertEqual(sum(r['quantity'] for r in rows if r['item_id']=='T2_METALBAR'),1998);self.assertEqual(len(rows),8)
        self.store.finish_bank('me','Thetford','base','Банк');self.store.close();self.store=StockStore(Path(self.folder.name)/'player.sqlite');self.assertTrue(self.store.bank_scans('me')[0]['complete'])
    def test_ambiguous_overlap_changes_nothing_until_manual_anchor(self):
        self.merge([('T2_ORE',999)]*6)
        before=self.store.rows('me')
        with self.assertRaises(ValueError):self.merge([('T2_ORE',999)]*4+[('T3_ORE',2)]*2)
        self.assertEqual(self.store.rows('me'),before)
        self.merge([('T2_ORE',999)]*4+[('T3_ORE',2)]*2,first=1);self.assertEqual(len(self.store.rows('me')),8)
    def test_separate_containers_and_reset_preserve_other_bank(self):
        self.merge([('T2_ORE',2)]*2);self.merge([('T2_ORE',3)]*2,'Другой банк')
        self.assertEqual(sum(r['quantity'] for r in self.store.rows('me')),10)
        self.store.start_bank('me','Thetford','base','Банк');self.assertEqual(sum(r['quantity'] for r in self.store.rows('me')),6)
        self.assertEqual(len(self.store.bank_scans('me')),1)
    def test_completion_rejects_holes_and_uncertain_cells(self):
        self.merge([('T2_ORE',2)]*2,first=2)
        with self.assertRaises(ValueError):self.store.finish_bank('me','Thetford','base','Банк')
        self.store.start_bank('me','Thetford','base','Банк');self.merge([('T2_ORE',2)]*2,warnings=['Ячейка 1: количество не распознано'])
        with self.assertRaises(ValueError):self.store.finish_bank('me','Thetford','base','Банк')
    def test_revisiting_slots_replaces_changed_quantity_and_invalidates_complete(self):
        self.merge([('T2_ORE',2)]*2);self.store.finish_bank('me','Thetford','base','Банк')
        self.merge([('T2_ORE',5)]*2,first=0);self.assertEqual(sum(r['quantity'] for r in self.store.rows('me')),10)
        self.assertFalse(self.store.bank_scans('me')[0]['complete'])
    def test_receipt_cost_is_recovered_when_total_is_only_known_after_more_pages(self):
        self.store.put('me','Fort Sterling','mail:1',dict(item_id='T2_ORE',quantity=10,price='3',kind='bought'))
        self.store.merge_bank('me','Fort Sterling','bought','Банк',viewport([('T2_ORE',4),('T3_ORE',1)]),2,2,0)
        ore=next(r for r in self.store.rows('me') if r['item_id']=='T2_ORE');self.assertIsNone(ore['price'])
        self.store.put('me','Fort Sterling',ore['key'],dict(ore,price='7',valuation_estimated=True))
        self.store.merge_bank('me','Fort Sterling','bought','Банк',viewport([('T2_ORE',6),('T4_ORE',1)]),2,2,1)
        self.assertTrue(all(r['price']=='3' and not r['valuation_estimated'] for r in self.store.rows('me') if r['item_id']=='T2_ORE'))
    def test_consumption_invalidates_complete_snapshot_and_undo_restores_it(self):
        from app.progression import PlayerStore
        from app.trip_inventory import consumption_changes
        self.merge([('T2_ORE',2),('T3_ORE',3)]);self.store.finish_bank('me','Thetford','base','Банк')
        player=PlayerStore(Path(self.folder.name)/'player.sqlite')
        try:
            changes=consumption_changes(player.db,'me',[dict(r,used=1) for r in self.store.rows('me')]);player.record('me',dict(stock_changes=changes))
            self.assertFalse(self.store.bank_scans('me')[0]['complete']);player.undo_last('me');self.assertTrue(self.store.bank_scans('me')[0]['complete'])
        finally:player.close()
    def test_same_city_container_cannot_be_counted_as_both_base_and_bought(self):
        self.merge([('T2_ORE',2),('T3_ORE',3)])
        with self.assertRaises(ValueError):self.store.merge_bank('me','Thetford','bought','Банк',viewport([('T2_ORE',2),('T3_ORE',3)]),2,2,0)
        self.assertEqual(sum(r['quantity'] for r in self.store.rows('me')),5)
