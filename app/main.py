import json
import logging
import sys
from pathlib import Path
from decimal import Decimal
from PySide6.QtCore import Qt,QSize,QTimer,QSignalBlocker
from PySide6.QtGui import QFont,QFontDatabase,QColor,QActionGroup
from .i18n_widgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QLabel,QComboBox,QPushButton,QSpinBox,QTableWidget,QTableWidgetItem,QLineEdit,
    QMessageBox,QAbstractItemView,QCheckBox,QMenu)
from .catalog import load_catalog
from .models import CITIES
from .api import AlbionAPI
from .workers import Fetch
from .scanner import scan
from .settings_dialog import SettingsDialog
from .details import Details
from .icons import Icons
from .formatting import money,roi,timestamp
from .trading import enchant_recipes,trading_scan
from .rules import effective_settings
from .scanner import number
from .market_stream import OrderStream,supplement
from .cache import Cache
from .filter_dialog import FilterSelection
from .result_filters import BoundsDialog,in_bounds,reliability
from .local_market import LocalReceiver,LocalStore,merge_local
from .item_names import item_name,recipe_variant,has_known_price,matches_item
from .enchantment import comparison_price_ids,prefer_enchanted
from .preferences import save_settings,exclusion_key,is_excluded
from .search_table import SearchTable,SEARCH_NAME_ROLE
from .calculator import DEMAND_LABELS,demand_text,demand_tip
from .paths import data_root,resource_root
from .version import __version__
from .i18n import LANGUAGES,get_language,set_language,tr,default_language
from .ui_layout import FlowLayout,explanation,fit_window,readable_table
from .number_fields import NumberBox
from .regions import REGIONS,region_key,region_root,preferences,save_preferences
from .responsive import GuiBatch,set_choices
from .background import ProcessWorker
from .dashboard import STYLE,panel,section,fold,move_widgets,title
from .material_cells import MaterialDelegate,MATERIAL_ROLE,breakdown,tip
from .i18n_widgets import QScrollArea,QStackedWidget
from PySide6.QtGui import QIcon

ROOT=data_root()
CATEGORIES={'weapons':'Оружие','armors':'Броня','offhands':'Левая рука','resources':'Сырьё','materials':'Материалы / переработка',
    'food':'Еда','potions':'Зелья','bags':'Сумки','capes':'Плащи','gathering':'Инструменты / сбор',
    'farming':'Фермерство','artefacts':'Артефакты','reagents':'Руны / души / реагенты','fish':'Рыба / рыбные продукты'}
FAMILIES={'sword':'Мечи','axe':'Топоры','mace':'Булавы','hammer':'Молоты','dagger':'Кинжалы',
    'spear':'Копья','bow':'Луки','crossbow':'Арбалеты','quarterstaff':'Боевые посохи',
    'firestaff':'Огненные посохи','froststaff':'Ледяные посохи','holystaff':'Священные посохи',
    'cursestaff':'Проклятые посохи','arcanestaff':'Мистические посохи','naturestaff':'Природные посохи',
    'shapeshifterstaff':'Посохи перевёртыша','cloth':'Ткань','leather':'Кожа','plate':'Латы',
    'shieldtype':'Щиты','booktype':'Книги','torchtype':'Факелы','totemtype':'Тотемы','orbtype':'Сферы','knuckles':'Боевые перчатки',
    'cloth_armor':'Тканевые мантии','cloth_helmet':'Тканевые капюшоны','cloth_shoes':'Тканевые сандалии',
    'leather_armor':'Кожаные куртки','leather_helmet':'Кожаные капюшоны','leather_shoes':'Кожаная обувь',
    'plate_armor':'Латные доспехи','plate_helmet':'Латные шлемы','plate_shoes':'Латные сапоги','other':'Другие'}
FAMILIES.update(ore='Руда',rock='Камень',wood='Древесина',fiber='Волокно',hide='Шкуры',metalbars='Слитки',stoneblock='Каменные блоки',
    bags='Сумки',satchels='Сумки прозрения',fish='Рыболовство',resources='Сырьё',refinedresources='Материалы',
    farm='Овощи / семена',herbgarden='Травы / семена',pasture='Животные / продукты',kennel='Животные',farmingproducts='Продукты',
    stews='Рагу',soups='Супы',salads='Салаты',pies='Пироги',omelettes='Омлеты',sandwiches='Сэндвичи',heal='Лечение',
    energy='Энергия',resistance='Сопротивление',invisibility='Невидимость',poison='Яд',alchemy='Алхимия',tracking='Выслеживание',
    accessoires_capes_capes='Обычные плащи')
COLORS={'green':'#203c30','blue':'#203447','red':'#452a2c','neutral':'#292e34','unknown':'#25282d'}
DEMAND=DEMAND_LABELS

class NumericItem(QTableWidgetItem):
    def __lt__(self,other):
        a=self.data(Qt.UserRole);b=other.data(Qt.UserRole)
        if isinstance(a,(int,float,Decimal)) and isinstance(b,(int,float,Decimal)):return a<b
        if isinstance(a,(int,float,Decimal)):return False
        if isinstance(b,(int,float,Decimal)):return True
        return self.text()<other.text()

def combo(options):
    box=QComboBox()
    box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);box.setMinimumContentsLength(16)
    for label,value in options:box.addItem(label,value)
    return box

