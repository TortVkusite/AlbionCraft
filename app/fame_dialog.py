import json,subprocess,sys,os,tempfile
from pathlib import Path
from PySide6.QtCore import QThread,Signal
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QLineEdit,QPushButton,QDoubleSpinBox,QCheckBox,QTableWidget,QTableWidgetItem,QAbstractItemView,QMessageBox)
from .ui_layout import FlowLayout,explanation,readable_table,compact_combos,fit_window
from .crafter_dialog import progression
from .destiny import build_branches,node_name
from .progression import PlayerStore
from .fame_optimizer import prepare,plan,FAME_PER_CREDIT
from .loadout import equipment,family
from .item_names import item_name
from .formatting import money
from .number_fields import LargeNumberBox

class FameWorker(QThread):
    ready=Signal(object);failed=Signal(str)
    def __init__(self,groups,budget):super().__init__();self.groups=groups;self.budget=budget
    def run(self):
        try:
            flags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
            from .paths import resource_root
            with tempfile.TemporaryDirectory(prefix='albioncraft-fame-') as folder:
                request=Path(folder)/'request.json';response=Path(folder)/'response.json'
                request.write_text(json.dumps(dict(groups=self.groups,budget=self.budget)),encoding='utf-8')
                command=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-m','app.entry']
                completed=subprocess.run(command+['--fame-worker',str(request),str(response)],cwd=str(resource_root()),creationflags=flags,timeout=35,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                result=json.loads(response.read_text(encoding='utf-8')) if response.is_file() else {}
                if completed.returncode or 'error' in result:raise ValueError('Решатель не завершился. Профиль не изменён. '+result.get('error',''))
                self.ready.emit(result)
        except Exception as exc:self.failed.emit(str(exc))

class FameDialog(QDialog):
    def __init__(self,parent,root,recipes,branch=None):
        super().__init__(parent);self.root=Path(root);self.owner=parent;self.game=progression(str(root));self.setWindowTitle('Свободная слава — уровень и распределение');self.resize(1120,730);self.worker=None;self.result=None;self.inputs=None
        owner=parent
        while not hasattr(owner,'settings') and owner.parent():owner=owner.parent()
        self.settings_owner=owner;prefs=owner.settings.get('fame_planner',{})
        self.branches=[b for b in build_branches(self.game,recipes) if b.mode=='COMBAT' and any(self.game.nodes[k]['@usetemplate'] in ('COMBAT_SPEC','COMBAT_OFF_SPEC') for k in b.nodes)]
        layout=QVBoxLayout(self);top=QHBoxLayout();layout.addLayout(top)
        top.addWidget(QLabel('Персонаж'));self.player=QLineEdit(prefs.get('player',owner.settings.get('progress_player','Мой персонаж')));top.addWidget(self.player)
        top.addWidget(QLabel('Свободная слава'));self.budget=LargeNumberBox();self.budget.setDecimals(0);self.budget.setRange(0,1e12);self.budget.setSingleStep(100000);self.budget.setValue(prefs.get('budget',1000000));top.addWidget(self.budget)
        selectors=FlowLayout();layout.addLayout(selectors)
        self.branch=QComboBox()
        for b in self.branches:self.branch.addItem(b.label+' • '+b.category,b.key)
        self.branch.setCurrentIndex(max(0,self.branch.findData(branch.key if branch and branch.mode=='COMBAT' else prefs.get('branch','COMBAT_SWORDS'))));selectors.addWidget(self.branch)
        self.item=QComboBox();selectors.addWidget(self.item,1);self.tier=QComboBox()
        for t in range(4,9):self.tier.addItem('IP на T'+str(t),t)
        self.tier.setCurrentIndex(max(0,self.tier.findData(prefs.get('tier',4))));selectors.addWidget(self.tier)
        self.mode=QComboBox()
        for label,key in [('Уровень одного предмета','level'),('Максимум IP выбранного предмета','item'),('Максимум среднего IP ветки','branch')]:self.mode.addItem(label,key)
        self.mode.setCurrentIndex(max(0,self.mode.findData(prefs.get('mode','item'))));layout.addWidget(self.mode)
        self.mastery=QCheckBox('Разрешить вкладывать в общее мастерство ветки');self.mastery.setChecked(prefs.get('mastery',False));layout.addWidget(self.mastery)
        self.profile_note=QLabel();self.profile_note.setWordWrap(True);layout.addWidget(self.profile_note)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.calculate_button=QPushButton('Рассчитать');self.calculate_button.clicked.connect(self.calculate);actions.addWidget(self.calculate_button)
        self.record_button=QPushButton('Распределение выполнено — записать в профиль');self.record_button.setEnabled(False);self.record_button.clicked.connect(self.record);actions.addWidget(self.record_button)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Узел','Сейчас','После','Вложить свободки','Получить XP','Прирост','XP внутри уровня']);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.verticalHeader().hide();self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table,1)
        self.summary=QLabel('Расчёт использует сохранённый профиль.');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        note=QLabel('Свободная слава тратится отдельно на каждый узел: 1 очко = 2 XP оружия, 4 XP брони, 8 XP шлема/обуви, 40 XP левой руки. «Уровень» направляет весь доступный запас в одну специализацию. «Максимум IP предмета» учитывает общие бонусы других специализаций. Для ветки максимизируется средний прирост IP всех её предметов с равными весами. Уровни 0–100, без LP, элитных уровней и списания существующих уровней. Узлы должны быть открыты в игре; неизвестные уровни профиля считаются нулевыми. Подбор IP оставляет очки, которых не хватает на следующий целый уровень. Запись в профиль выполняется только кнопкой после фактической прокачки.');note.setWordWrap(True);layout.addWidget(note)
        self.branch.currentIndexChanged.connect(self.populate)
        for control in (self.item,self.mode,self.tier):control.currentIndexChanged.connect(self.invalidate)
        self.mastery.toggled.connect(self.invalidate);self.budget.valueChanged.connect(self.invalidate);self.player.textChanged.connect(self.invalidate)
        note_text=note.text();layout.removeWidget(note);note.hide();note.deleteLater();explanation(layout,note_text,'Как распределяется слава')
        self.populate();readable_table(self.table);self.table.setColumnWidth(0,280)
        compact_combos(self);fit_window(self)
    def current_branch(self):return next(b for b in self.branches if b.key==self.branch.currentData())
    def populate(self,*args):
        self.item.blockSignals(True);self.item.clear()
        for k in self.current_branch().nodes:
            n=self.game.nodes[k]
            if n['@usetemplate'] in ('COMBAT_SPEC','COMBAT_OFF_SPEC'):
                uid='T4_'+family(n['@itemforsprite']);item=equipment(self.game,uid)
                if item and item.get('@slottype') in FAME_PER_CREDIT:self.item.addItem(node_name(self.game,k),uid)
        saved=self.settings_owner.settings.get('fame_planner',{}).get('item')
        if saved:self.item.setCurrentIndex(max(0,self.item.findData(saved)))
        self.item.blockSignals(False);self.invalidate()
    def invalidate(self,*args):
        self.result=None;self.record_button.setEnabled(False)
        if hasattr(self,'summary'):self.summary.setText('Параметры изменились — нужен расчёт.')
        self.settings_owner.settings['fame_planner']=dict(player=self.player.text(),budget=int(self.budget.value()),mode=self.mode.currentData(),branch=self.branch.currentData(),item=self.item.currentData(),tier=self.tier.currentData(),mastery=self.mastery.isChecked());self.settings_owner.persist_view()
    def calculate(self):
        if self.worker and self.worker.isRunning():return
        try:
            player=self.player.text().strip() or 'Мой персонаж';store=PlayerStore(self.root/'player.sqlite')
            try:states=store.states(player)
            finally:store.close()
            uid=f'T{self.tier.currentData()}_'+family(self.item.currentData());budget=int(self.budget.value());mode=self.mode.currentData();branch=self.current_branch()
            groups=prepare(self.game,branch,states,uid,budget,mode,self.mastery.isChecked())
            for g in groups:g['costs']=self.game.costs(g['node'])
            self.inputs=dict(player=player,states=states,uid=uid,budget=budget,mode=mode,branch=branch)
            self.settings_owner.settings['fame_planner']=dict(player=player,budget=budget,mode=mode,branch=branch.key,item=self.item.currentData(),tier=self.tier.currentData(),mastery=self.mastery.isChecked());self.settings_owner.persist_view()
            self.profile_note.setText('Профиль: '+player+' • предмет: '+item_name(uid,False).split(' (')[0]+f' • 1 очко = {FAME_PER_CREDIT[equipment(self.game,uid)["@slottype"]]} XP этого слота. Не задано узлов ветки: '+str(sum(k not in states for k in branch.nodes)))
            self.record_button.setEnabled(False)
            if mode=='level':self.received(plan(self.game,branch,states,uid,budget,mode));return
            self.calculate_button.setEnabled(False)
            for control in (self.branch,self.item,self.tier,self.player,self.budget,self.mode,self.mastery):control.setEnabled(False)
            self.summary.setText('Подбираю целые уровни под запас свободной славы…');self.worker=FameWorker(groups,budget);self.worker.ready.connect(self.received);self.worker.failed.connect(self.failed);self.worker.finished.connect(self.worker_finished);self.worker.start()
        except Exception as exc:self.failed(str(exc))
    def worker_finished(self):
        self.calculate_button.setEnabled(True)
        for control in (self.branch,self.item,self.tier,self.player,self.budget,self.mode,self.mastery):control.setEnabled(True)
    def failed(self,message):self.summary.setText(message);self.result=None;self.record_button.setEnabled(False)
    def received(self,result):
        self.result=result;self.table.setRowCount(len(result['lines']))
        branch_mode=self.inputs['mode']=='branch';count=sum(self.game.nodes[k]['@usetemplate'] in ('COMBAT_SPEC','COMBAT_OFF_SPEC') for k in self.inputs['branch'].nodes) if branch_mode else 1
        for n,line in enumerate(result['lines']):
            gain=line['gain']/count;unit='ур.' if self.inputs['mode']=='level' else 'IP'
            values=[node_name(self.game,line['node']),line['before']['level'],line['level'],money(line['cost']),money(line['cost']*line['ratio']),f'+{gain:.2f} {unit}',f'{line["xp"]:,.1f}'.replace(',',' ')]
            for c,value in enumerate(values):self.table.setItem(n,c,QTableWidgetItem(str(value)))
            self.table.setRowHeight(n,38)
        self.table.setColumnWidth(0,300)
        for c in range(1,7):self.table.setColumnWidth(c,110 if c not in (3,4) else 145)
        gain=result['gain']/count;unit='уровней' if self.inputs['mode']=='level' else 'IP в среднем по ветке' if branch_mode else 'IP выбранного предмета'
        self.summary.setText(('Максимум доказан' if result['optimal'] else 'Лучшее найденное распределение; максимум не доказан')+f': +{gain:.2f} {unit}. Вложить: {money(result["spent"])} / {money(self.inputs["budget"])}; остаток: {money(result["left"])}. '+('Подбор не применён к профилю.' if result['spent'] else 'На следующий уровень не хватает очков либо достигнут предел.'))
        self.record_button.setEnabled(bool(result['spent']))
    def record(self):
        if not self.result or not self.result['spent']:return
        store=PlayerStore(self.root/'player.sqlite')
        try:
            before=self.inputs['states']
            if store.states(self.inputs['player'])!=before:raise ValueError('Профиль изменился. Пересчитай распределение перед записью.')
            after={k:dict(v) for k,v in before.items()}
            for line in self.result['lines']:after[line['node']]=dict(level=line['level'],xp=line['xp'])
            store.record(self.inputs['player'],dict(type='Свободная слава',item=self.inputs['uid'],quantity=1,fame=sum(l['cost']*l['ratio'] for l in self.result['lines']),credits=self.result['spent'],states_before=before,states_after=after),after)
            self.summary.setText('Выполненное распределение записано. Его можно отменить в журнале.');self.result=None;self.record_button.setEnabled(False)
        except ValueError as exc:QMessageBox.warning(self,'Свободная слава',str(exc))
        finally:store.close()
    def reject(self):
        if self.worker and self.worker.isRunning():return
        super().reject()
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():event.ignore()
        else:super().closeEvent(event)
