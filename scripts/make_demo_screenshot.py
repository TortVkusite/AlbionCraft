"""Screenshot made from synthetic quotes and a temporary, empty profile."""
import os
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime,timezone
os.environ['QT_QPA_PLATFORM']='offscreen'
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from PySide6.QtWidgets import QApplication,QWidget,QCheckBox
from PySide6.QtGui import QFontDatabase,QFont
from app.catalog import load_catalog
from app.cache import Cache
from app.trip_dialog import TripDialog

app=QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf');app.setFont(QFont('Segoe UI',10))
catalog=load_catalog(root)
class Owner(QWidget):
    def __init__(self):
        super().__init__();self.recipes=catalog;self.worker=None;self.last=None;self.local_enabled=QCheckBox()
        self.settings=dict(auto_rules=True,premium=True,progress_player='Демонстрация',trip_optimizer=dict(selected=['T4_METALBAR','T4_METALBAR_LEVEL1@1','T5_METALBAR'],mastery=False,station='400',weight=2000,budget=1000000,focus=10000,depth_mode='quote'))
        self.setStyleSheet('QWidget{background:#1d2228;color:#e2e7ed;font-family:"Segoe UI";font-size:13px;} QHeaderView::section{background:#303944;padding:8px;} QTableWidget{gridline-color:#3b4550;} QPushButton,QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox{background:#29323c;padding:6px;border:1px solid #465467;}')
    def persist_view(self):pass
    def start_fetch(self,*args):pass

with tempfile.TemporaryDirectory() as folder:
    path=Path(folder);stamp=datetime.now(timezone.utc).isoformat()
    outputs={'T4_METALBAR','T4_METALBAR_LEVEL1@1','T5_METALBAR'}
    ingredients={i.item_id for r in catalog if r.item_id in outputs for i in r.ingredients}
    ids=outputs|ingredients
    quotes=[dict(item_id=uid,city=city,quality=1,sell_price_min=(500 if uid in outputs else 60)+(25 if city=='Martlock' else 0),buy_price_max=250,sell_price_min_date=stamp,buy_price_max_date=stamp) for uid in ids for city in ('Fort Sterling','Thetford','Martlock')]
    cache=Cache(path/'prices.sqlite');cache.merge_prices(quotes,ids,['Fort Sterling','Thetford','Martlock'],[1]);cache.close()
    owner=Owner();dialog=TripDialog(owner,path);dialog.resize(1420,800);dialog.show();dialog.calculate()
    deadline=time.monotonic()+35
    while dialog.worker.isRunning() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    app.processEvents();assert dialog.plans,dialog.status.text()
    dialog.tabs.setCurrentIndex(1);dialog.controls_scroll.verticalScrollBar().setValue(dialog.controls_scroll.verticalScrollBar().maximum());app.processEvents()
    dest=root/'docs/screenshots/trip.png';dest.parent.mkdir(parents=True,exist_ok=True)
    assert dialog.grab().save(str(dest))
    dialog.reject();owner.close()
print('Demo screenshot saved; no user data read')
