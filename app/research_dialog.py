"""Local market evidence and explicitly confirmed production bonuses."""
from datetime import datetime,timedelta,timezone
from PySide6.QtCore import QDateTime,QBuffer,QIODevice,Qt
from .i18n_widgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QTableWidget,QTableWidgetItem,QLineEdit,QTabWidget,QWidget,QCheckBox,QApplication
from PySide6.QtWidgets import QDateTimeEdit
from .number_fields import NumberBox
from .market_memory import MarketMemory
from .item_names import item_name
from .models import CITIES
from .formatting import money
from .background import ProcessWorker
from .ui_layout import readable_table,fit_window
from .i18n import tr

def local_time(stamp):
    return datetime.fromisoformat(stamp).astimezone().strftime('%d.%m.%Y %H:%M')

class ResearchDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.store=MarketMemory(owner.root/'prices.sqlite');self.worker=None
        self.setWindowTitle('История рынка и бонусы');self.resize(1000,720);body=QVBoxLayout(self)
        tabs=QTabWidget();body.addWidget(tabs)
        page=QWidget();layout=QVBoxLayout(page);tabs.addTab(page,'История рынка')
        bar=QHBoxLayout();layout.addLayout(bar);self.item=QComboBox();self.item.setEditable(True)
        ids=sorted({r.item_id for r in owner.recipes});self.item.addItem('Выбери предмет',None)
        from .responsive import set_choices
        set_choices(self.item,[('Выбери предмет',None)]+[(item_name(uid),uid) for uid in ids])
        self.city=QComboBox();self.city.addItems(CITIES);self.city.setCurrentText('Thetford');bar.addWidget(self.item,1);bar.addWidget(self.city)
        self.quality=QComboBox()
        for n,label in enumerate(['Обычное','Хорошее','Выдающееся','Отличное','Шедевр'],1):self.quality.addItem(label,n)
        bar.addWidget(self.quality)
        button=QPushButton('Обновить историю');button.clicked.connect(self.refresh);bar.addWidget(button)
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        from .history_chart import HistoryChart
        self.chart=HistoryChart();layout.addWidget(self.chart)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Дата','Продажа / покупка','Цена','Источник']);readable_table(self.table);layout.addWidget(self.table,1)
        self.volume=QTableWidget(0,3);self.volume.setHorizontalHeaderLabels(['Дата','Продано за интервал','Цена сделок']);readable_table(self.volume);layout.addWidget(self.volume,1)
        self.insight=QLabel();self.insight.setWordWrap(True);layout.addWidget(self.insight)
        self.item.currentIndexChanged.connect(self.refresh);self.city.currentIndexChanged.connect(self.refresh);self.quality.currentIndexChanged.connect(self.refresh)
        page=QWidget();layout=QVBoxLayout(page);tabs.addTab(page,'Бонусы производства')
        note=QLabel('Дневные бонусы и события имеют разные сроки. Подтверждённого циклического расписания нет. Прочитай экран событий из буфера и подтверди категорию, процент и окончание. Просроченный бонус перестаёт учитываться автоматически.');note.setWordWrap(True);layout.addWidget(note)
        bar=QHBoxLayout();layout.addLayout(bar);self.category=QComboBox()
        from .rules import rules
        categories=sorted({key for city in rules()['cities'].values() for key in city.get('bonuses',{})})
        from .main import FAMILIES
        for key in categories:self.category.addItem(FAMILIES.get(key,key),key)
        bar.addWidget(self.category)
        self.percent=NumberBox();self.percent.setRange(1,200);self.percent.setValue(10);self.percent.setSuffix(' %');bar.addWidget(self.percent)
        self.start=QDateTimeEdit(QDateTime.currentDateTime());self.end=QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        for field in (self.start,self.end):field.setDisplayFormat('dd.MM.yyyy HH:mm');field.setCalendarPopup(True);bar.addWidget(field)
        self.source=QLineEdit(tr('Экран событий Albion'));layout.addWidget(self.source)
        self.use=QCheckBox('Учитывать подтверждённые бонусы');self.use.setChecked(owner.settings.get('use_bonuses',True));layout.addWidget(self.use)
        self.remind=QCheckBox('Напоминать о начале и окончании подтверждённых бонусов');self.remind.setChecked(owner.settings.get('bonus_reminders',False));layout.addWidget(self.remind)
        self.use.toggled.connect(self.save_options);self.remind.toggled.connect(self.save_options)
        bar=QHBoxLayout();layout.addLayout(bar)
        self.ocr=QPushButton('Прочитать изображение из буфера');self.ocr.clicked.connect(self.read_image);bar.addWidget(self.ocr)
        save=QPushButton('Подтвердить бонус');save.clicked.connect(self.save_bonus);bar.addWidget(save)
        self.bonus_status=QLabel();self.bonus_status.setWordWrap(True);layout.addWidget(self.bonus_status)
        self.bonuses=QTableWidget(0,5);self.bonuses.setHorizontalHeaderLabels(['Категория','Бонус','Начало','Окончание','Источник']);readable_table(self.bonuses);layout.addWidget(self.bonuses,1)
        remove=QPushButton('Удалить выбранный бонус');remove.clicked.connect(self.remove_bonus);layout.addWidget(remove)
        page=QWidget();layout=QVBoxLayout(page);tabs.addTab(page,'Проверка прогнозов')
        self.player=QLineEdit(owner.settings.get('progress_player','Мой персонаж'));layout.addWidget(self.player)
        self.calibration_info=QLabel();self.calibration_info.setWordWrap(True);layout.addWidget(self.calibration_info)
        self.actuals=QTableWidget(0,5);self.actuals.setHorizontalHeaderLabels(['Маршрут','План','Факт','Отклонение','Продажа, ч']);readable_table(self.actuals);layout.addWidget(self.actuals,1)
        refresh=QPushButton('Обновить сверку');refresh.clicked.connect(self.refresh_actuals);layout.addWidget(refresh);self.refresh_actuals()
        from PySide6.QtWidgets import QAbstractItemView
        for table in (self.table,self.volume,self.bonuses,self.actuals):table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.refresh_bonuses();close=QPushButton('Закрыть');close.clicked.connect(self.accept);body.addWidget(close);fit_window(self)
    def refresh_actuals(self):
        from .trip_ledger import TripLedger,actual_summary
        from .market_memory import calibration
        ledger=TripLedger(self.owner.root/'player.sqlite')
        try:entries=ledger.entries(self.player.text().strip() or 'Мой персонаж')
        finally:ledger.close()
        rows=[]
        for entry in entries:
            summary=actual_summary(entry['snapshot'],entry['facts'])
            if summary['closed']:rows.append((entry,summary))
        self.actuals.setRowCount(len(rows))
        for n,(entry,summary) in enumerate(rows):
            snap=entry['snapshot'];values=[snap['buy']+' → '+snap['craft'],money(snap['profit']),money(summary['profit']),money(summary['delta']),str(entry['facts'].get('hours_to_sell') or 'Неизвестно')]
            for c,v in enumerate(values):self.actuals.setItem(n,c,QTableWidgetItem(v))
        labels={'sale':'Выручка','purchase':'Закупка','stock':'Запасы','station':'Станция','other':'Прочие','sale_fees':'Комиссии'}
        cal=calibration(entries);self.calibration_info.setText('Закрытых ходок: '+str(cal['count'])+'. Для каждого маршрута поправка появится после 10 сверок. Последовательная проверка использует только более ранние результаты. Причины отклонений: '+ '; '.join(labels[k]+': '+money(v) for k,v in cal['changes'].items())+'. Вероятности будущих продаж пока не оцениваются.')
    def save_options(self,*args):
        self.owner.settings.update(use_bonuses=self.use.isChecked(),bonus_reminders=self.remind.isChecked());self.owner.persist_view();self.owner.render()
    def save_bonus(self):
        try:
            self.store.add_bonus(self.category.currentData(),self.percent.value(),self.start.dateTime().toPython().astimezone().isoformat(),self.end.dateTime().toPython().astimezone().isoformat(),self.source.text())
            self.bonus_status.setText('Бонус сохранён. Пересчитай открытые планы.');self.refresh_bonuses();self.owner.render()
        except (ValueError,ArithmeticError) as exc:self.bonus_status.setText(str(exc))
    def refresh_bonuses(self):
        rows=self.store.bonuses();self.bonus_rows=rows;self.bonuses.setRowCount(len(rows))
        for n,b in enumerate(rows):
            index=self.category.findData(b['category']);label=self.category.itemText(index) if index>=0 else b['category']
            for col,value in enumerate([label,str(b['percent'])+' %',local_time(b['starts']),local_time(b['ends']),b['source']]):self.bonuses.setItem(n,col,QTableWidgetItem(value))
    def remove_bonus(self):
        row=self.bonuses.currentRow()
        if 0<=row<len(self.bonus_rows):self.store.remove_bonus(self.bonus_rows[row]['id']);self.refresh_bonuses();self.owner.render()
    def refresh(self,*args):
        uid=self.item.currentData()
        if not uid:return
        city=self.city.currentText();quality=self.quality.currentData();prices=self.store.timeline(uid,city,quality);volumes=self.store.volumes(uid,city,quality)
        self.chart.set_rows(prices)
        self.info.setText('История этого сервера и города. Котировки показывают предложения, объём — совершённые сделки. Пропуски означают отсутствие наблюдений.')
        self.table.setRowCount(len(prices));self.volume.setRowCount(len(volumes))
        for n,p in enumerate(prices):
            for c,v in enumerate([local_time(p['stamp']),'Продажа' if p['side']=='sell_price_min' else 'Покупка',money(p['price']),p['source']]):self.table.setItem(n,c,QTableWidgetItem(v))
        for n,p in enumerate(volumes):
            for c,v in enumerate([local_time(p['stamp']),str(p['count']),money(p['price'])]):
                cell=QTableWidgetItem(v);cell.setToolTip(f'Интервал: {p.get("bucket_hours",24)} ч.; период: {p.get("period_days",7)} дн.');self.volume.setItem(n,c,cell)
        sell=[p for p in prices if p['side']=='sell_price_min']
        text='Для решения «продать или подержать» пока мало наблюдений.'
        if len(sell)>=5 and (datetime.fromisoformat(sell[0]['stamp'])-datetime.fromisoformat(sell[-1]['stamp'])).days>=7:
            baseline=sorted(p['price'] for p in sell)[len(sell)//2];delta=(sell[0]['price']/baseline-1)*100
            text=f'Последнее предложение относительно медианы наблюдений: {delta:+.1f}%. Это сравнение цен; будущий рост не подтверждён.'
        marks=[b for b in self.store.bonuses() if prices and b['ends']>=prices[-1]['stamp'] and b['starts']<=prices[0]['stamp']]
        if marks:text+='\nБонусы в этот период: '+'; '.join(b['category']+' '+str(b['percent'])+'% '+b['starts'][:10]+' → '+b['ends'][:10] for b in marks[:6])
        arrivals=self.store.arrivals(uid,city,'sell_price_min',quality)
        if arrivals and arrivals['per_hour'] is not None:text+=f"\nНовых увиденных ордеров в час: {arrivals['per_hour']:.1f}. Страницы неполные; исчезновение ордера не подтверждает продажу."
        self.insight.setText(text)
    def read_image(self):
        image=QApplication.clipboard().image()
        if image.isNull():self.bonus_status.setText('Скопируй скриншот окна событий в буфер.');return
        if self.worker and self.worker.isRunning():return
        buffer=QBuffer();buffer.open(QIODevice.WriteOnly);image.save(buffer,'PNG')
        self.worker=ProcessWorker('bonus_ocr',dict(image=bytes(buffer.data())),self,timeout=60);self.ocr.setEnabled(False)
        self.worker.ready.connect(self.ocr_ready);self.worker.failed.connect(self.bonus_status.setText);self.worker.finished.connect(lambda:self.ocr.setEnabled(True));self.worker.start()
    def ocr_ready(self,text):
        import re
        # Only unambiguous percentages can be suggested; dates/categories remain reviewed input.
        values=set(re.findall(r'(?<!\d)(\d{1,3})\s*%',text))
        if len(values)==1 and 0<int(next(iter(values)))<=200:self.percent.setValue(int(next(iter(values))))
        self.bonus_status.setText('Распознано — проверь перед сохранением:\n'+text)
    def done(self,result):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption();self.bonus_status.setText('Останавливаю чтение…');self.worker.finished.connect(lambda:self.done(result));return
        if not getattr(self,'_closed',False):self.store.close();self._closed=True
        super().done(result)

def bonus_ocr(data):
    import io
    import numpy as np
    from PIL import Image
    from rapidocr import RapidOCR
    from rapidocr.utils.typings import LangRec,ModelType,OCRVersion
    from .paths import resource_root
    path=resource_root()/'app/assets/ocr/cyrillic_PP-OCRv5_rec_mobile.onnx'
    with Image.open(io.BytesIO(data['image'])) as im:
        if im.width*im.height>12000000:raise ValueError('Изображение слишком большое')
        result=RapidOCR(params={'Rec.model_path':str(path),'Rec.lang_type':LangRec.CYRILLIC,'Rec.model_type':ModelType.MOBILE,'Rec.ocr_version':OCRVersion.PPOCRV5})(np.asarray(im.convert('RGB')))
    return '\n'.join(result.txts or [])[:5000]
