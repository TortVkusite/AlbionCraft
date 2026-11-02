"""Opt-in private group controls. Network work always lives off the GUI thread."""
import asyncio
import logging
import sqlite3
from PySide6.QtCore import QThread, Signal, QTimer, Qt
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,
    QLineEdit,QTableWidget,QTableWidgetItem,QMessageBox,QApplication)
from .i18n import tr
from .peer_store import PeerStore
from .peer_network import PeerNode
from .ui_layout import fit_window,readable_table


class PeerWorker(QThread):
    state=Signal(object)
    updated=Signal()
    failed=Signal(str)

    def __init__(self,root,region,parent=None):
        super().__init__(parent);self.root=root;self.region=region

    def run(self):
        async def run():
            node=PeerNode(self.root,self.region,status=self.state.emit,changed=self.updated.emit)
            try:
                await node.start()
                while not self.isInterruptionRequested():await asyncio.sleep(0.2)
            finally:await node.stop()
        try:asyncio.run(run())
        except Exception as exc:
            logging.exception('Peer exchange stopped')
            self.failed.emit(type(exc).__name__+': '+str(exc))


class SandboxWorker(QThread):
    ready=Signal(object)
    failed=Signal(str)

    def run(self):
        from .peer_sandbox import run
        try:self.ready.emit(run(cancel=self.isInterruptionRequested))
        except Exception as exc:
            if not self.isInterruptionRequested():self.failed.emit(str(exc))


class PeerController:
    def __init__(self,window):
        self.window=window;self.worker=None;self.test_worker=None;self.dialog=None;self.state={};self.error=''
        path=window.root/'peer-sync.sqlite'
        if path.exists():
            with_store=PeerStore(window.root)
            try:enabled=with_store.get('enabled',False) and bool(with_store.group())
            finally:with_store.close()
            if enabled:self.start()

    def start(self):
        if self.worker and self.worker.isRunning():return
        self.error='';self.worker=PeerWorker(self.window.root,self.window.region,self.window)
        self.worker.state.connect(self.on_state)
        self.worker.failed.connect(self.on_error)
        self.worker.updated.connect(self.window.refresh_stream)
        self.worker.finished.connect(lambda worker=self.worker:self.finished(worker));self.worker.start()

    def finished(self,worker):
        if worker is self.worker:self.worker=None
        if worker:worker.deleteLater()
        if self.dialog:self.dialog.refresh()
        self.window.refresh_stream()

    def stop(self):
        if self.worker:self.worker.requestInterruption()

    def enabled(self):
        return bool(self.worker and self.worker.isRunning())

    def on_state(self,state):
        self.state=state
        if self.dialog:self.dialog.refresh()

    def on_error(self,message):
        self.error=message
        if self.dialog:self.dialog.refresh()

    def open(self):
        if self.dialog:
            self.dialog.show();self.dialog.raise_();return
        self.dialog=PeerDialog(self,self.window);self.dialog.finished.connect(lambda _:setattr(self,'dialog',None));self.dialog.show()


