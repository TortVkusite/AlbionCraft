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
            from app.i18n import set_language,tr
            set_language('en')
            assert item_name('T2_METALBAR',False)=='Copper Bar'
            assert tr('Мои заказы')=='My orders'
            result['localization']='ru/en ok'
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
            assert window.table.horizontalHeaderItem(0).text()=='Item'
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
            from app.background import ProcessWorker
            from decimal import Decimal as D
            from datetime import datetime,timezone
            recipe=next(r for r in recipes if r.item_id=='T2_METALBAR')
            stamp=datetime.now(timezone.utc).isoformat()
            prices=[dict(item_id=uid,city=city,quality=1,sell_price_min=value,sell_price_min_date=stamp)
                for uid,value in [('T2_ORE',16),('T2_METALBAR',22)] for city in ('Fort Sterling','Thetford')]
            settings=dict(auto_rules=True,other='0',tax='0',setup='0',prefer_upgrades=False)
            def calculate(kind,payload):
                job=ProcessWorker(kind,payload);values=[];errors=[]
                job.ready.connect(values.append);job.failed.connect(errors.append);job.start()
                end=time.monotonic()+45
                while job.isRunning() and time.monotonic()<end:app.processEvents();time.sleep(.01)
                if job.isRunning():job.requestInterruption();job.wait(6000)
                app.processEvents();assert not errors and values,(kind,errors)
                return values[0]
            scanned=calculate('scan',dict(recipes=[recipe],settings=settings,activity='craft',prices=prices,histories=[],
                quality=1,age=30,buy=['Thetford'],craft=['Thetford'],sell=['Thetford'],demand=None,with_prices=True,sort='profit',descending=True))
            assert len(scanned['rows'])==1
            recommendations=calculate('recommendations',dict(rows=scanned['recommendations'],settings=settings))
            assert recommendations['price_count']==2
            plans=calculate('trip',dict(root=folder,stock_rows=[],buy='Fort Sterling',city='Thetford',prices=prices,histories=[],age=30,
                joint=True,roots={recipe.item_id},recipes=[recipe],settings=settings,states={},day_bonus=D(0),rate=D(0),other=D(0),
                multiplier=D(1),mastery=False,limits={recipe.item_id:20},depth='quote',horizon=0,share=10,
                budget=1000,weight=1000,focus=100,repeat=True,objective='profit'))
            assert plans['plans'][0]['lines'] and plans['plans'][0]['profit']>0
            result['background_scan_trip_recommendations']='ok'
            from app.regions import region_root
            assert region_root(data_root(),'west')!=data_root() and region_root(data_root(),'east')!=data_root()
            result['server_profiles']='ok'
            from scipy.optimize import milp,Bounds
            solution=milp(c=np.array([-1.]),integrality=np.ones(1),bounds=Bounds([0],[3]))
            assert solution.success and round(solution.x[0])==3
            result['milp']='ok'
            reader=quantity_reader();reader(np.full((32,96,3),255,dtype=np.uint8))
            result['ocr']='ok'
            window.close();app.processEvents()
            set_language('ru')
            result['assets']='ok' if (resource_root()/'app/assets/albioncraft.svg').is_file() else 'missing'
            assert result['assets']=='ok'
    except Exception:
        result['error']=traceback.format_exc()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 1 if 'error' in result else 0
