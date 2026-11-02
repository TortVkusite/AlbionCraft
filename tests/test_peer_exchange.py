import json
import hashlib
import iroh
import struct
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from app.peer_store import PeerStore,now,canonical
from app.peer_market import CapturePublisher,shared_market,merge_shared
from app.peer_network import PeerNode,receive,MAX_FRAME


def page(price=1200):
    return dict(item='T4_MAIN_SWORD',city='Thetford',quality=1,side='sell_price_min',
        orders=[dict(id='42',price=price,amount=12,expires=(now()+timedelta(days=10)).isoformat())])


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.a=PeerStore(self.root/'a');self.b=PeerStore(self.root/'b')
        self.a.create_group();self.b.set_group(self.a.group())

    def tearDown(self):
        self.a.close();self.b.close();self.tmp.cleanup()

    def event(self,price=1200,at=None,region='europe'):
        return self.a.publish(region,'orders',page(price),at or now().isoformat())

    def test_identity_and_group_survive_restart_without_plaintext_secrets(self):
        identity=str(self.a.identity().public());group=self.a.group()
        self.a.close();self.a=PeerStore(self.root/'a')
        self.assertEqual(identity,str(self.a.identity().public()));self.assertEqual(group,self.a.group())
        self.assertNotIn(group['key'],str(self.a.get('group')))

    def test_forward_preserves_identity_time_and_is_idempotent(self):
        event=self.event();self.assertTrue(self.b.receive(event));self.assertFalse(self.b.receive(event))
        self.assertEqual(self.b.event(event['id']),event);self.assertEqual(len(self.b.inventory()),1)

    def test_tampering_does_not_enter_mailbox(self):
        e=self.event();e['data']['orders'][0]['price']=999
        with self.assertRaises(ValueError):self.b.receive(e)
        self.assertEqual(self.b.inventory(),[])

    def test_rehashed_tampered_payload_still_fails_original_signature(self):
        e=self.event();e['data']['orders'][0]['price']=999;e.pop('id')
        e['id']=hashlib.sha256(canonical(e)).hexdigest()
        with self.assertRaises(iroh.IrohError):self.b.receive(e)
        self.assertEqual(self.b.inventory(),[])

    def test_other_group_cannot_insert_signed_event(self):
        with tempfile.TemporaryDirectory() as folder:
            foreign=PeerStore(folder)
            try:
                foreign.create_group()
                with self.assertRaises(ValueError):foreign.receive(self.event())
            finally:foreign.close()

    def test_out_of_order_updates_choose_newest_and_supersede_pending(self):
        old=self.event(at=(now()-timedelta(minutes=2)).isoformat());new=self.event(1800)
        self.b.receive(new);self.b.receive(old);self.assertEqual(self.b.inventory(),[new['id']])
        self.b.prune();self.assertEqual(self.b.stats()['records'],1)

    def test_invalid_extra_fields_never_export_personal_data(self):
        p=page();p['bank']=[1,2]
        with self.assertRaises(ValueError):self.a.publish('europe','orders',p,now().isoformat())
        p=page();p['orders'][0]['character']='private'
        with self.assertRaises(ValueError):self.a.publish('europe','orders',p,now().isoformat())

    def test_expired_future_or_wrong_unit_records_rejected(self):
        with self.assertRaises(ValueError):self.event(at=(now()-timedelta(days=2)).isoformat())
        with self.assertRaises(ValueError):self.event(at=(now()+timedelta(hours=1)).isoformat())
        p=page();p['orders'][0]['price']=True
        with self.assertRaises(ValueError):self.a.publish('europe','orders',p,now().isoformat())

    def test_local_capture_export_does_not_repeat_or_read_private_tables(self):
        from app.local_market import LocalStore
        path=self.root/'a'/'prices.sqlite';store=LocalStore(path)
        time=now().isoformat();expiry=(now()+timedelta(days=10)).isoformat()
        store.save([('42','T4_MAIN_SWORD','Thetford',1,'sell_price_min',1200,12,time,expiry)])
        store.db.execute('CREATE TABLE private_data(secret TEXT)');store.db.execute("INSERT INTO private_data VALUES('PRIVATE_TOKEN')");store.db.commit();store.close()
        pub=CapturePublisher(self.a,path,'europe');self.assertEqual(pub.poll(),1);self.assertEqual(pub.poll(),0)
        self.assertEqual(CapturePublisher(self.a,path,'europe').poll(),0)
        e=self.a.event(self.a.inventory()[0]);self.assertNotIn('PRIVATE_TOKEN',json.dumps(e));self.assertEqual(e['data']['orders'][0]['price'],1200)

    def test_history_capture_preserves_period_and_daily_units(self):
        from app.local_market import LocalStore
        path=self.root/'a'/'prices.sqlite';store=LocalStore(path)
        history=dict(item_id='T4_MAIN_SWORD',location='Thetford',quality=1,observed=now().isoformat(),period_days=7,bucket_hours=6,
            data=[dict(timestamp=(now()-timedelta(hours=8)).isoformat(),item_count=70,avg_price=1200,bucket_hours=6)])
        store.save_history(history);store.close();self.assertEqual(CapturePublisher(self.a,path,'europe').poll(),1)
        self.b.receive(self.a.event(self.a.inventory()[0]));_,histories=shared_market(self.root/'b'/'peer-sync.sqlite','europe')
        self.assertEqual(histories[0]['period_days'],7);self.assertEqual(histories[0]['data'][0]['item_count'],70)

    def test_region_and_price_source_remain_separate(self):
        self.b.receive(self.event());self.b.receive(self.event(2000,region='east'))
        prices,_=shared_market(self.root/'b'/'peer-sync.sqlite','europe');self.assertEqual(prices[0]['sell_price_min'],1200)
        self.assertTrue(prices[0]['sell_price_min_source'].startswith('P2P:'))
        original=dict(item_id='T4_MAIN_SWORD',city='Thetford',quality=1,sell_price_min=999,sell_price_min_date=(now()+timedelta(seconds=1)).isoformat())
        self.assertEqual(merge_shared([original],prices)[0]['sell_price_min'],999)
        original['sell_price_min_date']=(now()+timedelta(hours=1)).isoformat()
        self.assertEqual(merge_shared([original],prices)[0]['sell_price_min'],1200)

    def test_own_export_is_not_mislabeled_as_a_peer_observation(self):
        self.event()
        self.assertEqual(shared_market(self.root/'a'/'peer-sync.sqlite','europe'),([],[]))

    def test_expiry_and_capacity_bound_durable_queue(self):
        event=self.event();self.b.receive(event)
        with patch('app.peer_store.now',return_value=now()+timedelta(days=2)):self.b.prune()
        self.assertEqual(self.b.stats()['records'],0);self.b.receive(event)
        with patch('app.peer_store.MAX_BYTES',1):self.b.prune()
        self.assertEqual(self.b.stats()['records'],0)

    def test_receipts_are_durable_and_leave_drops_group_records(self):
        e=self.event();self.b.receive(e);self.b.ack('test',e['id']);self.b.close();self.b=PeerStore(self.root/'b')
        self.assertEqual(self.b.db.execute('SELECT count(*) FROM receipts').fetchone()[0],1)
        self.b.leave();self.assertFalse(self.b.group());self.assertEqual(self.b.inventory(),[])


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_reader_rejects_oversize_before_allocating_body(self):
        class Stream:
            async def read_exact(self,size):
                self.assertion=size;return struct.pack('!I',MAX_FRAME+1)
        stream=Stream()
        with self.assertRaises(ValueError):await receive(stream)
        self.assertEqual(stream.assertion,4)

    async def test_partial_frame_disconnect_does_not_enter_mailbox(self):
        class Stream:
            calls=0
            async def read_exact(self,size):
                self.calls+=1
                if self.calls==1:return struct.pack('!I',100)
                raise EOFError('Disconnected')
        with self.assertRaises(EOFError):await receive(Stream())

    async def test_real_encrypted_connection_rejects_wrong_group_secret(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            sa=PeerStore(a);sa.create_group();sa.close();node1=PeerNode(a,local_only=True);await node1.start()
            sb=PeerStore(b);group=dict(node1.store.group());group['key']='0'*64;sb.set_group(group);sb.add_peer(node1.store.get('ticket'));sb.close()
            node1.store.publish('europe','orders',page(),now().isoformat());node2=PeerNode(b,local_only=True);await node2.start()
            try:
                await node2.pull(node2.store.peers()[0]);self.assertEqual(node2.store.inventory(),[]);self.assertTrue(node2.last_errors)
            finally:await node2.stop();await node1.stop()


if __name__=='__main__':unittest.main()