class PeerDialog(QDialog):
    def __init__(self,controller,parent=None):
        super().__init__(parent);self.controller=controller;self.root=controller.window.root
        self.setAttribute(Qt.WA_DeleteOnClose);self.setWindowTitle(tr('Обмен данными с друзьями'));self.resize(850,600)
        layout=QVBoxLayout(self)
        intro=QLabel('Закрытая группа P2P. Передаются только цены, количества и история рынка. Банк, профиль и личные заказы не передаются.');intro.setWordWrap(True);layout.addWidget(intro)
        note=QLabel('Приглашение даёт доступ к группе — отправляй его только друзьям. Прямая связь раскрывает сетевые адреса участников; при необходимости используются бесплатные ретрансляторы Iroh.');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();layout.addLayout(row)
        self.enabled=QCheckBox('Включить обмен');row.addWidget(self.enabled)
        self.publish=QCheckBox('Делиться наблюдениями из моей игры');row.addWidget(self.publish);row.addStretch()
        store=PeerStore(self.root)
        try:self.enabled.setChecked(controller.enabled());self.publish.setChecked(store.get('publish',True))
        finally:store.close()
        self.enabled.toggled.connect(self.toggle);self.publish.toggled.connect(self.set_publish)
        row=QHBoxLayout();layout.addLayout(row)
        create=QPushButton('Создать группу');create.clicked.connect(self.create);row.addWidget(create)
        copy=QPushButton('Скопировать приглашение');copy.clicked.connect(self.copy_invite);row.addWidget(copy)
        leave=QPushButton('Покинуть группу');leave.clicked.connect(self.leave);row.addWidget(leave)
        self.invite=QLineEdit();self.invite.setPlaceholderText('Вставь приглашение друга');self.invite.setEchoMode(QLineEdit.Password);layout.addWidget(self.invite)
        join=QPushButton('Присоединиться по приглашению');join.clicked.connect(self.join);layout.addWidget(join)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Участник','Последняя связь (UTC)','Доступ']);readable_table(self.table);layout.addWidget(self.table,1)
        self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        block=QPushButton('Разрешить / заблокировать выбранного');block.clicked.connect(self.block);layout.addWidget(block)
        self.test_button=QPushButton('Проверить обмен на этом ПК');self.test_button.clicked.connect(self.test_sandbox);layout.addWidget(self.test_button)
        footer=QLabel('Очередь сохраняется после выхода. Пересылаются актуальные записи за последние 24 часа; лимит полезных данных — 64 МиБ / 10 000 страниц. Блокировка действует на этом устройстве.');footer.setWordWrap(True);layout.addWidget(footer)
        close=QPushButton('Закрыть');close.clicked.connect(self.close);layout.addWidget(close)
        self.refresh();fit_window(self)

    def test_sandbox(self):
        if self.controller.test_worker:return
        self.test_button.setEnabled(False);self.test_button.setText(tr('Проверяю три изолированных узла…'))
        worker=SandboxWorker(self.controller.window);self.controller.test_worker=worker
        worker.ready.connect(lambda report:QMessageBox.information(self,tr('Песочница обмена'),tr('Проверка пройдена: три отдельных процесса, пересылка спящему участнику, перезапуск, отсутствие дублей и защита от старой цены. Основной профиль не изменён.')))
        worker.failed.connect(lambda message:QMessageBox.warning(self,tr('Песочница обмена'),message))
        def done():
            self.controller.test_worker=None;worker.deleteLater();self.test_button.setEnabled(True);self.test_button.setText(tr('Проверить обмен на этом ПК'))
        worker.finished.connect(done);worker.start()

    def closeEvent(self,event):
        worker=self.controller.test_worker
        if worker and worker.isRunning():
            worker.requestInterruption();event.ignore();QTimer.singleShot(100,self.close);return
        event.accept()

    def store_action(self,fn):
        store=PeerStore(self.root)
        try:return fn(store)
        except Exception as exc:QMessageBox.warning(self,tr('Обмен данными'),str(exc))
        finally:store.close();self.refresh()

    def create(self):
        self.store_action(lambda s:s.create_group())
        self.enabled.setChecked(True)

    def toggle(self,enabled):
        def apply(store):
            if enabled and not store.group():raise ValueError(tr('Сначала создай группу или вставь приглашение.'))
            store.set('enabled',enabled)
            if enabled:self.controller.start()
            else:self.controller.stop()
        self.store_action(apply)
        if enabled and not self.controller.enabled():self.enabled.blockSignals(True);self.enabled.setChecked(False);self.enabled.blockSignals(False)

    def set_publish(self,enabled):self.store_action(lambda s:s.set('publish',enabled))

    def copy_invite(self):
        def copy(store):QApplication.clipboard().setText(store.invitation())
        self.store_action(copy)

    def join(self):
        if self.controller.enabled():
            QMessageBox.information(self,tr('Обмен данными'),tr('Выключи обмен перед изменением группы.'));return
        text=self.invite.text().strip()
        def apply(store):
            store.join(text);store.set('enabled',True);return True
        joined=self.store_action(apply)
        if joined:self.invite.clear();self.enabled.setChecked(True)

    def leave(self):
        if self.controller.enabled():
            QMessageBox.information(self,tr('Обмен данными'),tr('Сначала выключи обмен и дождись остановки.'));return
        if QMessageBox.question(self,tr('Обмен данными'),tr('Удалить локальную очередь обмена и покинуть группу?'))==QMessageBox.Yes:
            self.store_action(lambda s:s.leave());self.controller.window.refresh_stream()

    def block(self):
        row=self.table.currentRow()
        if row<0:return
        peer=self.table.item(row,0).data(Qt.UserRole)
        def apply(store):
            with store.db:store.db.execute('UPDATE peers SET blocked=1-blocked WHERE id=?',(peer,))
        self.store_action(apply)

    def refresh(self):
        c=self.controller;s=c.state
        if c.enabled() and s.get('peer_rows') is not None:
            stats=s;peers=s['peer_rows'];group={'id':s['group_id']}
        else:
            try:
                store=PeerStore(self.root)
                try:stats=store.stats();peers=store.peers();group=store.group()
                finally:store.close()
            except sqlite3.Error:return
        state=tr('Обмен работает') if c.enabled() else tr('Обмен выключен')
        self.status.setText(state+' • '+tr('Группа: ')+(group['id'][:10] if group else '—')+'\n'+
            tr('Записей: ')+str(stats['records'])+' • '+f"{stats['bytes']/1024:.1f} KiB"+' • '+tr('Получено: ')+str(s.get('received',0))+' • '+tr('Отправлено: ')+str(s.get('sent',0))+
            ('\n'+tr('Ожидают связи: ')+str(s.get('errors',0)) if s.get('errors') else '')+ ('\n'+c.error if c.error else ''))
        self.table.setRowCount(len(peers))
        for row,p in enumerate(peers):
            item=QTableWidgetItem(p['id'][:16]);item.setData(Qt.UserRole,p['id']);item.setToolTip(p['id']);self.table.setItem(row,0,item)
            self.table.setItem(row,1,QTableWidgetItem(p['last_seen'] or '—'))
            self.table.setItem(row,2,QTableWidgetItem(tr('Заблокирован') if p['blocked'] else tr('Разрешён')))
