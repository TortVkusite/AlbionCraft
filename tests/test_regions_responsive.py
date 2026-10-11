import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from app.regions import REGIONS,region_root,region_key
from app.api import AlbionAPI
from app.cache import Cache
from app.models import CITIES
from app.local_market import make_server,LocalStore

ROOT=Path(__file__).resolve().parents[1]


class RegionTests(unittest.TestCase):
    def test_stock_edits_validate_whole_batch_and_move_atomically(self):
        from app.trip_inventory import StockStore
        with tempfile.TemporaryDirectory() as folder:
            store=StockStore(Path(folder)/'player.sqlite')
            row=dict(city='Thetford',key='a',item_id='T2_ORE',quantity=5,price='16',kind='base')
            store.put('test',row['city'],row['key'],row)
            move=dict(row,city='Fort Sterling',kind='bought')
            with self.assertRaises(ValueError):store.save_edits('test',[(row,move),(row,dict(row,quantity=-1))])
            self.assertEqual([(r['city'],r['quantity']) for r in store.rows('test')],[('Thetford',5)])
            store.save_edits('test',[(row,move)])
            self.assertEqual([(r['city'],r['quantity']) for r in store.rows('test')],[('Fort Sterling',5)])
            store.close()
    def test_hosts_and_stream_ports_are_server_specific(self):
        self.assertEqual([v['port'] for v in REGIONS.values()],[34222,4222,24222])
        for region in REGIONS:
            api=AlbionAPI(region);urls=[];api.get=lambda url:urls.append(url) or []
            api.prices(['T2_ORE'],['Brecilien'],1);api.history(['T2_ORE'],['Brecilien'],1)
            self.assertEqual(len(urls),2)
            self.assertTrue(all(url.startswith(REGIONS[region]['host']+'/') for url in urls))
        self.assertEqual(region_key(1),'west')
        with self.assertRaises(ValueError):region_key('../europe')

    def test_europe_legacy_data_and_other_servers_stay_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'settings.json').write_text('{"progress_player":"Existing"}')
            for key,value in [('europe',100),('west',200),('east',300)]:
                path=region_root(base,key)
                cache=Cache(path/'prices.sqlite');cache.put('same-key',[value]);cache.close()
                (path/'player.sqlite').write_bytes(key.encode())
            self.assertEqual(region_root(base,'europe'),base)
            for key,value in [('europe',100),('west',200),('east',300)]:
                path=region_root(base,key);cache=Cache(path/'prices.sqlite')
                self.assertEqual(cache.get('same-key'),[value]);cache.close()
                self.assertEqual((path/'player.sqlite').read_bytes(),key.encode())
            self.assertEqual(json.loads((base/'settings.json').read_text())['progress_player'],'Existing')

    def test_receiver_rejects_unknown_or_wrong_server_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prices.sqlite';server=make_server(path,'secret',lambda count:None,0,'west')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            payload={'Orders':[dict(Id=1,ItemTypeId='T2_ORE',LocationId=5003,QualityLevel=1,EnchantmentLevel=0,
                UnitPriceSilver=160000,Amount=10,AuctionType='offer',Expires=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())]}
            def post(region=None,endpoint='marketorders.ingest'):
                headers={'Content-Type':'application/json'}
                if region is not None:headers['X-Albion-Server']=str(region)
                return urlopen(Request(f'http://127.0.0.1:{server.server_port}/secret/{endpoint}',
                    data=json.dumps(payload).encode(),headers=headers),timeout=3)
            try:
                for key,status in [(None,422),(3,409),(2,409)]:
                    for endpoint in ('marketorders.ingest','ownorders.ingest','markethistories.ingest'):
                        with self.assertRaises(HTTPError) as error:post(key,endpoint)
                        self.assertEqual(error.exception.code,status);error.exception.close()
                self.assertFalse(path.exists());self.assertFalse(path.with_name('player.sqlite').exists())
                with post(1) as response:self.assertEqual(response.status,200)
                store=LocalStore(path);self.assertEqual(store.prices()[0]['city'],'Brecilien');store.close()
            finally:server.shutdown();server.server_close();thread.join()

    def test_brecilien_bonus_and_transport_are_explicit(self):
        from app.catalog import load_catalog
        from app.rules import automatic_profile
        from app.trading import allowed_route
        self.assertIn('Brecilien',CITIES)
        recipes=load_catalog(ROOT)
        for uid in ('T4_BAG','T4_CAPE','T4_POTION_HEAL'):
            recipe=next(r for r in recipes if r.item_id==uid and r.variant==0)
            profile=automatic_profile(recipe,'Brecilien',{})
            self.assertEqual(D(profile['rrr']),D('.33')/D('1.33')*100)
        self.assertFalse(allowed_route('Thetford','Brecilien'))
        self.assertTrue(allowed_route('Thetford','Brecilien',brecilien=True))

    def test_snapshot_reads_latest_history_of_selected_item_only(self):
        from app.market_snapshot import market_snapshot
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache=Cache(root/'prices.sqlite')
            cache.put(json.dumps(['history_item_all','T2_ORE','2026-10-01']),[dict(item_id='T2_ORE',location='Thetford',quality=1,data=[1])])
            cache.put(json.dumps(['history_item_all','T2_ORE','2026-10-02']),[dict(item_id='T2_ORE',location='Thetford',quality=1,data=[2])])
            cache.put(json.dumps(['history_item_all','T3_ORE','2026-10-02']),[dict(item_id='T3_ORE',location='Thetford',quality=1,data=[3])]);cache.close()
            owner=SimpleNamespace(last=None,local_enabled=Mock());owner.local_enabled.isChecked.return_value=False
            _,history=market_snapshot(owner,root,{'T2_ORE'})
            self.assertEqual(len(history),1);self.assertEqual(history[0]['data'],[2])


class ResponsiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def pump(self,predicate,timeout=10):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.001)
        self.app.processEvents();self.assertTrue(predicate(),'Timed out waiting for GUI work')

    def test_virtual_choices_and_check_state_survive_model_replacement(self):
        from app.responsive import set_choices,CheckChoiceModel
        from app.i18n_widgets import QComboBox
        from PySide6.QtCore import Qt
        box=QComboBox();entries=[('Item '+str(n),n) for n in range(10000)]
        set_choices(box,entries);box.setCurrentIndex(9999);self.assertEqual(box.currentData(),9999)
        set_choices(box,entries[:10]);self.assertEqual(box.count(),10)
        model=CheckChoiceModel(entries,{9999});model.setData(model.index(1),Qt.Checked,Qt.CheckStateRole)
        self.assertEqual(model.checked,{1,9999});model.clear();self.assertEqual(model.checked,set())
        box.deleteLater()

    def test_settings_keep_general_profile_and_every_city(self):
        from PySide6.QtWidgets import QWidget
        from app.settings_dialog import SettingsDialog
        from app.catalog import load_catalog
        with tempfile.TemporaryDirectory() as folder:
            owner=QWidget();dialog=SettingsDialog(owner,load_catalog(ROOT)[:20],{},Path(folder)/'settings.json')
            self.assertIsNone(dialog.recipe.currentData());self.assertEqual(dialog.previous,'__general__')
            self.assertEqual(dialog.grid.rowCount(),len(CITIES));self.assertEqual(dialog.grid.item(len(CITIES)-1,0).text(),'Brecilien')
            dialog.reject();owner.deleteLater()

    def test_large_own_order_snapshot_yields_and_update_keeps_other_rows(self):
        from PySide6.QtWidgets import QWidget
        from PySide6.QtCore import QTimer
        from app.own_orders import OwnOrderStore
        from app.own_orders_dialog import OwnOrdersDialog
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'player.sqlite';store=OwnOrderStore(path)
            rows=[dict(Id=n,ItemTypeId='T2_ORE',Amount=1,UnitPriceSilver=160000,QualityLevel=1) for n in range(1000)]
            payload=dict(CharacterId='test',CharacterName='Test',LocationId='0007',Side='buy',Orders=rows)
            store.observe(payload)
            owner=QWidget();owner.settings=dict(tax='0',auto_rules=False);ticks=[]
            timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
            dialog=OwnOrdersDialog(owner,path)
            try:
                self.pump(lambda:not dialog.reloading and dialog.total_batch.pending is None,30)
                self.assertEqual(dialog.table.rowCount(),1000);self.assertGreater(len(ticks),5)
                before=len(ticks)
                store.observe(dict(payload,Orders=[dict(rows[0],Amount=2)]));dialog.reload_captured()
                self.pump(lambda:not dialog.reloading and dialog.total_batch.pending is None,30)
                self.assertEqual(dialog.table.rowCount(),1000)
                self.assertEqual(sum(e['quantity'] for e in dialog.entries()),1001)
                self.assertGreater(len(ticks),before)
                self.assertLess(max((b-a for a,b in zip(ticks,ticks[1:])),default=0),.5)
            finally:timer.stop();dialog.done(0);store.close();owner.deleteLater()

    def test_batches_yield_to_other_events_and_cancellation_discards_remainder(self):
        from app.responsive import GuiBatch
        from PySide6.QtCore import QTimer,QObject
        owner=QObject();batch=GuiBatch(owner,milliseconds=2);heartbeats=[];values=[]
        timer=QTimer();timer.setInterval(1);timer.timeout.connect(lambda:heartbeats.append(len(values)));timer.start()
        def work():
            for n in range(60):
                end=time.perf_counter()+.001
                while time.perf_counter()<end:pass
                values.append(n);yield
        batch.start(work());self.pump(lambda:batch.pending is None)
        self.assertEqual(values,list(range(60)));self.assertGreater(len(heartbeats),5)
        self.assertTrue(any(0<n<60 for n in heartbeats))
        batch.start(iter(range(10000)));batch.cancel();self.app.processEvents();self.assertIsNone(batch.pending)
        timer.stop()

    def test_armor_hierarchy_opens_at_most_two_cards_and_preserves_edits(self):
        from PySide6.QtWidgets import QWidget
        from app.catalog import load_catalog
        from app.destiny_dialog import DestinyDialog,BoardNode
        from app.i18n import set_language
        set_language('ru')
        with tempfile.TemporaryDirectory() as folder:
            owner=QWidget();owner.settings={};owner.persist_view=lambda:None;owner.icons=None
            dialog=DestinyDialog(owner,Path(folder),load_catalog(ROOT))
            try:
                dialog.mode.setCurrentIndex(dialog.mode.findData('COMBAT'));dialog.select_category('Броня')
                self.pump(lambda:dialog.draw_batch.pending is None)
                self.assertEqual(len([n for n in dialog.scene.items() if isinstance(n,BoardNode)]),4)
                dialog.select_section('Тканевая');self.pump(lambda:dialog.draw_batch.pending is None)
                branch=next(b for b in dialog.branches if b.mode=='COMBAT' and b.key=='COMBAT_CLOTH_HEADS')
                dialog.select_branch(branch);self.assertEqual(len(dialog.cards),1)
                nodes=[n for n in branch.nodes if n!=branch.root]
                dialog.focus_card(nodes[0]);dialog.cards[nodes[0]][0].setValue(3)
                dialog.focus_card(nodes[1]);self.assertEqual(len(dialog.cards),2)
                self.assertEqual(dialog.store.states(dialog.active_player)[nodes[0]]['level'],3)
                dialog.navigate('category');self.assertIsNone(dialog.section);self.assertIsNone(dialog.branch)
            finally:dialog.done(0);owner.deleteLater()

    def test_isolated_trip_matches_direct_solver_and_worker_failure_is_reported(self):
        from app.background import ProcessWorker
        from app.trip_task import calculate_trip
        from app.catalog import load_catalog
        from PySide6.QtCore import QTimer
        recipe=next(r for r in load_catalog(ROOT) if r.item_id=='T2_METALBAR')
        stamp=datetime.now(timezone.utc).isoformat()
        prices=[dict(item_id=uid,city=city,quality=1,sell_price_min=value,sell_price_min_date=stamp)
            for uid,value in [('T2_ORE',16),('T2_METALBAR',22)] for city in ('Fort Sterling','Thetford')]
        data=dict(root=str(ROOT),stock_rows=[],buy='Fort Sterling',city='Thetford',prices=prices,histories=[],age=30,
            joint=True,roots={recipe.item_id},recipes=[recipe],settings=dict(auto_rules=True,other='0',tax='0',setup='0'),states={},
            day_bonus=D(0),rate=D(0),other=D(0),multiplier=D(1),mastery=False,limits={recipe.item_id:20},depth='quote',
            horizon=0,share=10,budget=1000,weight=1000,focus=100,repeat=True,objective='profit')
        direct=calculate_trip(data);self.assertTrue(direct['plans'][0]['lines'])
        worker=ProcessWorker('trip',data);results=[];errors=[];ticks=[]
        timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
        worker.ready.connect(results.append);worker.failed.connect(errors.append);worker.start()
        self.pump(lambda:not worker.isRunning(),30);timer.stop();self.assertFalse(errors);self.assertEqual(len(results),1)
        self.assertEqual([p['profit'] for p in direct['plans']],[p['profit'] for p in results[0]['plans']]);self.assertGreater(len(ticks),5)
        self.assertLess(max((b-a for a,b in zip(ticks,ticks[1:])),default=0),.25)
        broken=ProcessWorker('invalid',{});failures=[];broken.failed.connect(failures.append);broken.start()
        self.pump(lambda:not broken.isRunning());self.assertTrue(failures)
        cancelled=ProcessWorker('trip',data);emitted=[];cancelled.ready.connect(emitted.append);cancelled.start();cancelled.requestInterruption()
        self.pump(lambda:not cancelled.isRunning());self.assertFalse(emitted)

    def test_background_scan_keeps_results_beyond_first_page(self):
        from dataclasses import replace
        from app.catalog import load_catalog
        from app.scan_result import calculate_view
        recipe=next(r for r in load_catalog(ROOT) if r.item_id=='T2_METALBAR')
        recipes=[replace(recipe,item_id='TEST_'+str(n),base_id='TEST_'+str(n)) for n in range(250)]
        stamp=datetime.now(timezone.utc).isoformat()
        prices=[dict(item_id=r.item_id,city='Thetford',quality=1,buy_price_max=10,sell_price_min=20,
            buy_price_max_date=stamp,sell_price_min_date=stamp) for r in recipes]
        result=calculate_view(dict(recipes=recipes,settings=dict(setup='0',tax='0',other='0',prefer_upgrades=False),activity='flip',
            prices=prices,histories=[],quality=1,age=30,buy=['Thetford'],craft=['Thetford'],sell=['Thetford'],demand=None,
            with_prices=True,sort='profit',descending=True))
        self.assertEqual(len(result['rows']),250);self.assertEqual(len(result['recommendations']),250)


if __name__=='__main__':unittest.main()
