"""Inspectable sale-time forecasts, calculated outside the GUI process."""
from PySide6.QtCore import Qt,QTimer,QPointF
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath
from .i18n_widgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QTableWidget,QTableWidgetItem,QScrollArea
from .number_fields import LargeNumberBox
from .background import ProcessWorker
from .item_names import item_name
from .models import CITIES
from .responsive import set_choices
from .ui_layout import fit_window,readable_table
from .i18n import tr


def duration(hours):
    if hours is None:return tr('Более года')
    if hours<1:return tr('Менее часа')
    return f'{hours:.1f} '+tr('ч.') if hours<48 else f'{hours/24:.1f} '+tr('дн.')


def probability(p):
    if p<.001:return '<0.1%'
    if p>=.999:return '>99.9%'
    return f'{p*100:.1f}%'


class ProbabilityChart(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.rows=[];self.setMinimumHeight(160)
    def set_rows(self,rows):self.rows=rows;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        left,top,right,bottom=54,16,self.width()-24,self.height()-30
        p.fillRect(self.rect(),QColor('#101a23'))
        for v in (0,.5,1):
            y=bottom-v*(bottom-top);p.setPen(QColor('#293945'));p.drawLine(QPointF(left,y),QPointF(right,y))
            p.setPen(QColor('#8fa8b9'));p.drawText(5,int(y+5),str(int(v*100))+'%')
        if not self.rows:
            p.drawText(self.rect(),Qt.AlignCenter,tr('Выбери предмет и рассчитай прогноз'));return
        maximum=self.rows[-1]['hours'];path=QPainterPath()
        for n,row in enumerate(self.rows):
            pt=QPointF(left+(right-left)*row['hours']/maximum,bottom-(bottom-top)*row['probability'])
            path.moveTo(pt) if n==0 else path.lineTo(pt)
        p.setPen(QPen(QColor('#65d6bb'),3));p.drawPath(path);p.setPen(QColor('#8fa8b9'))
        for fraction in (0,.5,1):p.drawText(int(left+fraction*(right-left)-12),self.height()-7,f'{maximum*fraction:g} '+tr('ч.'))


class SaleForecastDialog(QDialog):
    def __init__(self,owner,item=None,city=None,quality=1,quantity=30,share=10):
        super().__init__(owner);self.owner=owner;self.worker=None;self.generation=0;self.pending=False;self.closing=False;self.result=None
        self.setWindowTitle(tr('Прогноз продажи партии'));self.resize(1100,860)
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);outer.addWidget(scroll)
        page=QWidget();body=QVBoxLayout(page);scroll.setWidget(page)
        title=QLabel('Прогноз продажи партии');title.setStyleSheet('font-size:23px;font-weight:600;color:#edf4fa;');body.addWidget(title)
        note=QLabel('Вероятность по модели: при выбранной доле рынка и сохранении конкурентной цены. Доля — твоё предположение, а не измеренный показатель.');note.setWordWrap(True);body.addWidget(note)
        row=QHBoxLayout();body.addLayout(row);self.item=QComboBox();self.item.setEditable(True);self.item.setMinimumWidth(230)
        ids=sorted({r.item_id for r in owner.recipes});set_choices(self.item,[(tr('Выбери предмет'),None)]+[(item_name(uid),uid) for uid in ids])
        if item:self.item.setCurrentIndex(self.item.findData(item))
        row.addWidget(self.item,1);self.city=QComboBox();self.city.addItems(CITIES);self.city.setCurrentText(city or 'Thetford');row.addWidget(self.city)
        self.quality=QComboBox()
        for n,label in enumerate(['Обычное','Хорошее','Выдающееся','Отличное','Шедевр'],1):self.quality.addItem(label,n)
        self.quality.setCurrentIndex(quality-1);row.addWidget(self.quality)
        row=QHBoxLayout();body.addLayout(row)
        self.quantity=LargeNumberBox();self.quantity.setDecimals(0);self.quantity.setRange(1,10**9);self.quantity.setValue(max(1,quantity))
        self.share=LargeNumberBox();self.share.setDecimals(2);self.share.setRange(.01,100);self.share.setValue(share);self.share.setSuffix(' %')
        self.hours=LargeNumberBox();self.hours.setDecimals(1);self.hours.setRange(.1,8760);self.hours.setValue(24);self.hours.setSuffix(' '+tr('ч.'))
        for label,control in [('Количество',self.quantity),('Моя доля рынка',self.share),('Следующая проверка через',self.hours)]:
            col=QVBoxLayout();col.addWidget(QLabel(label));col.addWidget(control);row.addLayout(col)
        col=QVBoxLayout();col.addWidget(QLabel('Окно истории'));self.period=QComboBox()
        for label,value in [('Последний просмотр',None),('24 часа',1),('7 дней',7),('4 недели',28)]:self.period.addItem(label,value)
        col.addWidget(self.period);row.addLayout(col)
        self.calculate=QPushButton('Рассчитать прогноз');self.calculate.setObjectName('primary');self.calculate.clicked.connect(self.request);body.addWidget(self.calculate)
        self.status=QLabel('Выбери предмет. Используются уже полученная история и локальный архив, без нового запроса к рынку.');self.status.setWordWrap(True);body.addWidget(self.status)
        self.metrics=QLabel();self.metrics.setWordWrap(True);self.metrics.setStyleSheet('font-size:17px;color:#65d6bb;padding:8px;');body.addWidget(self.metrics)
        self.chart=ProbabilityChart();body.addWidget(self.chart)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Срок','Продать всю партию','Ожидается продать','Ожидаемый остаток','Диапазон продаж 10–90%']);readable_table(self.table);self.table.setMinimumHeight(230);body.addWidget(self.table)
        from PySide6.QtWidgets import QAbstractItemView
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sensitivity=QLabel();self.sensitivity.setWordWrap(True);body.addWidget(self.sensitivity)
        self.explanation=QLabel();self.explanation.setWordWrap(True);self.explanation.setTextInteractionFlags(Qt.TextSelectableByMouse);body.addWidget(self.explanation)
        footer=QLabel('Новые конкуренты, изменение цены и твоя позиция в очереди могут изменить результат. Кривая не учитывает часы активности игроков. Интервал относится к модели, а не к проверенной точности твоих продаж.');footer.setWordWrap(True);body.addWidget(footer)
        close=QPushButton('Закрыть');close.clicked.connect(self.accept);outer.addWidget(close)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(350);self.timer.timeout.connect(self.start)
        for field in (self.item,self.city,self.quality,self.period):field.currentIndexChanged.connect(self.request)
        for field in (self.quantity,self.share,self.hours):field.valueChanged.connect(self.request)
        self.item.lineEdit().textEdited.connect(self.request)
        fit_window(self)
        if item:self.request()

    def request(self,*args):
        self.generation+=1;self.pending=True;self.result=None
        self.metrics.clear();self.chart.set_rows([]);self.table.setRowCount(0);self.sensitivity.clear();self.explanation.clear()
        self.status.setText(tr('Параметры изменились — пересчитываю прогноз…'));self.timer.start()

    def start(self):
        if self.closing or not self.pending or self.worker:return
        uid=self.item.currentData()
        if not uid or self.item.currentText()!=self.item.itemText(self.item.currentIndex()):
            self.status.setText(tr('Выбери предмет из списка'));return
        self.pending=False;generation=self.generation;self.calculate.setEnabled(False)
        histories=(self.owner.last or {}).get('histories',[])
        histories=[h for h in histories if h.get('item_id')==uid and h.get('location')==self.city.currentText() and h.get('quality',1)==self.quality.currentData()]
        data=dict(root=str(self.owner.root),item=uid,city=self.city.currentText(),quality=self.quality.currentData(),period=self.period.currentData(),
            quantity=int(self.quantity.value()),share=self.share.value(),hours=self.hours.value(),histories=histories)
        self.worker=ProcessWorker('sale_forecast',data,self,timeout=30)
        self.worker.ready.connect(lambda r:self.show_result(r) if generation==self.generation and not self.closing else None)
        self.worker.failed.connect(lambda message:self.status.setText(message) if generation==self.generation and not self.closing else None)
        self.worker.finished.connect(self.worker_finished);self.worker.start()

    def worker_finished(self):
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
        self.calculate.setEnabled(True)
        if self.closing:self.done(self._closing_result)
        elif self.pending:self.timer.start()

    def show_result(self,result):
        self.result=result;e=result['evidence']
        self.status.setText(tr('История: ')+str(e.get('period_days','—'))+' '+tr('дн.')+' • '+tr('Полнота: ')+f"{e['coverage']*100:.0f}%"+
            ' • '+tr('Сделок, шт.: ')+str(e['total'])+' • '+tr('Источник: ')+str(e.get('source','—')))
        if result['status']!='ready':
            self.metrics.setText(tr('Прогноз недоступен'));self.explanation.setText(tr(e['reason']));return
        selected=result['selected'];self.chart.set_rows(result['curve'])
        self.metrics.setText(tr('Продать к проверке: ')+probability(selected['probability'])+'  •  '+tr('Медиана: ')+duration(result['median_hours'])+
            '\n'+tr('Интервал времени 10–90%: ')+duration(result['p10_hours'])+' — '+duration(result['p90_hours'])+'  •  '+tr('Для вероятности 80%: ')+duration(result['p80_hours']))
        self.table.setRowCount(len(result['horizons']))
        for n,h in enumerate(result['horizons']):
            values=[duration(h['hours']),probability(h['probability']),f"{h['expected_sold']:,.1f}",f"{h['remaining']:,.1f}",f"{h['low_sold']:,} — {h['high_sold']:,}"]
            for c,value in enumerate(values):self.table.setItem(n,c,QTableWidgetItem(value))
        self.table.resizeColumnsToContents();self.table.horizontalHeader().setStretchLastSection(True)
        self.sensitivity.setText(tr('Чувствительность к твоей доле рынка: ')+'  |  '.join(f"{s['share']:g}% → "+probability(s['probability']) for s in result['sensitivity']))
        self.explanation.setText(tr('Темп рынка по наблюдаемым интервалам: ')+f"{e['market_per_day']:,.1f}"+' '+tr('шт./день')+'; '+tr('твой темп по модели: ')+f"{result['personal_per_day']:,.1f}"+' '+tr('шт./день')+'.\n'+
            tr('Модель: Gamma–Poisson. Учитывает объём истории и разброс между интервалами; персональная точность пока не откалибрована.')+
            ('\n'+'\n'.join(tr(w) for w in e['warnings']) if e['warnings'] else ''))

    def done(self,result):
        self.timer.stop();self.closing=True;self._closing_result=result
        if self.worker and self.worker.isRunning():self.worker.requestInterruption();return
        super().done(result)
