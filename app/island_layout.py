"""An original schematic; plot coordinates are a planning aid, not a game map."""
from decimal import Decimal as D
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QPainter,QColor,QPolygonF,QPen
from .i18n_widgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QPushButton,QWidget,QFormLayout
from .number_fields import NumberBox,LargeNumberBox
from .models import CITIES,quote
from .item_names import item_name
from .market_snapshot import market_snapshot
from .background import ProcessWorker
from .formatting import money
from .preferences import save_settings
from .i18n import tr

KINDS={'empty':'Пусто','crops':'Овощи','herbs':'Травы','animals':'Пастбище','wild':'Питомник','building':'Другая постройка'}
COLORS={'empty':'#293b45','crops':'#3b754e','herbs':'#4b65a0','animals':'#9a8243','wild':'#915b40','building':'#665f75'}
BUILD={'crops':{'T1_WOOD':15,'T1_ROCK':15},'herbs':{'T1_WOOD':25,'T1_ROCK':25,'T2_PLANKS':25,'T2_STONEBLOCK':25},'animals':{'T1_WOOD':30,'T1_ROCK':30,'T3_PLANKS':30,'T3_STONEBLOCK':30},'wild':{'T6_WOOD':50,'T6_ROCK':50,'T6_METALBAR':10}}

class IslandMap(QWidget):
    def __init__(self,dialog):super().__init__(dialog);self.dialog=dialog;self.setMinimumSize(430,330);self.cells=[]
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);w=self.width();h=self.height();p.setBrush(QColor('#203a35'));p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(w*.04,h*.5),QPointF(w*.3,h*.03),QPointF(w*.86,h*.04),QPointF(w*.97,h*.65),QPointF(w*.7,h*.95),QPointF(w*.2,h*.91)]))
        self.cells=[];cw=w*.19;ch=h*.18
        for n in range(self.dialog.count.value()):
            x=w*.12+n%4*w*.2;y=h*.13+n//4*h*.2;self.cells.append((x,y,cw,ch));plot=self.dialog.plots[n];kind=plot.get('kind','empty')
            p.setPen(QPen(QColor('#81918b'),1));p.setBrush(QColor(COLORS[kind]));p.drawRoundedRect(QRectF(x,y,cw,ch),7,7)
            p.setPen(QColor('#ffffff'));p.drawText(int(x+3),int(y+3),int(cw-6),int(ch-6),Qt.AlignCenter,tr(str(n+1)+'\n'+KINDS[kind]))
    def mousePressEvent(self,event):
        for n,(x,y,w,h) in enumerate(self.cells):
            if x<=event.position().x()<=x+w and y<=event.position().y()<=y+h:self.dialog.edit_plot(n);return

