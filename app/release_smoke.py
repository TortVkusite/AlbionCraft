"""Offline release checks: never read an existing user's settings or caches."""
import json
import os
import tempfile
import time
import traceback


def check(output):
    output=output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    result={}
    try:
        os.environ['QT_QPA_PLATFORM']='offscreen'
        with tempfile.TemporaryDirectory(prefix='albioncraft-release-check-') as folder:
            os.environ['ALBIONCRAFT_DATA_DIR']=folder
            from pathlib import Path
            from PySide6.QtWidgets import QApplication
            from app.paths import data_root,resource_root
            from app.catalog import load_catalog
            from app.progression import GameProgression
            from app.item_names import item_name
            from app.fame_dialog import FameWorker
            from app.stock_screen import quantity_reader
            import numpy as np
            assert data_root()==Path(folder)
            recipes=load_catalog(data_root());game=GameProgression(data_root())
            assert len(recipes)>100 and game.costs('COMBAT_SWORDS_SWORD')[0]>0
            assert 'Слиток' in item_name('T2_METALBAR')
            result['catalog']=len(recipes)
            app=QApplication.instance() or QApplication([])
            from PySide6.QtGui import QFont,QFontDatabase
            for filename in ('segoeui.ttf','seguisym.ttf'):
                path=Path('C:/Windows/Fonts')/filename
                if path.exists():QFontDatabase.addApplicationFont(str(path))
            app.setFont(QFont('Segoe UI',10))
            from app.main import Window
            # No public stream, receiver or price requests during smoke tests.
            Window.stream_changed=lambda *args,**kwargs:None
            Window.local_changed=lambda *args,**kwargs:None
            window=Window();window.load_timer.stop();window.stream_timer.stop()
            assert not (data_root()/'settings.json').exists()
            window.show();app.processEvents();assert window.grab().save(str(output.with_suffix('.png')))
            result['window']='ok'
            groups=[dict(node='a',before=dict(level=0,xp=0),ratio=2,choices=[dict(level=0,xp=0,cost=0,gain=0),dict(level=1,xp=0,cost=6,gain=12)]),dict(node='b',before=dict(level=0,xp=0),ratio=2,choices=[dict(level=0,xp=0,cost=0,gain=0),dict(level=1,xp=0,cost=5,gain=9),dict(level=2,xp=0,cost=10,gain=18)])]
            worker=FameWorker(groups,11);received=[];failed=[]
            worker.ready.connect(received.append);worker.failed.connect(failed.append);worker.start()
            deadline=time.monotonic()+45
            while worker.isRunning() and time.monotonic()<deadline:
                app.processEvents();time.sleep(.02)
            worker.wait(1000);app.processEvents()
            assert not failed and received,failed
            assert received[0]['optimal'] and received[0]['gain']==21
            result['fame_subprocess']='ok'
            from scipy.optimize import milp,Bounds
            solution=milp(c=np.array([-1.]),integrality=np.ones(1),bounds=Bounds([0],[3]))
            assert solution.success and round(solution.x[0])==3
            result['milp']='ok'
            reader=quantity_reader();reader(np.full((32,96,3),255,dtype=np.uint8))
            result['ocr']='ok'
            window.close();app.processEvents()
            result['assets']='ok' if (resource_root()/'app/assets/albioncraft.svg').is_file() else 'missing'
            assert result['assets']=='ok'
    except Exception:
        result['error']=traceback.format_exc()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 1 if 'error' in result else 0
