"""Reproducible RU/EN portfolio screenshots, using synthetic history only."""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def render():
    from PySide6.QtWidgets import QApplication,QMainWindow
    from PySide6.QtGui import QFont,QFontDatabase
    from app.dashboard import STYLE
    from app.models import Recipe
    from app.i18n import set_language
    from app.sale_forecast import forecast
    from app.sale_forecast_dialog import SaleForecastDialog
    root=Path(__file__).resolve().parents[1]
    app=QApplication.instance() or QApplication([])
    for name in ('segoeui.ttf','seguisym.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    app.setFont(QFont('Segoe UI',10))
    clock=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    h=dict(item_id='T4_MAIN_SWORD',location='Thetford',quality=1,period_days=7,bucket_hours=24,
        observed=clock.isoformat(),source='Synthetic demo',data=[dict(timestamp=(clock-timedelta(days=i)).isoformat(),item_count=c,avg_price=1200)
            for i,c in enumerate([80,90,100,110,95,105,120],1)])
    result=forecast(h,10,10,24,clock)
    with tempfile.TemporaryDirectory() as folder:
        owner=QMainWindow();owner.setStyleSheet(STYLE);owner.root=Path(folder);owner.last={'histories':[h]}
        owner.recipes=[Recipe('T4_MAIN_SWORD','Demo sword',0,())]
        for language in ('en','ru'):
            set_language(language);dialog=SaleForecastDialog(owner,'T4_MAIN_SWORD','Thetford',1,10,10)
            dialog.timer.stop();dialog.pending=False;dialog.show_result(result);dialog.resize(1180,1040);dialog.show();app.processEvents()
            target=root/'docs'/'screenshots'/('forecast-'+language+'.png');assert dialog.grab().save(str(target))
            print(target);dialog.accept();app.processEvents()
        set_language('en');dialog=SaleForecastDialog(owner,'T4_MAIN_SWORD');dialog.timer.stop();dialog.pending=False
        dialog.show_result(forecast(None,30,10,24,clock));dialog.resize(1000,800);dialog.show();app.processEvents()
        assert dialog.grab().save(str(root/'docs/screenshots/forecast-missing.png'));dialog.accept()


if __name__=='__main__':render()