class IslandLayoutDialog(QDialog):
    def __init__(self,page):
        super().__init__(page);self.page=page;self.owner=page.owner;self.worker=None;self.setWindowTitle('План острова');self.resize(760,740);body=QVBoxLayout(self)
        bar=QHBoxLayout();body.addLayout(bar);self.city=QComboBox();self.city.addItems(CITIES);bar.addWidget(self.city)
        self.level=NumberBox();self.level.setRange(1,6);self.level.setPrefix('Уровень ');bar.addWidget(self.level)
        self.count=NumberBox();self.count.setRange(1,16);self.count.setPrefix('Участки ');bar.addWidget(self.count)
        self.extra=LargeNumberBox();self.extra.setRange(0,1e10);self.extra.setPrefix('Остров / улучшение: ');bar.addWidget(self.extra)
        self.map=IslandMap(self);body.addWidget(self.map,1)
        note=QLabel('Нажми участок и выбери назначение. Незаполненные участки пустые. Схема условная; число доступных участков сверяй в игре. Стоимость острова и улучшения введи отдельно. Автовыбор сравнивает продукты одной категории по прибыли в день.');note.setWordWrap(True);body.addWidget(note)
        bar=QHBoxLayout();body.addLayout(bar);choose=QPushButton('Подобрать культуры и окупаемость');choose.clicked.connect(self.recommend);bar.addWidget(choose)
        apply=QPushButton('Использовать посадки в расчёте');apply.clicked.connect(self.apply_rows);bar.addWidget(apply)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setMaximumHeight(145);body.addWidget(self.status);self.city.currentTextChanged.connect(self.load);self.level.valueChanged.connect(self.level_changed);self.count.valueChanged.connect(self.count_changed);self.extra.valueChanged.connect(self.save);self.load()
        from .ui_layout import fit_window
        fit_window(self)
    def load(self,*args):
        self.loading=True;s=self.owner.settings.get('island_layouts',{}).get(self.city.currentText(),{});self.plots=[dict(p) for p in s.get('plots',[])][:16]
        self.plots.extend(dict(kind='empty') for _ in range(16-len(self.plots)))
        self.level.setValue(s.get('level',6));self.count.setValue(s.get('count',16));self.extra.setValue(s.get('extra',0));self.loading=False;self.map.update()
    def save(self,*args):
        if getattr(self,'loading',False):return
        self.owner.settings.setdefault('island_layouts',{})[self.city.currentText()]=dict(level=self.level.value(),count=self.count.value(),extra=self.extra.value(),plots=self.plots)
        save_settings(self.owner.settings_path,self.owner.settings)
    def count_changed(self,*args):self.map.update();self.save()
    def level_changed(self,*args):
        if getattr(self,'loading',False):return
        self.count.setValue([1,3,5,9,12,16][self.level.value()-1]);self.save()
    def edit_plot(self,n):
        dialog=QDialog(self);dialog.setWindowTitle('Участок '+str(n+1));form=QFormLayout(dialog);kind=QComboBox()
        for k,label in KINDS.items():kind.addItem(label,k)
        kind.setCurrentIndex(kind.findData(self.plots[n].get('kind','empty')));form.addRow('Назначение',kind);product=QComboBox();form.addRow('Культура / животное',product)
        def fill():
            product.clear();product.addItem('Выбрать самый выгодный',None)
            for p in self.page.products:
                if p['kind']==kind.currentData():product.addItem(item_name(p['id']),p['id'])
            product.setCurrentIndex(max(0,product.findData(self.plots[n].get('product'))))
        kind.currentIndexChanged.connect(fill);fill();built=QComboBox();built.addItem('Уже построено',True);built.addItem('Нужно построить',False);built.setCurrentIndex(0 if self.plots[n].get('built',True) else 1);form.addRow('Постройка',built)
        save=QPushButton('Сохранить');form.addRow(save)
        def commit():self.plots[n]=dict(kind=kind.currentData(),product=product.currentData(),built=built.currentData());self.save();self.map.update();dialog.accept()
        save.clicked.connect(commit);dialog.exec()
    def recommend(self):
        if self.worker and self.worker.isRunning():return
        ids={uid for p in self.page.products for uid in (p['id'],p['product'],p.get('food')) if uid}|{uid for parts in BUILD.values() for uid in parts}
        prices,_=market_snapshot(self.owner,self.page.root,ids);self.pending=[dict(p) for p in self.plots];self.pending_city=self.city.currentText()
        settings=dict(city=self.pending_city,plots=1,mastery=0,specialization=0,premium=self.page.premium.isChecked(),sale=self.page.sale.currentData(),any_age=self.page.age.isChecked())
        levels=self.page.profile_levels() if self.page.link_profile.isChecked() else {}
        self.pending_params=(self.count.value(),self.extra.value());self.worker=ProcessWorker('island_layout',dict(prices=prices,plots=self.pending[:self.count.value()],settings=settings,levels=levels,extra=self.extra.value()),self)
        self.worker.ready.connect(self.received);self.worker.failed.connect(self.status.setText);self.worker.start();self.status.setText('Сравниваю варианты…')
    def received(self,result):
        if self.pending_city!=self.city.currentText() or self.plots!=self.pending or self.pending_params!=(self.count.value(),self.extra.value()):self.status.setText('Схема изменилась — повтори подбор.');return
        self.plots[:len(result['plots'])]=result['plots'];self.save();self.map.update();self.status.setText(result['message'])
    def apply_rows(self):
        selected=[p for p in self.plots[:self.count.value()] if p['kind'] in BUILD]
        if any(not p.get('product') for p in selected):self.status.setText('Сначала выбери культуры или выполни подбор.');return
        for n in range(len(self.page.rows)-1,-1,-1):
            if self.page.rows[n]['city'].currentText()==self.city.currentText():self.page.inputs.removeRow(n);self.page.rows.pop(n)
        totals={}
        for p in selected:totals[p['product']]=totals.get(p['product'],0)+1
        for uid,count in totals.items():self.page.add_row(dict(city=self.city.currentText(),product=uid,plots=count),save=False)
        self.page.invalidate();self.accept()
    def done(self,result):
        if self.worker and self.worker.isRunning():self.worker.requestInterruption();self.worker.finished.connect(lambda:self.done(result));return
        self.save();super().done(result)

def solve_layout(data):
    from .island_planner import alternatives
    from .island import estimate,farming_data
    products={p['id']:p for p in farming_data()['products']};index={(p['item_id'],p['city']):p for p in data['prices'] if p.get('quality',1)==1};plots=[];capital=D(str(data['extra']));daily=D(0);missing=[];messages=[]
    for n,plot in enumerate(data['plots']):
        plot=dict(plot);kind=plot['kind']
        if kind not in BUILD:plots.append(plot);continue
        construction=D(0)
        if not plot.get('built',True):
            for uid,qty in BUILD[kind].items():
                value,age,status=quote(index.get((uid,data['settings']['city']),{}),'sell_price_min',None if data['settings']['any_age'] else 30)
                if value is None or 'будущем' in status or not data['settings']['any_age'] and 'устарело' in status:missing.append(uid)
                else:construction+=D(value)*qty
        choices=alternatives(dict(data,kind=kind,construction=construction));picked=next((r for r in choices if r['product']['id']==plot.get('product')),None) if plot.get('product') else (choices[0] if choices else None)
        if not picked:missing.append('Участок '+str(n+1));plots.append(plot);continue
        plot['product']=picked['product']['id'];capital+=construction+picked['result']['investment'];daily+=picked['financial']['daily'];plots.append(plot)
        if choices:
            fastest=min((r for r in choices if r['financial']['days'] is not None),key=lambda r:r['financial']['days'],default=None)
            messages.append('Участок '+str(n+1)+': '+item_name(picked['product']['id'])+' • '+money(picked['financial']['daily'])+' / день'+(' • быстрее окупится: '+item_name(fastest['product']['id']) if fastest else ''))
    text='Неизвестно: не хватает данных. '+', '.join(sorted(set(missing))) if missing else 'Без фокуса. Начальные затраты: '+money(capital)+' • прибыль / день: '+money(daily)+' • окупаемость: '+(str(round(capital/daily,1))+' дн.' if daily>0 else 'не окупается')+' • за 30 дней после затрат: '+money(daily*30-capital)
    return dict(plots=plots,message=text+'\n'+'\n'.join(messages[:4]))
