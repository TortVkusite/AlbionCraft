from pathlib import Path
from decimal import Decimal as D
from datetime import datetime,timezone
import logging
from PySide6.QtCore import Qt,QThread,Signal,QTimer,Slot
from PySide6.QtGui import QColor
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QComboBox,
    QLineEdit,QPushButton,QDoubleSpinBox,QSpinBox,QCheckBox,QTableWidget,QTableWidgetItem,
    QAbstractItemView,QTabWidget,QWidget,QMessageBox,QSplitter,QRadioButton,QButtonGroup)
from .models import CITIES
from .formatting import money,roi
from .item_names import item_name
from .scanner import number
from .crafter_dialog import progression
from .progression import PlayerStore
from .market_snapshot import market_snapshot
from .trip_optimizer import (refining_recipes,candidates,solve,shopping,sale_comparisons,
    simulate_progress,unlocked,fame_per_item,focus_per_operation)
from .trip_chain import dependency_recipes,prepare_chain,solve_chain
from .trip_inventory import StockStore,route_stock
from .trip_market import configure_market,turnover
from .ui_layout import FlowLayout,explanation,readable_table,fit_window
from .i18n_widgets import QScrollArea
from .number_fields import NumberBox,LargeNumberBox
from .background import ProcessWorker
from .dashboard import panel,section,fold,move_widgets,title,Metrics

FAMILIES={'ore':'Руда / слитки','fiber':'Волокно / ткань','hide':'Шкуры / кожа','wood':'Древесина / брусья','rock':'Камень / блоки'}

def decimal_text(value,places=2):
    return f'{value:,.{places}f}'.replace(',',' ').replace('.',',') if value is not None else '—'

def node_label(key):
    suffix=key.replace('CRAFT_REFINE_','');kind,_,tier=suffix.partition('_T')
    return FAMILIES.get(kind.lower(),kind)+' • T'+tier

class NoWheelDouble(LargeNumberBox):
    def wheelEvent(self,event):event.ignore()
class NoWheelInt(NumberBox):
    def wheelEvent(self,event):event.ignore()


