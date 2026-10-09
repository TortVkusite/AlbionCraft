"""Visible bank reader and editable route stock, without game input automation."""
import hashlib,ctypes,sys,uuid
from pathlib import Path
from decimal import Decimal
from PySide6.QtCore import Qt,QThread,Signal,QTimer,QRect
from PySide6.QtGui import QImage,QPainter,QColor,QPen
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
    QCheckBox,QSpinBox,QLineEdit,QTableWidget,QTableWidgetItem,QAbstractItemView,QFileDialog,
    QApplication,QMessageBox)
from .trip_inventory import StockStore
from .item_names import item_name
from .stock_screen import recognize_grid
from .market_snapshot import market_snapshot
from .models import quote
from .number_fields import NumberBox
from .i18n import tr
from .ui_layout import FlowLayout,explanation,readable_table,compact_combos,fit_window


class ChoiceBox(QComboBox):
    def wheelEvent(self,event):event.ignore()


class RegionPicker(QDialog):
    selected=Signal(object)
    def __init__(self,image,parent=None,screen=None):
        super().__init__(parent);self.image=image;self.screen=screen;self.begin=None;self.rect=QRect()
        self.setWindowTitle('Выдели полные ячейки банка; Esc — отмена')
        if screen:
            self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint)
            self.setGeometry(screen.geometry())
        else:self.resize(min(image.width(),1200),min(image.height(),850))
    def paintEvent(self,event):
        p=QPainter(self);p.drawImage(self.rect_for_image(),self.image)
        p.setPen(QPen(QColor('#ffd765'),2));p.drawRect(self.rect)
        p.setPen(QColor('#ffd765'));p.drawText(15,22,tr('Выдели прямоугольник полных ячеек с равными отступами. Обрезанные ряды пропусти. Esc — отмена.'))
    def rect_for_image(self):return QRect(0,0,self.width(),self.height())
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:self.begin=event.position().toPoint();self.rect=QRect(self.begin,self.begin)
    def mouseMoveEvent(self,event):
        if self.begin is not None:self.rect=QRect(self.begin,event.position().toPoint()).normalized();self.update()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.begin is None:return
        self.rect=self.rect.intersected(self.rect_for_image());self.begin=None
        if self.rect.width()<40 or self.rect.height()<40:return
        sx=self.image.width()/self.width();sy=self.image.height()/self.height()
        self.selected.emit(dict(logical=self.rect,pixels=QRect(round(self.rect.x()*sx),round(self.rect.y()*sy),round(self.rect.width()*sx),round(self.rect.height()*sy))))
        self.accept()


class ScreenWorker(QThread):
    ready=Signal(object,object);failed=Signal(str)
    def __init__(self,image,columns,templates):
        super().__init__();self.image=image;self.columns=columns;self.templates=templates
    def run(self):
        try:
            rows,warnings=recognize_grid(self.image,self.columns,self.templates);self.ready.emit(rows,warnings)
        except Exception as exc:self.failed.emit(str(exc))


def game_in_foreground():
    if sys.platform!='win32':return False
    user=ctypes.windll.user32;buf=ctypes.create_unicode_buffer(512)
    user.GetWindowTextW(user.GetForegroundWindow(),buf,len(buf))
    return 'albion online' in buf.value.casefold()


