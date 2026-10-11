import math
from html import escape
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF,QTimer
from PySide6.QtGui import QColor,QPen,QBrush,QPainter,QFont,QImage,QPixmap
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QComboBox,
    QGraphicsView,QGraphicsScene,QGraphicsObject,QSplitter,QWidget,QScrollArea,QGroupBox,
    QFormLayout,QSpinBox,QDoubleSpinBox,QProgressBar,QMessageBox)
from .crafter_dialog import progression,CrafterDialog
from .progression import PlayerStore,advance
from .destiny import build_branches,node_name,MODES,GROUP_COLORS
from .formatting import money
from .i18n import tr
from .responsive import GuiBatch,set_choices


class BoardNode(QGraphicsObject):
    def __init__(self,board,label,uid,active,level,experience,callback,radius=44,group=""):

        super().__init__();self.board=board;self.label=tr(label);self.uid=uid;self.active=active
        self.level=level;self.experience=tr(experience);self.callback=callback;self.radius=radius;self.group=group
        self.setCursor(Qt.PointingHandCursor);self.setToolTip(tr(label+'\n'+experience))
    def boundingRect(self):return QRectF(-94,-self.radius-8,188,self.radius*2+94)
    def paint(self,painter,option,widget=None):
        r=self.radius;painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(GROUP_COLORS.get(self.group,'#d7b76e' if self.active else '#64666a')),3))
        painter.setBrush(QColor('#4a4230' if self.active else '#292b2d'));painter.drawEllipse(QPointF(0,0),r,r)
        icon=self.board.icons.get(self.uid,1) if self.uid and self.board.icons else None
        if icon and not icon.isNull():
            pix=icon.pixmap(64,64)
            if not self.active:pix=QPixmap.fromImage(pix.toImage().convertToFormat(QImage.Format_Grayscale8))
            painter.drawPixmap(-32,-32,pix)
        else:
            painter.setPen(QColor('#dbbd80' if self.active else '#9c9b95'));painter.setFont(QFont('Segoe UI',18,QFont.Bold));painter.drawText(QRectF(-r,-r,r*2,r*2),Qt.AlignCenter,self.label[:1])
        if self.level:
            painter.setBrush(QColor('#242521'));painter.setPen(QColor('#bfb49a'));painter.drawRoundedRect(QRectF(-34,r-13,68,25),7,7)
            painter.setFont(QFont('Segoe UI',12,QFont.Bold));painter.drawText(QRectF(-34,r-13,68,25),Qt.AlignCenter,self.level)
        painter.setPen(QColor(GROUP_COLORS.get(self.group,'#e4d4b4' if self.active else '#afafa9')));painter.setFont(QFont('Segoe UI',13,QFont.Bold))
        painter.drawText(QRectF(-94,r+18,188,40),Qt.AlignHCenter|Qt.TextWordWrap,self.label)
        painter.setFont(QFont('Segoe UI',10));painter.setPen(QColor('#aea48e'));painter.drawText(QRectF(-94,r+61,188,22),Qt.AlignCenter,self.experience)
    def mousePressEvent(self,event):self.pressed=event.scenePos();event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and (event.scenePos()-self.pressed).manhattanLength()<8:self.callback()
        event.accept()


def scroll_number_parent(field,event):
    parent=field.parentWidget()
    while parent is not None:
        if isinstance(parent,QScrollArea):
            parent.wheelEvent(event)
            return
        parent=parent.parentWidget()
    event.ignore()


class WheelSafeSpinBox(QSpinBox):
    def __init__(self,*args):
        super().__init__(*args)
        from .number_fields import style
        style(self)
    def wheelEvent(self,event):scroll_number_parent(self,event)


class WheelSafeDoubleSpinBox(QDoubleSpinBox):
    def __init__(self,*args):
        super().__init__(*args)
        from .number_fields import style
        style(self)
    def wheelEvent(self,event):scroll_number_parent(self,event)