class TripDialog(QDialog):
    def __init__(self,parent,root):
        super().__init__(parent);self.owner=parent;self.root=Path(root);self.game=progression(str(root))
        self.store=PlayerStore(self.root/'player.sqlite');self.worker=None;self.plans=[];self.progress=[];self.recorded=False;self.closed=False;self.audit_options=[];self.rejected=[]
        self.stock_store=StockStore(self.root/'player.sqlite');self.stock_missing=[]
        self.setWindowTitle('Калькулятор ходки — максимальная прибыль');self.resize(1420,940)
        self.recipes=refining_recipes(parent.recipes);prefs=parent.settings.get('trip_optimizer',{})
        outer=QVBoxLayout(self);controls=QWidget();layout=QVBoxLayout(controls);layout.setContentsMargins(4,4,4,4)
        self.controls_scroll=QScrollArea();self.controls_scroll.setWidgetResizable(True);self.controls_scroll.setWidget(controls)
        self.controls_scroll.setMinimumHeight(180);outer.addWidget(self.controls_scroll,2)
        grid=QGridLayout();layout.addLayout(grid)
        self.buy=QComboBox();self.buy.addItems(CITIES);self.buy.setCurrentText(prefs.get('buy','Fort Sterling'))
        self.craft=QComboBox();self.craft.addItems(CITIES);self.craft.setCurrentText(prefs.get('craft','Thetford'))
        self.player=QLineEdit(prefs.get('player',parent.settings.get('progress_player','Мой персонаж')))
        self.weight=NoWheelDouble();self.weight.setDecimals(2);self.weight.setRange(.01,1000000);self.weight.setValue(float(prefs.get('weight',1000)));self.weight.setSuffix(' кг')
        self.budget=NoWheelDouble();self.budget.setDecimals(0);self.budget.setRange(0,1e12);self.budget.setValue(float(prefs.get('budget',1000000)))
        self.budget.setToolTip('Бюджет только новых покупок. Уже имеющиеся ресурсы в него не входят; 0 = переработка только запасов.')
        self.focus=NoWheelInt();self.focus.setRange(0,30000);self.focus.setValue(int(prefs.get('focus',10000)))
        self.station=QLineEdit(str(prefs.get('station',parent.settings.get('station_rates',{}).get(self.craft.currentText(),''))));self.station.setPlaceholderText('Обязательно; 0 = бесплатно')
        self.other=NoWheelDouble();self.other.setRange(0,1e8);self.other.setDecimals(2);self.other.setValue(float(prefs.get('other',0)))
        self.other.setToolTip('Дополнительные расходы на единицу результата. Плату станции сюда не вводи: она уже рассчитана по тарифу станции и питанию рецепта.')
        self.station.setToolTip('Тариф из игры: серебро за 100 питания. Калькулятор сам умножает его на питание рецепта; это не плата за один слиток.')
        self.multiplier=NoWheelDouble();self.multiplier.setRange(0,100);self.multiplier.setDecimals(2);self.multiplier.setValue(float(prefs.get('xp_multiplier',1)));self.multiplier.setSuffix(' ×')
        self.day_bonus=NoWheelDouble();self.day_bonus.setRange(0,200);self.day_bonus.setDecimals(1);self.day_bonus.setValue(float(prefs.get('day_bonus',0)));self.day_bonus.setSuffix(' %')
        self.day_bonus.setToolTip('Дневной бонус производства выбранных ресурсов из игры. Добавляется к производственному бонусу города для всех выбранных этапов. 0 = без дневного бонуса. Если ручной RRR уже включает его, оставь 0.')
        bonuses=QWidget();bonus_layout=QHBoxLayout(bonuses);bonus_layout.setContentsMargins(0,0,0,0);bonus_layout.addWidget(self.multiplier);bonus_layout.addWidget(self.day_bonus)
        self.sale=QComboBox();self.sale.addItem('Заказ на продажу','order');self.sale.addItem('Быстрая продажа','instant');self.sale.setCurrentIndex(max(0,self.sale.findData(prefs.get('sale','order'))))
        for n,(name,control) in enumerate([('Закупка',self.buy),('Переработка / продажа',self.craft),('Персонаж',self.player),('Свободный вес',self.weight),('Бюджет закупки',self.budget),('Доступный фокус',self.focus),('Станция: серебро / 100 питания',self.station),('Прочие расходы / выход',self.other),('Бонус XP / дневной бонус, %',bonuses),('Продажа',self.sale)]):
            grid.addWidget(QLabel(name),n//5*2,n%5);grid.addWidget(control,n//5*2+1,n%5)
        for col in range(5):grid.setColumnStretch(col,1)
        select=FlowLayout();layout.addLayout(select)
        self.family=QComboBox();self.family.addItem('Все ресурсы',None)
        for code,title in FAMILIES.items():self.family.addItem(title,code)
        self.family.setCurrentIndex(max(0,self.family.findData(prefs.get('family','ore'))));select.addWidget(self.family)
        self.search=QLineEdit(prefs.get('search',''));self.search.setPlaceholderText('Найти ресурс / T4.3…');select.addWidget(self.search)
        self.mastery=QCheckBox('Учитывать открытые тиры профиля');self.mastery.setChecked(prefs.get('mastery',True));select.addWidget(self.mastery)
        self.age=QCheckBox('Разрешить старые цены');self.age.setChecked(prefs.get('any_age',True));select.addWidget(self.age)
        check=QPushButton('Отметить видимые');select.addWidget(check);check.clicked.connect(lambda:self.check_visible(True))
        clear=QPushButton('Снять видимые');select.addWidget(clear);clear.clicked.connect(lambda:self.check_visible(False))
        self.selection_buttons=[check,clear]
        self.choices=self.table(['Считать','Результат','Тир / чары','Доступность','Фокус / операция','XP / выход','Макс. выход (0 = без лимита)'])
        self.choices.verticalHeader().setDefaultSectionSize(36);self.choices.setMinimumHeight(145);self.choices.setMaximumHeight(200);layout.addWidget(self.choices)
        self.items={};self.caps={};checked=set(prefs.get('selected',[]));limits=prefs.get('limits',{})
        self.states=self.store.states(self.player.text().strip() or 'Мой персонаж')
        for n,r in enumerate(self.recipes):
            self.choices.insertRow(n);cell=QTableWidgetItem();cell.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);cell.setCheckState(Qt.Checked if r.item_id in checked else Qt.Unchecked);self.choices.setItem(n,0,cell);self.items[r.item_id]=cell
            self.choices.setItem(n,1,QTableWidgetItem(r.name));self.choices.setItem(n,2,QTableWidgetItem(f'T{r.tier}.{r.enchantment}'))
            cap=NoWheelInt();cap.setRange(0,1000000);cap.setValue(int(limits.get(r.item_id,0)));self.choices.setCellWidget(n,6,cap);self.caps[r.item_id]=cap;cap.valueChanged.connect(self.invalidate)
        self.refresh_profile();self.choices.resizeColumnsToContents()
        buttons=FlowLayout();outer.addLayout(buttons)
        self.fetch_button=QPushButton('Обновить цены отмеченных');buttons.addWidget(self.fetch_button);self.fetch_button.clicked.connect(self.fetch_prices)
        self.calculate_button=QPushButton('Подобрать максимальную прибыль');buttons.addWidget(self.calculate_button);self.calculate_button.clicked.connect(self.calculate)
        self.cancel_button=QPushButton('Отмена');buttons.addWidget(self.cancel_button);self.cancel_button.setEnabled(False);self.cancel_button.clicked.connect(self.cancel_calculation)
        self.record_button=QPushButton('Партия выполнена — XP / запасы');buttons.addWidget(self.record_button);self.record_button.clicked.connect(self.record);self.record_button.setEnabled(False)
        self.record_button.setToolTip('Записать XP и списать взятые для партии запасы. Фактические возвраты и новые готовые ресурсы прочитай из банка после переработки.')
        self.audit_button=QPushButton('Проверка расчёта');buttons.addWidget(self.audit_button);self.audit_button.clicked.connect(self.show_audit);self.audit_button.setEnabled(False)
        self.status=QLabel('Отметь ресурсы, введи свободный вес, бюджет и тариф станции.');self.status.setWordWrap(True);outer.addWidget(self.status)
        fee_note=QLabel('Плата крафтилки уже учтена в тарифе станции. «Прочие расходы» — только дополнительные затраты на каждый выход.');fee_note.setWordWrap(True);layout.addWidget(fee_note)
        stock_controls=FlowLayout();layout.addLayout(stock_controls)
        self.use_stock=QCheckBox('Учитывать запасы и уже купленное');self.use_stock.setChecked(prefs.get('use_stock',True));stock_controls.addWidget(self.use_stock)
        self.stock_button=QPushButton('Запасы / чтение банка');stock_controls.addWidget(self.stock_button);self.stock_button.clicked.connect(self.open_stock)
        self.market_button=QPushButton('Рынок / сроки продажи');stock_controls.addWidget(self.market_button);self.market_button.clicked.connect(self.open_market)
        self.ledger_button=QPushButton('Ходки: план / факт');stock_controls.addWidget(self.ledger_button);self.ledger_button.clicked.connect(self.open_ledger)
        self.preset_button=QPushButton('Сценарии');stock_controls.addWidget(self.preset_button);self.preset_button.clicked.connect(self.open_presets)
        self.use_stock.toggled.connect(self.invalidate);stock_controls.addStretch()
        self.repeat=QCheckBox('Повторно перерабатывать возвраты');self.repeat.setChecked(prefs.get('repeat',True));layout.addWidget(self.repeat)
        self.repeat.setToolTip('Подбор учитывает все повторные операции, пока ожидаемых возвращённых материалов хватает на рецепт. Фокус, плата станции и XP считаются за все операции. Возврат в игре случаен: результат — оценка по ожидаемому возврату.')
        self.repeat.toggled.connect(self.invalidate)
        self.chain=QCheckBox('Подбирать производство промежуточных материалов');self.chain.setChecked(prefs.get('chain',True));layout.addWidget(self.chain);self.chain.toggled.connect(self.invalidate)
        self.chain.setToolTip('Отмеченные результаты можно продавать. Необходимые рецепты младших тиров подключаются автоматически для внутреннего использования, с учётом открытых тиров профиля. Подбор выбирает, что купить и что произвести.')
        target=QHBoxLayout();target.addWidget(QLabel('Цель подбора:'))
        self.cash_target=QRadioButton('Максимальная прибыль, серебро');self.roi_target=QRadioButton('Максимальный ROI, %')
        self.target_group=QButtonGroup(self);self.target_group.addButton(self.cash_target);self.target_group.addButton(self.roi_target)
        self.roi_target.setChecked(prefs.get('objective_mode')=='roi');self.cash_target.setChecked(not self.roi_target.isChecked())
        self.roi_target.setToolTip('Прибыль после расходов / стоимость нового и имеющегося сырья. Наибольший процент может дать меньшую прибыль за ходку. При равном ROI выбирается большая прибыль.')
        for button in (self.cash_target,self.roi_target):target.addWidget(button);button.toggled.connect(self.invalidate)
        target.addStretch();layout.addLayout(target)
        self.market_dialog=QDialog(self);self.market_dialog.setWindowTitle('Объёмы рынка и срок продажи');self.market_dialog.resize(1000,650)
        market_layout=QVBoxLayout(self.market_dialog)
        self.depth=QComboBox();self.depth.addItem('По одной котировке — теоретическая оценка','quote');self.depth.addItem('Учитывать увиденные ордера; без объёмов — оценка','observed');self.depth.addItem('Только увиденные объёмы; без них закупка запрещена','strict')
        self.depth.setCurrentIndex(max(0,self.depth.findData(prefs.get('depth','observed'))));market_layout.addWidget(self.depth)
        turnover_controls=QHBoxLayout();market_layout.addLayout(turnover_controls)
        self.horizon=NoWheelInt();self.horizon.setRange(0,365);self.horizon.setValue(int(prefs.get('horizon',0)));self.horizon.setSpecialValueText('Без ограничения срока');self.horizon.setSuffix(' дн.')
        self.share=NoWheelDouble();self.share.setRange(.1,100);self.share.setValue(float(prefs.get('market_share',10)));self.share.setSuffix(' %')
        turnover_controls.addWidget(QLabel('Продать партию за:'));turnover_controls.addWidget(self.horizon);turnover_controls.addWidget(QLabel('Моя доля продаж рынка:'));turnover_controls.addWidget(self.share)
        warning=QLabel('Ордеры — только увиденная страница из твоей игры, а не весь рынок; объём мог измениться. NATS и обычная котировка не подтверждают доступное количество. При заказе на продажу срок = количество / (продажи рынка в день × твоя доля). Это сценарий, не гарантия. Ограничение срока без истории запрещает продажу результата; быстрая продажа ограничивается увиденными заказами на покупку.');warning.setWordWrap(True);market_layout.addWidget(warning)
        self.market_results=self.table(['Результат','Продать','Рынок: шт. / день','Срок при моей доле','Ограничение']);market_layout.addWidget(self.market_results,1)
        self.market_warnings=QLabel();self.market_warnings.setWordWrap(True);market_layout.addWidget(self.market_warnings)
        close=QPushButton('Закрыть');close.clicked.connect(self.market_dialog.accept);market_layout.addWidget(close)
        self.depth.currentIndexChanged.connect(self.invalidate);self.horizon.valueChanged.connect(self.invalidate);self.share.valueChanged.connect(self.invalidate)
        result_split=QSplitter(Qt.Vertical);outer.addWidget(result_split,3)
        self.tabs=QTabWidget();result_split.addWidget(self.tabs)
        self.views=[]
        for title in ['Без фокуса','Распределить фокус']:
            widget=QWidget();body=QVBoxLayout(widget);summary=QLabel();summary.setWordWrap(True);body.addWidget(summary)
            table=self.table(['Результат','Произвести','Продать','В цепочку ≈','С фокусом','Стоимость сырья','Вес, кг','Вклад в прибыль¹','Фокус ≤','XP'])
            body.addWidget(table);self.tabs.addTab(widget,title);self.views.append((summary,table))
        bottom=QSplitter();result_split.addWidget(bottom)
        self.shopping_table=self.table(['Источник / ресурс','Количество','Цена / шт.','Стоимость','Ожидаемый остаток']);bottom.addWidget(self.shopping_table)
        self.cities=self.table(['Продажа в городе','Прибыль¹','Разница с городом\nпереработки']);bottom.addWidget(self.cities);bottom.setSizes([850,550]);result_split.setSizes([280,180])
        self.xp=QLabel();self.xp.setWordWrap(True);outer.addWidget(self.xp)
        self.stock_label=QLabel();self.stock_label.setWordWrap(True);outer.addWidget(self.stock_label)
        explanation(outer,'¹ Прибыль = чистая продажа − новая закупка − стоимость взятых запасов − расходы; остатки не считаются выручкой. Отрицательный вклад промежуточного этапа означает затраты следующей переработки. Возвраты случайны. Фокус ограничен по стартовым уровням. Увиденные объёмы и допущения о сроках — в «Рынок / сроки продажи». Другие города: тот же груз без второй доставки.','Как считается прибыль')
        self.tabs.currentChanged.connect(self.show_details)
        self.family.currentIndexChanged.connect(self.filter);self.search.textChanged.connect(self.filter)
        self.mastery.toggled.connect(self.profile_changed);self.player.editingFinished.connect(self.profile_changed)
        self.choices.itemChanged.connect(self.invalidate)
        for box in [self.buy,self.craft,self.sale]:box.currentIndexChanged.connect(self.invalidate)
        for field in [self.weight,self.budget,self.focus,self.other,self.multiplier,self.day_bonus]:field.valueChanged.connect(self.invalidate)
        self.multiplier.valueChanged.connect(self.refresh_profile);self.station.textChanged.connect(self.invalidate);self.age.toggled.connect(self.invalidate)
        self.filter()
        self.timer=QTimer(self);self.timer.setInterval(1500);self.timer.timeout.connect(self.poll_prices)
        self.price_signature=self.market_signature();self.timer.start()
        self.redesign(outer,layout,grid,select,buttons,stock_controls,target,result_split)
        fit_window(self)
        fit_window(self.market_dialog)

    def redesign(self,outer,old,grid,selection,buttons,stock,target,result_split):
        notes=[]
        while outer.count():
            item=outer.takeAt(0)
            if item.widget() and item.widget() not in (self.controls_scroll,self.status,result_split,self.xp,self.stock_label):notes.append(item.widget())
        outer.addWidget(title('Ходки'))
        horizontal=QHBoxLayout();outer.addLayout(horizontal,1)
        scroll,left=panel();horizontal.addWidget(scroll);self.controls_scroll.hide()
        section(left,'Маршрут и лимиты')
        fields=[]
        for row in range(grid.rowCount()):
            for col in range(grid.columnCount()):
                item=grid.itemAtPosition(row,col)
                if item and item.widget():fields.append(item.widget())
        while grid.count():grid.takeAt(0)
        # The original grid contains label rows followed by control rows.
        labels=fields[:5];values=fields[5:10];extra_labels=fields[10:15];extra_values=fields[15:20]
        for label,value in zip(labels,values):left.addWidget(label);left.addWidget(value)
        section(left,'Фокус и продажа')
        for index in (0,1,4):left.addWidget(extra_labels[index]);left.addWidget(extra_values[index])
        advanced=fold(left,'Дополнительные настройки')
        for index in (2,3):advanced.addWidget(extra_labels[index]);advanced.addWidget(extra_values[index])
        # Move remaining options individually; no repeated widgets or connections.
        section(left,'Запасы и рынок');move_widgets(stock,left)
        section(left,'Цель подбора');move_widgets(target,left)
        for widget in (self.mastery,self.age,self.repeat,self.chain):advanced.addWidget(widget)
        leftovers=fold(left,'Пояснения')
        for widget in notes:leftovers.addWidget(widget)
        while old.count():
            item=old.takeAt(0)
            if widget:=item.widget():
                if widget not in (self.choices,self.mastery,self.age,self.repeat,self.chain):leftovers.addWidget(widget)
        left.addStretch()
        right=QWidget();body=QVBoxLayout(right);body.setContentsMargins(8,0,0,0);horizontal.addWidget(right,1)
        self.metrics=Metrics(['Прибыль','Новая закупка','Вес','Фокус']);body.addWidget(self.metrics)
        toolbar=FlowLayout();body.addLayout(toolbar);move_widgets(buttons,toolbar)
        self.calculate_button.setObjectName('primary')
        body.addWidget(self.status)
        self.workspace_tabs=QTabWidget();body.addWidget(self.workspace_tabs,1)
        resources=QWidget();resources_body=QVBoxLayout(resources)
        move_widgets(selection,resources_body,(self.mastery,self.age))
        self.choices.setMaximumHeight(16777215);resources_body.addWidget(self.choices,1)
        self.workspace_tabs.addTab(resources,'Ресурсы');self.workspace_tabs.addTab(result_split,'План ходки')
        body.addWidget(self.xp);body.addWidget(self.stock_label)
        self.xp.setMaximumHeight(52);self.stock_label.setMaximumHeight(36)

    def table(self,headers):
        t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.setEditTriggers(QAbstractItemView.NoEditTriggers);t.verticalHeader().hide();t.horizontalHeader().setStretchLastSection(True);readable_table(t);return t
    def market_signature(self):
        path=self.root/'prices.sqlite'
        return (id(self.owner.last),path.stat().st_mtime_ns if path.exists() else 0,self.owner.local_enabled.isChecked(),repr(self.owner.settings.get('general')),repr(self.owner.settings.get('profiles')),self.owner.settings.get('premium'),repr(self.relevant_stock()))
    def poll_prices(self):
        signature=self.market_signature()
        if signature!=self.price_signature:
            self.price_signature=signature
            if self.plans and self.current_fingerprint()!=self.plan_fingerprint:
                self.status.setText('Показан сохранённый расчёт по снимку '+self.snapshot_time+'. Цены, запасы или настройки изменились — нажми подбор для обновления.');self.record_button.setEnabled(False)
        running=self.owner.worker and self.owner.worker.isRunning()
        self.fetch_button.setEnabled(not running and not(self.worker and self.worker.isRunning()))
    def selected_recipes(self):return [r for r in self.recipes if self.items[r.item_id].checkState()==Qt.Checked]
    def production_recipes(self):
        selected=self.selected_recipes()
        return dependency_recipes(selected,self.recipes) if self.chain.isChecked() else selected
    def relevant_stock(self):
        if not self.use_stock.isChecked():return []
        inputs={i.item_id for recipe in self.production_recipes() for i in recipe.ingredients}
        return [r for r in self.stock_store.rows(self.player.text().strip() or 'Мой персонаж') if r['item_id'] in inputs and ((r.get('kind')=='base' and r['city']==self.craft.currentText()) or (r.get('kind')=='bought' and r['city']==self.buy.currentText()))]
    def open_stock(self):
        from .stock_dialog import StockDialog
        dialog=StockDialog(self,self.root,self.player.text().strip() or 'Мой персонаж',self.buy.currentText(),self.craft.currentText(),self.recipes)
        dialog.changed.connect(self.invalidate);dialog.exec()
    def fingerprint(self,prices,histories=()):
        selected=self.production_recipes();outputs={r.item_id for r in selected};inputs={i.item_id for r in selected for i in r.ingredients}
        # Only prices used by this route or its city comparisons matter. New
        # observations for unrelated goods must not erase a completed plan.
        rows=sorted((p['item_id'],p['city'],p.get('quality',1),str(p.get('sell_price_min',0)),str(p.get('buy_price_max',0)),str(p.get('sell_price_min_date','')),str(p.get('buy_price_max_date','')),repr(p.get('local_observations',{})))
            for p in prices if p['item_id'] in outputs or (p['item_id'] in inputs and p['city'] in (self.buy.currentText(),self.craft.currentText())))
        return (rows,repr(sorted(histories,key=lambda h:(h['item_id'],h['location'],h['quality']))),repr(self.owner.settings.get('general')),repr(self.owner.settings.get('profiles')),self.owner.settings.get('premium'),self.owner.local_enabled.isChecked(),repr(self.relevant_stock()))
    def current_fingerprint(self):
        selected=self.production_recipes();ids={r.item_id for r in selected}|{i.item_id for r in selected for i in r.ingredients}
        prices,histories=market_snapshot(self.owner,self.root,ids)
        return self.fingerprint(prices,histories)
    def filter(self,*args):
        from .item_names import matches_item
        for n,r in enumerate(self.recipes):self.choices.setRowHidden(n,bool(self.family.currentData() and r.crafting_category!=self.family.currentData()) or not matches_item(r.item_id,self.search.text(),r.name+f' T{r.tier}.{r.enchantment}'))
    def check_visible(self,value):
        for n,r in enumerate(self.recipes):
            if not self.choices.isRowHidden(n):self.items[r.item_id].setCheckState(Qt.Checked if value else Qt.Unchecked)
    def refresh_profile(self,*args):
        self.choices.blockSignals(True)
        for n,r in enumerate(self.recipes):
            available=unlocked(self.game,r,self.states);f=focus_per_operation(self.game,r,self.states);xp=fame_per_item(self.game,r.item_id)
            for c,value in [(3,'Открыт' if available else 'Не открыт / не указан'),(4,money(f)),(5,decimal_text(xp*D(str(self.multiplier.value())) if xp is not None else None,1))]:self.choices.setItem(n,c,QTableWidgetItem(value))
        self.choices.blockSignals(False)
    def profile_changed(self,*args):
        self.states=self.store.states(self.player.text().strip() or 'Мой персонаж');self.refresh_profile();self.invalidate()
    def invalidate(self,*args):
        if hasattr(self,'metrics'):self.metrics.update_values(['—']*4)
        self.record_button.setEnabled(False);self.plans=[];self.progress=[]
        self.audit_options=[];self.audit_button.setEnabled(False)
        for label,t in self.views:label.setText('Параметры изменились — нужен расчёт.');t.setRowCount(0)
        self.shopping_table.setRowCount(0);self.cities.setRowCount(0);self.xp.clear();self.stock_label.clear()
    def preferences(self):
        self.owner.settings['trip_optimizer']=dict(player=self.player.text().strip() or 'Мой персонаж',buy=self.buy.currentText(),craft=self.craft.currentText(),weight=self.weight.value(),budget=self.budget.value(),focus=self.focus.value(),station=self.station.text(),other=self.other.value(),xp_multiplier=self.multiplier.value(),day_bonus=self.day_bonus.value(),sale=self.sale.currentData(),family=self.family.currentData(),mastery=self.mastery.isChecked(),any_age=self.age.isChecked(),repeat=self.repeat.isChecked(),chain=self.chain.isChecked(),objective_mode='roi' if self.roi_target.isChecked() else 'profit',selected=[r.item_id for r in self.selected_recipes()],limits={k:v.value() for k,v in self.caps.items() if v.value()})
        self.owner.settings['trip_optimizer']['use_stock']=self.use_stock.isChecked()
        self.owner.settings['trip_optimizer'].update(depth=self.depth.currentData(),horizon=self.horizon.value(),market_share=self.share.value(),search=self.search.text())
        self.owner.persist_view()
    def open_market(self):
        rows={c.recipe.item_id:[c,0] for c in self.audit_options if c.row.get('root',True)}
        if self.plans:
            for line in self.plans[self.tabs.currentIndex()]['lines']:
                c=line['candidate'];uid=c.recipe.item_id
                if uid not in rows:rows[uid]=[c,0]
                rows[uid][1]+=line.get('sold',line['quantity'])
        self.market_results.setRowCount(len(rows))
        for n,(c,qty) in enumerate(rows.values()):
            forecast=turnover(qty,c.row.get('demand',{}),self.share.value())
            duration='По заказам на покупку' if c.row.get('sale_mode')=='instant' else 'Неизвестно' if forecast['per_day'] is None else 'Нет продаж' if forecast['per_day']==0 else decimal_text(forecast['days'],1)+' дн.'
            values=[c.recipe.name,qty,decimal_text(forecast['per_day'],1),duration,c.row.get('sale_limit','Без ограничения')]
            for col,value in enumerate(values):self.market_results.setItem(n,col,QTableWidgetItem(str(value)))
        self.market_results.resizeColumnsToContents()
        labels={'purchase':'Нет количества для закупки','sale':'Нет количества для быстрой продажи','history':'Нет истории продаж'}
        warnings=[f"{labels[kind]}: {item_name(uid,False)} • {city}" for kind,uid,city in getattr(self,'depth_warnings',[]) if city in (self.buy.currentText(),self.craft.currentText())]
        self.market_warnings.setText('\n'.join(warnings[:5])+ (f'\nЕщё {len(warnings)-5} — полный список в подсказке.' if len(warnings)>5 else '') or 'Нет предупреждений о количестве. Увиденные ордера могут быть частью рынка.')
        self.market_warnings.setToolTip('\n'.join(warnings));self.market_dialog.exec()
    def open_ledger(self):
        from .trip_ledger import plan_snapshot
        from .trip_ledger_dialog import TripLedgerDialog
        current=None
        if self.plans:
            plan=self.plans[self.tabs.currentIndex()]
            if plan['lines']:current=plan_snapshot(plan,self.plan_buy,self.plan_city,self.owner.settings.get('trip_optimizer',{}))
        dialog=TripLedgerDialog(self,self.root,self.player.text().strip() or 'Мой персонаж',current);dialog.exec()
    def apply_preferences(self,prefs):
        widgets=[self.buy,self.craft,self.player,self.weight,self.budget,self.focus,self.station,self.other,self.multiplier,self.day_bonus,self.sale,self.family,self.search,self.mastery,self.age,self.repeat,self.chain,self.use_stock,self.depth,self.horizon,self.share,self.roi_target,self.cash_target,self.choices,*self.caps.values()]
        for w in widgets:w.blockSignals(True)
        try:
            for control,key,default in [(self.buy,'buy','Fort Sterling'),(self.craft,'craft','Thetford')]:control.setCurrentText(prefs.get(key,default))
            self.player.setText(prefs.get('player','Мой персонаж'));self.station.setText(str(prefs.get('station','')));self.search.setText(prefs.get('search',''))
            for control,key,default in [(self.weight,'weight',1000),(self.budget,'budget',1000000),(self.focus,'focus',10000),(self.other,'other',0),(self.multiplier,'xp_multiplier',1),(self.day_bonus,'day_bonus',0),(self.horizon,'horizon',0),(self.share,'market_share',10)]:control.setValue(prefs.get(key,default))
            for control,key,default in [(self.sale,'sale','order'),(self.family,'family','ore'),(self.depth,'depth','observed')]:control.setCurrentIndex(max(0,control.findData(prefs.get(key,default))))
            for control,key,default in [(self.mastery,'mastery',True),(self.age,'any_age',True),(self.repeat,'repeat',True),(self.chain,'chain',True),(self.use_stock,'use_stock',True)]:control.setChecked(prefs.get(key,default))
            (self.roi_target if prefs.get('objective_mode')=='roi' else self.cash_target).setChecked(True)
            selected=set(prefs.get('selected',[]));limits=prefs.get('limits',{})
            for uid,cell in self.items.items():cell.setCheckState(Qt.Checked if uid in selected else Qt.Unchecked);self.caps[uid].setValue(limits.get(uid,0))
        finally:
            for w in widgets:w.blockSignals(False)
        self.profile_changed();self.filter();self.preferences();self.status.setText('Сценарий загружен. Цены и запасы берутся текущие — нажми подбор.')
    def open_presets(self):
        from copy import deepcopy
        dialog=QDialog(self);dialog.setWindowTitle('Сохранённые сценарии ходки');dialog.resize(650,260);body=QVBoxLayout(dialog)
        choose=QComboBox();choose.setProperty('userText',True);body.addWidget(choose);name=QLineEdit();name.setMaxLength(80);name.setPlaceholderText('Например: Руда — Форт → Зетфорд');body.addWidget(name)
        info=QLabel('Сохраняются маршрут, персонаж, вес, бюджет, выбранные ресурсы, лимиты, фокус и настройки рынка. Цены и количество запасов загружаются заново при расчёте.');info.setWordWrap(True);body.addWidget(info)
        presets=self.owner.settings.setdefault('trip_presets',{})
        def refresh(selected=None):
            choose.clear();choose.addItems(sorted(presets))
            if selected:choose.setCurrentText(selected)
            name.setText(choose.currentText())
        choose.currentTextChanged.connect(name.setText);refresh()
        def save():
            title=name.text().strip()
            if not title:info.setText('Введи название сценария.');return
            self.preferences();presets[title]=deepcopy(self.owner.settings['trip_optimizer']);self.owner.persist_view();refresh(title);info.setText('Сценарий сохранён: '+title)
        def load():
            if choose.currentText() not in presets:return
            self.apply_preferences(deepcopy(presets[choose.currentText()]));dialog.accept()
        def remove():
            if choose.currentText() not in presets:return
            del presets[choose.currentText()];self.owner.persist_view();refresh();info.setText('Сценарий удалён.')
        bar=QHBoxLayout();body.addLayout(bar)
        for title,action in [('Сохранить / обновить',save),('Загрузить',load),('Удалить',remove),('Закрыть',dialog.accept)]:
            button=QPushButton(title);button.clicked.connect(action);bar.addWidget(button)
        dialog.exec()
    def fetch_prices(self):
        selected=self.production_recipes()
        if not selected:self.status.setText('Сначала отметь ресурсы.');return
        if self.owner.worker and self.owner.worker.isRunning():self.status.setText('Дождись текущей загрузки цен.');return
        ids={r.item_id for r in selected}|{i.item_id for r in selected for i in r.ingredients}
        self.owner.start_fetch([],True,ids);self.status.setText('Обновляю отмеченные ресурсы и ингредиенты во всех городах. После загрузки нажми подбор.');self.preferences()
    def calculate(self):
        if self.worker and self.worker.isRunning():return
        selected=self.production_recipes();rate=number(self.station.text())
        if not selected:self.status.setText('Отметь ресурсы для расчёта.');return
        if rate is None:self.status.setText('Введи тариф станции в серебре за 100 питания; 0 означает бесплатно.');return
        self.profile_changed();self.preferences()
        ids={r.item_id for r in selected}|{i.item_id for r in selected for i in r.ingredients};prices,histories=market_snapshot(self.owner,self.root,ids)
        self.plan_fingerprint=self.fingerprint(prices,histories);self.snapshot_time=datetime.now().strftime('%d.%m %H:%M')
        self.plan_settings=dict(self.owner.settings,sale_mode=self.sale.currentData())
        self.plan_city=self.craft.currentText();self.plan_buy=self.buy.currentText();self.plan_player=self.player.text().strip() or 'Мой персонаж'
        limits={uid:box.value() for uid,box in self.caps.items() if box.value()}
        joint=self.chain.isChecked() or self.use_stock.isChecked() or self.depth.currentData()!='quote' or self.horizon.value()>0
        from copy import deepcopy
        payload=dict(root=str(self.root),stock_rows=self.relevant_stock(),buy=self.plan_buy,city=self.plan_city,
            prices=prices,histories=histories,age=None if self.age.isChecked() else 30,joint=joint,
            roots={r.item_id for r in self.selected_recipes()},recipes=selected,settings=deepcopy(self.plan_settings),states=self.states,
            day_bonus=D(str(self.day_bonus.value())),rate=rate,other=D(str(self.other.value())),multiplier=D(str(self.multiplier.value())),
            mastery=self.mastery.isChecked(),limits=limits,depth=self.depth.currentData(),horizon=self.horizon.value(),share=self.share.value(),
            budget=self.budget.value(),weight=self.weight.value(),focus=self.focus.value(),repeat=self.repeat.isChecked(),
            objective='roi' if self.roi_target.isChecked() else 'profit')
        self.start_states={k:dict(v) for k,v in self.states.items()};self.recorded=False
        self.price_signature=self.market_signature()
        self.status.setText('Подготавливаю ресурсы и подбираю количества под вес, бюджет и фокус…')
        self.worker=ProcessWorker('trip',payload,self,timeout=90)
        self.cancel_button.setEnabled(True)
        self.calculate_button.setEnabled(False);self.fetch_button.setEnabled(False);self.set_inputs_enabled(False)
        self.worker.ready.connect(self.received,Qt.QueuedConnection)
        self.worker.failed.connect(self.calculation_failed,Qt.QueuedConnection)
        self.worker.finished.connect(self.worker_finished,Qt.QueuedConnection);self.worker.start()
    def cancel_calculation(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption();self.cancel_button.setEnabled(False);self.status.setText('Расчёт отменяется…')
    def set_inputs_enabled(self,enabled):
        for w in [self.buy,self.craft,self.player,self.weight,self.budget,self.focus,self.station,self.other,self.multiplier,self.day_bonus,self.sale,self.choices,self.mastery,self.age,self.repeat,self.chain,self.cash_target,self.roi_target,self.use_stock,self.stock_button,self.depth,self.horizon,self.share,self.market_button,self.ledger_button,self.preset_button,*self.selection_buttons]:w.setEnabled(enabled)
    @Slot()
    def worker_finished(self):
        if self.closed:return
        self.cancel_button.setEnabled(False)
        if self.worker.isInterruptionRequested():self.status.setText('Расчёт отменён. Профиль и запасы не изменены.')
        self.calculate_button.setEnabled(True);self.fetch_button.setEnabled(True);self.set_inputs_enabled(True)
    @Slot(str)
    def calculation_failed(self,error):
        if self.closed:return
        self.status.setText('Ошибка расчёта: '+error)
    @Slot(object)
    def received(self,plans):
        if self.closed:return
        if QThread.currentThread()!=self.thread():
            logging.error('Trip result delivered outside GUI thread');return
        try:
            self.audit_options=plans['options'];self.rejected=plans['rejected'];self.stock_missing=plans['stock_missing'];self.depth_warnings=plans['depth_warnings']
            self.audit_button.setEnabled(bool(self.audit_options))
            self.explanation='\n'.join(f'{r.name} T{r.tier}.{r.enchantment}: {reason}' for r,reason in self.rejected)
            self.explanation+='\n'+'\n'.join('Запас не включён — неизвестна стоимость: '+item_name(r['item_id'],False) for r in self.stock_missing)
            if not plans['plans']:
                self.status.setText('Нет допустимых ресурсов. Пропущено: '+str(len(self.rejected))+'. '+ '; '.join(reason for r,reason in self.rejected[:2]));self.status.setToolTip(self.explanation);return
            self.display_plans(plans['plans'])
        except Exception as exc:
            logging.exception('Trip result display failed');self.invalidate();self.calculation_failed(str(exc))
    def display_plans(self,plans):
        if hasattr(self,'workspace_tabs'):self.workspace_tabs.setCurrentIndex(1)
        self.plans=plans;self.progress=[]
        for n,plan in enumerate(plans):
            try:progress=simulate_progress(self.game,plan,self.start_states)
            except ValueError:progress=None
            self.progress.append(progress)
            label,t=self.views[n];returned=sum((l['calc']['returned']*l['operations'] for l in plan['lines']),D(0));fees=sum(((l['calc']['station']+l['calc']['fixed'])*l['operations'] for l in plan['lines']),D(0))
            revenue=sum(((l['calc']['sale']-l['calc']['fees'])*l['operations'] for l in plan['lines']),D(0))
            focus_display=money(plan['focus'])
            if plan['focus']>10000:focus_display='<span style="color:#ff7777">'+focus_display+'</span>'
            station=sum((l['calc']['station']*l['operations'] for l in plan['lines']),D(0));other=fees-station
            basis=plan.get('basis',plan['purchase']);margin=plan['profit']/basis*100 if basis else None
            heading=("Максимум по известным ценам и стартовым уровням" if plan['optimal'] else "Лучший найденный план; оптимум не доказан") if plan['lines'] else ('Нет прибыльной партии при этих ценах и расходах' if plan['optimal'] else 'Прибыльная партия пока не найдена; поиск не доказан')
            heading=('Цель: ROI, % • ' if plan.get('objective_mode')=='roi' else 'Цель: прибыль, серебро • ')+heading
            if plan.get('upper_bound') is not None and not plan['optimal']:heading+=f'; верхняя граница {money(plan["upper_bound"])}'
            inventory='остатки не включены в прибыль' if plan.get('chain') else 'возврат в запасе ≈ '+money(returned)
            label.setText(f'{heading}: прибыль¹ {money(plan["profit"])} • ROI {roi(margin)} • новая закупка {money(plan["purchase"])} / {money(self.budget.value())} • стоимость взятых запасов {money(plan.get("stock_value",0))} • вес {decimal_text(plan["weight"])} / {decimal_text(self.weight.value())} кг<br>Чистая выручка {money(revenue)} • {inventory} • плата станции {money(station)} • прочие {money(other)} (расходы нужны отдельно от закупки)<br>Фокус ≤ {focus_display} / {money(self.focus.value() if n else 0)}; с учётом прокачки ≈ {money(progress["focus"] if progress else None)}')
            label.setToolTip(label.text());label.setText(heading);label.setMaximumHeight(52)
            t.setRowCount(len(plan['lines']))
            for row,line in enumerate(plan['lines']):
                c=line['candidate'];calc=line['calc'];ops=line['operations']
                purchase=line.get('purchase',c.purchase*ops);weight=line.get('weight',c.weight*ops)
                values=[f'{c.recipe.name} • T{c.recipe.tier}.{c.recipe.enchantment}',line['quantity'],money(line.get('sold',line['quantity'])),decimal_text(line.get('internal',D(0))),'Да' if line['focused'] else 'Нет',money(purchase),decimal_text(weight),money(calc['profit']*ops),money((c.focus or 0)*ops if line['focused'] else 0),decimal_text(c.fame*line['quantity'] if c.fame is not None else None,1)]
                for col,value in enumerate(values):
                    detail=f'За {ops} операций: чистая продажа {money((calc["sale"]-calc["fees"])*ops)} + остаток в запасе {money(calc["returned"]*ops)} − стоимость сырья {money(purchase)} − станция {money(calc["station"]*ops)} − прочие {money(calc["fixed"]*ops)} = прибыль {money(calc["profit"]*ops)}.'
                    cell=QTableWidgetItem(str(value));cell.setToolTip(detail+'\n'+'\n'.join(c.row['issues']));t.setItem(row,col,cell)
                    if col==8 and plan['focus']>10000:cell.setForeground(QColor('#ff7777'))
            t.resizeColumnsToContents()
        self.status.setText(f'Расчёт готов. Пропущено ресурсов: {len(self.rejected)} (причины в подсказке). Снимок цен: '+self.snapshot_time+'.')
        if self.stock_missing:self.status.setText(self.status.text()+f' Запасов без стоимости, не включены: {len(self.stock_missing)}.')
        missing_depth=[w for w in getattr(self,'depth_warnings',[]) if w[2] in (self.plan_buy,self.plan_city)]
        if missing_depth:self.status.setText(self.status.text()+f' Нет объёма / истории для {len(missing_depth)} позиций — см. «Рынок / сроки продажи».')
        if any(s.get('estimated') for p in plans for s in p.get('existing',[])):self.status.setText(self.status.text()+' Стоимость части запасов — рыночная оценка, не фактическая цена покупки.')
        unknown=[c.recipe.name for c in self.audit_options if c.row.get('root') and self.plan_city not in c.sales]
        if unknown:self.status.setText(self.status.text()+' Не оценена продажа без цены: '+', '.join(unknown)+'.')
        if self.current_fingerprint()!=self.plan_fingerprint:self.status.setText('Расчёт по снимку '+self.snapshot_time+' готов. За время подбора появились новые цены — можно пересчитать; результат сохранён.')
        self.status.setToolTip(self.explanation);self.price_signature=self.market_signature();self.show_details()
    def show_details(self,*args):
        if hasattr(self,'metrics') and self.plans:
            plan=self.plans[self.tabs.currentIndex()];self.metrics.update_values([money(plan['profit']),money(plan['purchase']),decimal_text(plan['weight'])+' кг',money(plan['focus'])])
        if not self.plans:return
        n=self.tabs.currentIndex();plan=self.plans[n];progress=self.progress[n];goods=shopping(plan)
        existing=plan.get('existing',[]);self.shopping_table.setRowCount(len(goods)+len(existing))
        for row,(uid,part) in enumerate(goods.items()):
            for col,value in enumerate(['Купить: '+item_name(uid,False),part['quantity'],money(part['price']),money(part.get('cost',D(part['price'])*part['quantity'])),decimal_text(part['returned'])]):
                cell=QTableWidgetItem(str(value));cell.setToolTip(('Увиденные ордера; цена в таблице — взвешенная.' if part.get('depth_known') else 'Количество по этой цене неизвестно; теоретическая оценка.')+'\n'+'\n'.join(f"{l['quantity']} × {money(l['price'])}" for l in part.get('levels',[])));self.shopping_table.setItem(row,col,cell)
        for row,s in enumerate(existing,start=len(goods)):
            source='На базе' if s['kind']=='base' else 'Уже куплено'
            for col,value in enumerate([source+': '+item_name(s['item_id'],False),s['used'],money(s['price']),money(s['price']*s['used']),'—']):
                cell=QTableWidgetItem(str(value));cell.setToolTip(('Оценка по рыночной цене' if s.get('estimated') else 'Сохранённая цена приобретения')+' • '+s.get('source',''));self.shopping_table.setItem(row,col,cell)
        self.shopping_table.resizeColumnsToContents()
        stocks=[f'{item_name(uid,False)}: {decimal_text(q)}' for uid,q in plan.get('stocks',{}).items() if q>D('0.00001')]
        self.stock_label.setText('Непроданные остатки ≈ '+ '; '.join(stocks[:4])+ (f'; ещё {len(stocks)-4} (в подсказке)' if len(stocks)>4 else '') if stocks else '')
        self.stock_label.setToolTip('\n'.join(stocks))
        partial=[s for s in self.stock_store.bank_scans(self.player.text().strip() or 'Мой персонаж') if s['city'] in (self.plan_buy,self.plan_city) and not s.get('complete')]
        if partial:self.stock_label.setText(self.stock_label.text()+(' • ' if self.stock_label.text() else '')+'Частичные снимки банка: '+', '.join(s['container']+' ('+s['city']+')' for s in partial)+'. Непросмотренные ресурсы не учтены.')
        comparisons=sale_comparisons(plan,self.plan_city,self.plan_settings) if plan['lines'] else [];self.cities.setRowCount(len(comparisons))
        for row,c in enumerate(comparisons):
            profit_text=money(c['profit']) if c['profit'] is not None else 'Неизвестно'
            delta_text=('+' if c['delta']>0 else '')+money(c['delta']) if c['delta'] is not None else 'Неизвестно'
            for col,value in enumerate([c['city'],profit_text,delta_text]):
                cell=QTableWidgetItem(value);cell.setToolTip('Нет цены: '+', '.join(item_name(uid,False) for uid in c['missing']) if c['missing'] else 'Тот же план; расходы второй перевозки не включены');self.cities.setItem(row,col,cell)
        self.cities.resizeColumnsToContents()
        changes=[]
        if progress:
            for key,after in progress['states'].items():
                before=progress['before'].get(key,dict(level=0,xp=0))
                if after!=before:changes.append(f'{node_label(key)}: {before["level"]} → {after["level"]}, XP в уровне {decimal_text(after["xp"],1)}')
        order='по цепочке, внутри этапа с фокусом → без фокуса' if plan.get('chain') else 'младшие тиры сначала, затем без фокуса → с фокусом'
        self.xp.setText('Опыт партии: '+money(progress['fame'] if progress else None)+' • '+'; '.join(changes)+'. Порядок: '+order+'.')
        self.record_button.setEnabled(bool(plan['lines']) and progress is not None and not self.recorded)
    def show_audit(self):
        dialog=QDialog(self);dialog.setWindowTitle('Проверка исходных данных и прибыли');dialog.resize(1450,720);fit_window(dialog)
        body=QVBoxLayout(dialog)
        text=QLabel(f'Снимок {self.snapshot_time}. Закупка: {self.plan_buy}; продажа: {self.plan_city}. Здесь прибыль отдельного рецепта с покупными ингредиентами — справка, а не вклад в цепочку. Включённые цепочки совместно выбирают покупку или производство. Неизвестная цена может быть заменена внутренним производством. Источники и даты — в подсказках.');text.setWordWrap(True);body.addWidget(text)
        table=self.table(['Результат','Ингредиенты на рецепт:\nшт. × цена','Продажа\n/ шт.','Вес рецепта,\nкг','Возврат,\n%','Станция\n/ операция','Прибыль без F\n/ операция','Прибыль с F\n/ операция','Результат подбора']);body.addWidget(table)
        table.setRowCount(len(self.audit_options)+len(self.rejected))
        selected={l['candidate'].recipe.item_id for p in self.plans for l in p['lines']}
        for row,c in enumerate(self.audit_options):
            ingredients='\n'.join(f"{item_name(p['ingredient'].item_id,False)}: {p['ingredient'].amount} × {money(p['price'])}" for p in c.parts)
            reason='Входит в план' if c.recipe.item_id in selected else 'Не выбран при текущих лимитах и ценах'
            if c.row.get('root') is False:reason+='\nПромежуточный рецепт'
            if c.row.get('age') is not None and c.row['age']>30:reason+='\nЕсть цена старше 30 минут'
            standalone=c.row.get('standalone',True)
            values=[f'{c.recipe.name} • T{c.recipe.tier}.{c.recipe.enchantment}',ingredients,money(c.row['sale']),decimal_text(c.weight),decimal_text(D(c.row['profile']['rrr'])),decimal_text(c.plain['station']),decimal_text(c.plain['profit'] if standalone else None),decimal_text(c.focused['profit'] if c.focused and standalone else None),reason]
            details='\n'.join(f"{item_name(p['ingredient'].item_id,False)} • {self.plan_buy}: {money(p['price'])} • {p.get('source','')} • {p.get('date','')} • {p.get('status','')}" for p in c.parts)
            details+=f"\nПродажа • {self.plan_city}: {money(c.row['sale'])} • {c.row.get('sale_source','')} • {c.row.get('sale_date','')}\nВес взят из каталога игровых предметов. Возврат с фокусом: {decimal_text(D(c.row['profile']['focus_rrr']))}%."
            for col,value in enumerate(values):
                cell=QTableWidgetItem(str(value));cell.setToolTip(details);table.setItem(row,col,cell)
                if col in (6,7) and value.startswith('-'):cell.setForeground(QColor('#ff7777'))
        for row,(r,reason) in enumerate(self.rejected,start=len(self.audit_options)):
            table.setItem(row,0,QTableWidgetItem(f'{r.name} • T{r.tier}.{r.enchantment}'));table.setItem(row,8,QTableWidgetItem(reason))
        for col,width in enumerate([190,280,85,90,80,95,110,110,220]):table.setColumnWidth(col,width)
        table.resizeRowsToContents()
        close=QPushButton('Закрыть');close.clicked.connect(dialog.accept);body.addWidget(close);dialog.exec()
    def record(self):
        if not self.plans or self.recorded:return
        n=self.tabs.currentIndex();plan=self.plans[n];progress=self.progress[n]
        if progress is None:return
        current=self.store.states(self.plan_player)
        if current!=self.start_states:
            self.status.setText('Профиль изменился после расчёта. Пересчитай, чтобы не перезаписать новые уровни.');self.record_button.setEnabled(False);return
        payload=dict(type='Выполнено',kind='REFINE',item='Переработка: '+self.plan_buy+' → '+self.plan_city,quantity=sum(l['quantity'] for l in plan['lines']),fame=float(progress['fame']),focus=progress['focus'],
            states_before=self.start_states,states_after=progress['states'],profit_estimate=str(plan['profit']),
            trip=[dict(item=l['candidate'].recipe.item_id,quantity=l['quantity'],focused=l['focused']) for l in plan['lines']])
        try:
            from .trip_inventory import consumption_changes
            payload['stock_changes']=consumption_changes(self.store.db,self.plan_player,plan.get('existing',[]))
            self.store.record(self.plan_player,payload,progress['states'])
        except ValueError as exc:self.status.setText(str(exc));self.record_button.setEnabled(False);return
        self.recorded=True;self.record_button.setEnabled(False)
        self.status.setText('Партия записана, XP обновлён, взятые запасы списаны. Прочитай банк заново для фактических возвратов. Фактическую прибыль запиши после продаж.');self.states=progress['states'];self.refresh_profile()
    def done(self,result):
        if self.worker and self.worker.isRunning():
            self.cancel_calculation();QTimer.singleShot(100,lambda:self.done(result));return
        if not self.closed:self.timer.stop();self.preferences();self.store.close();self.stock_store.close();self.closed=True
        super().done(result)
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():self.done(0);event.ignore();return
        self.done(0);event.accept()
