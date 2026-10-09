from decimal import Decimal as D
from PySide6.QtCore import Qt
from .i18n_widgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QTableWidget,QTableWidgetItem,QLineEdit,QPushButton,QCheckBox,QInputDialog
from .trip_ledger import TripLedger,actual_summary
from .item_names import item_name
from .formatting import money
from .ui_layout import readable_table,compact_combos,fit_window

KINDS={'purchase':'Новая закупка','stock':'Взятые запасы','production':'Произведено','sale':'Продажа','leftover':'Остаток'}

def amount(value):return f'{D(value):,.2f}'.replace(',',' ').replace('.',',')
def quantity(value):return format(D(value).quantize(D('.01')),'f').rstrip('0').rstrip('.') if '.' in str(D(value).quantize(D('.01'))) else str(value)


class TripLedgerDialog(QDialog):
    def __init__(self,parent,root,player,current=None):
        super().__init__(parent);self.store=TripLedger(root/'player.sqlite');self.player=player;self.current=current;self.loading=False
        self.setWindowTitle('Ходки — план и факт');self.resize(1120,760)
        layout=QVBoxLayout(self);bar=QHBoxLayout();layout.addLayout(bar)
        self.choose=QComboBox();bar.addWidget(self.choose,1);self.choose.currentIndexChanged.connect(self.load)
        add=QPushButton('Сохранить текущий план как ходку');add.setEnabled(current is not None);bar.addWidget(add);add.clicked.connect(self.create)
        note=QLabel('Суммы относятся ко всей строке, не к одной штуке. Заполняй фактические покупки, стоимость использованных запасов, выпуск и продажи. Пусто = неизвестно; 0 = подтверждённый ноль. Продажа — до комиссий. План сверки — денежный результат, без оценки возвратов и непроданных остатков. Уровни и банк здесь не изменяются.');note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['Этап / ресурс','План: шт.','План: сумма','Факт: шт.','Факт: сумма','Разница']);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table,1);self.table.itemChanged.connect(self.preview)
        add_line=QPushButton('Добавить ресурс / этап вне плана');layout.addWidget(add_line);add_line.clicked.connect(self.add_line)
        form=QFormLayout();layout.addLayout(form);self.fields={};self.expected={}
        for key,title in [('station','Плата станции'),('other','Прочие расходы'),('sale_fees','Комиссии рынка, включая перевыставление')]:
            line=QHBoxLayout();field=QLineEdit();field.setPlaceholderText('Фактическая сумма');expected=QLabel();line.addWidget(field);line.addWidget(expected);form.addRow(title,line);self.fields[key]=field;self.expected[key]=expected;field.textChanged.connect(self.preview)
        self.closed=QCheckBox('Учёт партии завершён — записать результат в журнал');self.closed.setToolTip('Подтверди только после сверки всех расходов и продаж. Непроданные остатки не оценены: прибыль включает затраты на них.');layout.addWidget(self.closed);self.closed.toggled.connect(self.preview)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        bar=QHBoxLayout();layout.addLayout(bar);save=QPushButton('Сохранить фактические данные');save.clicked.connect(self.save);bar.addWidget(save);close=QPushButton('Закрыть');close.clicked.connect(self.accept);bar.addWidget(close)
        self.refresh()
        readable_table(self.table);self.table.setColumnWidth(0,330)
        compact_combos(self);fit_window(self)
    def refresh(self,selected=None):
        self.loading=True;self.entries=self.store.entries(self.player);self.choose.clear()
        for e in self.entries:self.choose.addItem(e['stamp'][:16].replace('T',' ')+' • '+e['snapshot']['buy']+' → '+e['snapshot']['craft']+(' • завершена' if e['facts'].get('closed') else ''),e['id'])
        if selected is not None:self.choose.setCurrentIndex(self.choose.findData(selected))
        self.loading=False;self.load()
    def create(self):
        if self.current is None:return
        run=self.store.create(self.player,self.current);self.current=None;self.sender().setEnabled(False);self.refresh(run)
    def load(self,*args):
        if self.loading:return
        self.entry=next((e for e in self.entries if e['id']==self.choose.currentData()),None);self.loading=True
        rows=self.entry['snapshot']['rows'] if self.entry else [];facts=self.entry['facts'] if self.entry else {};actual={(r['kind'],r['item_id']):r for r in facts.get('rows',[])}
        self.table.setRowCount(len(rows))
        for n,r in enumerate(rows):
            a=actual.get((r['kind'],r['item_id']),{})
            for col,value in enumerate([KINDS[r['kind']]+': '+item_name(r['item_id'],False),quantity(r['quantity']),amount(r['amount']) if r['amount'] is not None else '—',a.get('quantity',''),a.get('amount',''),'']):
                cell=QTableWidgetItem(str(value or ''))
                if col==1:cell.setToolTip(r['quantity'])
                if col not in (3,4) or col==4 and r['kind'] in ('production','leftover'):cell.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable)
                self.table.setItem(n,col,cell)
        for key,field in self.fields.items():field.setText(str(facts.get(key,'') or ''));self.expected[key].setText('План: '+amount(self.entry['snapshot'][key]) if self.entry else '')
        self.closed.setChecked(bool(facts.get('closed')));self.loading=False;self.table.resizeColumnsToContents();self.preview()
    def facts(self):
        def text(value):return value.strip().replace(' ','').replace(',','.')
        return dict(rows=[dict(kind=r['kind'],item_id=r['item_id'],quantity=text(self.table.item(n,3).text()),amount=text(self.table.item(n,4).text())) for n,r in enumerate(self.entry['snapshot']['rows'])],closed=self.closed.isChecked(),**{k:text(f.text()) for k,f in self.fields.items()})
    def add_line(self):
        if not self.entry:return
        labels=list(KINDS.values());label,ok=QInputDialog.getItem(self,'Этап','Что учитывать?',labels,0,False)
        if not ok:return
        ids=sorted({r.item_id for r in self.parent().recipes}|{i.item_id for r in self.parent().recipes for i in r.ingredients})
        names=[item_name(uid,False)+' ['+uid+']' for uid in ids]
        name,ok=QInputDialog.getItem(self,'Ресурс','Предмет:',names,0,False)
        if not ok:return
        try:
            self.store.save(self.player,self.entry['id'],dict(self.facts(),closed=False))
            self.store.add_row(self.player,self.entry['id'],next(k for k,v in KINDS.items() if v==label),ids[names.index(name)]);self.refresh(self.entry['id'])
        except (ValueError,ArithmeticError) as exc:self.summary.setText(str(exc))
    def preview(self,*args):
        if self.loading:return
        if not self.entry:self.summary.setText('Сохрани текущий план или выбери ранее сохранённую ходку.');return
        try:
            facts=self.facts();s=actual_summary(self.entry['snapshot'],facts)
            self.loading=True
            for n,(r,a) in enumerate(zip(self.entry['snapshot']['rows'],facts['rows'])):
                self.table.item(n,5).setText(amount(D(a['amount'])-D(r['amount'])) if r['amount'] is not None and a['amount'] else quantity(D(a['quantity'])-D(r['quantity']))+' шт.' if r['amount'] is None and a['quantity'] else '—')
            self.loading=False
            if s['profit'] is None:self.summary.setText(f"План: {amount(self.entry['snapshot']['profit'])}. Не заполнено фактических значений: {len(s['missing'])}.")
            else:
                reasons={'sale':'Выручка','purchase':'Закупка','stock':'Запасы','station':'Станция','other':'Прочие','sale_fees':'Комиссии'}
                changes=' • '.join(f'{reasons[k]}: {amount(v)}' for k,v in s['changes'].items() if v)
                self.summary.setText(('Итог партии' if s['closed'] else 'Промежуточный результат')+f": {amount(s['profit'])} • отклонение от плана: {amount(s['delta'])}. Непроданные остатки не включены в выручку.\n"+changes)
        except (ValueError,ArithmeticError) as exc:self.loading=False;self.summary.setText(str(exc))
    def save(self):
        if not self.entry:return
        try:self.store.save(self.player,self.entry['id'],self.facts());self.refresh(self.entry['id']);self.summary.setText(self.summary.text()+'\nСохранено.')
        except (ValueError,ArithmeticError) as exc:self.summary.setText('Не сохранено: '+str(exc))
    def done(self,result):
        if not getattr(self,'_closed',False):self.store.close();self._closed=True
        super().done(result)
