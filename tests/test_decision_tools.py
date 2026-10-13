import unittest,tempfile,json,sqlite3,zipfile,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from app.market_memory import MarketMemory,archive_prices,archive_volumes,sale_scenario,calibration
from app.trip_inventory import StockStore,consumption_changes
from app.profile_backup import backup,stage_restore,apply_restore,diagnostic
from app.island_planner import animal_risk,payback
from app.catalog_visibility import available,name_key

class Decisions(unittest.TestCase):
    def test_second_instance_raises_existing_window_through_local_channel(self):
        import os,time,subprocess,sys
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        from app.desktop import single_instance
        app=QApplication.instance() or QApplication([])
        class Target:
            count=0
            def showNormal(self):self.count+=1
            def raise_(self):pass
            def activateWindow(self):pass
        target=Target();app._albioncraft_window=target
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(single_instance(app,Path(folder)));server=app._instance_server
            try:
                code="from PySide6.QtCore import QCoreApplication; from app.desktop import single_instance; from pathlib import Path; import sys; app=QCoreApplication([]); sys.exit(0 if not single_instance(app,Path(sys.argv[1])) else 1)"
                child=subprocess.Popen([sys.executable,'-c',code,folder],creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                end=time.monotonic()+10
                while child.poll() is None and time.monotonic()<end:app.processEvents();time.sleep(.005)
                if child.poll() is None:child.kill();child.wait();self.fail('Second instance timed out')
                app.processEvents();self.assertEqual(child.returncode,0);self.assertEqual(target.count,1)
            finally:server.close();server.deleteLater();app._albioncraft_window=None
    def test_restore_retry_keeps_original_recovery_backup(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);settings=root/'settings.json';settings.write_text('{"premium":true}')
            (root/'app_preferences.json').write_text('{"desktop":{"startup":true}}')
            backup(root,root/'backup.zip');settings.write_text('{}');(root/'app_preferences.json').write_text('{"desktop":{"startup":false}}');stage_restore(root,root/'backup.zip')
            original=Path.replace
            def failure(source,target):
                if Path(target)==settings:raise OSError('Simulated interruption')
                return original(source,target)
            with patch.object(Path,'replace',failure),self.assertRaises(OSError):apply_restore(root)
            before=(root/'before-restore.zip').read_bytes();self.assertTrue(apply_restore(root))
            self.assertEqual((root/'before-restore.zip').read_bytes(),before)
            self.assertFalse(json.loads((root/'app_preferences.json').read_text())['desktop']['startup'])
    def test_active_daily_and_event_bonuses_stack_but_repeat_confirmation_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            store=MarketMemory(Path(folder)/'prices.sqlite');now=datetime.now(timezone.utc)
            try:
                start=(now-timedelta(hours=1)).isoformat();end=(now+timedelta(hours=1)).isoformat()
                store.add_bonus('ore',10,start,end,'Daily');store.add_bonus('ore',10,start,end,'Daily reread')
                store.add_bonus('ore',20,start,(now+timedelta(days=2)).isoformat(),'Event')
                self.assertEqual(store.active(now)['ore']['percent'],30)
                self.assertEqual(store.active(now+timedelta(hours=2))['ore']['percent'],20)
                store.remove_bonus(store.bonuses()[0]['id']);self.assertEqual(len(store.bonuses()),1)
            finally:store.close()
    def test_calibration_backtest_follows_completion_order_not_creation_order(self):
        snapshot=dict(buy='Fort Sterling',craft='Thetford',profit='100',revenue='100',sale_fees='0',purchase='0',stock='0',station='0',other='0',rows=[dict(kind='sale',item_id='T2_METALBAR',quantity='1')])
        now=datetime.now(timezone.utc);entries=[]
        for n in range(11):
            facts=dict(closed=True,completed_at=(now+timedelta(hours=n)).isoformat(),station='0',other='0',sale_fees='0',rows=[dict(kind='sale',item_id='T2_METALBAR',quantity=1,amount=500 if n==10 else 100)])
            entries.append(dict(id=11-n,snapshot=snapshot,facts=facts))
        result=calibration(entries)
        self.assertEqual(result['backtest_count'],1);self.assertEqual(result['backtest_mae'],400)
    def test_farming_bonus_snapshot_is_generated_from_game_modifiers(self):
        from app.island import farming_data
        table=farming_data()['bonuses']
        self.assertIn('T1_CARROT',table['Lymhurst']);self.assertIn('T2_AGARIC',table['Thetford'])
        self.assertEqual(set(table['Caerleon']),{'T3_COMFREY','T5_TEASEL','T7_MULLEIN'})
        self.assertEqual(len(table['Brecilien']),8)
    def test_startup_command_is_hidden_and_background_mode_is_explicit(self):
        from unittest.mock import patch
        from app.desktop import startup_command,game_running
        with patch('sys.frozen',True,create=True),patch('sys.executable',r'C:\Program Files\AlbionCraft\AlbionCraft.exe'):
            self.assertEqual(startup_command(),'"C:\\Program Files\\AlbionCraft\\AlbionCraft.exe" --background')
        self.assertIsInstance(game_running(),bool)
    def test_catalog_requires_explicit_evidence_and_keeps_unlock_flags(self):
        self.assertTrue(available({'@uniquename':'T4_MAIN_SWORD','@unlockedtocraft':'false','@unlockedtoequip':'false'}))
        self.assertFalse(available({'@uniquename':'T8_ARMOR_CLOTH_PROTOTYPE'}))
        self.assertFalse(available({'@uniquename':'T4_TEST','@showinmarketplace':'false'}))
        self.assertTrue(available({'@uniquename':'T4_TEST_DECAY'}))
        self.assertEqual(name_key({'@uniquename':'T4_TEST_DECAY','@namelocatag':'@ITEMS_T4_TEST'}),'T4_TEST')
    def test_reservations_are_atomic_and_own_plan_can_replan(self):
        with tempfile.TemporaryDirectory() as folder:
            store=StockStore(Path(folder)/'player.sqlite')
            try:
                store.put('p','Thetford','a',dict(item_id='T2_ORE',quantity=10,price='15',kind='base'))
                store.reserve('p',1,[dict(city='Thetford',key='a',quantity=7)])
                self.assertEqual(store.available_rows('p')[0]['quantity'],3)
                self.assertEqual(store.available_rows('p',1)[0]['quantity'],10)
                with self.assertRaises(ValueError):store.reserve('p',2,[dict(city='Thetford',key='a',quantity=4)])
                row=store.available_rows('p')[0];row['used']=2
                self.assertEqual(json.loads(consumption_changes(store.db,'p',[row])[0]['after'])['quantity'],8)
                store.release('p',1);self.assertEqual(store.available_rows('p')[0]['quantity'],10)
                store.reserve('p',1,[dict(city='Thetford',key='a',quantity=7,item_id='T2_ORE')])
                store.delete('p','Thetford','a');store.put('p','Thetford','b',dict(item_id='T2_ORE',quantity=10,price='15',kind='base'))
                self.assertEqual(store.available_rows('p')[0]['quantity'],3)
                with self.assertRaises(ValueError):store.reserve('p',2,[dict(city='Thetford',key='b',quantity=1,item_id='T3_ORE')])
            finally:store.close()
    def test_archive_deduplicates_quotes_and_does_not_invent_future_data(self):
        with tempfile.TemporaryDirectory() as folder:
            store=MarketMemory(Path(folder)/'prices.sqlite');now=datetime.now(timezone.utc)
            try:
                row=dict(item_id='T2_ORE',city='Thetford',quality=1,sell_price_min=22,sell_price_min_date=now.isoformat())
                archive_prices(store.db,[row,row,dict(row,sell_price_min_date=(now+timedelta(days=1)).isoformat())]);store.db.commit()
                self.assertEqual(len(store.timeline('T2_ORE','Thetford')),1);self.assertEqual(store.timeline('T2_ORE','Martlock'),[])
                history=dict(item_id='T2_ORE',location='Thetford',quality=1,data=[dict(timestamp=now.isoformat(),item_count=50,avg_price=20),1])
                archive_volumes(store.db,[history]);archive_volumes(store.db,[history],'Local');store.db.commit()
                self.assertEqual(sum(r['count'] for r in store.volumes('T2_ORE','Thetford')),50)
                store.add_bonus('ore',20,(now-timedelta(hours=1)).isoformat(),(now+timedelta(hours=1)).isoformat(),'Game')
                self.assertEqual(store.active(now)['ore']['percent'],20);self.assertEqual(store.active(now+timedelta(hours=2)),{})
            finally:store.close()
    def test_sale_scenarios_are_explicit_and_not_probabilities(self):
        s=sale_scenario(100,1000,10,12)
        self.assertEqual(s['days'],1);self.assertEqual(s['remaining'],50);self.assertEqual(s['slow_days'],2)
        self.assertIsNone(sale_scenario(100,None)['days'])
    def test_exact_animal_distribution_matches_expected_economics(self):
        p=dict(kind='wild',seed_return='0',focus_bonus='.1',actions=3)
        r=dict(profit=D(40),count=2,focused=2,revenue=D(200),feed_cost=D(0),seed_price=D(100))
        risk=animal_risk(p,r)
        self.assertAlmostEqual(sum(x['probability'] for x in risk['outcomes']),D(1))
        self.assertEqual(risk['expected'],60);self.assertEqual(risk['positive'],D('.51'));self.assertEqual(risk['p10'],0)
        self.assertEqual(payback(100,10,22)['days'],10)
    def test_backup_restores_database_and_rejects_paths_and_preserves_desktop_consent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'settings.json').write_text(json.dumps({'premium':True,'local_token':'private'}))
            (root/'app_preferences.json').write_text(json.dumps({'desktop':{'startup':True,'auto_client':True}}))
            db=sqlite3.connect(root/'player.sqlite');db.execute('CREATE TABLE test (value TEXT)');db.execute("INSERT INTO test VALUES('secret-player')");db.commit();db.close()
            backup(root,root/'backup.zip');(root/'settings.json').write_text('{}')
            (root/'app_preferences.json').write_text(json.dumps({'desktop':{'startup':False}}))
            stage_restore(root,root/'backup.zip');self.assertTrue(apply_restore(root));self.assertTrue(json.loads((root/'settings.json').read_text())['premium'])
            self.assertEqual(json.loads((root/'app_preferences.json').read_text())['desktop'],{'startup':False})
            self.assertNotIn('secret-player',json.dumps(diagnostic(root)));self.assertNotIn('private',json.dumps(diagnostic(root)))
            value=b'{}';name='../evil.json'
            with zipfile.ZipFile(root/'bad.zip','w') as z:z.writestr(name,value);z.writestr('manifest.json',json.dumps(dict(version=1,files={name:hashlib.sha256(value).hexdigest()})))
            with self.assertRaises(ValueError):stage_restore(root,root/'bad.zip')
