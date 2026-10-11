from pathlib import Path
from functools import lru_cache
from PySide6.QtCore import Qt,QTimer
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QLineEdit,QPushButton,
    QSpinBox,QDoubleSpinBox,QFormLayout,QGroupBox,QGridLayout,QProgressBar,QCheckBox,QTabWidget,
    QWidget,QTableWidget,QTableWidgetItem,QMessageBox,QAbstractItemView)
from .progression import GameProgression,PlayerStore,advance
from .formatting import money,timestamp
from .ui_layout import FlowLayout,compact_combos,readable_table,fit_window
from .number_fields import NumberBox,LargeNumberBox

def progression(root):
    from .paths import catalog_root
    return _progression(str(catalog_root(root).resolve()))

@lru_cache(maxsize=2)
def _progression(root):return GameProgression(Path(root))

class CrafterDialog(QDialog):
    def __init__(self,parent,root,recipes,row=None):
        super().__init__(parent);self.setWindowTitle('Профиль — прогресс и журнал');self.resize(1080,850)
        self.game=progression(str(root));self.store=PlayerStore(Path(root)/'player.sqlite');self.row=row;self.cards={};self.states={};self.result=None
        self.setStyleSheet('QDialog,QWidget{background:#d2c09d;color:#332a20;font-family:"Segoe UI";font-size:13px;}'
            'QGroupBox{border:2px solid #8c7148;border-radius:12px;margin-top:14px;padding:14px;background:#e3d3b4;}'
            'QGroupBox::title{subcontrol-origin:margin;left:15px;color:#47351d;font-weight:bold;}'
            'QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox{background:#f2e8d1;border:1px solid #9b8057;border-radius:5px;padding:5px;}'
            'QPushButton{background:#bd9b61;border:1px solid #7c6034;border-radius:6px;padding:8px;}'
            'QProgressBar{background:#79654b;border:1px solid #7c6034;border-radius:4px;text-align:center;color:#2e251c;}'
            'QProgressBar::chunk{background:#c49a49;}'
            'QTableWidget{background:#eadbbd;gridline-color:#b9a27d;}QHeaderView::section{background:#c6ad80;padding:7px;}')
        layout=QVBoxLayout(self);top=FlowLayout();layout.addLayout(top)
        top.addWidget(QLabel('Персонаж:'));self.player=QLineEdit(getattr(parent,'settings',{}).get('progress_player','Мой персонаж'));top.addWidget(self.player)
        load=QPushButton('Загрузить профиль');top.addWidget(load);load.clicked.connect(self.load_profile)
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        from .i18n_widgets import QScrollArea
        calc=QWidget();body=QVBoxLayout(calc);body.setAlignment(Qt.AlignTop)
        calc_scroll=QScrollArea();calc_scroll.setWidgetResizable(True);calc_scroll.setWidget(calc);self.tabs.addTab(calc_scroll,'Прогресс / партия')
        selectors=QHBoxLayout();body.addLayout(selectors)
        self.kind=QComboBox();self.kind.addItem('Крафтер','CRAFT');self.kind.addItem('Ношение / бой','COMBAT');self.kind.addItem('Зачарование / торговля — без XP','OTHER');selectors.addWidget(self.kind)
        if row and row.get('activity','craft')!='craft':self.kind.setCurrentIndex(self.kind.findData('OTHER'))
        self.item=QComboBox();self.item.setEditable(True);self.item.setInsertPolicy(QComboBox.NoInsert);selectors.addWidget(self.item,1)
        unique={r.item_id:r for r in recipes if r.path in ('Прямой крафт','Рынок')}
        self.recipe_map=unique
        self.recipe_names={uid:r.name for uid,r in unique.items()};self.recipe_families={uid:r.family for uid,r in unique.items()}
        for uid,r in sorted(unique.items(),key=lambda x:(x[1].name,x[1].tier,x[1].enchantment)):self.item.addItem(f'{r.name} • T{r.tier}.{r.enchantment}',uid)
        if row:self.item.setCurrentIndex(max(0,self.item.findData(row['recipe'].item_id)))
        self.node_area=QWidget();self.node_grid=QGridLayout(self.node_area);body.addWidget(self.node_area)
        form=QFormLayout();body.addLayout(form)
        self.quantity=NumberBox();self.quantity.setRange(1,100000);self.quantity.setValue(1);form.addRow('Предметов / событий:',self.quantity)
        if row and row.get('activity')=='craft':self.quantity.setValue(row['recipe'].output_count)
        self.fame=LargeNumberBox();self.fame.setRange(0,1e9);self.fame.setDecimals(2);self.fame.setSpecialValueText('Введите фактический XP');form.addRow('XP за предмет / событие, с бонусами:',self.fame)
        self.focus_on=QCheckBox('Крафт с Focus');form.addRow(self.focus_on)
        self.focus_override=LargeNumberBox();self.focus_override.setRange(0,1e6);self.focus_override.setDecimals(2);self.focus_override.setSpecialValueText('Авто по профилю');form.addRow('Focus на предмет — ручная замена:',self.focus_override)
        self.target=NumberBox();self.target.setRange(0,100);self.target.setValue(100);form.addRow('Целевой уровень специализации:',self.target)
        self.preview=QLabel();self.preview.setWordWrap(True);body.addWidget(self.preview)
        self.focus_label=QLabel();self.focus_label.setStyleSheet('font-size:18px;font-weight:bold;');body.addWidget(self.focus_label)
        self.note=QLabel('Уровни и XP внутри текущего уровня вводятся из доски судьбы. Не заданные узлы считаются 0.\n'
            'Опыт за предмет вводится из игры уже с Premium и прочими бонусами. Журналы рабочих — другой вид опыта.\n'
            'Крафт повышает мастерство/специализацию крафтера; ношение меняется только по отдельно введённому боевому XP.\n'
            'Элитные уровни ношения 101–120 и очки обучения здесь не рассчитываются.');self.note.setWordWrap(True);body.addWidget(self.note)
        buttons=QHBoxLayout();body.addLayout(buttons)
        save=QPushButton('Сохранить текущие уровни');buttons.addWidget(save);save.clicked.connect(self.save_profile)
        plan=QPushButton('Записать план');buttons.addWidget(plan);plan.clicked.connect(lambda:self.record(False))
        fact=QPushButton('Записать выполненную партию');buttons.addWidget(fact);fact.clicked.connect(lambda:self.record(True))
        journal=QWidget();j=QVBoxLayout(journal);self.tabs.addTab(journal,'Журнал сделок и партий')
        self.journal_summary=QLabel();j.addWidget(self.journal_summary)
        self.journal=QTableWidget(0,9);self.journal.setHorizontalHeaderLabels(['Дата','Тип','Предмет','Кол-во','Затраты','Выручка','Прибыль','XP','Focus']);self.journal.setEditTriggers(QAbstractItemView.NoEditTriggers);j.addWidget(self.journal)
        actual=QFormLayout();j.addLayout(actual)
        self.cost=QLineEdit();self.revenue=QLineEdit();self.fees=QLineEdit();self.fees.setText('0')
        actual.addRow('Фактические затраты всей партии:',self.cost);actual.addRow('Фактическая выручка всей партии:',self.revenue);actual.addRow('Комиссии всей партии:',self.fees)
        deal=QPushButton('Записать завершённую сделку');j.addWidget(deal);deal.clicked.connect(self.record_deal)
        undo=QPushButton('Отменить последнюю запись');j.addWidget(undo);undo.clicked.connect(self.undo)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(200);self.timer.timeout.connect(self.recalculate)
        for field in [self.quantity,self.fame,self.focus_override,self.target]:field.valueChanged.connect(lambda:self.timer.start())
        self.focus_on.toggled.connect(lambda:self.timer.start());self.kind.currentIndexChanged.connect(self.build_nodes);self.item.currentIndexChanged.connect(self.build_nodes)
        self.load_profile()
        compact_combos(self);readable_table(self.journal);fit_window(self)
    def load_profile(self):
        self.states=self.store.states(self.player.text().strip() or 'Мой персонаж');self.build_nodes(preserve=False);self.fill_journal()
    def collect(self):
        states={k:dict(v) for k,v in self.states.items()}
        for key,(level,xp,bar,label) in self.cards.items():states[key]=dict(level=level.value(),xp=xp.value())
        return states
    def build_nodes(self,*args,preserve=True):
        if preserve:self.states=self.collect()
        while self.node_grid.count():
            item=self.node_grid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.cards={};uid=self.item.currentData()
        if not uid:return
        for i,key in enumerate(self.game.matching(uid,self.kind.currentData())):
            node=self.game.nodes[key];spec=node['@usetemplate'].endswith('_SPEC')
            box=QGroupBox('Специализация' if spec else 'Мастерство');v=QVBoxLayout(box)
            icon=QLabel();icon.setAlignment(Qt.AlignCenter)
            if hasattr(self.parent(),'icons'):icon.setPixmap(self.parent().icons.get(uid,1).pixmap(64,64))
            v.addWidget(icon)
            from .main import FAMILIES
            title=QLabel(self.recipe_names.get(uid,uid).split(' (')[0] if spec else FAMILIES.get(self.recipe_families.get(uid,''),'Общая ветка'));title.setAlignment(Qt.AlignCenter);v.addWidget(title)
            form=QFormLayout();v.addLayout(form);level=NumberBox();level.setRange(0,len(self.game.costs(key)));level.setValue(self.states.get(key,{}).get('level',0));form.addRow('Уровень:',level)
            xp=LargeNumberBox();xp.setRange(0,1e9);xp.setDecimals(2);xp.setValue(self.states.get(key,{}).get('xp',0));form.addRow('XP в уровне:',xp)
            bar=QProgressBar();bar.setRange(0,1000);v.addWidget(bar);label=QLabel();label.setWordWrap(True);v.addWidget(label)
            self.cards[key]=(level,xp,bar,label);self.node_grid.addWidget(box,i//2,i%2)
            level.valueChanged.connect(lambda:self.timer.start());xp.valueChanged.connect(lambda:self.timer.start())
        craft=self.kind.currentData()=='CRAFT';self.focus_on.setEnabled(craft);self.focus_override.setEnabled(craft)
        self.fame.setEnabled(self.kind.currentData()!='OTHER');self.target.setEnabled(self.kind.currentData()!='OTHER')
        self.recalculate()
    def recalculate(self):
        uid=self.item.currentData()
        if not uid:return
        try:
            states=self.collect();kind=self.kind.currentData()
            result=self.game.simulate(uid,self.quantity.value(),states,self.fame.value() if kind!='OTHER' else 0,self.focus_on.isChecked() and kind=='CRAFT',kind,
                self.focus_override.value() or None,recipe=self.row['recipe'] if self.row and self.row['recipe'].item_id==uid else self.recipe_map.get(uid));self.result=result
            lines=[]
            for key,(level,xp,bar,label) in self.cards.items():
                costs=self.game.costs(key);current=states[key];after=result['states'][key];limit=costs[current['level']] if current['level']<len(costs) else None
                bar.setValue(round(current['xp']/limit*1000) if limit else 1000);bar.setFormat(f'{current["level"]} / {len(costs)}')
                remaining=costs[after['level']]-after['xp'] if after['level']<len(costs) else 0
                label.setText(f'После партии: {after["level"]} (+{after["level"]-current["level"]})\nXP в уровне: {money(after["xp"])} • до следующего: {money(remaining)}')
                if key.endswith('_SPEC') or self.game.nodes[key]['@usetemplate'].endswith('_SPEC'):
                    need=max(0,sum(costs[current['level']:self.target.value()])-current['xp']) if self.target.value()>current['level'] else 0
                    lines.append('До цели: '+(str(__import__('math').ceil(need/self.fame.value()))+' предметов/событий' if self.fame.value() else 'введите XP за предмет/событие'))
            lines.insert(0,'Опыт и Focus не начисляются при зачаровании / торговле.' if kind=='OTHER' else 'XP партии: '+money(result['fame']) if self.fame.value() else 'XP партии неизвестен — введите опыт за предмет из игры.')
            if not self.cards and kind!='OTHER':lines.append('Для этого предмета ещё не подключены узлы прогрессии. Focus рассчитан по базовой стоимости; персональное снижение укажите вручную.')
            if self.row and uid==self.row['recipe'].item_id:
                x=self.row['focus'] if self.focus_on.isChecked() and kind=='CRAFT' else self.row['base']
                if x:lines.append('Прогноз прибыли партии: '+('≤ ' if self.row.get('pending_costs') else '')+money(x['profit']*self.quantity.value())+' серебра; по выбранным котировкам.')
            self.preview.setText('\n'.join(lines));f=result['focus'];self.focus_label.setText('Focus партии: '+(money(f) if f is not None else 'нет базовой стоимости в выгрузке'))
            self.focus_label.setStyleSheet('font-size:18px;font-weight:bold;color:'+('#b52a21' if f is not None and f>10000 else '#45351d')+';')
        except ValueError as exc:self.result=None;self.preview.setText(str(exc));self.focus_label.clear()
    def save_profile(self):
        self.recalculate()
        if self.result is None:return
        self.states=self.collect();self.store.save(self.player.text().strip() or 'Мой персонаж',self.states);self.preview.setText('Текущие уровни сохранены. Прогноз партии не применялся.')
    def record(self,fact):
        self.recalculate()
        if self.result is None:return
        if fact and self.kind.currentData()!='OTHER' and (not self.cards or not self.fame.value()):QMessageBox.warning(self,'Опыт','Для выполненной партии укажите фактический XP и подтверждённые узлы.');return
        payload=dict(type='Выполнено' if fact else 'План',kind=self.kind.currentData(),item=self.item.currentData(),quantity=self.quantity.value(),fame=self.result['fame'],focus=self.result['focus'])
        if fact:payload.update(states_before=self.collect(),states_after=self.result['states'])
        player=self.player.text().strip() or 'Мой персонаж'
        self.store.record(player,payload,self.result['states'] if fact else None)
        if fact:self.load_profile()
        self.fill_journal();self.preview.setText('Партия записана.'+(' Уровни обновлены по введённому XP.' if fact else ' Уровни не изменялись.'))
    def record_deal(self):
        from .scanner import number
        cost=number(self.cost.text());revenue=number(self.revenue.text());fees=number(self.fees.text())
        if any(v is None for v in (cost,revenue,fees)):QMessageBox.warning(self,'Сделка','Введите фактические суммы; 0 допустим.');return
        payload=dict(type='Сделка',item=self.item.currentData(),quantity=self.quantity.value(),cost=str(cost),revenue=str(revenue),profit=str(revenue-cost-fees),fees=str(fees))
        self.store.record(self.player.text().strip() or 'Мой персонаж',payload);self.fill_journal()
    def undo(self):
        try:self.store.undo_last(self.player.text().strip() or 'Мой персонаж');self.load_profile()
        except ValueError as exc:QMessageBox.warning(self,'Отмена',str(exc))
    def fill_journal(self):
        rows=self.store.entries(self.player.text().strip() or 'Мой персонаж');self.journal.setRowCount(len(rows))
        from datetime import datetime,timezone
        from decimal import Decimal
        today=datetime.now(timezone.utc).date();daily_focus=sum(p.get('focus') or 0 for _,stamp,p in rows if p['type']=='Выполнено' and datetime.fromisoformat(stamp).date()==today)
        profit=sum((Decimal(p['profit']) for _,_,p in rows if p['type']=='Сделка'),Decimal(0))
        self.journal_summary.setText('Прибыль завершённых сделок: '+money(profit)+' • Focus выполненных партий сегодня (UTC): '+money(daily_focus))
        self.journal_summary.setStyleSheet('color:'+('#b52a21' if daily_focus>10000 else '#45351d')+';font-weight:bold;')
        for n,(_,stamp,p) in enumerate(rows):
            values=[timestamp(stamp),p['type'],self.recipe_names.get(p['item'],p['item']),p['quantity'],money(p.get('cost')),money(p.get('revenue')),money(p.get('profit')),money(p.get('fame')),money(p.get('focus'))]
            for c,value in enumerate(values):
                cell=QTableWidgetItem(str(value));self.journal.setItem(n,c,cell)
                if c==8 and p.get('focus') is not None and p['focus']>10000:
                    from PySide6.QtGui import QColor
                    cell.setForeground(QColor('#b52a21'))
        self.journal.resizeColumnsToContents();self.journal.horizontalHeader().setStretchLastSection(True)
    def done(self,result):self.timer.stop();self.store.close();super().done(result)
    def closeEvent(self,event):self.timer.stop();self.store.close();event.accept()
