import json,time,sqlite3
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QTimer,QUrl
from PySide6.QtGui import QDesktopServices,QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,
    QSpinBox,QCheckBox,QGridLayout,QTableWidget,QTableWidgetItem,QAbstractItemView,QSplitter,QWidget)
from .builds import ACTIVITIES,SLOTS,SOURCE,fetch_grind,evaluate,variant,build_variants
from .models import CITIES
from .formatting import money,roi,timestamp
from .calculator import demand_text
from .filter_dialog import QUALITY_NAMES
from .item_names import item_name
from .ui_layout import FlowLayout,explanation,readable_table,compact_combos,fit_window


class BuildFetch(QThread):
    ready=Signal(object);failed=Signal(str)
    def __init__(self,activity):super().__init__();self.activity=activity
    def run(self):
        try:self.ready.emit(fetch_grind(self.activity))
        except Exception as exc:self.failed.emit(str(exc))


class BuildsDialog(QDialog):
    def __init__(self,parent,root):
        super().__init__(parent);self.owner=parent;self.root=Path(root);self.setWindowTitle('Билды / рынок');self.resize(1420,880)
        self.path=self.root/'builds_grind.json';self.snapshots={};self.rows=[];self.selected=None;self.worker=None;self.signature=None
        try:self.snapshots=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
        prefs=parent.settings.get('build_tracker',{})
        layout=QVBoxLayout(self);controls=QGridLayout();layout.addLayout(controls)
        self.activity=QComboBox()
        for key,label in ACTIVITIES.items():self.activity.addItem(label,key)
        self.city=QComboBox();self.city.addItems(CITIES)
        self.tier=QComboBox();self.tier.addItem('Все тиры',None)
        for n in range(1,9):self.tier.addItem('T'+str(n),n)
        self.enchantment=QComboBox();self.enchantment.addItem('Все чары',None)
        for n in range(5):self.enchantment.addItem('.'+str(n),n)
        self.quality=QComboBox();self.quality.addItem('Качество неважно',None)
        for n,label in enumerate(QUALITY_NAMES,1):self.quality.addItem(label,n)
        for box in (self.activity,self.city,self.tier,self.enchantment,self.quality):
            box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);box.setMinimumContentsLength(8)
        self.budget=QSpinBox();self.budget.setRange(0,1000000000);self.budget.setSingleStep(50000);self.budget.setSpecialValueText('Без ограничения');self.budget.setValue(int(prefs.get('budget',300000)))
        self.sort=QComboBox();self.sort.addItem('Популярные в бюджете','popular');self.sort.addItem('Дешёвые сначала','cheap')
        for n,(name,control) in enumerate([('Контент',self.activity),('Город',self.city),('Тир',self.tier),('Чары',self.enchantment),('Качество',self.quality),('Бюджет',self.budget),('Сортировка',self.sort)]):
            controls.addWidget(QLabel(name),n//4,(n%4)*2)
            controls.addWidget(control,n//4,(n%4)*2+1)
        self.tier.setCurrentIndex(self.tier.findData(4));self.enchantment.setCurrentIndex(self.enchantment.findData(0))
        self.city.setCurrentText(prefs.get('city') or parent.craft.currentData() or 'Thetford')
        for key,control in [('activity',self.activity),('tier',self.tier),('enchantment',self.enchantment),('quality',self.quality),('sort',self.sort)]:
            if key in prefs:
                n=control.findData(prefs[key])
                if n>=0:control.setCurrentIndex(n)
        options=FlowLayout();layout.addLayout(options)
        self.incomplete=QCheckBox('Показывать комплекты с недостающими ценами');self.incomplete.setChecked(True);options.addWidget(self.incomplete)
        self.site_button=QPushButton('Обновить билды сайта');options.addWidget(self.site_button);self.site_button.clicked.connect(lambda:self.load_site(True))
        self.price_button=QPushButton('Обновить цены выбранного комплекта');options.addWidget(self.price_button);self.price_button.clicked.connect(self.update_prices)
        source=QPushButton('Открыть источник');options.addWidget(source);source.clicked.connect(self.open_source)
        personal=FlowLayout();layout.addLayout(personal)
        own=QPushButton('Мой билд — подобрать дешевле');personal.addWidget(own);own.clicked.connect(self.open_loadout)
        imported=QPushButton('Подобрать дешевле выбранный билд');personal.addWidget(imported);imported.clicked.connect(lambda:self.open_loadout(True));personal.addStretch()
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        split=QSplitter(Qt.Vertical);layout.addWidget(split,1)
        self.build_table=self.table(['Билд / активность','Голоса сайта','Стоимость','Цены / проверка','Обновлён автором']);split.addWidget(self.build_table)
        bottom=QSplitter();split.addWidget(bottom)
        self.parts=self.table(['Предмет / слот','Цена покупки','Качество','Продажи','Крафт\nприбыль / ROI','Перепокупка\nприбыль / ROI','Дата цены']);bottom.addWidget(self.parts)
        self.common=self.table(['Общие предметы','Билдов']);bottom.addWidget(self.common);bottom.setSizes([1050,330]);split.setSizes([300,360])
        self.build_table.itemSelectionChanged.connect(self.select_build);self.parts.cellDoubleClicked.connect(self.details)
        self.common.cellDoubleClicked.connect(self.search_common)
        explanation(layout,'Рейтинг — голоса пользователей сайта, не число покупок. Бюджет применяется только к комплектам с полными ценами. Оружие и броня пересчитываются на выбранные T/чары; еда и зелье остаются из билда, по 1 штуке. Без сумки, маунта и альтернатив. Дешёвые популярные комплекты — кандидаты для проверки; фактический оборот указан отдельно.','Как читать результаты')
        self.timer=QTimer(self);self.timer.setInterval(2000);self.timer.timeout.connect(self.refresh)
        for control in (self.city,self.tier,self.enchantment,self.quality,self.sort):control.currentIndexChanged.connect(self.changed)
        self.activity.currentIndexChanged.connect(self.activity_changed);self.budget.valueChanged.connect(self.changed);self.incomplete.toggled.connect(self.changed)
        self.refresh();QTimer.singleShot(0,lambda:self.load_site(False))
        compact_combos(self)
        for table in (self.build_table,self.parts,self.common):readable_table(table)
        fit_window(self)
    def table(self,headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection);table.verticalHeader().hide();table.horizontalHeader().setStretchLastSection(True);return table
    def open_loadout(self,selected=False):
        from .loadout_dialog import LoadoutDialog
        LoadoutDialog(self.owner,self.root,self.selected['build'] if selected and self.selected else None).exec()
    def changed(self,*args):
        self.owner.settings['build_tracker']=dict(activity=self.activity.currentData(),city=self.city.currentText(),tier=self.tier.currentData(),enchantment=self.enchantment.currentData(),quality=self.quality.currentData(),budget=self.budget.value(),sort=self.sort.currentData())
        self.owner.persist_view();self.signature=None;self.refresh()
    def activity_changed(self,*args):self.changed();self.load_site(False)
    def load_site(self,force=False):
        if self.worker and self.worker.isRunning():return
        key=self.activity.currentData();saved=self.snapshots.get(key)
        if not force and saved and time.time()-saved.get('fetched',0)<21600:
            self.status.setText('Билды из сохранённого списка '+SOURCE+'; обновление: '+time.strftime('%d.%m %H:%M',time.localtime(saved['fetched'])));return
        self.worker=BuildFetch(key);self.site_button.setEnabled(False);self.status.setText('Загружаю популярные билды '+SOURCE+'…')
        self.worker.ready.connect(lambda data,key=key:self.received(key,data));self.worker.failed.connect(lambda error:self.status.setText('Сайт недоступен: '+error+'. Сохранённый список остаётся доступен.'))
        self.worker.finished.connect(self.fetch_finished);self.worker.start()
    def fetch_finished(self):
        self.site_button.setEnabled(True)
        if self.worker.activity!=self.activity.currentData():self.load_site(False)
    def received(self,key,data):
        self.snapshots[key]=data;temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.snapshots,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(self.path)
        self.status.setText('Получено '+str(len(data['builds']))+' билдов '+SOURCE+('. Это первая страница рейтинга; есть ещё билды.' if data['has_more'] else '.'))
        self.signature=None;self.refresh()
    def market(self,ids):
        from .market_snapshot import market_snapshot
        return market_snapshot(self.owner,self.root,ids)
    def refresh(self):
        self.price_button.setEnabled(bool(self.selected) and not(self.owner.worker and self.owner.worker.isRunning()))
        signature=(self.activity.currentData(),id(self.owner.last),repr(self.owner.settings.get('general')),int(time.time()//10))
        if signature==self.signature:return
        self.signature=signature
        builds=self.snapshots.get(self.activity.currentData(),{}).get('builds',[])
        available={r.item_id for r in self.owner.recipes}
        scenarios=[(b,t,e) for b in builds for t,e in build_variants(b,self.tier.currentData(),self.enchantment.currentData(),available)]
        ids={variant(uid,slot,t,e) for b,t,e in scenarios for slot,uid in b['items'].items()}
        # Also include recipe ingredients when evaluating crafting profit.
        recipes=[r for r in self.owner.recipes if r.item_id in ids];all_ids=ids|{i.item_id for r in recipes for i in r.ingredients}
        prices,histories=self.market(all_ids);settings=dict(self.owner.settings,activity='craft',sale_mode='order')
        context={}
        results=[evaluate(b,prices,histories,self.city.currentText(),t,e,self.quality.currentData(),recipes,settings,context) for b,t,e in scenarios]
        self.rows=[r for r in results if (r['complete'] and (not self.budget.value() or r['cost']<=self.budget.value())) or (not r['complete'] and self.incomplete.isChecked())]
        self.rows.sort(key=lambda r:(not r['complete'],r['cost'] if self.sort.currentData()=='cheap' else -r['build']['votes'],r['cost'] if r['complete'] else float('inf'),r['build']['id'],r['tier'],r['enchantment']))
        selected_id=self.selected['key'] if self.selected else None
        self.build_table.blockSignals(True);self.build_table.setRowCount(len(self.rows))
        for n,r in enumerate(self.rows):
            b=r['build'];state='В бюджете' if r['complete'] and self.budget.value() else 'Цены полные' if r['complete'] else 'Недостаёт цен: '+str(len(r['missing']))+'; бюджет неизвестен'
            if any(p['age'] is not None and p['age']>30 for p in r['parts']):state+='; есть старые цены'
            values=[item_name(b['items']['weapon_id'],False).split(' (')[0]+f' • T{r["tier"]}.{r["enchantment"]} — '+ACTIVITIES.get(b['activity'],b['activity']),b['votes'],('Нет цен' if not r['complete'] and not r['cost'] else ('≥ ' if not r['complete'] else '')+money(r['cost'])),state,b['updated'][:10]]
            for c,value in enumerate(values):
                cell=QTableWidgetItem(str(value));cell.setToolTip(b['title']+'\n'+b['url']);self.build_table.setItem(n,c,cell)
            self.build_table.setRowHeight(n,40)
        self.build_table.setColumnWidth(0,360);self.build_table.setColumnWidth(1,110);self.build_table.setColumnWidth(2,150);self.build_table.setColumnWidth(3,460)
        self.build_table.blockSignals(False)
        self.summary.setText(f'Вариантов показано: {len(self.rows)} / {len(results)} • билдов: {len(builds)} • с полной стоимостью: {sum(r["complete"] for r in results)}. Цены: {self.city.currentText()} / {self.tier.currentText()} / {self.enchantment.currentText()}. Источник: {SOURCE}.')
        index=next((n for n,r in enumerate(self.rows) if r['key']==selected_id),0)
        self.selected=None
        if self.rows:self.build_table.selectRow(index);self.select_build()
        else:self.parts.setRowCount(0)
        counts={};concrete=False
        for b in builds:
            # One vote per build, not one per tier/enchantment combination.
            concrete=self.tier.currentData() is not None and self.enchantment.currentData() is not None
            values={variant(uid,slot,self.tier.currentData(),self.enchantment.currentData()) if concrete else uid.split('@')[0] for slot,uid in b['items'].items()}
            for uid in values:counts[uid]=counts.get(uid,0)+1
        self.common_ids=sorted(counts,key=lambda uid:(-counts[uid],uid));self.common.setRowCount(len(self.common_ids))
        for n,uid in enumerate(self.common_ids):
            self.common.setItem(n,0,QTableWidgetItem(item_name(uid) if concrete else item_name(uid,False).split(' (')[0]));self.common.setItem(n,1,QTableWidgetItem(str(counts[uid])))
        self.common_concrete=concrete
        self.common.setColumnWidth(0,230);self.common.setColumnWidth(1,75)
    def select_build(self):
        n=self.build_table.currentRow()
        if not 0<=n<len(self.rows):return
        self.selected=self.rows[n];self.parts.setRowCount(len(self.selected['parts']))
        for n,p in enumerate(self.selected['parts']):
            def profit(row):return ('≤ ' if row.get('pending_costs') else '')+money(row['base']['profit'])+' / '+roi(row['base']['roi']) if row else 'Нет расчёта'
            values=[p['name']+'\n'+SLOTS[p['slot']],money(p['price']),QUALITY_NAMES[p['quality']-1],demand_text(p['demand']),profit(p['craft']),profit(p['flip']),timestamp(p['date'])]
            for c,value in enumerate(values):
                cell=QTableWidgetItem(str(value));cell.setToolTip(p['item_id']+'\n'+p['status']+'\n'+p['source']);self.parts.setItem(n,c,cell)
                if c==0:cell.setIcon(self.owner.icons.get(p['item_id'],p['quality']))
                if c in (4,5):
                    row=p['craft' if c==4 else 'flip']
                    if row:cell.setToolTip('\n'.join(row['issues']+row['reasons']))
                    if row and row['base']['profit']<0:cell.setForeground(QColor('#ff7777'))
            self.parts.setRowHeight(n,72 if p['demand']['per_day']>=1000 else 60)
        for c,width in enumerate([230,100,105,150,155,170,155]):self.parts.setColumnWidth(c,width)
        self.price_button.setEnabled(not(self.owner.worker and self.owner.worker.isRunning()))
    def update_prices(self):
        if not self.selected or self.owner.worker and self.owner.worker.isRunning():return
        ids={p['item_id'] for p in self.selected['parts']};recipes=[r for r in self.owner.recipes if r.item_id in ids]
        ids|={i.item_id for r in recipes for i in r.ingredients}
        self.owner.start_fetch(recipes,True,ids);self.status.setText('Обновляются предметы комплекта, ингредиенты и история рынка. Просмотр в игре также обновляет цены.');self.price_button.setEnabled(False)
    def open_source(self):
        url=self.selected['build']['url'] if self.selected else 'https://albiononlinegrind.com/builds?sort=POPULAR'
        QDesktopServices.openUrl(QUrl(url))
    def details(self,n,column):
        if not self.selected:return
        p=self.selected['parts'][n];row=p['flip'] if column==5 else p['craft'] or p['flip']
        if row:
            from .details import Details
            Details(self.owner,row,p['quality'],self.owner.settings).exec()
    def search_common(self,n,column):
        if n<len(self.common_ids):
            from PySide6.QtWidgets import QApplication
            name=item_name(self.common_ids[n],False)
            if not self.common_concrete:name=name.split(' (')[0]
            QApplication.clipboard().setText(name);self.status.setText('Название скопировано для поиска в игре.')
    def showEvent(self,event):super().showEvent(event);self.timer.start();self.signature=None;self.refresh();self.load_site(False)
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)
    def closeEvent(self,event):
        self.timer.stop()
        if self.worker and self.worker.isRunning():self.hide();event.ignore()
        else:super().closeEvent(event)
