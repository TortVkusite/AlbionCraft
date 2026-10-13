import json
from .i18n_widgets import QDialog,QVBoxLayout,QLabel,QPushButton,QFileDialog,QMessageBox
from .profile_backup import backup,stage_restore,diagnostic
from .background import ProcessWorker

class ProfileDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.worker=None;self.setWindowTitle('Резервная копия и диагностика');layout=QVBoxLayout(self)
        self.status=QLabel('Резервная копия содержит личные профили, запасы и заказы — храни её приватно. Отчёт диагностики содержит версии и количество записей, без имён персонажей, ордеров, токенов и путей.');self.status.setWordWrap(True);layout.addWidget(self.status)
        for label,action in [('Создать резервную копию',self.backup),('Восстановить при следующем запуске',self.restore),('Сохранить отчёт диагностики',self.report),('Закрыть',self.accept)]:
            button=QPushButton(label);button.clicked.connect(action);layout.addWidget(button)
        self.resize(580,300)
    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,'Резервная копия','AlbionCraft-backup.zip','ZIP (*.zip)')
        if path:self.run('backup',path)
    def restore(self):
        path,_=QFileDialog.getOpenFileName(self,'Восстановление','','ZIP (*.zip)')
        if not path:return
        if QMessageBox.question(self,'Восстановление','При следующем запуске текущие профили будут заменены. Создай резервную копию перед восстановлением. Продолжить?')!=QMessageBox.Yes:return
        self.run('restore',path)
    def report(self):
        from pathlib import Path
        path,_=QFileDialog.getSaveFileName(self,'Диагностика','AlbionCraft-diagnostic.json','JSON (*.json)')
        if path:self.run('report',path)
    def run(self,action,path):
        if self.worker and self.worker.isRunning():return
        self.worker=ProcessWorker('profile_data',dict(action=action,root=str(self.owner.base_root),path=path),self,timeout=300)
        self.worker.ready.connect(lambda value:self.status.setText(value));self.worker.failed.connect(self.status.setText);self.worker.start();self.status.setText('Обрабатываю данные…')
    def done(self,result):
        if self.worker and self.worker.isRunning():self.status.setText('Дождись завершения операции с данными.');return
        super().done(result)
