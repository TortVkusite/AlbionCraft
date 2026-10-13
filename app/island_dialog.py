from pathlib import Path
from PySide6.QtCore import Qt,QSize
from .i18n_widgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QCheckBox,QTableWidget,QTableWidgetItem,QAbstractItemView,QLineEdit
from .number_fields import NumberBox,LargeNumberBox
from .dashboard import panel,section,title,Metrics
from .ui_layout import readable_table,explanation,FlowLayout
from .island import farming_data
from .item_names import item_name
from .formatting import money,timestamp
from .preferences import save_settings
from .market_snapshot import market_snapshot
from .background import ProcessWorker
from .workers import Fetch
from .api import AlbionAPI
from .models import CITIES

class IslandPage(QWidget):
    def __init__(self,owner,root):
        super().__init__(owner);self.owner=owner;self.root=Path(root);self.worker=None;self.calculation=None;self.closed=False;self.rows=[];self.results=[]
        self.products=farming_data()['products'];prefs=owner.settings.get('islands',{})
        body=QVBoxLayout(self);body.addWidget(title('Остров'))
        horizontal=QHBoxLayout();body.addLayout(horizontal,1);scroll,left=panel();horizontal.addWidget(scroll)
        section(left,'Хозяйство');self.premium=QCheckBox('Premium');self.premium.setChecked(prefs.get('premium',owner.settings.get('premium',False)));left.addWidget(self.premium)
        left.addWidget(QLabel('Доступный фокус'));self.focus=NumberBox();self.focus.setRange(0,30000);self.focus.setValue(int(prefs.get('focus',10000)));left.addWidget(self.focus)
        self.sale=QComboBox();self.sale.addItem('Заказ на продажу','order');self.sale.addItem('Быстрая продажа','instant');self.sale.setCurrentIndex(max(0,self.sale.findData(prefs.get('sale','order'))));left.addWidget(self.sale)
        self.age=QCheckBox('Разрешить старые цены');self.age.setChecked(prefs.get('any_age',True));left.addWidget(self.age)
        self.add_button=QPushButton('Добавить посадку');self.add_button.clicked.connect(lambda:self.add_row());left.addWidget(self.add_button)
        self.remove_button=QPushButton('Удалить выбранную');self.remove_button.clicked.connect(self.remove_row);left.addWidget(self.remove_button)
        self.fetch_button=QPushButton('Обновить цены');self.fetch_button.clicked.connect(self.fetch);left.addWidget(self.fetch_button)
        self.calculate_button=QPushButton('Рассчитать острова');self.calculate_button.setObjectName('primary');self.calculate_button.clicked.connect(self.calculate);left.addWidget(self.calculate_button)
        self.cancel=QPushButton('Отмена');self.cancel.setEnabled(False);self.cancel.clicked.connect(self.cancel_work);left.addWidget(self.cancel)
        section(left,'Правила расчёта')
        explanation(left,'Урожай — ожидаемое значение. Полив увеличивает возврат семян. Семена для следующего цикла сохраняются; продаётся только избыток. Выращивание животных считает продажу взрослого животного, без разделки и седлания. Количество корма за весь цикл проверь в игре. Постройка острова, доставка и побочные черви не включены.','Что включено')
        explanation(left,'Фокус: базовая стоимость / 2^((100 × мастерство + 200 × специализация) / 10000), с округлением вверх. Для выбранного животного учитываются все разрешённые действия ухода. Запас фокуса делится между сохранёнными посадками по дополнительной прибыли.','Распределение фокуса')
        left.addStretch()
        right=QWidget();layout=QVBoxLayout(right);layout.setContentsMargins(8,0,0,0);horizontal.addWidget(right,1)
        self.metrics=Metrics(['Без фокуса / сбор','С фокусом / сбор','Закупка первого цикла','Фокус']);layout.addWidget(self.metrics)
        self.status=QLabel('Добавь свои посадки и обнови цены.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.inputs=QTableWidget(0,7);self.inputs.setHorizontalHeaderLabels(['Город','Культура / животное','Участки','Мастерство','Специализация','Корм / животное','Уход']);readable_table(self.inputs)
        self.inputs.verticalHeader().hide();self.inputs.setMinimumHeight(150);self.inputs.setMaximumHeight(280);layout.addWidget(self.inputs)
        self.output=QTableWidget(0,9);self.output.setHorizontalHeaderLabels(['Результат','Урожай / сбор','Возврат семян /\nдетёнышей','Докупить / цикл','Без фокуса','С фокусом','Фокус','Цикл, ч','Цена / дата']);readable_table(self.output);self.output.verticalHeader().hide();self.output.setEditTriggers(QAbstractItemView.NoEditTriggers);self.output.setIconSize(QSize(32,32));layout.addWidget(self.output,1)
        for col,width in enumerate([210,120,155,115,100,100,90,90,165]):self.output.setColumnWidth(col,width)
        self.details=QLabel();self.details.setWordWrap(True);layout.addWidget(self.details)
        for saved in prefs.get('rows',[{}]):self.add_row(saved,save=False)
        for control in (self.premium,self.age):control.toggled.connect(self.invalidate)
        self.focus.valueChanged.connect(self.invalidate);self.sale.currentIndexChanged.connect(self.invalidate)
    def add_row(self,saved=None,save=True):
        if len(self.rows)>=32:self.status.setText('Максимум 32 посадки.');return
        saved=saved or {};city=QComboBox();city.addItems(CITIES);city.setCurrentText(saved.get('city','Thetford'))
        product=QComboBox()
        for p in self.products:product.addItem(item_name(p['id']),p['id'])
        product.setCurrentIndex(max(0,product.findData(saved.get('product','T1_FARM_CARROT_SEED'))))
        plots=NumberBox();plots.setRange(1,16);plots.setValue(int(saved.get('plots',1)))
        mastery=NumberBox();mastery.setRange(0,100);mastery.setValue(int(saved.get('mastery',0)))
        spec=NumberBox();spec.setRange(0,100);spec.setValue(int(saved.get('specialization',0)))
        food=LargeNumberBox();food.setDecimals(2);food.setRange(0,10000)
        item=self.products[product.currentIndex()];food.setValue(float(saved.get('food_amount',item.get('food_amount',0))))
        label=QLabel();row=dict(city=city,product=product,plots=plots,mastery=mastery,specialization=spec,food_amount=food,actions=label)
        self.rows.append(row);n=self.inputs.rowCount();self.inputs.insertRow(n)
        for col,key in enumerate(('city','product','plots','mastery','specialization','food_amount','actions')):self.inputs.setCellWidget(n,col,row[key])
        self.inputs.setColumnWidth(0,140);self.inputs.setColumnWidth(1,240)
        for col in (2,3,4,5):self.inputs.setColumnWidth(col,115)
        self.inputs.setColumnWidth(5,145);self.inputs.setColumnWidth(6,80)
        def changed_product():
            p=self.products[product.currentIndex()];food.setValue(float(p.get('food_amount',0)));self.update_row(row);self.invalidate()
        product.currentIndexChanged.connect(changed_product)
        for control in (city,plots,mastery,spec,food):
            signal=control.currentIndexChanged if isinstance(control,QComboBox) else control.valueChanged
            signal.connect(self.invalidate)
        self.update_row(row)
        if save:self.invalidate()
    def update_row(self,row):
        p=self.products[row['product'].currentIndex()];animal=p['kind']=='animals'
        row['food_amount'].setEnabled(animal);row['food_amount'].setToolTip(item_name(p['food']) if animal else 'Корм не нужен')
        row['actions'].setText(str(p['actions']) if animal else '1')
    def remove_row(self):
        n=self.inputs.currentRow()
        if n>=0:self.inputs.removeRow(n);self.rows.pop(n);self.invalidate()
    def snapshot(self):
        return [dict(city=r['city'].currentText(),product=r['product'].currentData(),plots=r['plots'].value(),mastery=r['mastery'].value(),specialization=r['specialization'].value(),food_amount=str(r['food_amount'].value())) for r in self.rows]
    def persist(self):
        self.owner.settings['islands']=dict(rows=self.snapshot(),premium=self.premium.isChecked(),focus=self.focus.value(),sale=self.sale.currentData(),any_age=self.age.isChecked());save_settings(self.owner.settings_path,self.owner.settings)
    def invalidate(self,*args):
        if self.closed:return
        self.persist();self.metrics.update_values(['—']*4);self.output.setRowCount(0);self.details.clear();self.status.setText('Настройки изменились — нужен расчёт.')
    def ids(self):
        selected={r['product'].currentData() for r in self.rows};products=[p for p in self.products if p['id'] in selected]
        return {uid for p in products for uid in (p['id'],p['product'],p.get('food')) if uid}
    def busy(self,value):
        self.inputs.setEnabled(not value);self.fetch_button.setEnabled(not value);self.calculate_button.setEnabled(not value);self.cancel.setEnabled(value)
        self.premium.setEnabled(not value);self.focus.setEnabled(not value);self.sale.setEnabled(not value);self.age.setEnabled(not value)
        self.add_button.setEnabled(not value);self.remove_button.setEnabled(not value)
    def fetch(self):
        if self.worker or self.calculation:return
        self.worker=Fetch(AlbionAPI(self.owner.region),[],1,self.root,True,extra_price_ids=self.ids());self.busy(True)
        self.worker.progress.connect(self.status.setText);self.worker.failed.connect(self.status.setText)
        self.worker.ready.connect(lambda data:self.status.setText('Цены обновлены.'+(' '+data['warning'] if data['warning'] else '')))
        self.worker.finished.connect(self.fetch_finished);self.worker.start()
    def fetch_finished(self):
        self.worker.deleteLater();self.worker=None;self.busy(False)
    def calculate(self):
        if self.worker or self.calculation:return
        saved=self.snapshot();counts={}
        for row in saved:counts[row['city']]=counts.get(row['city'],0)+row['plots']
        if any(n>16 for n in counts.values()):self.status.setText('На одном острове не больше 16 участков.');return
        prices,_=market_snapshot(self.owner,self.root,self.ids());self.persist()
        self.calculation=ProcessWorker('island',dict(islands=saved,prices=prices,premium=self.premium.isChecked(),focus=self.focus.value(),sale=self.sale.currentData(),any_age=self.age.isChecked()),self)
        self.busy(True);self.status.setText('Распределяю фокус…')
        self.calculation.ready.connect(self.display);self.calculation.failed.connect(self.status.setText);self.calculation.finished.connect(self.calculated);self.calculation.start()
    def calculated(self):
        self.calculation.deleteLater();self.calculation=None;self.busy(False)
    def display(self,rows):
        if self.closed:return
        self.results=rows;self.output.setRowCount(len(rows));missing=[]
        for n,row in enumerate(rows):
            a=row['plain'];b=row['selected'];p=row['product'];s=row['settings'];missing.extend(b['missing'])
            values=[item_name(p['product'])+' • '+s['city'],f"{b['output']:,.1f}",f"{b['returned']:,.2f}",f"{b['replacement']:,.2f}",money(a['profit']),money(b['profit']),money(b['focus']),str(b['hours']),money(b['sale_price'])+'\n'+timestamp(b['sale_date'])]
            detail='\n'.join([f"{item_name(p['id'])}: {money(b['seed_price'])} • {timestamp(b['seed_date'])} • {b['seed_status']}",f"{item_name(p['product'])}: {money(b['sale_price'])} • {timestamp(b['sale_date'])} • {b['sale_status']}",'Нет цены: '+', '.join(item_name(uid) for uid in b['missing']) if b['missing'] else f"{b['output']} × {b['sale_price']} − комиссии; докупить {b['replacement']} × {b['seed_price']}; корм {money(b['feed_cost'])}; избыток {b['surplus']}."])
            for c,value in enumerate(values):
                cell=QTableWidgetItem(str(value));cell.setToolTip(detail)
                if c==0:cell.setIcon(self.owner.icons.get(p['product']))
                self.output.setItem(n,c,cell)
            self.output.setRowHeight(n,56)
        complete=all(r['selected']['profit'] is not None for r in rows)
        def total(key,group):return sum(r[group][key] for r in rows) if complete and rows else None
        self.metrics.update_values([money(total('profit','plain')),money(total('profit','selected')),money(total('investment','selected')),money(sum(r['selected']['focus'] for r in rows))])
        self.status.setText('Расчёт готов.' if complete else 'Неизвестно: не хватает цен. '+', '.join(item_name(uid) for uid in sorted(set(missing))))
        if rows and complete:
            from decimal import Decimal as D
            daily=sum(r['selected']['profit']*24/max(D(24),r['selected']['hours']) for r in rows)
            self.details.setText(f'При сборе раз в день: прибыль за 30 дней ≈ {money(daily*30)}. Закупка первого цикла оплачивается заранее; в следующих циклах докупается только недостающий посадочный материал и корм.')
    def cancel_work(self):
        for worker in (self.worker,self.calculation):
            if worker:worker.requestInterruption()
    def closeEvent(self,event):
        self.closed=True;self.cancel_work();self.persist();event.accept()
