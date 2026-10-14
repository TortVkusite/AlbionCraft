from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QColor
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,QTableWidget,QTableWidgetItem,
    QAbstractItemView,QPushButton,QApplication)
from .item_names import item_name,recipe_variant
from .filter_dialog import QUALITY_NAMES
from .formatting import money,roi,timestamp
from .ui_layout import FlowLayout,readable_table,fit_window
from .responsive import GuiBatch
from .background import ProcessWorker


class RecommendationsDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Рекомендации');self.resize(1120,680)
        self.owner=parent;layout=QVBoxLayout(self);self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.paint_batch=GuiBatch(self)
        self.calculation_worker=None;self.generation=0;self.closed=False
        self.data=dict(update=[],known=[],candidates=[],gaps=[],with_price=0,price_count=0)
        self.calculate_timer=QTimer(self);self.calculate_timer.setSingleShot(True);self.calculate_timer.setInterval(180);self.calculate_timer.timeout.connect(self.start_calculation)
        self.tabs=QTabWidget();layout.addWidget(self.tabs);self.tables=[]
        headers=[['Предмет','Город','Роль','Причина','Цена','Возраст','Рецептов'],
            ['Предмет','Город','Роль','Цена','Дата UTC','Источник'],
            ['Предмет','Город','Сценарий','Прибыль','ROI','Спрос / проверка']]
        for title,columns in zip(['Обновить данные','Цены уже есть','Кандидаты'],headers):
            table=QTableWidget(0,len(columns));table.setHorizontalHeaderLabels(columns);table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows);table.horizontalHeader().setStretchLastSection(True);table.verticalHeader().setVisible(False)
            self.tabs.addTab(table,title);self.tables.append(table)
        self.tables[2].cellDoubleClicked.connect(self.details)
        from .number_fields import NumberBox,LargeNumberBox
        from .i18n_widgets import QWidget
        page=QWidget();body=QVBoxLayout(page);controls=FlowLayout();body.addLayout(controls);prefs=parent.settings.get('price_gaps',{})
        self.gap_min=NumberBox();self.gap_min.setRange(1,500);self.gap_min.setValue(int(prefs.get('minimum',10)))
        self.gap_age=NumberBox();self.gap_age.setRange(1,180);self.gap_age.setValue(int(prefs.get('minutes',15)))
        self.gap_budget=LargeNumberBox();self.gap_budget.setDecimals(0);self.gap_budget.setRange(0,1e12);self.gap_budget.setValue(float(prefs.get('budget',0)))
        for label,field in [('Разрыв от, %',self.gap_min),('Не старше, мин',self.gap_age),('Деньги на партию (0 — без лимита)',self.gap_budget)]:controls.addWidget(QLabel(label));controls.addWidget(field);field.valueChanged.connect(self.gap_preferences)
        note=QLabel('Дешёвые партии на просмотренных страницах этого сервера. Выкуп всей дешёвой части и продажа на 1 серебро ниже следующей цены — сценарий. Следующая цена не доказывает спрос; полный рынок может отличаться. Двойной клик — уровни и формулы.');note.setWordWrap(True);body.addWidget(note)
        table=QTableWidget(0,8);table.setHorizontalHeaderLabels(['Предмет / качество','Город','Купить, шт.','Закупка','Следующая цена','Разрыв, %','Прибыль партии','Продаж / день']);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.verticalHeader().setVisible(False);table.horizontalHeader().setStretchLastSection(True);body.addWidget(table)
        self.tabs.addTab(page,'Дешёвые партии');self.tables.append(table);table.cellDoubleClicked.connect(self.gap_details)
        actions=FlowLayout();layout.addLayout(actions)
        copy=QPushButton('Скопировать название');actions.addWidget(copy);copy.clicked.connect(self.copy_name)
        self.update=QPushButton('Обновить недостающие и старые цены API');actions.addWidget(self.update);self.update.clicked.connect(self.refresh_api)
        close=QPushButton('Закрыть');actions.addWidget(close);close.clicked.connect(self.accept)
        tip=QLabel('Просмотр рынка в игре обновляет это окно автоматически. Общий ресурс указан один раз для города и качества. Кандидаты — повод проверить цены и расходы, а не обещание прибыли. Двойной клик по кандидату открывает расчёт.');tip.setWordWrap(True);layout.addWidget(tip)
        self.timer=QTimer(self);self.timer.setInterval(2000);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()
        for table in self.tables:readable_table(table);table.setColumnWidth(0,330)
        fit_window(self)
    def refresh(self):
        if self.closed:return
        import time
        last=self.owner.last or {}
        signature=(id(self.owner.recommendation_rows),id(last.get('prices')),id(last.get('histories')),repr(self.owner.settings.get('price_gaps',{})),repr(self.owner.settings.get('recommendations',{})),repr(self.owner.settings.get('result_limits',{})),int(time.time()//60))
        if signature==getattr(self,'signature',None):
            self.update.setEnabled(bool(self.data['update']) and not (self.owner.worker and self.owner.worker.isRunning()));return
        self.signature=signature
        self.generation+=1;self.paint_batch.cancel()
        if self.calculation_worker and self.calculation_worker.isRunning():self.calculation_worker.requestInterruption()
        self.calculate_timer.start()
    def start_calculation(self):
        if self.calculation_worker and self.calculation_worker.isRunning():self.calculate_timer.start();return
        from copy import deepcopy
        generation=self.generation
        self.summary.setText('Пересчитываю рекомендации…')
        last=self.owner.last or {}
        self.calculation_worker=ProcessWorker('recommendations',dict(rows=self.owner.recommendation_rows,settings=deepcopy(self.owner.settings),prices=last.get('prices',[]),histories=last.get('histories',[])),self)
        self.calculation_worker.ready.connect(lambda data:self.received(data) if generation==self.generation and not self.closed else None)
        self.calculation_worker.failed.connect(lambda message:self.summary.setText(message) if generation==self.generation and not self.closed else None)
        self.calculation_worker.finished.connect(self.calculation_finished)
        self.calculation_worker.start()
    def calculation_finished(self):
        worker=self.sender()
        if worker is self.calculation_worker:self.calculation_worker=None
        if worker:worker.deleteLater()
    def received(self,data):
        self.data=data
        self.summary.setText(f'Для выбранных фильтров: цены есть {self.data["with_price"]}/{self.data["price_count"]} • обновить: {len(self.data["update"])} • кандидатов: {len(self.data["candidates"])}. Порог давности: {self.owner.settings.get("recommendations",{}).get("stale_hours",6)} ч.')
        self.summary.setText(self.summary.text()+f' Дешёвых партий на просмотренных страницах: {len(self.data["gaps"])}.')
        self.update.setEnabled(bool(self.data['update']) and not (self.owner.worker and self.owner.worker.isRunning()))
        self.paint_batch.start(self.paint_rows())
    def paint_rows(self):
        for group,table in zip(('update','known','candidates','gaps'),self.tables):
            # Preserve selection while new prices arrive.
            selected=table.item(table.currentRow(),0);selected_key=selected.data(Qt.UserRole) if selected else None
            entries=self.data[group];table.setRowCount(0);table.setRowCount(len(entries))
            for n,p in enumerate(entries):
                if group=='gaps':
                    from .calculator import demand_text,demand_tip
                    key=(p['item_id'],p['city'],p['quality']);label=item_name(p['item_id'])+' • '+QUALITY_NAMES[p['quality']-1]
                    values=[label,p['city'],p['quantity'],money(p['purchase']),money(p['reference']),f'{p["gap"]:.1f}',('≤ ' if p['pending'] else '')+money(p['profit']),demand_text(p['demand'])]
                elif group=='candidates':
                    row=p['row'];r=row['recipe'];key=(r.item_id,row['sell'],row.get('quality',1))
                    notes=[]
                    if row.get('pending_costs'):notes.append('Не вычтены: '+', '.join(row['pending_costs']))
                    if any('устарело' in part['status'] for part in row['parts']) or 'устарело' in row['sale_status']:notes.append('Старые цены')
                    d=row['demand'];notes.append('Нет истории' if d['kind']=='unknown' else f'{d["per_day"]:.1f} ед./день')
                    prefix='≤ ' if row.get('pending_costs') else ''
                    label=item_name(r.item_id)
                    if r.variant:label+='\n'+recipe_variant(r)
                    values=[label,row['sell'],'С Focus' if p['scenario']=='focus' else 'Без Focus',prefix+money(p['result']['profit']),prefix+roi(p['result']['roi']),'; '.join(notes)]
                else:
                    key=(p['item_id'],p['city'],p['quality']);label=item_name(p['item_id'])+' • '+QUALITY_NAMES[p['quality']-1]
                    values=[label,p['city'],p['role'],p['state'],money(p['price']),('—' if p['age'] is None else f'{max(0,p["age"])/60:.1f} ч'),p['recipes']] if group=='update' else [label,p['city'],p['role'],money(p['price']),timestamp(p['date']),p['source']]
                for c,v in enumerate(values):
                    cell=QTableWidgetItem(str(v));cell.setData(Qt.UserRole,key);cell.setToolTip(key[0]);table.setItem(n,c,cell)
                    if group=='gaps':cell.setToolTip(key[0]+'\n'+timestamp(p['stamp'])+' UTC')
                    if group=='update' and c==3:cell.setForeground(QColor('#ff9999'))
                    if group=='gaps' and c==7:cell.setToolTip(demand_tip(p['demand']))
                table.setRowHeight(n,82 if group=='gaps' else 56 if group=='candidates' and '\n' in values[0] else 40)
                if key==selected_key:table.selectRow(n)
                yield
            if group=='gaps':
                for column,width in enumerate((240,95,90,105,130,80,120,155)):table.setColumnWidth(column,width)
            else:table.setColumnWidth(0,330);table.setColumnWidth(1,110)
    def copy_name(self):
        table=self.tables[self.tabs.currentIndex()];cell=table.item(table.currentRow(),0)
        if cell:QApplication.clipboard().setText(item_name(cell.data(Qt.UserRole)[0],False))
    def refresh_api(self):self.owner.refresh_price_ids({p['item_id'] for p in self.data['update']});self.refresh()
    def details(self,n,c):
        from .details import Details
        row=self.data['candidates'][n]['row'];Details(self.owner,row,row.get('quality',1),self.owner.settings).exec()
    def gap_preferences(self,*args):
        self.owner.settings['price_gaps']=dict(minimum=self.gap_min.value(),minutes=self.gap_age.value(),budget=self.gap_budget.value())
        self.owner.save_local_settings();self.refresh()
    def gap_details(self,n,c):
        from .price_gap_dialog import GapDetails
        GapDetails(self,self.data['gaps'][n]).exec()
    def done(self,result):
        self.closed=True;self.generation+=1;self.timer.stop();self.calculate_timer.stop();self.paint_batch.cancel()
        if self.calculation_worker and self.calculation_worker.isRunning():self.calculation_worker.requestInterruption()
        super().done(result)
    def showEvent(self,event):super().showEvent(event);self.closed=False;self.signature=None;self.timer.start();self.refresh()
