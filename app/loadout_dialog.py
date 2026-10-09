from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSpinBox,QCheckBox,QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QLineEdit,QApplication)
from .ui_layout import FlowLayout,explanation,compact_combos,fit_window
from .crafter_dialog import progression
from .progression import PlayerStore
from .loadout import SLOTS,family,variants,equipment,cheapest
from .item_names import item_name
from .models import CITIES
from .formatting import money,timestamp
from .filter_dialog import QUALITY_NAMES
from .market_snapshot import market_snapshot
from .number_fields import NumberBox

class LoadoutDialog(QDialog):
    def __init__(self,parent,root,build=None):
        super().__init__(parent);self.owner=parent;self.root=Path(root);self.game=progression(str(root));self.setWindowTitle('Мой билд — самые дешёвые варианты');self.resize(1250,780)
        self.loading=True;self.controls={};self.results={};prefs=parent.settings.get('loadout',{})
        layout=QVBoxLayout(self);top=FlowLayout();layout.addLayout(top)
        top.addWidget(QLabel('Город'));self.city=QComboBox();self.city.addItems(CITIES);self.city.setCurrentText(prefs.get('city',parent.craft.currentData() or 'Thetford'));top.addWidget(self.city)
        top.addWidget(QLabel('Персонаж'));self.player=QLineEdit(prefs.get('player',parent.settings.get('progress_player','Мой персонаж')));top.addWidget(self.player)
        self.profile=QCheckBox('Учитывать IP мастерства');self.profile.setChecked(prefs.get('profile',True));top.addWidget(self.profile)
        self.quality=QComboBox();self.quality.addItem('Любое качество',None)
        for q,name in enumerate(QUALITY_NAMES,1):self.quality.addItem(name,q)
        self.quality.setCurrentIndex(max(0,self.quality.findData(prefs.get('quality',1))));top.addWidget(self.quality)
        options=FlowLayout();layout.addLayout(options)
        options.addWidget(QLabel('Сила оружия и брони как T'));self.global_tier=NumberBox();self.global_tier.setRange(4,8);self.global_tier.setValue(7);options.addWidget(self.global_tier)
        apply=QPushButton('Применить к оружию и броне');options.addWidget(apply);apply.clicked.connect(self.apply_tier)
        self.old=QCheckBox('Разрешить старые цены');self.old.setChecked(prefs.get('old',False));options.addWidget(self.old)
        self.pristine=QCheckBox('Включить .4');self.pristine.setChecked(prefs.get('pristine',False));options.addWidget(self.pristine)
        self.table=QTableWidget(len(SLOTS),7);self.table.setHorizontalHeaderLabels(['Слот','Предмет','Тир цели','Чары цели','Дешёвый вариант','Цена','IP / проверка']);self.table.verticalHeader().hide();self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table,1)
        slots=prefs.get('slots',{})
        for n,(key,(label,types)) in enumerate(SLOTS.items()):
            self.table.setItem(n,0,QTableWidgetItem(label));box=QComboBox();box.setEditable(True);box.setInsertPolicy(QComboBox.NoInsert);box.addItem('Не использовать',None)
            bases={family(uid):uid for uid,item in self.game.items.items() if uid.startswith('T4_') and item.get('@slottype') in types and '@itempower' in item and item.get('@shopcategory') in ('weapons','offhands','armors','bags','capes','head','shoes')}
            for suffix,uid in sorted(bases.items(),key=lambda e:item_name(e[1],False)):box.addItem(item_name(uid,False).split(' (')[0],uid)
            box.completer().setCaseSensitivity(Qt.CaseInsensitive);box.completer().setFilterMode(Qt.MatchContains)
            saved=slots.get(key,{})
            imported=(build or {}).get('items',{}).get(key);uid=imported or saved.get('item')
            if uid:box.setCurrentIndex(max(0,box.findData('T4_'+family(uid))))
            tier=NumberBox();tier.setRange(4,8);tier.setValue(int(imported[1]) if imported else saved.get('tier',7 if key not in ('bag_id','cape_id') else 4))
            ench=NumberBox();ench.setRange(0,4);ench.setValue(int(imported.partition('@')[2] or 0) if imported else saved.get('ench',0))
            self.table.setCellWidget(n,1,box);self.table.setCellWidget(n,2,tier);self.table.setCellWidget(n,3,ench);self.controls[key]=(box,tier,ench)
            box.currentIndexChanged.connect(self.changed);tier.valueChanged.connect(self.changed);ench.valueChanged.connect(self.changed);self.table.setRowHeight(n,56)
        for n,width in enumerate([100,280,85,85,260,100]):self.table.setColumnWidth(n,width)
        actions=FlowLayout();layout.addLayout(actions)
        refresh=QPushButton('Подобрать по сохранённым ценам');refresh.clicked.connect(self.calculate);actions.addWidget(refresh)
        self.fetch=QPushButton('Обновить цены всех замен');self.fetch.clicked.connect(self.update_prices);actions.addWidget(self.fetch)
        copy=QPushButton('Скопировать список покупок');copy.clicked.connect(self.copy);actions.addWidget(copy)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        explanation(layout,'Для каждого слота выбирается тот же предмет с IP не ниже цели. Тиры 4–8, реальные зачарования из игровой таблицы. Сумка и плащ имеют отдельные цели. Цена — покупка с рынка за 1 шт.; минимум только среди известных котировок. Способности, ограничения ношения и бонусы пробуждения .4 проверь в игре. IP до ограничений активности, без перегрузки и элитных уровней.','Правила подбора')
        for control in (self.city,self.quality):control.currentIndexChanged.connect(self.changed)
        for control in (self.profile,self.old,self.pristine):control.toggled.connect(self.changed)
        self.player.editingFinished.connect(self.changed);self.loading=False;self.timer=QTimer(self);self.timer.setInterval(3000);self.timer.timeout.connect(self.calculate);self.timer.start();self.changed()
        compact_combos(self);fit_window(self)
    def targets(self):
        result={}
        for key,(box,tier,ench) in self.controls.items():
            if box.currentText()!=box.itemText(box.currentIndex()):raise ValueError('Выбери предмет из списка для слота «'+SLOTS[key][0]+'».')
            if box.currentData():result[key]=f'T{tier.value()}_'+family(box.currentData())+('@'+str(ench.value()) if ench.value() else '')
        weapon=equipment(self.game,result.get('weapon_id',''))
        if weapon and weapon.get('@twohanded')=='true':result.pop('offhand_id',None)
        return result
    def changed(self,*args):
        if self.loading:return
        self.owner.settings['loadout']=dict(city=self.city.currentText(),player=self.player.text(),profile=self.profile.isChecked(),quality=self.quality.currentData(),old=self.old.isChecked(),pristine=self.pristine.isChecked(),slots={k:dict(item=b.currentData(),tier=t.value(),ench=e.value()) for k,(b,t,e) in self.controls.items()})
        self.owner.persist_view();self.calculate()
    def apply_tier(self):
        self.loading=True
        for k,(box,tier,ench) in self.controls.items():
            if k not in ('bag_id','cape_id'):tier.setValue(self.global_tier.value());ench.setValue(0)
        self.loading=False;self.changed()
    def ids(self):return {uid for target in self.targets().values() for uid in variants(self.game,target)}
    def calculate(self):
        try:targets=self.targets()
        except ValueError as exc:self.summary.setText(str(exc));self.results={};return
        prices,_=market_snapshot(self.owner,self.root,self.ids());states={}
        if self.profile.isChecked():
            store=PlayerStore(self.root/'player.sqlite')
            try:states=store.states(self.player.text().strip() or 'Мой персонаж')
            finally:store.close()
        self.results={};total=0;missing=0;unchecked=0
        for n,key in enumerate(SLOTS):
            target=targets.get(key)
            if not target:
                values=['Не используется','—','Левая рука недоступна с двуручным оружием' if key=='offhand_id' and self.controls[key][0].currentData() else '—'];tip=''
            else:
                try:
                    result=cheapest(self.game,target,prices,self.city.currentText(),states,self.quality.currentData(),None if self.old.isChecked() else 30,self.pristine.isChecked());self.results[key]=result
                    unchecked+=len(result['missing']);best=result['best']
                    if best:
                        total+=best['price'];tier=int(best['item_id'][1]);ench=best['item_id'].partition('@')[2] or '0'
                        values=[item_name(best['item_id'],False).split(' (')[0]+f' • T{tier}.{ench} • '+QUALITY_NAMES[best['quality']-1],money(best['price']),f'{best["power"]:.1f} / цель {result["target"]:.1f}'+(' • старая цена' if best['age']>30 else '')]
                    else:missing+=1;values=['Нет подходящей цены','Неизвестно',f'Цель IP {result["target"]:.1f}']
                    tip='Известные варианты:\n'+'\n'.join(p['item_id']+' • '+QUALITY_NAMES[p['quality']-1]+' • '+money(p['price'])+' • IP '+str(round(p['power'],1))+' • '+timestamp(p['date']) for p in result['choices'][:25])+f'\nНет допустимой цены у {len(result["missing"])} вариантов/качеств.'
                except ValueError as exc:missing+=1;values=['Неверная цель','Неизвестно',str(exc)];tip=str(exc)
            for c,v in enumerate(values,4):cell=QTableWidgetItem(v);cell.setToolTip(tip);self.table.setItem(n,c,cell)
        self.summary.setText(('Стоимость известных частей: ≥ ' if missing else 'Стоимость комплекта: ')+money(total)+f' серебра. Без подходящей цены: {missing}; непроверенных замен/качеств: {unchecked}. '+('Подбор по известным ценам; абсолютный минимум не подтверждён.' if unchecked else 'Все допустимые замены имеют цены.'))
        if not targets:self.summary.setText('Выбери предметы своего билда и силу для каждого слота.')
        self.fetch.setEnabled(not(self.owner.worker and self.owner.worker.isRunning()))
    def update_prices(self):
        if self.owner.worker and self.owner.worker.isRunning():return
        try:ids=self.ids()
        except ValueError as exc:self.summary.setText(str(exc));return
        if ids:self.owner.start_fetch([r for r in self.owner.recipes if r.item_id in ids],True,ids)
        self.calculate()
    def copy(self):
        QApplication.clipboard().setText('\n'.join(item_name(r['best']['item_id'])+' • '+QUALITY_NAMES[r['best']['quality']-1]+' • '+money(r['best']['price']) for r in self.results.values() if r['best']))
    def done(self,result):self.timer.stop();super().done(result)
