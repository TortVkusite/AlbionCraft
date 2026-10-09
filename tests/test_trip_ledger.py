import unittest,tempfile
from pathlib import Path
from decimal import Decimal as D
from tests.test_trip_inventory import options
from app.trip_chain import solve_chain
from app.trip_ledger import plan_snapshot,actual_summary,TripLedger
from app.progression import PlayerStore


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'player.sqlite';self.store=TripLedger(self.path)
        self.snapshot=plan_snapshot(solve_chain(options(D(3)),30,5),'Fort Sterling','Thetford')
    def tearDown(self):self.store.close();self.folder.cleanup()
    def facts(self):
        return dict(rows=[dict(r,quantity=str(int(D(r['quantity']))) if r['kind']=='leftover' else r['quantity'],amount=r['amount'] or '') for r in self.snapshot['rows']],station=self.snapshot['station'],other='0',sale_fees=self.snapshot['sale_fees'],closed=True)
    def test_forecast_is_not_automatically_fact(self):
        run=self.store.create('me',self.snapshot);s=actual_summary(self.snapshot,{})
        self.assertIsNone(s['profit']);self.assertTrue(s['missing'])
        with self.assertRaises(ValueError):self.store.save('me',run,dict(closed=True))
    def test_repeated_updates_do_not_duplicate_journal_and_restore_incomplete(self):
        run=self.store.create('me',self.snapshot);facts=self.facts()
        self.store.save('me',run,facts);self.store.save('me',run,facts)
        p=PlayerStore(self.path)
        try:
            self.assertEqual(len(p.entries('me')),1);self.assertFalse(p.states('me'))
            self.store.save('me',run,dict(facts,closed=False));self.assertFalse(p.entries('me'))
        finally:p.close()
    def test_actual_delta_matches_component_explanation(self):
        facts=self.facts();facts['station']=str(D(facts['station'])+2)
        sold=next(r for r in facts['rows'] if r['kind']=='sale');sold['amount']=str(D(sold['amount'])-10)
        s=actual_summary(self.snapshot,facts)
        self.assertEqual(s['delta'],-12);self.assertEqual(sum(s['changes'].values()),s['delta'])
    def test_unknown_zero_and_negative_are_distinct(self):
        facts=self.facts();facts['sale_fees']='';self.assertIsNone(actual_summary(self.snapshot,facts)['profit'])
        facts['sale_fees']='0';self.assertIsNotNone(actual_summary(self.snapshot,facts)['profit'])
        facts['other']='-1'
        with self.assertRaises(ValueError):actual_summary(self.snapshot,facts)
    def test_data_survives_reopen_and_is_player_scoped(self):
        run=self.store.create('me',self.snapshot);self.store.save('me',run,self.facts());self.store.close();self.store=TripLedger(self.path)
        self.assertTrue(self.store.entries('me')[0]['facts']['closed']);self.assertFalse(self.store.entries('other'))
    def test_independent_plan_still_has_purchase_rows_and_cash_profit(self):
        from app.trip_optimizer import solve
        c=options(D(3))[0];c.purchase=D(3);c.weight=D(1);c.row['buy']='Fort Sterling'
        c.plain.update(profit=D(16),sale=D(20),fees=D(0),fixed=D(0),returned=D(0))
        p=solve([c],30,5);snapshot=plan_snapshot(p,'Fort Sterling','Thetford')
        self.assertTrue(any(r['kind']=='purchase' for r in snapshot['rows']))
    def test_unplanned_resource_reopens_accounting_and_can_be_entered(self):
        run=self.store.create('me',self.snapshot);self.store.save('me',run,self.facts())
        self.store.add_row('me',run,'purchase','T3_ORE');entry=self.store.entries('me')[0]
        self.assertFalse(entry['facts']['closed']);self.assertIsNone(actual_summary(entry['snapshot'],entry['facts'])['profit'])
        facts=self.facts();facts['rows'].append(dict(kind='purchase',item_id='T3_ORE',quantity='1',amount='2'))
        s=self.store.save('me',run,facts);self.assertEqual(s['delta'],-2)