class BoardView(QGraphicsView):
    def wheelEvent(self,event):event.accept()
    def mousePressEvent(self,event):
        if event.button()==Qt.RightButton:self.board.back();event.accept()
        else:super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.RightButton:event.accept()
        else:super().mouseReleaseEvent(event)
    def contextMenuEvent(self,event):event.accept()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'board'):QTimer.singleShot(0,self.board.fit)


class DestinyDialog(QDialog):
    def __init__(self,parent,root,recipes,row=None):
        super().__init__(parent);self.setWindowTitle('Доска развития — профиль');self.resize(1440,900)
        from .ui_layout import fit_window,compact_combos
        self.root=Path(root);self.recipes=recipes;self.market_row=row;self.game=progression(str(root));self.store=PlayerStore(self.root/'player.sqlite')
        self.branches=build_branches(self.game,recipes);self.icons=getattr(parent,'icons',None);self.states={};self.cards={};self.category=None;self.section=None;self.branch=None;self.loading=False;self.board_page=0
        self.draw_batch=GuiBatch(self)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(180);self.search_timer.timeout.connect(self.search_changed)
        self.setStyleSheet('QDialog,QWidget{background:#242722;color:#e5d6b8;font-family:"Segoe UI";font-size:13px;}'
            'QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox{background:#34382f;border:1px solid #746c51;border-radius:5px;padding:5px;}'
            'QSpinBox,QDoubleSpinBox{padding:5px 30px 5px 5px;min-height:24px;}'
            'QSpinBox::up-button,QDoubleSpinBox::up-button{subcontrol-origin:border;subcontrol-position:top right;width:26px;border-left:1px solid #746c51;}'
            'QSpinBox::down-button,QDoubleSpinBox::down-button{subcontrol-origin:border;subcontrol-position:bottom right;width:26px;border-left:1px solid #746c51;}'
            'QPushButton{background:#494735;border:1px solid #8f7b51;border-radius:6px;padding:8px 12px;}'
            'QPushButton:hover{background:#63593b;}QGroupBox{border:1px solid #706b55;border-radius:9px;margin-top:12px;padding:12px;}'
            'QGroupBox::title{subcontrol-origin:margin;left:12px;}QProgressBar{background:#34382f;border:1px solid #746c51;border-radius:4px;text-align:center;}'
            'QProgressBar::chunk{background:#9b854f;}')
        layout=QVBoxLayout(self);top=QHBoxLayout();layout.addLayout(top)
        title=QLabel('ДОСКА РАЗВИТИЯ');title.setStyleSheet('font-size:22px;font-weight:bold;color:#d7b76e;');top.addWidget(title);top.addStretch()
        top.addWidget(QLabel('Персонаж:'));self.player=QLineEdit(parent.settings.get('progress_player','Мой персонаж'));self.player.setMaximumWidth(220);top.addWidget(self.player)
        load=QPushButton('Загрузить');top.addWidget(load);load.clicked.connect(self.load_profile)
        calc=QPushButton('Калькулятор / журнал');top.addWidget(calc);calc.clicked.connect(self.open_calculator)
        credits=QPushButton('Свободная слава');top.addWidget(credits);credits.clicked.connect(self.open_fame)
        tools=QHBoxLayout();layout.addLayout(tools)
        self.mode=QComboBox()
        for key,label in MODES.items():self.mode.addItem(label,key)
        tools.addWidget(self.mode);self.search=QLineEdit();self.search.setPlaceholderText('Найти ветку: мечи, ткань, алхимия…');tools.addWidget(self.search,1)
        back=QPushButton('← Назад');tools.addWidget(back);back.clicked.connect(self.back)
        self.previous=QPushButton('◀');tools.addWidget(self.previous);self.previous.clicked.connect(lambda:self.turn_page(-1))
        self.page_label=QLabel();tools.addWidget(self.page_label)
        self.next=QPushButton('▶');tools.addWidget(self.next);self.next.clicked.connect(lambda:self.turn_page(1))
        self.breadcrumb=QLabel();self.breadcrumb.setTextFormat(Qt.RichText);self.breadcrumb.linkActivated.connect(self.navigate);layout.addWidget(self.breadcrumb)
        legend=QLabel('<span style="color:#cf7770">● Воин</span>　<span style="color:#7dbb80">● Охотник</span>　<span style="color:#7ca6dc">● Чародей</span>');layout.addWidget(legend)
        split=QSplitter();layout.addWidget(split,1)
        self.scene=QGraphicsScene(self);self.view=BoardView(self.scene);self.view.setRenderHint(QPainter.Antialiasing);self.view.board=self;self.view.setDragMode(QGraphicsView.NoDrag);self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setBackgroundBrush(QColor('#252a25'));split.addWidget(self.view)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setMinimumWidth(390);self.panel=QWidget();self.panel_layout=QVBoxLayout(self.panel);self.scroll.setWidget(self.panel);split.addWidget(self.scroll);split.setSizes([950,440])
        self.feedback=QLabel('Уровни сохраняются локально. Нулевые значки — ЧБ. ЛКМ — открыть прокачку, ПКМ — назад. Колесо прокручивает список и не меняет числа.');self.feedback.setWordWrap(True);layout.addWidget(self.feedback)
        note=QLabel('Вводится текущий уровень и XP внутри уровня. Требование до следующего берётся из игровой таблицы для конкретного узла. Это лёгкая версия доски: уровни 0–100, без LP и элитных уровней.');note.setWordWrap(True);layout.addWidget(note)
        self.save_timer=QTimer(self);self.save_timer.setSingleShot(True);self.save_timer.setInterval(400);self.save_timer.timeout.connect(self.save_cards)
        self.mode.currentIndexChanged.connect(self.reset);self.search.textChanged.connect(lambda:self.search_timer.start())
        if self.icons:self.icons.ready.connect(self.icons_ready)
        self.load_profile()
        if row:
            uid=row['recipe'].item_id
            keys=self.game.matching(uid,'CRAFT' if row.get('activity')=='craft' else 'COMBAT')
            selected=next((b for b in self.branches if any(k in b.nodes for k in keys)),None)
            if selected:self.mode.setCurrentIndex(self.mode.findData(selected.mode));self.select_branch(selected)
        compact_combos(self);fit_window(self)
    def load_profile(self):
        if self.save_cards() is False:return
        self.clear_panel()
        self.save_timer.stop();self.active_player=self.player.text().strip() or 'Мой персонаж';self.player.setText(self.active_player)
        self.states=self.store.states(self.active_player);self.parent().settings['progress_player']=self.active_player;self.parent().persist_view();self.reset()
    def open_fame(self):
        if self.save_cards() is False:return
        from .fame_dialog import FameDialog
        FameDialog(self,self.root,self.recipes,self.branch).exec()
        self.clear_panel()
        self.states=self.store.states(self.active_player)
        if self.branch:self.select_branch(self.branch)
        else:self.draw()
    def reset(self,*args):
        if self.save_cards() is False:return
        self.category=None;self.section=None;self.branch=None;self.board_page=0;self.clear_panel();self.draw()
    def search_changed(self):
        if self.save_cards() is False:return
        self.category=None;self.section=None;self.branch=None;self.board_page=0;self.clear_panel();self.draw()
    def back(self):
        if self.save_cards() is False:return
        if self.branch:self.branch=None;self.clear_panel()
        elif self.section:self.section=None
        elif self.category:self.category=None
        self.board_page=0
        self.draw()
    def clear_panel(self):
        self.loading=True
        while self.panel_layout.count():
            widget=self.panel_layout.takeAt(0).widget()
            if widget:widget.setParent(None);widget.deleteLater()
        self.cards={};self.loading=False
        self.panel_layout.addWidget(QLabel('Нажми на категорию, затем на ветку.\nСправа появятся уровень ветки и специализации.'))
        self.panel_layout.addStretch()
    def active(self,keys):return any(self.states.get(k,{}).get('level',0)>0 for k in keys)
    def draw(self,fit=True):
        self.draw_batch.cancel();self.scene.clear();self.scene.setSceneRect(-690,-690,1380,1380)
        crumbs=[('root',MODES[self.mode.currentData()])]
        if self.category:crumbs.append(('category',self.category))
        if self.section:crumbs.append(('section',self.section))
        if self.branch:crumbs.append(('branch',self.branch.label))
        self.breadcrumb.setText(' › '.join(f'<a style="color:#d7b76e" href="{key}">{escape(tr(label))}</a>' for key,label in crumbs))
        branches=[b for b in self.branches if b.mode==self.mode.currentData()]
        query=self.search.text().strip().casefold()
        if query:branches=[b for b in branches if query in b.label.casefold() or any(query in node_name(self.game,k).casefold() for k in b.nodes)]
        if self.branch:
            b=self.branch;center_keys=[b.root] if b.root else b.nodes
            leaves=[k for k in b.nodes if k!=b.root]
            center=(self.root_label(b),b.icon,center_keys,lambda:self.focus_card(b.root),b.root,b.group)
            options=[(node_name(self.game,k),self.game.nodes[k].get('@itemforsprite',''),[k],lambda k=k:self.focus_card(k),k,b.group) for k in leaves]
        elif self.category=='Броня' and not self.section and not query:
            visible=[b for b in branches if b.category==self.category]
            sections=sorted({b.section for b in visible})
            center=(self.category,'',[k for b in visible for k in b.nodes],self.back,None)
            options=[(section,next(b.icon for b in visible if b.section==section),[k for b in visible if b.section==section for k in b.nodes],lambda section=section:self.select_section(section),None,
                {'Тканевая':'MAGE','Кожаная':'HUNTER','Латная':'WARRIOR'}.get(section,'')) for section in sections]
        elif self.category or query:
            visible=[b for b in branches if not self.category or b.category==self.category]
            if self.section:visible=[b for b in visible if b.section==self.section]
            center=(self.section or self.category or 'Поиск','',[k for b in visible for k in b.nodes],self.back,None)
            options=[(b.label,b.icon,b.nodes,lambda b=b:self.select_branch(b),b.root,b.group) for b in visible]
        else:
            categories=sorted({b.category for b in branches});center=(self.active_player,'',[k for b in branches for k in b.nodes],lambda:None,None)
            options=[(cat,next(b.icon for b in branches if b.category==cat),[k for b in branches if b.category==cat for k in b.nodes],lambda cat=cat:self.select_category(cat),None) for cat in categories]
        def add(option,x,y,radius=44):
            label,uid,keys,action,key=option[:5];group=option[5] if len(option)>5 else "";state=self.states.get(key,dict(level=0,xp=0)) if key else None
            level=f'{state["level"]}/100' if state else ''
            costs=self.game.costs(key) if key else [];cap=costs[state['level']] if state and state['level']<len(costs) else None
            xp=f'XP {money(state["xp"])} / {money(cap)}' if state and cap else 'Максимум' if state else f'{sum(self.states.get(k,{}).get("level",0)>0 for k in keys)}/{len(keys)} развито'
            node=BoardNode(self,label,uid,self.active(keys),level,xp,action,radius,group);node.setPos(x,y);self.scene.addItem(node);return node
        pages=max(1,(len(options)+11)//12);self.board_page=min(self.board_page,pages-1)
        self.previous.setEnabled(self.board_page>0);self.next.setEnabled(self.board_page+1<pages)
        self.page_label.setText(f'{self.board_page+1} / {pages}' if pages>1 else '')
        self.previous.setVisible(pages>1);self.next.setVisible(pages>1)
        options=options[self.board_page*12:(self.board_page+1)*12]
        add(center,0,0,58)
        groups=[o[5] if len(o)>5 else '' for o in options]
        gaps=[2.0 if groups[n] and groups[n]!=groups[(n+1)%len(groups)] else 1.0 for n in range(len(groups))]
        def populate():
            angle=-math.pi/2
            for n,option in enumerate(options):
                if n:angle+=2*math.pi*gaps[n-1]/sum(gaps)
                radius=520 if len(options)>9 else 340
                x,y=radius*math.cos(angle),radius*math.sin(angle);active=self.active(option[2])
                color=QColor(GROUP_COLORS.get(groups[n],'#bfa263' if active else '#555b54'))
                if groups[n] and not active:color.setAlpha(120)
                pen=QPen(color,3 if active else 2)
                self.scene.addLine(0,0,x,y,pen).setZValue(-1);add(option,x,y)
                yield
            if fit:self.fit()
        self.draw_batch.start(populate())
    def turn_page(self,delta):
        self.board_page=max(0,self.board_page+delta);self.draw()
    def navigate(self,level):
        if self.save_cards() is False:return
        if level=='branch':return
        self.branch=None
        if level in ('root','category'):self.section=None
        if level=='root':self.category=None
        self.board_page=0;self.clear_panel();self.draw()
    def fit(self):self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-40,-40,40,40),Qt.KeepAspectRatio)
    def select_category(self,category):
        if self.save_cards() is False:return
        self.category=category;self.section=None;self.branch=None;self.board_page=0;self.clear_panel();self.draw()
    def select_section(self,section):
        if self.save_cards() is False:return
        self.section=section;self.branch=None;self.board_page=0;self.clear_panel();self.draw()
    def select_branch(self,branch):
        if self.save_cards() is False:return
        self.branch=branch;self.category=branch.category;self.section=branch.section or None;self.board_page=0;self.clear_panel();self.loading=True
        while self.panel_layout.count():
            widget=self.panel_layout.takeAt(0).widget()
            if widget:widget.setParent(None);widget.deleteLater()
        choice=QComboBox();set_choices(choice,[(node_name(self.game,key),key) for key in branch.nodes]);self.panel_layout.addWidget(choice)
        choice.setCurrentIndex(0);choice.currentIndexChanged.connect(lambda:self.focus_card(choice.currentData()))
        self.card_choice=choice
        key=branch.root or branch.nodes[0];self.add_card(key,key==branch.root)
        self.panel_layout.addStretch();self.loading=False;self.draw()
    def root_label(self,branch):
        role={'CRAFT':'Создание','COMBAT':'Ношение','REFINE':'Переработка','GATHER':'Сбор','FARM':'Выращивание'}[branch.mode]
        return role+': '+branch.label
    def add_card(self,key,mastery):
        costs=self.game.costs(key);state=self.states.get(key,dict(level=0,xp=0));box=QGroupBox(self.root_label(self.branch) if mastery else node_name(self.game,key));v=QVBoxLayout(box)
        top=QHBoxLayout();v.addLayout(top);icon=QLabel();uid=self.game.nodes[key].get('@itemforsprite','');icon.setProperty('uid',uid)
        if self.icons:icon.setPixmap(self.icons.get(uid,1).pixmap(48,48))
        top.addWidget(icon);form=QFormLayout();top.addLayout(form,1)
        level=WheelSafeSpinBox();level.setRange(0,len(costs));level.setValue(state['level']);form.addRow('Уровень:',level)
        xp=WheelSafeDoubleSpinBox();xp.setDecimals(2);xp.setRange(0,1e12);xp.setValue(state['xp']);form.addRow('XP в уровне:',xp)
        bar=QProgressBar();bar.setRange(0,1000);v.addWidget(bar);required=QLabel();v.addWidget(required)
        extra=QHBoxLayout();v.addLayout(extra);add=WheelSafeDoubleSpinBox();add.setRange(0,1e12);add.setDecimals(2);add.setPrefix('+ XP ');extra.addWidget(add)
        apply=QPushButton('Применить');extra.addWidget(apply);apply.clicked.connect(lambda:self.add_xp(key,add))
        self.cards[key]=(level,xp,bar,required,box)
        last=self.panel_layout.itemAt(self.panel_layout.count()-1)
        if last and last.spacerItem():self.panel_layout.insertWidget(self.panel_layout.count()-1,box)
        else:self.panel_layout.addWidget(box)
        level.valueChanged.connect(lambda:self.card_changed(key,True));xp.valueChanged.connect(lambda:self.card_changed(key))
        self.update_card(key)
    def update_card(self,key):
        level,xp,bar,label,box=self.cards[key];costs=self.game.costs(key);cap=costs[level.value()] if level.value()<len(costs) else None
        xp.setEnabled(cap is not None);bar.setValue(round(xp.value()/cap*1000) if cap else 1000)
        bar.setFormat(f'{money(xp.value())} / {money(cap)} XP' if cap else 'Максимальный уровень')
        label.setText('До следующего: '+money(max(0,cap-xp.value()))+' XP' if cap else 'Достигнут уровень 100')
    def card_changed(self,key,level_change=False):
        if self.loading:return
        if level_change:
            level,xp,*_=self.cards[key];costs=self.game.costs(key);cap=costs[level.value()] if level.value()<len(costs) else 0
            xp.blockSignals(True);xp.setValue(min(xp.value(),max(0,cap-.01)));xp.blockSignals(False)
        self.update_card(key);self.save_timer.start()
    def save_cards(self):
        if self.loading or not self.cards:return
        self.save_timer.stop();new={k:dict(v) for k,v in self.states.items()}
        try:
            for key,(level,xp,*_) in self.cards.items():
                advance(level.value(),xp.value(),0,self.game.costs(key));new[key]=dict(level=level.value(),xp=xp.value())
        except ValueError as exc:self.feedback.setText(str(exc)+' — текущие изменения ещё не сохранены.');return False
        self.states=new;self.store.save(self.active_player,new);self.feedback.setText('Сохранено для '+self.active_player+'. XP до следующего уровня взят из игровой таблицы.');self.draw(fit=False);return True
    def add_xp(self,key,field):
        level,xp,*_=self.cards[key]
        try:l,x=advance(level.value(),xp.value(),field.value(),self.game.costs(key))
        except ValueError as exc:QMessageBox.warning(self,'Опыт',str(exc));return
        level.blockSignals(True);xp.blockSignals(True);level.setValue(l);xp.setValue(x);level.blockSignals(False);xp.blockSignals(False);field.setValue(0)
        self.update_card(key);self.save_cards()
    def focus_card(self,key):
        if key and key not in self.cards:
            if self.save_cards() is False:return
            self.loading=True
            for old,values in list(self.cards.items()):
                if old!=self.branch.root:
                    box=values[4];self.panel_layout.removeWidget(box);box.deleteLater();del self.cards[old]
            self.add_card(key,key==self.branch.root);self.loading=False
            index=self.card_choice.findData(key);self.card_choice.blockSignals(True);self.card_choice.setCurrentIndex(index);self.card_choice.blockSignals(False)
        if key in self.cards:self.scroll.ensureWidgetVisible(self.cards[key][4]);self.cards[key][0].setFocus()
    def icons_ready(self,*args):
        self.scene.update()
        for label in self.panel.findChildren(QLabel):
            if uid:=label.property('uid'):label.setPixmap(self.icons.get(uid,1).pixmap(48,48))
    def open_calculator(self):
        if self.save_cards() is False:return
        dialog=CrafterDialog(self.parent(),self.root,self.recipes,self.market_row);dialog.player.setText(self.active_player);dialog.load_profile();dialog.exec()
        branch=self.branch;self.clear_panel();self.states=self.store.states(self.active_player)
        if branch:self.select_branch(branch)
        else:self.draw()
    def done(self,result):
        if self.save_cards() is False:return
        self.draw_batch.cancel();self.search_timer.stop()
        self.save_timer.stop();self.store.close();super().done(result)