class StockDialog(QDialog):
    changed=Signal()
    def __init__(self,parent,root,player,buy,craft,recipes):
        super().__init__(parent);self.root=Path(root);self.player=player;self.buy=buy;self.craft=craft
        self.store=StockStore(self.root/'player.sqlite');self.worker=None;self.region=None;self.capture_screen=None
        self.last_hash=None;self.closed=False;self.preview=[];self.pending_signature=None;self.applied_signature=None;self.owner=parent.owner;self.dirty=False
        self.capture_revision=0
        self.ids=sorted({r.item_id for r in recipes}|{i.item_id for r in recipes for i in r.ingredients})
        self.setWindowTitle('Запасы для ходки — банк и уже купленное');self.resize(1190,700)
        body=QVBoxLayout(self)
        note=QLabel('На базе: город переработки, без перевозки. Уже куплено: город закупки, с весом, без повторной закупки. Цена — стоимость приобретения за штуку. Банк не показывает цену покупки: для купленного без известной цены фиксируется доступная рыночная оценка при чтении. Её можно заменить фактической ценой. Для базы пустая цена означает текущую рыночную оценку.');note.setWordWrap(True);body.addWidget(note)
        controls=FlowLayout();body.addLayout(controls)
        self.kind=QComboBox();self.kind.addItem('На базе: '+craft,'base');self.kind.addItem('Уже куплено: '+buy,'bought');controls.addWidget(self.kind)
        self.columns=NumberBox();self.columns.setRange(1,12);self.columns.setValue(5);controls.addWidget(QLabel('Столбцов в банке:'));controls.addWidget(self.columns)
        region=QPushButton('Выбрать область экрана');controls.addWidget(region);region.clicked.connect(self.choose_region)
        file=QPushButton('Прочитать скриншот');controls.addWidget(file);file.clicked.connect(self.choose_file)
        self.auto=QCheckBox('Читать автоматически');controls.addWidget(self.auto);self.auto.toggled.connect(self.toggle_auto)
        self.kind.currentIndexChanged.connect(self.reset_capture);self.columns.valueChanged.connect(self.reset_capture)
        bank_controls=FlowLayout();body.addLayout(bank_controls)
        containers={s['container'] for s in self.store.bank_scans(player)}
        default_container='Банк' if 'Банк' in containers else tr('Банк')
        self.container=ChoiceBox();self.container.setProperty('userText',True);self.container.setEditable(True);self.container.addItems(sorted({default_container}|containers));self.container.setCurrentText(default_container)
        bank_controls.addWidget(QLabel('Контейнер:'));bank_controls.addWidget(self.container)
        self.align=QCheckBox('Автопозиция по перекрытию');self.align.setChecked(True);bank_controls.addWidget(self.align)
        self.first_row=NumberBox();self.first_row.setRange(1,10000);self.first_row.setValue(1);self.first_row.setEnabled(False);bank_controls.addWidget(QLabel('Первая строка области:'));bank_controls.addWidget(self.first_row)
        self.align.toggled.connect(lambda checked:self.first_row.setEnabled(not checked));self.align.toggled.connect(self.reset_capture);self.first_row.valueChanged.connect(self.reset_capture)
        self.container.currentTextChanged.connect(self.reset_capture)
        new=QPushButton('Начать новый снимок');bank_controls.addWidget(new);new.clicked.connect(self.new_bank)
        finish=QPushButton('Контейнер просмотрен полностью');bank_controls.addWidget(finish);finish.clicked.connect(self.finish_bank)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['Ресурс','Где','Количество','Цена / шт.','Источник','Наблюдение'])
        self.table.verticalHeader().hide();self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.horizontalHeader().setStretchLastSection(True);body.addWidget(self.table,1)
        self.table.itemChanged.connect(self.mark_dirty)
        actions=FlowLayout();body.addLayout(actions)
        add=QPushButton('Добавить вручную');actions.addWidget(add);add.clicked.connect(self.add_row)
        remove=QPushButton('Удалить выбранные');actions.addWidget(remove);remove.clicked.connect(self.remove_rows)
        save=QPushButton('Сохранить правки');actions.addWidget(save);save.clicked.connect(self.save_rows)
        self.apply=QPushButton('Применить прочитанный снимок');actions.addWidget(self.apply);self.apply.setEnabled(False);self.apply.clicked.connect(self.apply_preview)
        self.status=QLabel('Выдели только полные ячейки банка. Чтение распознаёт ресурсы для переработки; сомнительные ячейки пропускаются.');self.status.setWordWrap(True);body.addWidget(self.status)
        explanation(body,'Для каждого банка / вкладки укажи своё имя контейнера. Начинай новый снимок сверху, затем прокручивай с перекрытием минимум двух строк с разными ресурсами: ячейки объединяются по позиции. При неоднозначном совпадении укажи первую строку вручную. После сортировки или перемещения предметов начни снимок заново. «Просмотрен полностью» подтверждай только после чтения от верха до низа. Авточтение работает в этом окне, пока игра на переднем плане.','Как прочитать весь банк')
        receipts=FlowLayout();body.addLayout(receipts)
        self.character=QLineEdit();self.character.setPlaceholderText('Точное имя персонажа в игре');receipts.addWidget(self.character)
        self.watch=QCheckBox('Добавлять новые покупки по письмам рынка');receipts.addWidget(self.watch)
        watched=self.store.watcher(player)
        if watched and watched[2]!=buy:self.store.watch(player,'',buy,False);watched=None
        if watched:self.character.setText(watched[0]);self.watch.setChecked(True)
        self.character.setEnabled(not bool(watched))
        self.watch.toggled.connect(self.toggle_watch)
        info=QLabel('Письма: только завершённые заказы на покупку после включения, в городе закупки. Клиент должен быть подключён, письмо — открыто. Быструю покупку этот источник не подтверждает. Забери купленное перед ходкой; старые письма не добавляются.');info.setWordWrap(True);body.addWidget(info)
        close=QPushButton('Закрыть');body.addWidget(close);close.clicked.connect(self.accept)
        self.rows=[];self.reload();self.signature=repr(self.store.rows(self.player))
        self.timer=QTimer(self);self.timer.setInterval(2500);self.timer.timeout.connect(self.tick);self.timer.start()
        # Load templates through the existing icon cache, never from the game process.
        if hasattr(self.owner,'icons'):
            for uid in self.ids:self.owner.icons.get(uid)
        readable_table(self.table);self.table.setColumnWidth(0,300)
        compact_combos(self);fit_window(self)
    def reset_capture(self,*args):
        self.capture_revision+=1
        self.auto.setChecked(False);self.last_hash=None;self.pending_signature=None;self.applied_signature=None;self.preview=[];self.apply.setEnabled(False)
    def new_bank(self):
        if self.worker and self.worker.isRunning():self.status.setText('Дождись завершения чтения.');return
        if self.dirty and not self.save_rows():return
        container=self.container.currentText().strip()
        if not container:self.status.setText('Укажи имя контейнера.');return
        self.store.start_bank(self.player,self.craft if self.kind.currentData()=='base' else self.buy,self.kind.currentData(),container)
        self.reset_capture();self.first_row.setValue(1);self.reload();self.signature=repr(self.store.rows(self.player));self.changed.emit();self.status.setText('Снимок этого контейнера очищен. Прочитай его с первой строки; другие контейнеры сохранены.')
    def finish_bank(self):
        if self.worker and self.worker.isRunning():self.status.setText('Дождись завершения чтения.');return
        if self.preview and self.apply.isEnabled():self.status.setText('Сначала примени последнюю прочитанную область.');return
        try:
            self.store.finish_bank(self.player,self.craft if self.kind.currentData()=='base' else self.buy,self.kind.currentData(),self.container.currentText().strip())
            self.changed.emit();self.status.setText('Контейнер помечен полностью просмотренным. При изменениях в банке начни новый снимок.')
        except ValueError as exc:self.status.setText(str(exc))
    def add_row(self):
        row=dict(item_id=self.ids[0],quantity=1,price=None,city=self.craft if self.kind.currentData()=='base' else self.buy,kind=self.kind.currentData(),key='manual:'+uuid.uuid4().hex,source='Вручную')
        self.rows.append(row);self.paint_rows();self.mark_dirty()
    def mark_dirty(self,*args):
        self.dirty=True
        if self.auto.isChecked():self.auto.setChecked(False);self.status.setText('Авточтение приостановлено. Сохрани правки перед следующим чтением.')
    def paint_rows(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for n,row in enumerate(self.rows):
            uid=ChoiceBox();uid.setEditable(True)
            for value in self.ids:
                uid.addItem(item_name(value,False),value);uid.setItemData(uid.count()-1,value,Qt.ToolTipRole)
            uid.setCurrentIndex(uid.findData(row['item_id']));self.table.setCellWidget(n,0,uid)
            uid.lineEdit().setCursorPosition(0);uid.setToolTip(item_name(row['item_id'],False)+'\n'+row['item_id'])
            uid.currentIndexChanged.connect(self.mark_dirty);uid.lineEdit().textEdited.connect(self.mark_dirty)
            location=ChoiceBox();location.addItem('На базе: '+self.craft,('base',self.craft));location.addItem('Куплено: '+self.buy,('bought',self.buy))
            location.setCurrentIndex(0 if row.get('kind')=='base' else 1);self.table.setCellWidget(n,1,location)
            location.currentIndexChanged.connect(self.mark_dirty)
            for c,value in [(2,str(row['quantity'])),(3,str(row.get('price') or '') if row.get('price')!=0 else '0'),(4,row.get('source','')+(' • '+row['container'] if row.get('container') else '')),(5,row.get('observed','')[:19].replace('T',' '))]:
                cell=QTableWidgetItem(value)
                if c>3:cell.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable)
                cell.setToolTip(row.get('observed',''));self.table.setItem(n,c,cell)
                if c==3 and row.get('valuation_estimated'):cell.setForeground(QColor('#e9bd6c'));cell.setToolTip('Сохранённая рыночная оценка при чтении, не фактическая цена покупки. Она не меняется вслед за рынком.')
        for col,width in enumerate([300,180,110,110,250]):self.table.setColumnWidth(col,width)
        self.table.blockSignals(False)
    def reload(self):
        self.rows=[r for r in self.store.rows(self.player) if (r.get('kind')=='base' and r['city']==self.craft) or (r.get('kind')=='bought' and r['city']==self.buy)];self.paint_rows()
    def save_rows(self):
        try:
            values=[]
            current={(r['city'],r['key']):r for r in self.store.rows(self.player)}
            for n,row in enumerate(self.rows):
                uid=self.table.cellWidget(n,0).currentData()
                if uid not in self.ids or self.table.cellWidget(n,0).currentText()!=item_name(uid,False)+f' [{uid}]':raise ValueError('Выбери ресурс из списка')
                before=current.get((row['city'],row['key']))
                if row.get('observed') and (before is None or before.get('observed')!=row['observed']):raise ValueError('Запас обновился из игры. Закрой окно и открой его заново для сверки правок.')
                kind,city=self.table.cellWidget(n,1).currentData();qty=int(self.table.item(n,2).text());text=self.table.item(n,3).text().strip().replace(',','.')
                price=Decimal(text) if text else None
                if qty<0 or price is not None and (not price.is_finite() or price<0):raise ValueError('Количество и цена должны быть неотрицательными')
                estimated=bool(row.get('valuation_estimated') and price is not None and str(price)==str(row.get('price')))
                values.append((row,dict(row,item_id=uid,quantity=qty,price=str(price) if price is not None else None,city=city,kind=kind,valuation_estimated=estimated)))
            for old,value in values:
                if old['city']!=value['city']:self.store.delete(self.player,old['city'],old['key'])
                self.store.put(self.player,value['city'],value['key'],value)
            self.reload();self.dirty=False;self.signature=repr(self.store.rows(self.player));self.changed.emit();self.status.setText('Запасы сохранены. Пересчитай ходку.');return True
        except (ValueError,ArithmeticError) as exc:self.status.setText('Правки не сохранены: '+str(exc));return False
    def remove_rows(self):
        for n in sorted({i.row() for i in self.table.selectedIndexes()},reverse=True):
            row=self.rows.pop(n);self.store.delete(self.player,row['city'],row['key'])
        self.paint_rows();self.changed.emit()
    def choose_region(self):
        self.reset_capture();self.hide();QTimer.singleShot(250,self.open_picker)
    def open_picker(self):
        screen=QApplication.primaryScreen();im=screen.grabWindow(0).toImage();picker=RegionPicker(im,None,screen)
        def selected(value):self.region=value['logical'];self.capture_screen=screen;self.last_hash=None
        picker.selected.connect(selected);picker.exec();self.show()
        if self.region:self.status.setText('Область выбрана. Открой банк в игре и включи автоматическое чтение.')
    def choose_file(self):
        file,_=QFileDialog.getOpenFileName(self,'Скриншот банка','','Изображения (*.png *.jpg *.jpeg)')
        if not file:return
        im=QImage(file)
        if im.isNull():self.status.setText('Не удалось открыть изображение.');return
        self.reset_capture();picker=RegionPicker(im,self)
        picker.selected.connect(lambda value:self.read_image(im.copy(value['pixels']),False));picker.exec()
    def toggle_auto(self,enabled):
        if enabled and not self.region:
            self.auto.setChecked(False);self.status.setText('Сначала выбери область экрана.');return
        self.last_hash=None;self.pending_signature=None
    def toggle_watch(self,enabled):
        try:
            if enabled and any(r.get('kind')=='bought' and r.get('source')=='Экран банка' for r in self.store.rows(self.player) if r['city']==self.buy):raise ValueError('Для этого города уже есть снимок купленного. Удали его перед включением писем, чтобы не учитывать покупки дважды.')
            self.store.watch(self.player,self.character.text(),self.buy,enabled)
            self.character.setEnabled(not enabled);self.status.setText('Новые завершённые покупки будут добавляться после чтения подтверждающего письма.' if enabled else 'Наблюдение за покупками выключено.')
        except ValueError as exc:self.watch.blockSignals(True);self.watch.setChecked(False);self.watch.blockSignals(False);self.status.setText(str(exc))
    def tick(self):
        signature=repr(self.store.rows(self.player))
        if signature!=self.signature:
            if not self.dirty and self.table.state()!=QAbstractItemView.EditingState:self.signature=signature;self.reload();self.changed.emit()
        if self.auto.isChecked() and self.region and game_in_foreground() and not (self.worker and self.worker.isRunning()):
            im=self.capture_screen.grabWindow(0,self.region.x(),self.region.y(),self.region.width(),self.region.height()).toImage()
            self.read_image(im,True)
    def read_image(self,image,automatic=False):
        if self.worker and self.worker.isRunning():return
        if self.dirty and not self.save_rows():return
        templates={u:QImage(str(self.root/'icons'/(u+'__1.png'))) for u in self.ids if (self.root/'icons'/(u+'__1.png')).exists()}
        if len(templates)!=len(self.ids):
            if hasattr(self.owner,'icons'):
                for uid in self.ids:
                    if uid not in templates:self.owner.icons.failed.discard(uid+'__1');self.owner.icons.get(uid)
            self.status.setText(f'Шаблоны ресурсов загружаются: {len(templates)} / {len(self.ids)}. Повтори чтение после загрузки.');return
        self.capture_kind=self.kind.currentData();self.capture_city=self.craft if self.capture_kind=='base' else self.buy;self.automatic=automatic
        self.capture_container=self.container.currentText().strip();self.capture_columns=self.columns.value();self.capture_cells=int(image.height()/(image.width()/self.capture_columns))*self.capture_columns
        self.capture_first_row=None if self.align.isChecked() else self.first_row.value()-1
        self.read_revision=self.capture_revision
        digest=hashlib.sha256(bytes(image.bits())).hexdigest()
        if automatic and digest==self.last_hash and self.pending_signature is None:return
        self.last_hash=digest;self.worker=ScreenWorker(image.copy(),self.columns.value(),templates)
        self.worker.ready.connect(self.read_done,Qt.QueuedConnection);self.worker.failed.connect(self.read_failed,Qt.QueuedConnection);self.worker.start();self.status.setText('Читаю видимые ячейки…')
    def read_failed(self,error):self.status.setText('Чтение не удалось: '+error);self.last_hash=None
    def read_done(self,rows,warnings):
        if self.closed:return
        if getattr(self,'read_revision',self.capture_revision)!=self.capture_revision:self.status.setText('Область или контейнер изменились во время чтения. Повтори чтение.');return
        self.preview=rows;signature=tuple((r['cell'],r['item_id'],r['quantity']) for r in rows)
        self.capture_warnings=warnings
        self.status.setText(f'Распознано ячеек ресурсов: {len(rows)}. Требуют проверки: {len(warnings)}.');self.status.setToolTip('\n'.join(warnings))
        self.apply.setEnabled(True)
        if self.automatic:
            if self.dirty:self.auto.setChecked(False);return
            if (self.capture_city,self.capture_kind,signature)==self.applied_signature:self.pending_signature=None;self.apply.setEnabled(False);return
            if warnings:self.auto.setChecked(False);self.status.setText('Есть сомнительные ячейки. Проверь область и примени вручную или повтори чтение.');return
            if self.pending_signature is not None and signature==self.pending_signature:self.apply_preview();self.pending_signature=None
            else:self.pending_signature=signature;self.last_hash=None
    def apply_preview(self):
        if self.dirty and not self.save_rows():return
        try:
            offset,state=self.store.merge_bank(self.player,self.capture_city,self.capture_kind,self.capture_container,self.preview,self.capture_columns,self.capture_cells,self.capture_first_row,getattr(self,'capture_warnings',[]))
        except ValueError as exc:self.auto.setChecked(False);self.status.setText(str(exc));return
        if self.capture_kind=='bought':
            prices,_=market_snapshot(self.owner,self.root,{r['item_id'] for r in self.preview});index={(p['item_id'],p['city'],p.get('quality',1)):p for p in prices}
            for row in self.store.rows(self.player):
                if row['city']!=self.capture_city or not row['key'].startswith('screen:bought:') or row.get('price') is not None:continue
                price,age,status=quote(index.get((row['item_id'],self.capture_city,1),{}),'sell_price_min',None if self.parent().age.isChecked() else 30)
                if price is not None and 'будущем' not in status:self.store.put(self.player,row['city'],row['key'],dict(row,price=str(price),valuation_estimated=True))
        if self.capture_kind=='bought':self.watch.setChecked(False)
        self.reload();self.signature=repr(self.store.rows(self.player));self.changed.emit();self.apply.setEnabled(False)
        self.applied_signature=(self.capture_city,self.capture_kind,tuple((r['cell'],r['item_id'],r['quantity']) for r in self.preview))
        self.status.setText(f'Контейнер «{self.capture_container}»: область с строки {offset//self.capture_columns+1}, ресурсов в этой области {len(self.preview)}. Всего просмотрено ячеек: {len(state["slots"])}; снимок частичный. Для купленного проверь цены.')
    def done(self,result):
        if self.worker and self.worker.isRunning():self.status.setText('Дождись завершения чтения.');return
        if not self.closed:self.timer.stop();self.store.close();self.closed=True
        super().done(result)
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():event.ignore();return
        self.done(0);event.accept()