class Window(QMainWindow):
    def __init__(self,region=None):
        super().__init__();self.base_root=ROOT
        prefs=preferences(self.base_root)
        try:self.region=region_key(region or prefs.get('region','europe'))
        except ValueError:self.region='europe'
        self.root=region_root(self.base_root,self.region);self.region_label=REGIONS[self.region]['label']
        self.setWindowTitle('AlbionCraft • '+self.region_label);self.resize(1540,900)
        self.setWindowIcon(QIcon(str(resource_root()/'app/assets/albioncraft.svg')))
        self.restoring_view=True
        self.settings_path=self.root/'settings.json'
        try:self.settings=json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.settings={}
        set_language(prefs.get('language',self.settings.get('language','ru' if self.settings else get_language())))
        if not self.settings:self.settings['progress_player']=tr('Мой персонаж')
        help_menu=self.menuBar().addMenu(tr('Помощь'))
        about=help_menu.addAction(tr('О программе'));about.triggered.connect(self.about)
        folder=help_menu.addAction(tr('Папка моих данных'));folder.triggered.connect(self.open_data_folder)
        research=help_menu.addAction(tr('История рынка и бонусы'));research.triggered.connect(self.open_research)
        profile=help_menu.addAction(tr('Резервная копия и диагностика'));profile.triggered.connect(self.open_data_tools)
        language_menu=self.menuBar().addMenu('Language / Язык')
        language_group=QActionGroup(self);language_group.setExclusive(True);self.language_actions={}
        for code,label in LANGUAGES.items():
            action=language_menu.addAction(label);action.setCheckable(True);action.setChecked(code==get_language())
            language_group.addAction(action);self.language_actions[code]=action
            action.triggered.connect(lambda checked=False,code=code:self.change_language(code))
        self.recipes=load_catalog(self.root);self.api=AlbionAPI(self.region);self.worker=None;self.last=None;self.visible=[];self.recommendation_rows=[]
        self.render_worker=None;self.render_generation=0;self.pending_render=False
        from .live_refresh import LiveRefresh
        self.market_version=0;self.live_refresh=LiveRefresh(self)
        self.live_refresh.ready.connect(self.live_received)
        self.live_refresh.failed.connect(lambda message:self.local_status.setText(tr('Ошибка обновления рынка: ')+message))
        self.capture_timer=QTimer(self);self.capture_timer.setSingleShot(True);self.capture_timer.setInterval(250);self.capture_timer.timeout.connect(self.refresh_stream)
        self.render_timer=QTimer(self);self.render_timer.setSingleShot(True);self.render_timer.timeout.connect(self.render_now)
        self.table_batch=GuiBatch(self);self.table_batch.failed.connect(lambda message:self.status.setText(message))
        self.settings.setdefault('auto_rules',True)
        self.settings['region_label']=self.region_label
        self.icons=Icons(self.base_root,self);self.icons.ready.connect(self.icon_ready)
        self.setStyleSheet('QMainWindow,QDialog,QWidget{background:#1d2127;color:#e0e5eb;font-family:"Segoe UI";font-size:13px;}'
            'QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox{background:#2a3038;border:1px solid #424b56;border-radius:5px;padding:6px;}'
            'QPushButton{background:#303b49;border:1px solid #4c6179;border-radius:5px;padding:8px 14px;}'
            'QPushButton:hover{background:#3b4b60;}QPushButton:disabled{color:#758090;}'
            'QTableWidget{background:#23282f;gridline-color:#39404a;border:1px solid #39404a;}'
            'QHeaderView::section{background:#303842;padding:8px;border:0;border-right:1px solid #454e5b;}'
            'QTableWidget::item:selected{background:#41536a;color:white;}')
        body=QWidget();self.setCentralWidget(body);layout=QVBoxLayout(body);layout.setSpacing(8)
        heading_bar=FlowLayout();layout.addLayout(heading_bar)
        heading=QLabel('AlbionCraft  /  '+self.region_label);heading.setStyleSheet('font-size:24px;font-weight:600;');heading_bar.addWidget(heading);heading_bar.addStretch()
        operation=FlowLayout();layout.addLayout(operation)
        operation.addWidget(QLabel('Что ищем:'))
        self.activity=combo([('Крафт / переработка','craft'),('Зачарование готового предмета','enchant'),
            ('Межгородская перепродажа','resale'),('Перепокупка: buy order → sell order','flip')]);self.activity.setFixedWidth(310);operation.addWidget(self.activity)
        self.sort_metric='profit';self.sort_descending=True
        self.with_prices=QCheckBox('Только с ценами');self.with_prices.setChecked(True);operation.addWidget(self.with_prices)
        self.with_prices.setToolTip('Показывать, если известна хотя бы цена результата или одного компонента. Недостающие цены перечисляются в состоянии расчёта.')
        self.live=QCheckBox('Доп. ордера NATS');self.live.setChecked(bool(self.settings.get('live_orders',True)));operation.addWidget(self.live)
        self.live.setToolTip('REST остаётся основным. Поток наблюдавшихся ордеров пополняет отсутствующие цены и сохраняется отдельно. Это неполный срез рынка AODP.')
        self.page=NumberBox();self.page.setRange(1,1);self.page.setPrefix('Страница ');operation.addWidget(self.page)
        bounds=QPushButton('Прибыль / бюджет');self.bounds_button=bounds;operation.addWidget(bounds);bounds.clicked.connect(self.configure_bounds)
        self.hide_excluded=QCheckBox('Без исключённых');self.hide_excluded.setChecked(True);operation.addWidget(self.hide_excluded);operation.addStretch()
        cities=FlowLayout();layout.addLayout(cities)
        cities.addWidget(QLabel('Сервер:'));self.server=combo([(v['label'],k) for k,v in REGIONS.items()]);self.server.setCurrentIndex(self.server.findData(self.region));cities.addWidget(self.server)
        self.server.currentIndexChanged.connect(lambda:self.change_region(self.server.currentData()))
        self.buy=combo([('Все города',None)]+[(c,c) for c in CITIES])
        self.craft=combo([('Все города',None)]+[(c,c) for c in CITIES])
        self.craft.setCurrentIndex(self.craft.findData('Thetford'))
        self.sell=combo([('Все города',None)]+[(c,c) for c in CITIES])
        self.city_labels=[]
        for label,box in [('Покупка в городе',self.buy),('Город',self.craft),('Продажа в городе',self.sell)]:
            lab=QLabel(label);self.city_labels.append(lab);cities.addWidget(lab);box.setFixedWidth(170);cities.addWidget(box)
        self.caerleon=QCheckBox('Включить Caerleon');self.caerleon.setChecked(bool(self.settings.get('include_caerleon',False)));cities.addWidget(self.caerleon)
        self.caerleon.setToolTip('Межгородская перепродажа: соседние города по кольцу; с этой галочкой также маршруты в/из Caerleon (обычный рынок).')
        self.brecilien=QCheckBox('Включить Brecilien');self.brecilien.setChecked(bool(self.settings.get('include_brecilien',False)));cities.addWidget(self.brecilien)
        self.brecilien.setToolTip('Сравнивать цены в/из Brecilien. Доступ через Туманы / Пути Авалона и стоимость перевозки нужно учитывать отдельно.')
        self.brecilien.toggled.connect(self.routes_changed)
        cities.addStretch()
        rule_bar=FlowLayout();layout.addLayout(rule_bar)
        self.auto_rules=QCheckBox('Авто: игровые бонусы и комиссии');self.auto_rules.setChecked(self.settings['auto_rules']);rule_bar.addWidget(self.auto_rules)
        self.premium=QCheckBox('Считать с Premium');self.premium.setChecked(bool(self.settings.get('premium',False)));rule_bar.addWidget(self.premium)
        self.rule_info=QLabel();self.rule_info.setWordWrap(True);self.rule_info.setMaximumWidth(440);rule_bar.addWidget(self.rule_info)
        rule_bar.addWidget(QLabel('Станция: серебро / 100 питания'))
        self.station_rate=QLineEdit();self.station_rate.setPlaceholderText('Тариф неизвестен');self.station_rate.setMaximumWidth(160);rule_bar.addWidget(self.station_rate)
        apply_rate=QPushButton('Учесть тариф');rule_bar.addWidget(apply_rate);apply_rate.clicked.connect(self.apply_station_rate)
        filters=FlowLayout();layout.addLayout(filters)
        self.search=QLineEdit();self.search.setPlaceholderText('Название или ID предмета');self.search.setMinimumWidth(240);filters.addWidget(self.search)
        cats=sorted({r.category for r in self.recipes})
        self.category=combo([('Все типы',None)]+[(CATEGORIES.get(c,c),c) for c in cats]);filters.addWidget(self.category)
        self.material=combo([('Все материалы',None),('Тканевая','cloth'),('Кожаная','leather'),('Латная','plate')]);filters.addWidget(self.material)
        self.material.currentIndexChanged.connect(self.rebuild_family)
        self.family=combo([('Все виды',None)]);filters.addWidget(self.family)
        self.item=combo([('Все предметы',None)]);filters.addWidget(self.item,2)
        self.tier=combo([('Все уровни',None)]+[(f'T{n}',n) for n in range(1,9)]);self.tier.setCurrentIndex(self.tier.findData(4));filters.addWidget(self.tier)
        self.enchantment=combo([('Все зачарования',None)]+[(f'.{n}',n) for n in range(5)]+[('Выбранные чары','custom')]);self.enchantment.setCurrentIndex(self.enchantment.findData('custom') if 'enchantment_mask' in self.settings else 1);filters.addWidget(self.enchantment)
        self.quality=combo([('Качество неважно','any'),('Все качества',None)]+[(s,n) for n,s in enumerate(['Обычное','Хорошее','Выдающееся','Отличное','Шедевр'],1)]);filters.addWidget(self.quality)
        for box,width in [(self.category,175),(self.family,140),(self.tier,85),(self.enchantment,140),(self.quality,145)]:box.setFixedWidth(width)
        choose_filters=QPushButton('Выбор…');self.choose_filters=choose_filters;choose_filters.setToolTip('Выбрать несколько зачарований и качеств галочками');choose_filters.clicked.connect(self.select_filters);filters.addWidget(choose_filters)
        self.update_mask_labels()
        actions=FlowLayout();layout.addLayout(actions)
        self.mode=combo([('Выставить на продажу','order'),('Продать сразу','instant')]);actions.addWidget(self.mode)
        self.demand=combo([('Любой объём продаж',None)]+[(label,key) for key,label in DEMAND.items()]);actions.addWidget(self.demand)
        actions.addWidget(QLabel('Старше, мин:'));self.age=NumberBox();self.age.setRange(1,10080);self.age.setValue(30);actions.addWidget(self.age)
        self.any_age=QCheckBox('Любой возраст цен');actions.addWidget(self.any_age)
        self.any_age.setToolTip('Использовать все доступные котировки независимо от давности. Отсутствующие цены и игровые расходы не восстанавливаются этой настройкой.')
        self.any_age.setChecked(bool(self.settings.get('any_age',False)))
        self.age.setEnabled(not self.any_age.isChecked())
        self.configure=QPushButton('RRR и комиссии');actions.addWidget(self.configure)
        self.cached=QPushButton('Сканировать кэш');actions.addWidget(self.cached)
        self.update=QPushButton('Обновить цены');self.update.setStyleSheet('background:#315b83;font-weight:600;');actions.addWidget(self.update)
        self.cancel=QPushButton('Отмена');self.cancel.setEnabled(False);actions.addWidget(self.cancel)
        self.status=QLabel('Выберите предметы и обновите цены. Расходы заполните в «RRR и комиссии».');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.stream_status=QLabel('NATS: ожидание подключения');self.stream_status.setWordWrap(True);layout.addWidget(self.stream_status)
        local_bar=FlowLayout();layout.addLayout(local_bar)
        self.local_enabled=QCheckBox('Цены из моей игры');self.local_enabled.setChecked(bool(self.settings.get('local_enabled',False)));local_bar.addWidget(self.local_enabled)
        local_setup=QPushButton('Подключить клиент…');local_bar.addWidget(local_setup);local_setup.clicked.connect(self.configure_local)
        self.local_status=QLabel('Из игры: выключено');self.local_status.setWordWrap(True);self.local_status.setMaximumWidth(850);local_bar.addWidget(self.local_status)
        self.table=SearchTable(0,15)
        self.table.setHorizontalHeaderLabels(['Предмет','Город','Продажа в','Закупка','Продажа','Прибыль\n(≤: граница)','ROI, %','Прибыль с F','ROI с F, %','Объём продаж\nшт./день','Дата','Состояние расчёта','Надёжность','Материалы','Артефакт'])
        self.material_delegate=MaterialDelegate(self.icons,self.table)
        for column in (13,14):self.table.setItemDelegateForColumn(column,self.material_delegate)
        header=self.table.horizontalHeader();header.moveSection(header.visualIndex(13),header.visualIndex(3));header.moveSection(header.visualIndex(14),header.visualIndex(13)+1)
        readable_table(self.table)
        for c,width in enumerate([250,110,110,105,105,130,95,140,110,210,155,180,160]):self.table.setColumnWidth(c,width)
        self.table.setIconSize(QSize(44,44));self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False);self.table.horizontalHeader().setSortIndicatorShown(True);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table,1)
        self.table.sortByColumn(5,Qt.DescendingOrder)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        legend=QLabel('Зелёный: ROI > +5%  •  Синий: только с Focus > +5%  •  Красный: ROI < −5%  •  Остальные: нейтральные\n'
            'Закупка и продажа — серым; давность цен — красным у даты. «?» — неполные данные. Двойной клик открывает полный расчёт.\n'
            '«≤» — верхняя граница до неизвестных расходов; «≥» — неполная сумма закупки. Себестоимость с учётом возврата ресурсов — в подробностях.\n'
            'Качество при крафте — сценарий продажи, а не гарантированный выход. Программа не размещает заказы в игре.')
        legend_text=legend.text();legend.deleteLater();explanation(layout,legend_text,'Обозначения и ограничения')
        self.category.currentIndexChanged.connect(self.rebuild_family);self.family.currentIndexChanged.connect(self.rebuild_items)
        for box in [self.item,self.tier,self.enchantment,self.quality,self.buy,self.craft,self.sell,self.demand,self.mode]:box.currentIndexChanged.connect(self.render)
        self.search.textChanged.connect(self.render);self.age.valueChanged.connect(self.render)
        self.any_age.toggled.connect(self.age_changed)
        self.auto_rules.toggled.connect(self.rules_changed);self.premium.toggled.connect(self.rules_changed)
        self.configure.clicked.connect(self.config);self.cached.clicked.connect(lambda:self.fetch(False));self.update.clicked.connect(lambda:self.fetch(True))
        self.table.cellDoubleClicked.connect(self.detail)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu);self.table.customContextMenuRequested.connect(self.item_menu)
        self.table.horizontalHeader().sectionClicked.connect(self.sort_header)
        self.activity.currentIndexChanged.connect(self.activity_changed);self.page.valueChanged.connect(self.render)
        self.caerleon.toggled.connect(self.routes_changed)
        self.with_prices.toggled.connect(self.render)
        self.hide_excluded.toggled.connect(self.render)
        self.cancel.clicked.connect(self.cancel_scan)
        self.category.setCurrentIndex(self.category.findData('weapons'));self.rebuild_family()
        self.family.setCurrentIndex(self.family.findData('sword'))
        self.restore_view()
        self.activity_changed()
        self.rules_changed(save=False)
        self.stream=None;self.stream_dirty=False;self.closing=False
        self.live.toggled.connect(self.stream_changed)
        self.stream_timer=QTimer(self);self.stream_timer.setInterval(10000);self.stream_timer.timeout.connect(self.refresh_stream);self.stream_timer.start()
        self.stream_changed(self.live.isChecked(),save=False)
        self.loaded_ids=set();self.loaded_history=set();self.loading_signature=None;self.pending_reload=False
        self.load_timer=QTimer(self);self.load_timer.setSingleShot(True);self.load_timer.setInterval(600);self.load_timer.timeout.connect(self.auto_fetch)
        self.load_timer.start()
        import secrets
        self.settings.setdefault('local_token',secrets.token_hex(24))
        self.local_receiver=None;self.local_count=0;self.client_process=None
        self.local_enabled.toggled.connect(self.local_changed)
        self.local_changed(self.local_enabled.isChecked(),save=False)
        self.view_timer=QTimer(self);self.view_timer.setSingleShot(True);self.view_timer.setInterval(300);self.view_timer.timeout.connect(self.persist_view)
        for control in self.view_controls().values():
            if isinstance(control,QComboBox):control.currentIndexChanged.connect(self.queue_view_save)
            elif isinstance(control,QCheckBox):control.toggled.connect(self.queue_view_save)
            elif isinstance(control,QSpinBox):control.valueChanged.connect(self.queue_view_save)
            else:control.textChanged.connect(self.queue_view_save)
        self.restoring_view=False
        self.build_dashboard(layout,heading_bar,operation,cities,rule_bar,filters,actions,local_bar)
        fit_window(self)
    def build_dashboard(self,old,heading,operation,cities,rules,filters,actions,local):
        self.setStyleSheet(STYLE)
        market=QWidget();market_body=QVBoxLayout(market);market_body.setContentsMargins(4,0,4,0)
        market_body.addWidget(title('Рынок'))
        row=QHBoxLayout();market_body.addLayout(row,1);scroll,settings=panel();row.addWidget(scroll)
        section(settings,'Задача');move_widgets(operation,settings,(self.page,self.with_prices,self.live,self.bounds_button,self.hide_excluded))
        section(settings,'Предметы');move_widgets(filters,settings,(self.tier,self.enchantment,self.quality,self.choose_filters))
        variants=QHBoxLayout();variants.addWidget(self.tier);variants.addWidget(self.enchantment);settings.addLayout(variants)
        self.tier.setMinimumWidth(0);self.tier.setMaximumWidth(130);self.enchantment.setMinimumWidth(0);self.enchantment.setMaximumWidth(150)
        server_label=cities.takeAt(0).widget();server_label.deleteLater()
        section(settings,'Города');move_widgets(cities,settings,(self.server,))
        section(settings,'Продажа');move_widgets(actions,settings,(self.cached,self.update,self.cancel,self.configure))
        advanced=fold(settings,'Дополнительные настройки')
        for widget in (self.with_prices,self.hide_excluded,self.bounds_button,self.quality,self.choose_filters):advanced.addWidget(widget)
        move_widgets(rules,advanced);advanced.addWidget(self.configure)
        connection=fold(settings,'Источники данных');connection.addWidget(self.live);move_widgets(local,connection);connection.addWidget(self.stream_status)
        settings.addStretch()
        results=QWidget();results_body=QVBoxLayout(results);results_body.setContentsMargins(8,0,0,0);row.addWidget(results,1)
        buttons=FlowLayout();results_body.addLayout(buttons)
        for button in (self.update,self.cached,self.cancel):buttons.addWidget(button)
        self.update.setObjectName('primary');self.update.setStyleSheet('');buttons.addStretch();buttons.addWidget(self.page)
        self.detail_columns=QCheckBox('Подробные столбцы');buttons.addWidget(self.detail_columns)
        self.detail_columns.toggled.connect(self.show_extra_columns)
        results_body.addWidget(self.table,1);results_body.addWidget(self.status);results_body.addWidget(self.summary)
        # Keep existing explanatory controls available, but out of the main table area.
        leftovers=fold(settings,'Справка')
        while old.count():
            item=old.takeAt(0)
            if widget:=item.widget():
                if widget not in (self.table,self.status,self.summary,self.stream_status):leftovers.addWidget(widget)
        self.table.setColumnWidth(13,165);self.table.setColumnWidth(14,145)
        self.page_stack=QStackedWidget();self.page_stack.addWidget(market);self.market_page=market
        shell=QWidget();shell_body=QHBoxLayout(shell);shell_body.setContentsMargins(0,0,8,8);shell_body.setSpacing(12)
        navigation=QWidget();navigation.setObjectName('navigation');navigation.setFixedWidth(172);nav=QVBoxLayout(navigation)
        nav.setContentsMargins(12,16,12,12);brand=QLabel('AlbionCraft');brand.setStyleSheet('font-size:20px;font-weight:600;color:#65d6bb;');nav.addWidget(brand)
        nav.addWidget(QLabel(self.region_label));self.nav_buttons={}
        for key,text,action in [('market','Рынок',self.show_market),('trip','Ходки',self.open_trip),('orders','Мои заказы',self.open_orders),('builds','Билды',self.open_builds),('profile','Персонаж',self.open_profile),('island','Остров',self.open_island),('recommendations','Рекомендации',self.open_recommendations),('preferences','Персонализация',self.personalize)]:
            button=QPushButton(text);button.setObjectName('navButton');button.setCheckable(True);button.clicked.connect(action);nav.addWidget(button);self.nav_buttons[key]=button
        nav.addStretch();section(nav,'Сервер');nav.addWidget(self.server)
        shell_body.addWidget(navigation);shell_body.addWidget(self.page_stack,1)
        previous=self.takeCentralWidget();self.setCentralWidget(shell);previous.deleteLater()
        self.show_market();self.show_extra_columns(False)
    def show_extra_columns(self,checked):
        self.table.setColumnHidden(3,not checked and self.activity.currentData() in ('craft','enchant'))
        for col in (7,8):self.table.setColumnHidden(col,not checked or self.activity.currentData()!='craft')
        for col in (10,11,12):self.table.setColumnHidden(col,not checked)
    def activate_page(self,key,page):
        self.page_stack.setCurrentWidget(page)
        for name,button in self.nav_buttons.items():button.setChecked(name==key)
    def show_market(self):self.activate_page('market',self.market_page)
    def open_island(self):
        from .island_dialog import IslandPage
        if not hasattr(self,'island_page'):
            self.island_page=IslandPage(self,self.root);self.page_stack.addWidget(self.island_page)
        self.activate_page('island',self.island_page)
    def view_controls(self):
        return {key:getattr(self,key) for key in ('activity','buy','craft','sell','category','material','family','item','tier','enchantment','quality','demand','mode','search','age','any_age','with_prices','hide_excluded')}
    def about(self):
        QMessageBox.about(self,'AlbionCraft',f'<h3>AlbionCraft {__version__} · Beta</h3>'
            '<p>Рынок, переработка, ходки и прогресс для Albion Online.</p>'
            '<p>Исходный код AlbionCraft — MIT. Сторонние библиотеки и игровые данные имеют собственные условия.</p>'
            '<p>Независимый проект сообщества. Не связан с Sandbox Interactive.</p>'
            '<p>Цены и объёмы могут быть неполными; прибыль — оценка по доступным данным.</p>')
    def open_data_folder(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.root)))
    def restore_view(self):
        view=self.settings.get('view',{})
        if not view:return
        controls=self.view_controls();blockers=[QSignalBlocker(control) for control in controls.values()]
        try:
            def restore(key):
                if key not in view:return
                control=controls[key];value=view[key]
                if isinstance(control,QComboBox):
                    index=control.findData(value)
                    if index>=0:control.setCurrentIndex(index)
                elif isinstance(control,QCheckBox):control.setChecked(bool(value))
                elif isinstance(control,QSpinBox):control.setValue(int(value))
                else:control.setText(str(value))
            restore('category')
            restore('material')
            if 'category' in view:self.rebuild_family()
            restore('family')
            if 'category' in view or 'family' in view:self.rebuild_items()
            restore('item')
            for key in controls:
                if key not in ('category','material','family','item'):restore(key)
            metric=view.get('sort_metric','profit')
            self.sort_metric=metric if metric in ('profit','roi','focus_profit','focus_roi') else 'profit'
            self.sort_descending=bool(view.get('sort_descending',True))
        finally:del blockers
        self.age.setEnabled(not self.any_age.isChecked())
    def queue_view_save(self,*args):
        if not self.restoring_view:self.view_timer.start()
    def persist_view(self):
        if self.restoring_view:return
        self.view_timer.stop();view={}
        for key,control in self.view_controls().items():
            view[key]=control.currentData() if isinstance(control,QComboBox) else control.isChecked() if isinstance(control,QCheckBox) else control.value() if isinstance(control,QSpinBox) else control.text()
        view.update(sort_metric=self.sort_metric,sort_descending=self.sort_descending)
        self.settings['view']=view;save_settings(self.settings_path,self.settings)
    def personalize(self):
        from .personalization import PersonalizationDialog
        if dialog:=getattr(self,'preferences_page',None):self.activate_page('preferences',dialog);return
        dialog=PersonalizationDialog(self,self.recipes,self.settings);self.preferences_page=dialog
        def saved():
            self.settings.update(excluded_items=dialog.excluded,recommendations=dialog.recommendations)
            self.persist_view();self.page.setValue(1);self.render()
        dialog.accepted.connect(saved);self.present_dialog('preferences','preferences_page',dialog,retire=True)
    def present_dialog(self,key,attribute,dialog,retire=False):
        if self.page_stack.indexOf(dialog)<0:
            dialog.setWindowFlags(Qt.Widget);self.page_stack.addWidget(dialog)
            def finished(*args):
                if self.page_stack.currentWidget()==dialog:self.show_market()
                if retire:
                    self.page_stack.removeWidget(dialog);setattr(self,attribute,None);dialog.deleteLater()
            dialog.finished.connect(finished)
        self.activate_page(key,dialog);dialog.show()
    def item_menu(self,pos):
        n=self.table.indexAt(pos).row();cell=self.table.item(n,0)
        if not cell:return
        row=self.visible[cell.data(Qt.UserRole+1)];r=row['recipe'];menu=QMenu(self)
        copy=menu.addAction('Скопировать название для поиска')
        action=menu.addAction('Вернуть предмет из исключений' if is_excluded(r,self.settings) else 'Исключить предмет — все уровни и чары')
        selected=menu.exec(self.table.viewport().mapToGlobal(pos))
        if selected==action:self.toggle_exclusion(r)
        elif selected==copy:QApplication.clipboard().setText(item_name(r.item_id,False))
    def toggle_exclusion(self,recipe):
        key=exclusion_key(recipe);excluded=set(self.settings.get('excluded_items',[]))
        if key in excluded:excluded.remove(key)
        else:excluded.add(key)
        self.settings['excluded_items']=sorted(excluded);self.persist_view();self.page.setValue(1);self.render()
    def open_builds(self):
        from .builds_dialog import BuildsDialog
        if not hasattr(self,'builds_dialog'):self.builds_dialog=BuildsDialog(self,self.root)
        self.present_dialog('builds','builds_dialog',self.builds_dialog)
    def open_trip(self):
        from .trip_dialog import TripDialog
        if not hasattr(self,'trip_page'):
            self.trip_page=TripDialog(self,self.root);self.trip_page.setWindowFlags(Qt.Widget);self.page_stack.addWidget(self.trip_page)
        self.activate_page('trip',self.trip_page)
    def open_recommendations(self):
        from .recommendations_dialog import RecommendationsDialog
        if not hasattr(self,'recommendation_dialog'):self.recommendation_dialog=RecommendationsDialog(self)
        self.present_dialog('recommendations','recommendation_dialog',self.recommendation_dialog);self.recommendation_dialog.refresh()
    def open_orders(self):
        from .own_orders_dialog import OwnOrdersDialog
        if not getattr(self,'orders_page',None):self.orders_page=OwnOrdersDialog(self,self.root/'player.sqlite')
        self.present_dialog('orders','orders_page',self.orders_page,retire=True)
    def save_local_settings(self):
        self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
    def configure_local(self):
        from .local_client_dialog import ClientDialog
        ClientDialog(self).exec()
    def local_changed(self,checked,save=True):
        self.settings['local_enabled']=checked
        if save:self.save_local_settings()
        if checked and (self.local_receiver is None or not self.local_receiver.isRunning()):
            self.local_receiver=LocalReceiver(self.root/'prices.sqlite',self.settings['local_token'],region=self.region)
            self.local_receiver.finished.connect(self.local_stopped)
            self.local_receiver.status.connect(self.local_status.setText);self.local_receiver.updated.connect(self.local_updated);self.local_receiver.start()
        elif not checked and self.local_receiver:
            self.local_receiver.requestInterruption();self.local_status.setText('Из игры: выключено')
        self.refresh_stream()
    def local_stopped(self):
        worker=self.sender()
        if worker is self.local_receiver:self.local_receiver=None
        if worker:worker.deleteLater()
        if self.local_enabled.isChecked() and not self.closing:
            QTimer.singleShot(1500,lambda:self.local_changed(True,save=False) if self.local_enabled.isChecked() and not self.closing else None)
    def local_updated(self,count):
        if not count:return
        self.local_count+=max(0,count)
        from datetime import datetime
        self.local_status.setText(f'Из игры: получено {self.local_count} ордеров • '+(f'история: {abs(count)} точек • ' if count<0 else '')+f'последнее наблюдение {datetime.now().strftime("%H:%M")} • {self.region_label}')
        if self.last is None:self.last=dict(prices=[],api_prices=[],histories=[],cached=False,warning='Из твоей игры: только просмотренные ордера; история спроса загружается отдельно.')
        if not self.capture_timer.isActive():self.capture_timer.start()
    def configure_bounds(self):
        dialog=BoundsDialog(self,self.settings.get('result_limits',{}))
        if dialog.exec():
            self.settings['result_limits']=dialog.limits;self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8');self.page.setValue(1);self.render()
    def open_profile(self):
        from .destiny_dialog import DestinyDialog
        if dialog:=getattr(self,'profile_page',None):self.activate_page('profile',dialog);return
        current=self.table.currentRow();cell=self.table.item(current,0) if current>=0 else None
        row=self.visible[cell.data(Qt.UserRole+1)] if cell else None
        self.profile_page=DestinyDialog(self,self.root,self.recipes,row);self.present_dialog('profile','profile_page',self.profile_page,retire=True)
    def comparison_ids(self,recipes):
        quality=self.quality.currentData()
        if self.settings.get('prefer_upgrades',True):return comparison_price_ids(recipes,self.recipes)
        if quality!=5 and (quality not in (None,'any') or 5 not in self.settings.get('quality_mask',range(1,6))):return set()
        targets={}
        for r in recipes:
            base=r.item_id.split('@')[0];targets[base]=min(targets.get(base,r.enchantment),r.enchantment)
        # Include higher enchantments even when the display mask excludes them.
        return {r.item_id for r in self.recipes if r.item_id.split('@')[0] in targets and r.enchantment>targets[r.item_id.split('@')[0]]}
    def required_ids(self,recipes):
        return {r.item_id for r in recipes}|self.comparison_ids(recipes)|({i.item_id for r in recipes for i in r.ingredients} if self.activity.currentData() in ('craft','enchant') else set())
    def selected_enchantments(self):
        choice=self.enchantment.currentData()
        return set(self.settings.get('enchantment_mask',range(5))) if choice=='custom' else set(range(5)) if choice is None else {choice}
    def update_mask_labels(self):
        values=self.settings.get('enchantment_mask',list(range(5)))
        self.enchantment.setItemText(self.enchantment.findData('custom'),' / '.join(f'.{n}' for n in values))
        names=['Обычное','Хорошее','Выдающееся','Отличное','Шедевр']
        selected=self.settings.get('quality_mask',list(range(1,6)))
        self.quality.setItemText(self.quality.findData(None),'Все качества' if len(selected)==5 else 'Все выбранные')
        self.quality.setToolTip('Отмечены: '+', '.join(names[n-1] for n in selected)+'. Изменить: «Выбор…». Конкретное качество в списке задаёт отдельный сценарий.')
    def select_filters(self):
        choice=self.quality.currentData()
        qualities={choice} if isinstance(choice,int) else self.settings.get('quality_mask',list(range(1,6)))
        dialog=FilterSelection(self,self.selected_enchantments(),qualities,self.settings.get('prefer_upgrades',True))
        if dialog.exec():
            self.settings.update(enchantment_mask=dialog.enchantment_mask,quality_mask=dialog.quality_mask,prefer_upgrades=dialog.prefer_upgrades.isChecked())
            self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
            self.update_mask_labels();self.enchantment.setCurrentIndex(self.enchantment.findData('custom'))
            if isinstance(choice,int):self.quality.setCurrentIndex(self.quality.findData('any'))
            self.page.setValue(1);self.render()
    def auto_fetch(self):
        recipes=self.filtered()
        ids=self.required_ids(recipes);history={r.item_id for r in recipes}
        if not recipes or (ids<=self.loaded_ids and history<=self.loaded_history):return
        if self.worker and self.worker.isRunning():self.pending_reload=True;return
        if self.loading_signature==(frozenset(ids),frozenset(history)):return
        self.fetch(False)
    def stream_changed(self,checked,save=True):
        if save:
            self.settings['live_orders']=checked
            self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
        if checked and (self.stream is None or not self.stream.isRunning()):
            ids={r.item_id for r in self.recipes}|{i.item_id for r in self.recipes for i in r.ingredients}
            self.stream=OrderStream(self.root/'prices.sqlite',ids,self.region)
            self.stream.status.connect(self.stream_status.setText);self.stream.updated.connect(self.stream_updated);self.stream.start()
            self.stream.finished.connect(self.stream_stopped)
        elif not checked and self.stream:
            self.stream.requestInterruption();self.stream_status.setText('NATS: выключен')
        self.stream_dirty=True;self.refresh_stream()
    def stream_stopped(self):
        if self.live.isChecked() and not self.closing:self.stream_changed(True,save=False)
    def stream_updated(self):self.stream_dirty=True
    def refresh_stream(self):
        if hasattr(self,'client_process') and self.client_process and self.client_process.poll() is not None:
            code=self.client_process.returncode
            self.local_status.setText(f'Albion Data Client завершился (код {code}). Ошибка сохранена в logs/data-client-output.log; запусти клиент повторно через «Подключить клиент…».')
            self.client_process=None
        if self.last is None:return
        # Database waits and decoding happen in the worker, never a GUI slot.
        primary=self.last.get('api_prices',self.last['prices'])
        self.last['api_prices']=primary
        api_history=self.last.get('api_histories',self.last['histories']);self.last['api_histories']=api_history
        recipes=self.filtered()
        self.live_refresh.request(dict(path=str(self.root/'prices.sqlite'),prices=primary,histories=api_history,
            ids=self.required_ids(recipes),history_ids={r.item_id for r in recipes},
            live=self.live.isChecked(),local=hasattr(self,'local_enabled') and self.local_enabled.isChecked(),context=self.live_context()))
        self.stream_dirty=False
    def live_context(self):
        return (self.market_version,self.live.isChecked(),hasattr(self,'local_enabled') and self.local_enabled.isChecked())
    def live_received(self,data):
        if self.closing or self.last is None or data['context']!=self.live_context():return
        if data['prices']!=self.last['prices'] or data['histories']!=self.last['histories']:
            self.last['prices']=data['prices'];self.last['histories']=data['histories'];self.render()
    def rules_changed(self,*args,save=True):
        self.settings.update(auto_rules=self.auto_rules.isChecked(),premium=self.premium.isChecked())
        active=effective_settings(self.settings)
        self.rule_info.setText(f'Размещение: {active.get("setup","?")}% • налог: {active.get("tax","?")}% • дневной бонус не учтён')
        if save:self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
        self.render()
    def apply_station_rate(self):
        text=self.station_rate.text().strip();rate=number(text)
        if text and rate is None:
            QMessageBox.warning(self,'Тариф','Введите неотрицательное число.');return
        cities=self.selected_cities(self.craft)
        rates=self.settings.setdefault('station_rates',{})
        for city in cities:
            if text:rates[city]=str(rate)
            else:rates.pop(city,None)
        self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8');self.render()
    def activity_changed(self):
        resale=self.activity.currentData()=='resale'
        self.caerleon.setVisible(resale)
        self.brecilien.setVisible(resale)
        if self.activity.currentData()=='enchant' and self.enchantment.currentData()==0:self.enchantment.setCurrentIndex(self.enchantment.findData(1))
        for n,box in enumerate([self.buy,self.craft,self.sell]):
            box.setVisible(resale if n!=1 else not resale);self.city_labels[n].setVisible(resale if n!=1 else not resale)
        self.mode.setEnabled(self.activity.currentData()!='flip')
        self.table.horizontalHeaderItem(1).setText('Покупка в' if resale else 'Город')
        self.station_rate.setEnabled(self.activity.currentData()=='craft')
        self.page.setValue(1);self.render()
    def cancel_scan(self):
        self.pending_reload=False;self.load_timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption();self.status.setText('Отмена после завершения текущего запроса…')
    def age_changed(self,checked):
        self.age.setEnabled(not checked);self.settings['any_age']=checked
        self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
        self.render()
    def sort_header(self,column):
        metric={5:'profit',6:'roi',7:'focus_profit',8:'focus_roi'}.get(column)
        if metric:
            self.sort_descending=not self.sort_descending if self.sort_metric==metric else True
            self.sort_metric=metric;self.page.setValue(1);self.render()
            self.queue_view_save()
    def routes_changed(self):
        self.settings['include_caerleon']=self.caerleon.isChecked()
        self.settings['include_brecilien']=self.brecilien.isChecked()
        self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8');self.page.setValue(1);self.render()
    def rebuild_family(self):
        self.material.setVisible(self.category.currentData()=='armors')
        self.family.blockSignals(True);self.family.clear();self.family.addItem('Все виды',None)
        families=sorted({r.family for r in self.recipes if self.category.currentData() in (None,r.category) and self.material_matches(r)})
        for f in families:self.family.addItem(FAMILIES.get(f,f),f)
        self.family.setCurrentIndex(0);self.family.blockSignals(False);self.rebuild_items()
    def rebuild_items(self):
        self.item.blockSignals(True)
        items={}
        for r in self.recipes:
            if self.category.currentData() in (None,r.category) and self.family.currentData() in (None,r.family) and self.material_matches(r):
                key=r.base_id.split('_',1)[1];label=r.name.split(' (')[0];items.setdefault(key,label)
        set_choices(self.item,[('Все предметы',None)]+[(label,k) for k,label in sorted(items.items(),key=lambda x:x[1])])
        self.item.setCurrentIndex(0);self.item.blockSignals(False);self.render()
    def material_matches(self,recipe):
        return self.category.currentData()!='armors' or not self.material.currentData() or recipe.family.startswith(self.material.currentData()+'_')
    def filtered(self):
        text=self.search.text().strip().casefold()
        result=[r for r in self.recipes if self.category.currentData() in (None,r.category)
            and self.material_matches(r)
            and self.family.currentData() in (None,r.family)
            and self.item.currentData() in (None,r.base_id.split('_',1)[1])
            and self.tier.currentData() in (None,r.tier) and r.enchantment in self.selected_enchantments()
            and (not text or matches_item(r.item_id,text,r.name))]
        if self.hide_excluded.isChecked():
            excluded=set(self.settings.get('excluded_items',[]));result=[r for r in result if exclusion_key(r) not in excluded]
        if self.activity.currentData()=='craft':return [r for r in result if r.path=='Прямой крафт']
        if self.activity.currentData()=='enchant':return enchant_recipes(result)
        return list({r.item_id:r for r in result}.values())
    def selected_cities(self,box):return [box.currentData()] if box.currentData() else CITIES
    def config(self):
        recipes=self.filtered()
        if not recipes:self.status.setText('Нет рецептов по выбранным фильтрам.');return
        dlg=SettingsDialog(self,recipes,self.settings,self.settings_path)
        if dlg.exec():self.settings=dlg.settings;self.render()
    def fetch(self,force):
        if self.worker and self.worker.isRunning():self.pending_reload=True;return
        recipes=self.filtered()
        if not recipes:self.status.setText('Нет подходящих рецептов. Сырьё без рецепта доступно в перепокупке и межгородской перепродаже.');return
        self.loading_signature=(frozenset(self.required_ids(recipes)),frozenset(r.item_id for r in recipes))
        self.start_fetch(recipes,force,self.comparison_ids(recipes))
    def refresh_price_ids(self,ids):
        if not ids or self.worker and self.worker.isRunning():return
        self.start_fetch([],True,ids)
    def start_fetch(self,recipes,force,extra_ids):
        self.update.setEnabled(False);self.cached.setEnabled(False);self.cancel.setEnabled(True)
        self.worker=Fetch(self.api,recipes,None,self.root,force,self.activity.currentData(),extra_ids)
        self.worker.progress.connect(self.status.setText);self.worker.ready.connect(self.received)
        self.worker.failed.connect(self.error);self.worker.finished.connect(self.finished);self.worker.start()
    def finished(self):
        self.update.setEnabled(True);self.cached.setEnabled(True);self.cancel.setEnabled(False)
        if self.pending_reload:self.pending_reload=False;self.load_timer.start()
    def error(self,message):
        self.status.setText('Ошибка API. Предыдущие результаты сохранены.');QMessageBox.warning(self,'Ошибка API',message)
    def received(self,data):
        self.market_version+=1
        old=self.last or {}
        prices={(p['item_id'],p['city'],p['quality']):p for p in old.get('api_prices',old.get('prices',[]))}
        prices.update({(p['item_id'],p['city'],p['quality']):p for p in data['prices']})
        histories={(h['item_id'],h['location'],h['quality']):h for h in old.get('api_histories',old.get('histories',[]))}
        histories.update({(h['item_id'],h['location'],h['quality']):h for h in data['histories']})
        self.loaded_ids.update(data.get('loaded_ids',{p['item_id'] for p in data['prices']}))
        self.loaded_history.update(data.get('loaded_history',{h['item_id'] for h in data['histories']}))
        self.last={**data,'recipes':self.recipes,'prices':list(prices.values()),'histories':list(histories.values())}
        self.last['api_histories']=self.last['histories']
        self.last['api_prices']=self.last['prices'];self.render();self.refresh_stream()
    def render(self,*args):
        if hasattr(self,'load_timer'):self.load_timer.start()
        if not self.last or getattr(self,'closing',False):return
        self.render_generation+=1;self.table_batch.cancel()
        if self.render_worker and self.render_worker.isRunning():self.render_worker.requestInterruption()
        self.render_timer.start(180)
    def open_research(self):
        from .research_dialog import ResearchDialog
        ResearchDialog(self).exec()
    def open_data_tools(self):
        from .profile_dialog import ProfileDialog
        ProfileDialog(self).exec()
    def render_now(self):
        if not self.last or getattr(self,'closing',False):return
        if self.render_worker and self.render_worker.isRunning():self.pending_render=True;return
        from copy import deepcopy
        from .market_memory import bonus_settings
        activity=self.activity.currentData();recipes=self.filtered()
        self.settings.update(sale_mode=self.mode.currentData(),activity=activity,same_city=activity in ('craft','enchant'),nearby_only=True,include_caerleon=self.caerleon.isChecked(),include_brecilien=self.brecilien.isChecked())
        data=dict(recipes=recipes,settings=deepcopy(bonus_settings(self.root,self.settings)),activity=activity,
            prices=self.last['prices'],histories=self.last['histories'],quality=self.quality.currentData(),
            age=None if self.any_age.isChecked() else self.age.value(),buy=self.selected_cities(self.buy),
            craft=self.selected_cities(self.craft),sell=self.selected_cities(self.sell),demand=self.demand.currentData(),
            with_prices=self.with_prices.isChecked(),sort=self.sort_metric,descending=self.sort_descending)
        generation=self.render_generation
        self.status.setText('Пересчитываю выбранные предметы…')
        self.render_worker=ProcessWorker('scan',data,self)
        self.render_worker.ready.connect(lambda result:self.render_received(generation,result,data))
        self.render_worker.failed.connect(lambda message:self.status.setText('Ошибка расчёта: '+message) if generation==self.render_generation else None)
        self.render_worker.finished.connect(self.render_finished);self.render_worker.start()
    def render_finished(self):
        worker=self.sender()
        if worker is self.render_worker:self.render_worker=None
        if worker:worker.deleteLater()
        if self.pending_render and not getattr(self,'closing',False):self.pending_render=False;self.render_timer.start(0)
    def render_received(self,generation,result,data):
        if generation!=self.render_generation or getattr(self,'closing',False):return
        self.recommendation_rows=result['recommendations']
        self.table_batch.start(self.display_rows(result,data))
    def display_rows(self,result,data):
        rows=result['rows'];upgrade_hidden=result['upgrades'];hidden=result['hidden'];limits_hidden=result['limited']
        recipes=data['recipes'];allowed=set(recipes);activity=data['activity'];sort=data['sort']
        total=len(rows);pages=max(1,(total+99)//100)
        self.page.blockSignals(True);self.page.setMaximum(pages);self.page.blockSignals(False)
        begin=(self.page.value()-1)*100;self.visible=rows[begin:begin+100]
        self.table.setSortingEnabled(False);self.table.setRowCount(0);self.table.setRowCount(len(self.visible))
        self.table.setColumnHidden(2,activity!='resale')
        variants={}
        for recipe in recipes:variants.setdefault((recipe.item_id,recipe.path),set()).add(recipe.variant)
        for c in (7,8):self.table.setColumnHidden(c,activity!='craft')
        if hasattr(self,'detail_columns'):self.show_extra_columns(self.detail_columns.isChecked())
        for c in (13,14):self.table.setColumnHidden(c,activity not in ('craft','enchant'))
        if activity in ('craft','enchant'):
            self.table.setColumnHidden(1,self.craft.currentData() is not None)
            self.table.setColumnHidden(14,not any(breakdown(row,True)['parts'] for row in self.visible))
        else:self.table.setColumnHidden(1,False);self.table.setColumnHidden(3,False)
        for n,row in enumerate(self.visible):
            r=row['recipe'];a=row['base'];b=row['focus'];d=row['demand']
            confidence='?' if row['reasons'] else '⚠' if row['issues'] else '✓'
            pending=row.get('pending_costs',[]);prefix='≤ ' if pending else ''
            margin=row.get('gross_margin')
            profit=prefix+money(a['profit']) if a else ('Маржа '+money(margin) if margin is not None else 'Нужны цены' if has_known_price(row) else 'Нет цен')
            state='; '.join(dict.fromkeys(row['reasons'])) if row['reasons'] else 'Не вычтены: '+', '.join(pending) if pending else 'Предварительный' if row['issues'] else 'Рассчитано'
            purchase=row.get('purchase_cost')
            purchase_text=('≥ ' if not row.get('purchase_complete',True) else '')+money(purchase)
            if not row.get('purchase_complete',True) and not any(p.get('price') is not None for p in row['parts']):purchase_text='—'
            q=row.get('quality',self.quality.currentData());row['quality']=q
            label=r.name+f'  T{r.tier}.{r.enchantment}'+(' • '+self.quality.itemText(self.quality.findData(q)) if r.max_quality>1 and self.quality.currentData() in (None,'any') else '')
            if activity=='enchant':label+='\n'+r.path
            elif activity=='craft' and len(variants[(r.item_id,r.path)])>1:label+='\n'+recipe_variant(r)
            if row.get('sale_source','').startswith('Из твоей игры') or any(p.get('source','').startswith('Из твоей игры') for p in row['parts']):label+='\n● Из твоей игры'
            reliability_label,reliability_tip=reliability(row)
            values=[label,row['buy'],row['sell'],
                purchase_text,money(row['sale']),profit,
                prefix+roi(a['roi']) if a else '—',prefix+money(b['profit']) if b else '—',prefix+roi(b['roi']) if b else '—',
                demand_text(d),
                timestamp(row['sale_date'])+'  '+confidence,state,reliability_label]
            tips='\n'.join(dict.fromkeys(row['reasons']+row['issues'])) or 'Расчёт по заданным параметрам'
            if row.get('max_station_fee') is not None:
                tips+='\nПредельные расходы станции: '+money(row['max_station_fee'])+' серебра'
                if row.get('max_station_rate') is not None:tips+='\nПорог тарифа: '+money(row['max_station_rate'])+' серебра / 100 питания'
            nums={3:purchase,4:row['sale'],5:a['profit'] if a else None,6:a['roi'] if a else None,
                  7:b['profit'] if b else None,8:b['roi'] if b else None,9:d['per_day']}
            for c,value in enumerate(values):
                cell=NumericItem(str(value));cell.setBackground(QColor(COLORS[row['color']]));cell.setToolTip(tips);cell.setData(Qt.UserRole+1,n)
                if c==0:cell.setData(SEARCH_NAME_ROLE,item_name(r.item_id,False))
                if c in nums and nums[c] is not None:cell.setData(Qt.UserRole,float(nums[c]))
                if c==9:cell.setToolTip(demand_tip(d))
                if c==12:
                    cell.setToolTip(reliability_tip);cell.setForeground(QColor('#ffb77d' if reliability_label=='Неполный расчёт' else '#dccb88' if reliability_label=='Требует проверки' else '#a6d7ac'))
                if c==0:cell.setIcon(self.icons.get(r.item_id,q));cell.setToolTip(r.item_id+'\n'+r.path+f' #{r.variant+1}\n'+tips)
                if c in (3,4):cell.setForeground(QColor('#b8bec6'))
                if c in (6,8) and nums.get(c) is not None and nums[c]<0:cell.setForeground(QColor('#ff7777'))
                if c==10 and (any('устарело' in p['status'] or 'будущем' in p['status'] for p in row['parts']) or 'устарело' in row['sale_status'] or 'будущем' in row['sale_status']):cell.setForeground(QColor('#ff7777'))
                self.table.setItem(n,c,cell)
            material_height=60
            for column,artifacts in ((13,False),(14,True)):
                data=breakdown(row,artifacts);cell=NumericItem('');cell.setData(MATERIAL_ROLE,data);cell.setToolTip(tip(data));cell.setBackground(QColor(COLORS[row['color']]))
                cell.setData(Qt.UserRole,float(data['total']) if data['complete'] else None);self.table.setItem(n,column,cell)
                material_height=max(material_height,30+25*len(data['parts']))
            self.table.setRowHeight(n,max(material_height,80 if label.count('\n')>1 else 66 if '\n' in label else 60,92 if d['per_day']>=1000 else 76))
            yield
        for c,width in enumerate([210,95,95,105,95,120,85,140,110,245,160,180,160]):self.table.setColumnWidth(c,width)
        self.table.setColumnWidth(9,165);self.table.setColumnWidth(14,105)
        column={'profit':5,'roi':6,'focus_profit':7,'focus_roi':8}[sort]
        self.table.horizontalHeader().setSortIndicator(column,Qt.DescendingOrder if self.sort_descending else Qt.AscendingOrder)
        source='кэш REST' if self.last['cached'] else self.region_label+' REST API'
        extra=sum(bool(p.get('nats_observations')) for p in self.last['prices'])
        if extra:source+=f' + NATS: {extra} предметов/городов/качеств'
        local_quotes=sum(bool(p.get('local_observations')) for p in self.last['prices'])
        if local_quotes:source+=f' + Из твоей игры: {local_quotes} предметов/городов/качеств'
        self.status.setText(f'{len(recipes)} предметов/рецептов • {len(self.last["prices"])} котировок • {source}. '+self.last['warning'])
        calculated=sum(r['base'] is not None for r in rows)
        partial=sum(bool(r.get('pending_costs')) and r['base'] is not None for r in rows)
        self.summary.setText(f'Вариантов: {total} • расчётов: {calculated} (до неизвестных расходов: {partial}) • скрыто без цен: {hidden}, по диапазонам: {limits_hidden} • страница {self.page.value()}/{pages}. '
            +(f'Скрыто из-за более выгодных старших чар: {len(upgrade_hidden)}. ' if upgrade_hidden else '')
            +('Часть выбранных предметов ещё не загружена — нажмите Scan. ' if len(recipes)<len(allowed) else '')
            +('Недостающие котировки перечислены в состоянии расчёта. ' if calculated<total else '')
            +'Сортировка действует на все результаты, страницы не отбрасывают данные.')
        self.summary.setToolTip('\n'.join(f'{item_name(x["row"]["recipe"].item_id)} → {item_name(x["alternative"]["item_id"])} • {x["row"]["sell"]} • цена старших: {money(x["alternative"]["price"])}; '+('старшие чары не дороже младших' if x['alternative']['upgrade_cost'] is None else 'стоимость зачарования: '+money(x['alternative']['upgrade_cost'])) for x in upgrade_hidden[:50]))
        logging.info('Scan %d recipes: %d variants, %d calculated',len(recipes),total,calculated)
    def icon_ready(self,key):
        for n in range(self.table.rowCount()):
            cell=self.table.item(n,0)
            if cell:
                row=self.visible[cell.data(Qt.UserRole+1)];r=row['recipe']
                q=row.get('quality',self.quality.currentData())
                if key==r.item_id+'__'+str(q):cell.setIcon(self.icons.get(r.item_id,q))
    def detail(self,n,c):
        cell=self.table.item(n,0)
        if cell:
            row=self.visible[cell.data(Qt.UserRole+1)];Details(self,row,row.get('quality',self.quality.currentData()),self.settings).exec()
    def change_region(self,region):
        if region==self.region or self.closing:return
        save_preferences(self.base_root,region=region,language=get_language())
        self.change_language(get_language(),region)
    def change_language(self,code,region=None):
        if self.closing:return
        if code==get_language() and region is None:return
        tracker=getattr(self,'builds_dialog',None)
        if region is None and ((self.worker and self.worker.isRunning()) or (tracker and tracker.worker and tracker.worker.isRunning())):
            self.language_actions[get_language()].setChecked(True)
            QMessageBox.information(self,'Language / Язык',tr('Запрос выполняется; дождитесь завершения.'));return
        self.settings['language']=code;self.persist_view();save_preferences(self.base_root,language=code)
        app=QApplication.instance();app.setQuitOnLastWindowClosed(False)
        client_process=self.client_process;self.client_process=None
        self.force_exit=True
        restart_client=region is not None and client_process and client_process.poll() is None
        if restart_client:client_process.terminate();client_process=None
        for name in ('builds_dialog','recommendation_dialog'):
            if dialog:=getattr(self,name,None):dialog.close()
        self.close()
        def reopen():
            if self.isVisible():QTimer.singleShot(200,reopen);return
            try:
                set_language(code);window=Window(region or self.region);app._albioncraft_window=window;window.show()
                if hasattr(self,'desktop'):
                    from .desktop import DesktopController
                    window.desktop=DesktopController(window)
                window.client_process=client_process
                if hasattr(self,'client_error_log'):window.client_error_log=self.client_error_log
                if restart_client:
                    from .local_client_dialog import ClientDialog
                    dialog=ClientDialog(window);dialog.start();dialog.deleteLater()
                self.deleteLater()
            except Exception as exc:
                if client_process and client_process.poll() is None:client_process.terminate()
                logging.exception('Language switch');QMessageBox.critical(None,'AlbionCraft',str(exc));app.quit()
            finally:app.setQuitOnLastWindowClosed(True)
        QTimer.singleShot(0,reopen)

    def closeEvent(self,event):
        desktop=getattr(self,'desktop',None)
        if not getattr(self,'force_exit',False) and not getattr(self,'closing',False) and desktop and desktop.close_to_tray():event.ignore();return
        first=not getattr(self,'closing',False)
        self.closing=True;self.render_timer.stop();self.table_batch.cancel()
        if first:
            if desktop:desktop.shutdown()
            self.live_refresh.stop()
            self.centralWidget().setEnabled(False);self.menuBar().setEnabled(False)
            for name in ('builds_dialog','recommendation_dialog','orders_page','profile_page','preferences_page'):
                if dialog:=getattr(self,name,None):dialog.close()
        for timer_name in ('load_timer','stream_timer','view_timer','capture_timer'):
            if timer:=getattr(self,timer_name,None):timer.stop()
        tracker=getattr(self,'builds_dialog',None)
        recommendations=getattr(self,'recommendation_dialog',None)
        trip=getattr(self,'trip_page',None);island=getattr(self,'island_page',None)
        if first:
            if trip:trip.close()
            if island:island.close()
        workers=[self.worker,self.render_worker,self.live_refresh.worker,self.local_receiver,self.stream,getattr(tracker,'worker',None),getattr(tracker,'calculation_worker',None),getattr(recommendations,'calculation_worker',None),getattr(trip,'worker',None),getattr(island,'worker',None),getattr(island,'calculation',None)]
        for worker in workers:
            if worker and worker.isRunning():worker.requestInterruption()
        if any(worker and worker.isRunning() for worker in workers):
            self.status.setText('Завершаю фоновые задачи…');event.ignore();QTimer.singleShot(100,self.close);return
        self.persist_view()
        if self.client_process and self.client_process.poll() is None:self.client_process.terminate()
        event.accept()

def main():
    logging.basicConfig(filename=ROOT/'albioncraft.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',force=True)
    def report_exception(kind,value,trace):
        logging.error('Unhandled application exception',exc_info=(kind,value,trace))
    sys.excepthook=report_exception
    # pythonw has no stderr: preserve native crash stacks in a dedicated file.
    import faulthandler
    global _crash_output
    _crash_output=open(ROOT/'albioncraft-crash.log','a',encoding='utf-8')
    faulthandler.enable(file=_crash_output,all_threads=True)
    app=QApplication(sys.argv)
    from .desktop import single_instance,DesktopController
    if not single_instance(app,ROOT):return 0
    from .profile_backup import apply_restore
    try:apply_restore(ROOT)
    except Exception as exc:
        logging.exception('Profile restore');QMessageBox.warning(None,'AlbionCraft',tr('Не удалось завершить восстановление. Резервная копия перед восстановлением находится в папке данных.'))
    set_language(default_language())
    for file in ['segoeui.ttf','seguisym.ttf']:
        path=Path('C:/Windows/Fonts')/file
        if path.exists():QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Segoe UI',10))
    try:
        window=Window();app._albioncraft_window=window;window.desktop=DesktopController(window)
        if '--background' not in sys.argv or not window.desktop.tray.isVisible():window.show()
    except Exception as exc:logging.exception('Startup');QMessageBox.critical(None,'AlbionCraft',str(exc));return 1
    return app.exec()

if __name__=='__main__':sys.exit(main())
