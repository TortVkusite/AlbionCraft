import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from tests.test_own_capture import payload
from app.own_orders import OwnOrderStore,order_totals
from app.order_time import remaining_time


class OrderEventTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.store=OwnOrderStore(Path(self.folder.name)/'player.sqlite')
    def tearDown(self):self.store.close();self.folder.cleanup()
    def action(self,action,**extra):return dict(CharacterId='owner',CharacterName='Персонаж',LocationId='0007',Side='buy',Action=action,Confirmed=True,**extra)
    def test_confirmed_creation_only_and_duplicate_upsert(self):
        p=payload();p.update(Action='created',Confirmed=False)
        with self.assertRaises(ValueError):self.store.observe(p)
        self.assertEqual(self.store.orders(),[])
        p['Confirmed']=True;self.store.observe(p);self.store.observe(p)
        self.assertEqual(len(self.store.orders()),1)
        self.assertEqual(order_totals(self.store.orders(),8)['buy'],5150)
    def test_cancel_only_target_and_no_resurrection_by_old_page(self):
        self.store.observe(payload(key=1));self.store.observe(payload(key=2))
        self.store.observe(self.action('cancelled',OrderIds=[1]))
        self.assertEqual(order_totals(self.store.orders(),8)['buy'],5150)
        self.store.observe(payload(key=1));self.store.new_snapshot();self.store.observe(payload(key=2))
        self.assertEqual(next(o for o in self.store.orders() if o['order_id']=='1')['status'],'cancelled')
        self.assertEqual(order_totals(self.store.orders(),8)['active'],1)
    def test_cancel_before_first_seen_page_and_owner_isolation(self):
        self.store.observe(self.action('cancelled',OrderIds=[1]));self.store.observe(payload(key=1));self.store.observe(payload(key=1,owner='other'))
        self.assertEqual(self.store.orders(owner='owner')[0]['status'],'cancelled')
        self.assertEqual(self.store.orders(owner='other')[0]['status'],'active')
    def mail(self):
        return self.action('mail',Mail=dict(Id=50,Type='MARKETPLACE_BUYORDER_FINISHED_SUMMARY',LocationId='0007',Received=datetime.now(timezone.utc).isoformat(),Body='10|T3_2H_BOW|51500000|5150000'))
    def test_mail_exact_unique_match_and_dedup(self):
        p=payload(key=1);p['Orders'][0]['Expires']=(datetime.now(timezone.utc)+timedelta(days=29)).isoformat();self.store.observe(p)
        event=self.mail();self.assertEqual(self.store.observe(event),1);self.assertEqual(self.store.observe(event),0)
        self.assertEqual(order_totals(self.store.orders(),8)['active'],0)
    def test_mail_ambiguity_and_old_mail_never_close_new_order(self):
        p=payload(key=1);p['Orders'][0]['Expires']=(datetime.now(timezone.utc)+timedelta(days=29)).isoformat();self.store.observe(p)
        p['Orders'][0]['Id']=2;self.store.observe(p)
        self.assertEqual(self.store.observe(self.mail()),0)
        self.assertEqual(order_totals(self.store.orders(),8)['active'],2)
        event=self.mail();event['Mail']['Received']=(datetime.now(timezone.utc)-timedelta(days=5)).isoformat()
        self.assertEqual(self.store.observe(event),0)
    def test_incomplete_creation_does_not_invent_numbers(self):
        self.assertEqual(self.store.observe(self.action('created',Orders=[],Request={'0':123})),0)
        self.assertEqual(self.store.orders(),[]);self.assertIn('точного',self.store.capture_status())
    def test_partial_update_keeps_other_orders_and_cost(self):
        self.store.observe(payload(key=1));self.store.observe(payload(key=2))
        rows=self.store.orders();rows[0]['cost']='100';self.store.save(rows)
        self.store.observe(payload(key=1,amount=3))
        first,second=self.store.orders();self.assertEqual((first['quantity'],first['original_quantity'],first['cost']),(3,10,'100'));self.assertEqual(second['quantity'],10)
    def test_time_days_hours_tooltip_seconds(self):
        now=datetime(2026,10,5,12,tzinfo=timezone.utc)
        expires=now+timedelta(days=2,hours=3,minutes=4,seconds=5)
        text,tip,value=remaining_time({'expires':expires.isoformat()},now)
        self.assertEqual(text,'2 д 3 ч');self.assertIn('4 мин 5 с',tip);self.assertEqual(value,183845)
        self.assertEqual(remaining_time({})[0],'Неизвестно')
