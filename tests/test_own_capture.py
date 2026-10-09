import json,tempfile,unittest,threading
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.request import Request,urlopen
from app.own_orders import OwnOrderStore,order_totals,decode_own_orders
from app.local_market import make_server,LocalStore
from app.progression import GameProgression
from app.destiny import build_branches
from app.catalog import load_catalog

ROOT=Path(__file__).resolve().parents[1]
def payload(side='buy',owner='owner',amount=10,key=9007199254740993):
    return dict(CharacterId=owner,CharacterName='Персонаж',LocationId='0007',Side=side,Orders=[dict(Id=key,ItemTypeId='T3_2H_BOW',
        Amount=amount,UnitPriceSilver=5150000,QualityLevel=1,EnchantmentLevel=0,AuctionType='request' if side=='buy' else 'offer',
        Expires=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat())])

class CaptureTests(unittest.TestCase):
    def test_page_upsert_fixed_point_cost_preserved_and_owner_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            s=OwnOrderStore(Path(folder)/'player.sqlite');s.observe(payload());s.observe(payload())
            rows=s.orders();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['price'],'515');self.assertEqual(rows[0]['order_id'],'9007199254740993')
            rows[0]['cost']='200';s.save(rows);s.observe(payload(amount=6))
            self.assertEqual((s.orders()[0]['quantity'],s.orders()[0]['cost']),(6,'200'))
            s.observe(payload(key=123));self.assertEqual(len(s.orders()),2) # New page does not erase another page.
            s.observe(payload(owner='other'));self.assertEqual(len(s.orders(owner='owner')),2)
            self.assertEqual(order_totals(s.orders(owner='owner'),8)['buy'],8240)
            old=s.orders();p=payload();p['Orders'].append(dict(p['Orders'][0],UnitPriceSilver=-1))
            with self.assertRaises(ValueError):s.observe(p)
            self.assertEqual(s.orders(),old);s.close()
    def test_expiry_and_superseded_seed_do_not_fake_finished_orders(self):
        with tempfile.TemporaryDirectory() as folder:
            from app.own_orders import import_user_snapshot
            path=Path(folder)/'player.sqlite';import_user_snapshot(path);s=OwnOrderStore(path)
            s.observe(payload());self.assertEqual(len([r for r in s.orders() if r['source']=='manual']),4)
            p=payload(key=1);p['Orders'][0]['Expires']=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat();s.observe(p)
            self.assertEqual(next(r for r in s.orders() if r.get('order_id')=='1')['status'],'finished')
            self.assertEqual(order_totals([r for r in s.orders() if r['source']=='auto'],8)['buy'],5150);s.close()
    def test_private_http_ingest_does_not_become_public_quotes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prices.sqlite';events=[];server=make_server(path,'test',events.append,0)
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                request=Request(f'http://127.0.0.1:{server.server_port}/test/ownorders.ingest',data=json.dumps(payload()).encode(),headers={'Content-Type':'application/json'})
                self.assertEqual(urlopen(request).status,200)
                s=OwnOrderStore(path.with_name('player.sqlite'));self.assertEqual(len(s.orders()),1);s.close()
                quotes=LocalStore(path);self.assertEqual(quotes.prices(),[]);quotes.close();self.assertEqual(events,[])
            finally:server.shutdown();thread.join();server.server_close()
    def test_bad_metadata_not_interpreted_as_owned(self):
        for update in ({'CharacterId':''},{'Side':'offer'},{'LocationId':'unknown'}):
            p=payload();p.update(update)
            with self.assertRaises(ValueError):decode_own_orders(p)
    def test_new_snapshot_preserves_costs_and_finished_notifications_remove_reserve(self):
        with tempfile.TemporaryDirectory() as folder:
            s=OwnOrderStore(Path(folder)/'player.sqlite');s.observe(payload(side='sell'));rows=s.orders();rows[0]['cost']='150';s.save(rows)
            s.new_snapshot();self.assertEqual(order_totals(s.orders(),8)['active'],0)
            s.observe(payload(side='sell',amount=3));self.assertEqual(order_totals(s.orders(),8)['cost'],450)
            s.observe(dict(CharacterId='other',Orders=[{'Id':9007199254740993}],Finished=True));self.assertEqual(order_totals(s.orders(),8)['active'],1)
            s.observe(dict(CharacterId='owner',Orders=[{'Id':9007199254740993}],Finished=True));self.assertEqual(order_totals(s.orders(),8)['active'],0);s.close()
    def test_fresh_page_clears_failed_event_note_without_reconfirming_old_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            s=OwnOrderStore(Path(folder)/'player.sqlite');s.observe(payload(key=1));s.new_snapshot()
            s.observe(dict(CharacterId='owner',LocationId='0007',Side='sell',Action='created',Confirmed=True,Orders=None))
            self.assertIn('точного заказа',s.capture_status())
            s.observe(payload(key=2,amount=1))
            self.assertEqual({r['order_id']:r['status'] for r in s.orders()},{'1':'unconfirmed','2':'active'})
            self.assertEqual(order_totals(s.orders(),8)['buy'],515)
            self.assertIn('Получено с последней страницы: 1',s.capture_status());s.close()
    def test_expiry_does_not_replace_confirmed_cancellation(self):
        with tempfile.TemporaryDirectory() as folder:
            s=OwnOrderStore(Path(folder)/'player.sqlite');p=payload(key=1)
            p['Orders'][0]['Expires']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat();s.observe(p)
            s.observe(dict(CharacterId='owner',LocationId='0007',Side='buy',Action='cancelled',Confirmed=True,OrderIds=[1]))
            self.assertEqual(s.orders()[0]['status'],'cancelled');s.close()

class DestinyTests(unittest.TestCase):
    def test_each_game_node_occurs_in_one_branch_and_requirements_are_real(self):
        game=GameProgression(ROOT);branches=build_branches(game,load_catalog(ROOT))
        nodes=[k for b in branches for k in b.nodes]
        self.assertEqual(len(nodes),len(set(nodes)));self.assertEqual(set(nodes),set(game.nodes))
        self.assertTrue({'CRAFT','COMBAT','REFINE','GATHER','FARM'}<=set(b.mode for b in branches))
        sword=next(b for b in branches if b.key=='CRAFT_SWORDS')
        self.assertEqual(sword.label,'Мечи');self.assertEqual(sword.root,'CRAFT_SWORDS');self.assertIn('CRAFT_SWORDS_SWORD',sword.nodes)
        self.assertEqual(game.costs('CRAFT_AXES_AXE')[0],28848);self.assertEqual(game.costs('CRAFT_AXES_AXE')[4],33164)

if __name__=='__main__':unittest.main()
