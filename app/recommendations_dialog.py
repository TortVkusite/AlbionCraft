from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,QTableWidget,QTableWidgetItem,
    QAbstractItemView,QPushButton,QApplication)
from .recommendations import build_recommendations
from .item_names import item_name,recipe_variant
from .filter_dialog import QUALITY_NAMES
from .formatting import money,roi,timestamp
from .ui_layout import FlowLayout,readable_table,fit_window


class RecommendationsDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Рекомендации');self.resize(1120,680)
        self.owner=parent;layout=QVBoxLayout(self);self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.tabs=QTabWidget();layout.addWidget(self.tabs);self.tables=[]
        headers=[['Предмет','Город','Роль','Причина','Цена','Возраст','Рецептов'],
            ['Предмет','Город','Роль','Цена','Дата UTC','Источник'],
            ['Предмет','Город','Сценарий','Прибыль','ROI','Спрос / проверка']]
        for title,columns in zip(['Обновить данные','Цены уже есть','Кандидаты'],headers):
            table=QTableWidget(0,len(columns));table.setHorizontalHeaderLabels(columns);table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows);table.horizontalHeader().setStretchLastSection(True);table.verticalHeader().setVisible(False)
            self.tabs.addTab(table,title);self.tables.append(table)
        self.tables[2].cellDoubleClicked.connect(self.details)
        actions=FlowLayout();layout.addLayout(actions)
        copy=QPushButton('Скопировать название');actions.addWidget(copy);copy.clicked.connect(self.copy_name)
        self.update=QPushButton('Обновить недостающие и старые цены API');actions.addWidget(self.update);self.update.clicked.connect(self.refresh_api)
        close=QPushButton('Закрыть');actions.addWidget(close);close.clicked.connect(self.accept)
        tip=QLabel('Просмотр рынка в игре обновляет это окно автоматически. Общий ресурс указан один раз для города и качества. Кандидаты — повод проверить цены и расходы, а не обещание прибыли. Двойной клик по кандидату открывает расчёт.');tip.setWordWrap(True);layout.addWidget(tip)
        self.timer=QTimer(self);self.timer.setInterval(2000);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()
        for table in self.tables:readable_table(table);table.setColumnWidth(0,330)
        fit_window(self)
    def refresh(self):
        import time
        signature=(id(self.owner.recommendation_rows),repr(self.owner.settings.get('recommendations',{})),repr(self.owner.settings.get('result_limits',{})),int(time.time()//60))
        if signature==getattr(self,'signature',None):
            self.update.setEnabled(bool(self.data['update']) and not (self.owner.worker and self.owner.worker.isRunning()));return
        self.signature=signature
        self.data=build_recommendations(self.owner.recommendation_rows,self.owner.settings)
        self.summary.setText(f'Для выбранных фильтров: цены есть {self.data["with_price"]}/{self.data["price_count"]} • обновить: {len(self.data["update"])} • кандидатов: {len(self.data["candidates"])}. Порог давности: {self.owner.settings.get("recommendations",{}).get("stale_hours",6)} ч.')
        self.update.setEnabled(bool(self.data['update']) and not (self.owner.worker and self.owner.worker.isRunning()))
        for group,table in zip(('update','known','candidates'),self.tables):
            # Preserve selection while new prices arrive.
            selected=table.item(table.currentRow(),0);selected_key=selected.data(Qt.UserRole) if selected else None
            entries=self.data[group];table.setRowCount(len(entries))
            for n,p in enumerate(entries):
                if group=='candidates':
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
                    if group=='update' and c==3:cell.setForeground(QColor('#ff9999'))
                table.setRowHeight(n,56 if group=='candidates' and '\n' in values[0] else 40)
                if key==selected_key:table.selectRow(n)
            table.setColumnWidth(0,330);table.setColumnWidth(1,110)
    def copy_name(self):
        table=self.tables[self.tabs.currentIndex()];cell=table.item(table.currentRow(),0)
        if cell:QApplication.clipboard().setText(item_name(cell.data(Qt.UserRole)[0],False))
    def refresh_api(self):self.owner.refresh_price_ids({p['item_id'] for p in self.data['update']});self.refresh()
    def details(self,n,c):
        from .details import Details
        row=self.data['candidates'][n]['row'];Details(self.owner,row,row.get('quality',1),self.owner.settings).exec()
    def done(self,result):self.timer.stop();super().done(result)
    def showEvent(self,event):super().showEvent(event);self.timer.start();self.refresh()
