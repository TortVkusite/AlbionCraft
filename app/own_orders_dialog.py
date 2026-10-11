from .i18n import tr
from datetime import datetime,timezone,timedelta
from PySide6.QtCore import Qt,QTimer,QDateTime
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,
    QComboBox,QSpinBox,QLineEdit,QPushButton,QDialogButtonBox,QMessageBox,QDateTimeEdit)
from .models import CITIES
from .own_orders import OwnOrderStore,order_totals,amount
from .order_time import remaining_time,utc_time
from .formatting import money
from .rules import effective_settings
from .responsive import GuiBatch

DATA=Qt.UserRole;SORT=Qt.UserRole+1
STATES={'active':'Активен','finished':'Завершён','cancelled':'Отменён','unconfirmed':'Не проверен'}


class OrderCell(QTableWidgetItem):
    def __lt__(self,other):
        a=self.data(SORT);b=other.data(SORT)
        if isinstance(a,(int,float)) and isinstance(b,(int,float)):return a<b
        return str(a).casefold()<str(b).casefold() if a is not None and b is not None else super().__lt__(other)


class OwnOrdersDialog(QDialog):
    def __init__(self,parent,path):
        super().__init__(parent);self.setWindowTitle('Мои рыночные заказы');self.resize(1240,760)
        from .ui_layout import fit_window,readable_table,compact_combos
        self.store=OwnOrderStore(path);self.original=self.store.orders();self.seen_version=self.store.version();self.reloading=False;self.sort_column=None;self.sort_order=Qt.AscendingOrder
        layout=QVBoxLayout(self)
        note=QLabel('Клиент получает данные из сетевых сообщений игры. Создание и отмена учитываются после подтверждения сервера.\nСобственные страницы дополняют список; пропажа с одной страницы не удаляет остальные заказы. Двойной клик по заголовку — сортировка.');note.setWordWrap(True);layout.addWidget(note)
        self.capture_note=QLabel();self.capture_note.setWordWrap(True);layout.addWidget(self.capture_note)
        top=QHBoxLayout();layout.addLayout(top);top.addWidget(QLabel('Город:'))
        self.city=QComboBox();self.city.addItem('Все города',None)
        for city in CITIES:self.city.addItem(city,city)
        top.addWidget(self.city);self.city.currentIndexChanged.connect(self.totals)
        self.side=QComboBox()
        for text,key in [('Покупка и продажа',None),('Покупка','buy'),('Продажа','sell')]:self.side.addItem(text,key)
        top.addWidget(self.side);self.side.currentIndexChanged.connect(self.totals)
        self.state=QComboBox()
        for text,key in [('Текущие (подтверждённые)','current'),('Все состояния',None),('Активные','active'),('Завершённые','finished'),('Отменённые','cancelled'),('Не проверенные','unconfirmed')]:self.state.addItem(text,key)
        top.addWidget(self.state);self.state.currentIndexChanged.connect(self.totals);top.addStretch()
        actions=QHBoxLayout();actions.addStretch();layout.addLayout(actions);self.action_buttons=[]
        for title,action in [('Начать новый снимок',self.new_snapshot),('Добавить заказ',lambda:self.add_order()),('Удалить выбранный',self.remove_order)]:
            button=QPushButton(title);actions.addWidget(button);button.clicked.connect(action);self.action_buttons.append(button)
        self.table=QTableWidget(0,9);self.table.setHorizontalHeaderLabels(['Город','Заказ','Предмет','Остаток, шт.','Цена / шт.','Осталось','Сумма','Состояние','Источник / персонаж'])
        self.table.horizontalHeader().setStretchLastSection(True);self.table.verticalHeader().setVisible(False);layout.addWidget(self.table)
        self.table.horizontalHeader().sectionDoubleClicked.connect(self.sort_by)
        self.table.cellDoubleClicked.connect(self.edit_expiry);self.table.cellChanged.connect(self.totals)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setStyleSheet('font-size:16px;');layout.addWidget(self.summary)
        disclaimer=QLabel('Итоги относятся к выбранным фильтрам и полученным заказам. Комиссия размещения уже уплачена. Завершённые и отменённые заказы не входят в текущие суммы. Себестоимость, если была задана раньше, сохраняется.');disclaimer.setWordWrap(True);layout.addWidget(disclaimer)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);layout.addWidget(buttons);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Save).setText(tr('Сохранить'));buttons.button(QDialogButtonBox.Cancel).setText(tr('Отмена'))
        self.save_button=buttons.button(QDialogButtonBox.Save)
        self.row_batch=GuiBatch(self);self.total_batch=GuiBatch(self)
        self.row_batch.finished.connect(self.rows_loaded)
        self.reloading=True
        if len(self.original)>50:
            self.table.setEnabled(False);self.save_button.setEnabled(False)
            for button in self.action_buttons:button.setEnabled(False)
            self.row_batch.start(self.load_rows(self.original))
        else:
            for order in self.original:self.add_order(order)
            self.reloading=False
        for n,width in enumerate([110,105,285,105,105,120,110,110]):self.table.setColumnWidth(n,width)
        self.totals();self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.reload_captured);self.timer.start()
        readable_table(self.table);self.table.setColumnWidth(2,300)
        compact_combos(self);fit_window(self)

    def load_rows(self,orders):
        for n,order in enumerate(orders):
            self.add_order(order)
            self.capture_note.setText(f'Загружено заказов: {n+1} / {len(orders)}')
            yield
    def rows_loaded(self):
        self.reloading=False;self.table.blockSignals(False);self.table.setEnabled(True);self.save_button.setEnabled(True)
        for button in self.action_buttons:button.setEnabled(True)
        self.totals();self.apply_sort()

    def cell(self,n,col,text,key=None):
        item=OrderCell(str(text));item.setFlags(item.flags()&~Qt.ItemIsEditable);item.setData(SORT,str(text).casefold() if key is None else key);self.table.setItem(n,col,item);return item

    def add_order(self,order=None):
        order=dict(order) if order else dict(city=self.city.currentData() or 'Thetford',side=self.side.currentData() or 'buy',name='',quantity=1,price='0',cost=None,status='active',created=datetime.now(timezone.utc).isoformat(),expires=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat())
        n=self.table.rowCount();self.table.blockSignals(True);self.table.insertRow(n)
        self.cell(n,2,order['name']).setData(DATA,order)
        if order.get('source')=='auto':self.update_auto(n,order)
        else:
            self.table.item(n,2).setFlags(self.table.item(n,2).flags()|Qt.ItemIsEditable)
            city=QComboBox()
            for label in CITIES:city.addItem(label,label)
            city.setCurrentIndex(max(0,city.findData(order['city'])));self.table.setCellWidget(n,0,city)
            side=QComboBox();side.addItem('Покупка','buy');side.addItem('Продажа','sell');side.setCurrentIndex(max(0,side.findData(order['side'])));self.table.setCellWidget(n,1,side)
            qty=QSpinBox();qty.setRange(0,2000000000);qty.setValue(order['quantity']);self.table.setCellWidget(n,3,qty)
            price=QLineEdit(str(order['price']));self.table.setCellWidget(n,4,price)
            status=QComboBox()
            for key,text in STATES.items():status.addItem(text,key)
            status.setCurrentIndex(max(0,status.findData(order.get('status','active'))));self.table.setCellWidget(n,7,status)
            for col in (0,1,3,4,7):self.cell(n,col,'')
            self.cell(n,5,'');self.cell(n,6,'');self.cell(n,8,'Ручной ввод')
            for box in (city,side,status):box.currentIndexChanged.connect(self.totals)
            qty.valueChanged.connect(self.totals);price.textChanged.connect(self.totals)
        self.table.setRowHeight(n,42);self.table.blockSignals(False);self.totals()

    def update_auto(self,n,order):
        for col,value in {0:order['city'],1:'Покупка' if order['side']=='buy' else 'Продажа',2:order['name'],3:order['quantity'],4:money(amount(order['price'])),7:STATES[order['status']],8:'Из игры • '+order.get('player','')}.items():
            item=self.table.item(n,col)
            if item is None:item=self.cell(n,col,value)
            else:item.setText(str(value))
            item.setData(SORT,float(amount(order['price'])) if col==4 else order['quantity'] if col==3 else str(value).casefold())
            item.setToolTip(order.get('note','')+'\nID '+order['order_id'])
        self.table.item(n,2).setData(DATA,dict(order))
        for col in (5,6):
            if self.table.item(n,col) is None:self.cell(n,col,'')

    def entries(self):
        result=[]
        for n in range(self.table.rowCount()):
            record=dict(self.table.item(n,2).data(DATA))
            if record.get('source')!='auto':record.update(city=self.table.cellWidget(n,0).currentData(),side=self.table.cellWidget(n,1).currentData(),name=self.table.item(n,2).text().strip(),quantity=self.table.cellWidget(n,3).value(),price=str(amount(self.table.cellWidget(n,4).text())),status=self.table.cellWidget(n,7).currentData())
            result.append(record)
        return result

    def totals(self,*args):
        if not hasattr(self,'summary') or self.reloading:return
        try:entries=self.entries()
        except (ValueError,AttributeError):self.summary.setText('Проверь суммы в полях цены.');return
        self.total_batch.start(self.paint_totals(entries))
    def paint_totals(self,entries):
        visible=[];unconfirmed=[];self.table.blockSignals(True)
        for n,entry in enumerate(entries):
            if entry.get('expires') and utc_time(entry['expires'])<=datetime.now(timezone.utc) and entry['status']=='active':entry['status']='finished'
            total=amount(entry['price'])*entry['quantity'];self.table.item(n,6).setText(money(total));self.table.item(n,6).setData(SORT,float(total))
            text,tip,seconds=remaining_time(entry);self.table.item(n,5).setText(text);self.table.item(n,5).setToolTip(tip);self.table.item(n,5).setData(SORT,seconds)
            for col,val in {0:entry['city'],1:'Покупка' if entry['side']=='buy' else 'Продажа',2:entry['name'],3:entry['quantity'],4:float(amount(entry['price'])),7:STATES[entry['status']]}.items():
                # QVariant compares numeric strings equal to numbers. Clear the
                # old role first so its type really becomes numeric for sorting.
                self.table.item(n,col).setData(SORT,None);self.table.item(n,col).setData(SORT,val.casefold() if isinstance(val,str) else val)
            if entry.get('source')=='auto':self.table.item(n,7).setText(STATES[entry['status']])
            show=(not self.city.currentData() or entry['city']==self.city.currentData()) and (not self.side.currentData() or entry['side']==self.side.currentData())
            if show and entry['status']=='unconfirmed':unconfirmed.append(entry)
            state=self.state.currentData();show=show and (state is None or (entry['status']=='active' if state=='current' else entry['status']==state))
            self.table.setRowHidden(n,not show)
            if show:visible.append(entry)
            yield
        self.table.blockSignals(False)
        tax=effective_settings(self.parent().settings).get('tax');known_tax=True
        try:x=order_totals(visible,tax)
        except ValueError:x=order_totals(visible,0);known_tax=False
        net=f'после налога {tax}%: ≈ {money(x["net"])}' if known_tax else 'налог не задан — чистая выручка неизвестна'
        lower='≥ ' if x['unknown_cost'] else ''
        self.summary.setText(f'Зарезервировано на покупку: {money(x["buy"])}\nПродажи по ордерам: {money(x["sell"])} • {net}\nВсего по ценам заказов: {money(x["order_value"])} • фактически вложено по известным затратам: {lower}{money(x["invested"])}\nАктивных заказов: {x["active"]}; без себестоимости продажи: {x["unknown_cost"]}.')
        if unconfirmed and state in (None,'current','active','unconfirmed'):
            previous=order_totals([dict(e,status='active') for e in unconfirmed],0)
            unknown=f'Не проверено: {len(unconfirmed)}. Последний известный резерв покупки: {money(previous["buy"])}; продажи: {money(previous["sell"])}. Эти суммы не входят в подтверждённый итог.'
            if not x['active']:
                self.summary.setText('Текущие суммы неизвестны: заказы после нового снимка ещё не подтверждены.\n'+unknown+'\nПросмотри свои заказы в игре. Старые записи доступны в фильтре «Не проверенные».')
            else:self.summary.setText(self.summary.text()+'\n'+unknown)
        auto=[e for e in entries if e.get('source')=='auto']
        self.capture_note.setText(f'Из игры: {len(auto)} заказов. '+self.store.capture_status() if auto else 'Собственные заказы ещё не получены. '+self.store.capture_status())

    def sort_by(self,column):
        self.sort_order=Qt.DescendingOrder if self.sort_column==column and self.sort_order==Qt.AscendingOrder else Qt.AscendingOrder
        self.sort_column=column;self.apply_sort()

    def apply_sort(self):
        if self.sort_column is not None:
            self.total_batch.cancel();self.table.blockSignals(False)
            self.table.horizontalHeader().setSortIndicatorShown(True);self.table.horizontalHeader().setSortIndicator(self.sort_column,self.sort_order);self.table.sortItems(self.sort_column,self.sort_order)
            self.totals()

    def reload_captured(self):
        if self.reloading:return
        version=self.store.version()
        if version==self.seen_version:
            if self.total_batch.pending is None:self.totals()
            return
        self.total_batch.cancel();self.table.blockSignals(False)
        new=self.store.orders();auto={tuple(e['auto_key']):e for e in new if e.get('source')=='auto'}
        seed_ids={e['id'] for e in new if e.get('source')!='auto'}
        self.reloading=True;self.table.blockSignals(True)
        self.table.setEnabled(False);self.save_button.setEnabled(False)
        for button in self.action_buttons:button.setEnabled(False)
        self.seen_version=version
        self.row_batch.start(self.update_rows(auto,seed_ids))

    def update_rows(self,auto,seed_ids):
        for n in reversed(range(self.table.rowCount())):
            record=self.table.item(n,2).data(DATA)
            if record.get('source')=='auto':
                key=tuple(record['auto_key'])
                if key in auto:self.update_auto(n,auto.pop(key))
            elif record.get('note','').startswith('Только видимые строки пользовательского скриншота') and record.get('id') not in seed_ids:self.table.removeRow(n)
            yield
        for order in auto.values():self.add_order(order);yield

    def edit_expiry(self,n,col):
        if col!=5:return
        record=dict(self.table.item(n,2).data(DATA))
        if record.get('source')=='auto':return
        popup=QDialog(self);popup.setWindowTitle('Срок ручного заказа');layout=QVBoxLayout(popup)
        edit=QDateTimeEdit(QDateTime(utc_time(record.get('expires')) or datetime.now(timezone.utc)));edit.setDisplayFormat('dd.MM.yyyy HH:mm:ss');edit.setCalendarPopup(True);layout.addWidget(edit)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);layout.addWidget(buttons);buttons.accepted.connect(popup.accept);buttons.rejected.connect(popup.reject)
        if popup.exec():record['expires']=edit.dateTime().toPython().astimezone(timezone.utc).isoformat();self.table.item(n,2).setData(DATA,record);self.totals();self.apply_sort()

    def remove_order(self):
        n=self.table.currentRow()
        if n>=0:
            if self.table.item(n,2).data(DATA).get('source')=='auto':self.capture_note.setText('Отмени этот заказ в игре. Подтверждение сервера обновит только его строку.');return
            self.table.removeRow(n);self.totals()

    def new_snapshot(self):self.store.new_snapshot();self.reload_captured()
    def save(self):
        if self.reloading:return
        try:self.store.save(self.entries())
        except ValueError as exc:QMessageBox.warning(self,'Заказы',str(exc));return
        self.accept()
    def done(self,result):self.timer.stop();self.row_batch.cancel();self.total_batch.cancel();self.table.blockSignals(False);self.store.close();super().done(result)
