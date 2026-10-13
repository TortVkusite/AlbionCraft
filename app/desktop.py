"""Opt-in tray, game detection and startup; capture remains local and passive."""
import ctypes,hashlib,os,subprocess,sys
from pathlib import Path
from PySide6.QtCore import QObject,QTimer
from PySide6.QtWidgets import QSystemTrayIcon
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from .i18n_widgets import QDialog,QVBoxLayout,QCheckBox,QLabel,QPushButton,QMenu
from .regions import preferences,save_preferences
from .paths import resource_root
from .i18n import tr

def game_running():
    if os.name!='nt':return False
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),('exe',wintypes.WCHAR*260)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD];api.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    api.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];api.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];api.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=api.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:return False
    try:
        entry=Entry();entry.size=ctypes.sizeof(entry);ok=api.Process32FirstW(handle,ctypes.byref(entry))
        while ok:
            if entry.exe.lower() in ('albion-online.exe','albion-online-be.exe'):return True
            ok=api.Process32NextW(handle,ctypes.byref(entry))
        return False
    finally:api.CloseHandle(handle)

def startup_command():
    if getattr(sys,'frozen',False):return subprocess.list2cmdline([sys.executable,'--background'])
    python=Path(sys.executable);hidden=python.with_name('pythonw.exe')
    return subprocess.list2cmdline([str(hidden if hidden.exists() else python),str(resource_root()/'app/entry.py'),'--background'])

def set_startup(enabled):
    if os.name!='nt':raise ValueError('Автозапуск доступен в Windows')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:winreg.SetValueEx(key,'AlbionCraft',0,winreg.REG_SZ,startup_command())
        else:
            try:winreg.DeleteValue(key,'AlbionCraft')
            except FileNotFoundError:pass

def single_instance(app,root):
    name='AlbionCraft-'+hashlib.sha256(str(Path(root).resolve()).lower().encode()).hexdigest()[:20]
    socket=QLocalSocket();socket.connectToServer(name)
    if socket.waitForConnected(250):
        socket.write(b'show');socket.waitForBytesWritten(250);socket.waitForReadyRead(1000);socket.disconnectFromServer();return False
    server=QLocalServer(app)
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(name):
        QLocalServer.removeServer(name)
        if not server.listen(name):raise RuntimeError('Не удалось открыть локальный канал приложения')
    def receive():
        peer=server.nextPendingConnection()
        def show():
            if not peer.readAll():return
            if window:=getattr(app,'_albioncraft_window',None):window.showNormal();window.raise_();window.activateWindow()
            peer.write(b'ok');peer.flush()
            peer.disconnectFromServer();peer.deleteLater()
        peer.readyRead.connect(show)
        if peer.bytesAvailable():show()
    server.newConnection.connect(receive);app._instance_server=server;return True

class DesktopController(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.owned=False;self.last_attempt=0;self.status='Ожидание';self.stopped=False;self.bonus_signature=None
        self.tray=QSystemTrayIcon(window.windowIcon(),self);menu=QMenu(window)
        menu.addAction(tr('Открыть AlbionCraft'),self.open)
        self.state=menu.addAction(tr('Ожидание'));self.state.setEnabled(False)
        menu.addAction(tr('Настройки фоновой работы'),self.configure)
        self.pause=menu.addAction(tr('Приостановить сбор'));self.pause.setCheckable(True);self.pause.toggled.connect(self.tick)
        menu.addSeparator();menu.addAction(tr('Выйти'),self.quit);self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason:self.open() if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick) else None)
        self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(self.tick);self.timer.start()
        window.menuBar().actions()[0].menu().addAction(tr('Фоновая работа'),self.configure)
        self.apply();QTimer.singleShot(0,self.tick)
    def options(self):return preferences(self.window.base_root).get('desktop',{})
    def apply(self):
        self.tray.setVisible(bool(self.options().get('tray')) and QSystemTrayIcon.isSystemTrayAvailable())
    def open(self):self.window.showNormal();self.window.raise_();self.window.activateWindow()
    def quit(self):self.window.force_exit=True;self.window.close()
    def stop_owned(self):
        if self.owned and (process:=self.window.client_process) and process.poll() is None:process.terminate()
        self.owned=False
    def tick(self,*args):
        import time
        if self.stopped or getattr(self.window,'closing',False):return
        from .market_memory import bonus_settings
        active=bonus_settings(self.window.root,self.window.settings)['production_bonuses'];signature=repr(active)
        if self.bonus_signature is not None and signature!=self.bonus_signature:
            self.window.render()
            if self.window.settings.get('bonus_reminders') and self.tray.isVisible():self.tray.showMessage('AlbionCraft',tr('Бонусы изменились. Обнови цены и пересчитай планы.'))
        self.bonus_signature=signature
        options=self.options();game=game_running() if options.get('watch_game') else True
        if not options.get('auto_client'):self.stop_owned()
        if self.pause.isChecked() or options.get('watch_game') and not game:
            if (process:=self.window.client_process) and process.poll() is None:process.terminate()
            self.stop_owned();self.status='Сбор приостановлен' if self.pause.isChecked() else 'Ожидание Albion Online'
        elif (process:=self.window.client_process) and process.poll() is None:self.status='Клиент работает'
        elif options.get('auto_client') and time.monotonic()-self.last_attempt>60:
            self.last_attempt=time.monotonic()
            from .local_client_dialog import ClientDialog
            dialog=ClientDialog(self.window);ok=dialog.start(interactive=False);self.owned=bool(ok)
            self.status='Клиент работает' if ok else dialog.info.text();dialog.deleteLater()
        else:self.status='Клиент не запущен'
        self.state.setText(tr(self.status));self.tray.setToolTip('AlbionCraft — '+tr(self.status))
    def configure(self):
        dialog=QDialog(self.window);dialog.setWindowTitle('Фоновая работа');body=QVBoxLayout(dialog);fields={};options=self.options()
        for key,label in [('tray','Сворачивать в трей при закрытии'),('auto_client','Подключать клиент автоматически'),('watch_game','Собирать данные только пока запущен Albion'),('startup','Запускать с Windows в фоне')]:
            field=QCheckBox(label);field.setChecked(bool(options.get(key)));body.addWidget(field);fields[key]=field
        note=QLabel('Рынок обновляется при просмотре в игре. Распознавание банка запускается отдельно.');note.setWordWrap(True);body.addWidget(note)
        save=QPushButton('Сохранить');body.addWidget(save)
        def commit():
            selected={key:field.isChecked() for key,field in fields.items()}
            if selected['startup']:selected['tray']=True;selected['auto_client']=True;selected['watch_game']=True
            try:set_startup(selected['startup'])
            except (OSError,ValueError) as exc:note.setText(str(exc));return
            save_preferences(self.window.base_root,desktop=selected);self.apply();self.tick();dialog.accept()
        save.clicked.connect(commit);dialog.exec()
    def close_to_tray(self):
        if self.options().get('tray') and self.tray.isVisible():self.window.hide();return True
        return False
    def shutdown(self):self.stopped=True;self.timer.stop();self.tray.hide();self.stop_owned()
