import os,subprocess
from pathlib import Path
from .i18n_widgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QPushButton,QFileDialog,QApplication,QMessageBox
from .local_market import PORT
from .client_setup import SetupWorker,capture_ready
from .paths import data_root,resource_root
from .ui_layout import fit_window

class ClientDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.parent_window=parent;self.setWindowTitle('Цены из твоей игры — '+getattr(parent,'region_label','Europe'));self.resize(760,480)
        layout=QVBoxLayout(self)
        self.setup_worker=None
        self.auto_setup=QPushButton('Установить всё и подключить');self.auto_setup.setStyleSheet('background:#315b83;font-weight:bold;padding:12px;');layout.addWidget(self.auto_setup);self.auto_setup.clicked.connect(self.install_all)
        text=QLabel('Запусти Albion Data Client вместе с AlbionCraft и Albion Online.\n'
            'Открывай рынок, предложения продажи и заказы покупки нужных предметов и ресурсов.\n'
            'Приложение пересчитает прибыль по новым наблюдениям. Видимые страницы — неполный рынок.\n'
            'Время получения подтверждает наблюдение, но не гарантирует, что ордер ещё доступен.\n'
            'Кнопка выше сама скачает клиент и Npcap. В мастере Npcap нажми I Agree → Install → Finish.\n'
            'Для своих заказов открой в игре вкладку собственных покупок и продаж. Полученные страницы попадут в «Мои заказы».\n'
            'Подтверждённое создание и отмена обновляют конкретный заказ. Чтение письма рынка может закрыть однозначно найденный заказ.\n'
            'Цены и собственные заказы передаются только на этот компьютер.');text.setWordWrap(True);layout.addWidget(text)
        text.setText(text.text()+'\n'+getattr(parent,'region_label','Europe')+' — сервер в игре должен совпадать с выбранным в приложении.')
        self.path=QLineEdit(parent.settings.get('data_client_path',''))
        enhanced=resource_root()/'tools'/'albion-data-client'/'albioncraft-data-client.exe'
        if enhanced.is_file():self.path.setText(str(enhanced))
        if not self.path.text():
            local=data_root()/'tools'/'albion-data-client'/'albiondata-client.exe'
            if local.is_file():self.path.setText(str(local))
            for base in ('ProgramFiles','ProgramFiles(x86)'):
                p=Path(os.environ.get(base,''))/'Albion Data Client'/'albiondata-client.exe'
                if p.is_file():self.path.setText(str(p));break
        self.path.setPlaceholderText('Путь к albiondata-client.exe');layout.addWidget(self.path)
        choose=QPushButton('Выбрать установленный клиент');layout.addWidget(choose);choose.clicked.connect(self.choose)
        start=QPushButton('Запустить клиент с локальной передачей');layout.addWidget(start);start.clicked.connect(self.start)
        self.start_button=start
        self.info=QLabel('Сначала включи «Цены из моей игры» в основном окне. Клиент должен быть один; обычный запуск без этой команды не передаёт данные локально.');self.info.setWordWrap(True);layout.addWidget(self.info)
        downloaded=Path.home()/'Downloads'/'albiondata-client-amd64-installer.exe'
        if downloaded.is_file():self.info.setText('В Downloads найден правильный установщик клиента. Проще нажать «Установить всё и подключить»: путь будет задан автоматически.')
        fit_window(self)
    def install_all(self):
        w=self.parent_window
        if w.client_process and w.client_process.poll() is None:self.info.setText('Клиент уже работает. Открой рынок в игре.');return
        self.auto_setup.setEnabled(False)
        self.start_button.setEnabled(False)
        self.setup_worker=SetupWorker(data_root())
        self.setup_worker.progress.connect(self.info.setText);self.setup_worker.failed.connect(self.install_failed);self.setup_worker.ready.connect(self.install_ready)
        self.setup_worker.finished.connect(lambda:(self.auto_setup.setEnabled(True),self.start_button.setEnabled(True)));self.setup_worker.start()
    def install_failed(self,message):self.info.setText(message)
    def install_ready(self,path):
        self.path.setText(path);self.parent_window.settings['data_client_path']=path;self.parent_window.save_local_settings();self.start()
    def closeEvent(self,event):
        if self.setup_worker and self.setup_worker.isRunning():self.info.setText('Подожди завершения установки. Её можно отменить в открытом мастере Npcap.');event.ignore()
        else:event.accept()
    def reject(self):
        if self.setup_worker and self.setup_worker.isRunning():self.info.setText('Дождись завершения или отмени установку в мастере Npcap.');return
        super().reject()
    def command(self):
        local=f'http://127.0.0.1:{PORT}/{self.parent_window.settings["local_token"]}'
        command=[self.path.text().strip(),'-i',local,'-p','']
        if Path(self.path.text()).name=='albioncraft-data-client.exe':command+=['-own-orders',local+'/ownorders.ingest']
        return command
    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'Albion Data Client','','Программа (*.exe)')
        if path:self.path.setText(path)
    def start(self):
        w=self.parent_window
        if not w.local_enabled.isChecked():w.local_enabled.setChecked(True)
        path=Path(self.path.text().strip())
        if not path.is_file():QMessageBox.warning(self,'Клиент','Скачай и установи Albion Data Client, затем выбери его .exe.');return
        if 'installer' in path.name.lower():self.info.setText('Это установщик. Нажми «Установить всё и подключить» — выбирать программу вручную не потребуется.');return
        if not capture_ready():
            QMessageBox.warning(self,'Npcap','Не найден драйвер захвата Npcap. Установи его с WinPcap API-compatible Mode и повтори запуск.');return
        if w.client_process and w.client_process.poll() is None:self.info.setText('Запущенный из приложения клиент уже работает.');return
        try:
            logs=data_root()/'logs';logs.mkdir(exist_ok=True)
            w.client_error_log=logs/'data-client-output.log'
            with w.client_error_log.open('ab') as output:
                w.client_process=subprocess.Popen(self.command(),stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as exc:QMessageBox.warning(self,'Запуск',str(exc));return
        w.settings['data_client_path']=str(path);w.save_local_settings()
        self.info.setText('Клиент запущен. Открой рынок в игре. Если ордеров нет, проверь клиент обычным запуском: захвату могут потребоваться права администратора. Повторные экземпляры не запускай.')
