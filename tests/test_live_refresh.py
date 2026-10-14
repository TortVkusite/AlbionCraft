import os,subprocess,sys,unittest,tempfile,json
from pathlib import Path
from datetime import datetime,timezone,timedelta


class LiveRefreshTests(unittest.TestCase):
    def test_capture_burst_and_database_lock_do_not_block_gui(self):
        code='''
import os,tempfile,json
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
 os.environ['ALBIONCRAFT_DATA_DIR']=folder
 from PySide6.QtWidgets import QApplication
 from app.main import Window
 from app.release_smoke import check_live_updates
 app=QApplication([])
 Window.stream_changed=lambda *a,**k:None
 Window.local_changed=lambda *a,**k:None
 Window.fetch=lambda *a,**k:None
 window=Window();window.load_timer.stop();window.stream_timer.stop()
 try:
  print(json.dumps(check_live_updates(app,window,folder)))
  import time
  calls=[];window.local_changed=lambda *a,**k:calls.append(time.monotonic())
  started=time.monotonic();window.local_stopped()
  assert not calls
  end=started+3
  while not calls and time.monotonic()<end:app.processEvents();time.sleep(.005)
  assert len(calls)==1 and calls[0]-started>=1.2, calls
 finally:
  window.close()
  import time
  end=time.monotonic()+6
  while window.live_refresh.worker and time.monotonic()<end:app.processEvents();time.sleep(.01)
  app.processEvents()
'''
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=40,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout.strip().splitlines()[-1]);self.assertEqual(value['packets'],100)
        self.assertLess(value['max_ui_delay'],.75)

    def test_busy_bonus_database_preserves_confirmed_rows_and_expiry(self):
        from app.market_memory import MarketMemory,bonus_settings
        from unittest.mock import patch
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);now=datetime.now(timezone.utc);memory=MarketMemory(root/'prices.sqlite')
            memory.add_bonus('ore',10,(now-timedelta(hours=1)).isoformat(),(now+timedelta(hours=1)).isoformat(),'Daily')
            memory.add_bonus('ore',20,(now-timedelta(hours=1)).isoformat(),(now+timedelta(hours=2)).isoformat(),'Event');memory.close()
            self.assertEqual(bonus_settings(root,{})['production_bonuses']['ore']['percent'],30)
            db=sqlite3.connect(root/'prices.sqlite');db.execute('BEGIN EXCLUSIVE')
            try:
                self.assertEqual(bonus_settings(root,{})['production_bonuses']['ore']['percent'],30)
                with patch('app.market_memory.datetime') as clock:
                    clock.now.return_value=now+timedelta(hours=1,minutes=5);clock.fromisoformat.side_effect=datetime.fromisoformat
                    self.assertEqual(bonus_settings(root,{})['production_bonuses']['ore']['percent'],20)
            finally:db.rollback();db.close()

    def test_old_snapshot_cannot_replace_new_api_or_disabled_local_data(self):
        from app.main import Window
        from types import SimpleNamespace
        old=dict(prices=[{'item_id':'old'}],histories=[])
        owner=SimpleNamespace(closing=False,last=old,live_context=lambda:(2,False,False),render=lambda:self.fail('Stale result rendered'))
        Window.live_received(owner,dict(context=(1,False,True),prices=[{'item_id':'stale'}],histories=[]))
        self.assertIs(owner.last,old)
