from .i18n import tr
from PySide6.QtCore import Qt,QSortFilterProxyModel,QTimer
from PySide6.QtWidgets import QListView
from .responsive import CheckChoiceModel
from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,
    QListWidgetItem,QTabWidget,QWidget,QFormLayout,QSpinBox,QDoubleSpinBox,QDialogButtonBox,QPushButton,QMessageBox)
from .preferences import exclusion_key
from .ui_layout import fit_window


class PersonalizationDialog(QDialog):
    def __init__(self,parent,recipes,settings):
        super().__init__(parent);self.setWindowTitle('Персонализация');self.resize(640,650)
        layout=QVBoxLayout(self);tabs=QTabWidget();layout.addWidget(tabs)
        exclusions=QWidget();body=QVBoxLayout(exclusions);tabs.addTab(exclusions,'Исключения')
        label=QLabel('Отмеченные предметы скрываются при галочке «Без исключённых» в главном окне.\nИсключение действует на все уровни, чары и качества выбранного предмета.');label.setWordWrap(True);body.addWidget(label)
        self.search=QLineEdit();self.search.setPlaceholderText('Найти предмет…');body.addWidget(self.search)
        self.items=QListView();body.addWidget(self.items)
        names={}
        for r in recipes:names.setdefault(exclusion_key(r),r.name.split(' (')[0])
        selected=set(settings.get('excluded_items',[]))
        self.item_model=CheckChoiceModel([(name,key) for key,name in sorted(names.items(),key=lambda x:x[1])],selected,self)
        self.proxy=QSortFilterProxyModel(self);self.proxy.setSourceModel(self.item_model);self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive);self.items.setModel(self.proxy)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(150);self.search_timer.timeout.connect(lambda:self.filter(self.search.text()))
        self.search.textChanged.connect(lambda:self.search_timer.start())
        clear=QPushButton('Снять все исключения');body.addWidget(clear);clear.clicked.connect(self.clear)
        options=QWidget();form=QFormLayout(options);tabs.addTab(options,'Рекомендации')
        prefs=settings.get('recommendations',{})
        self.hours=QSpinBox();self.hours.setRange(1,720);self.hours.setValue(int(prefs.get('stale_hours',6)));self.hours.setSuffix(' ч');form.addRow('Напоминать о ценах старше:',self.hours)
        self.low=QDoubleSpinBox();self.low.setRange(0,100000);self.low.setSuffix(' %');self.low.setValue(float(prefs.get('roi_min',5)));form.addRow('Кандидаты: ROI от:',self.low)
        self.high=QDoubleSpinBox();self.high.setRange(0,100000);self.high.setSuffix(' %');self.high.setValue(float(prefs.get('roi_max',200)));form.addRow('Кандидаты: ROI до:',self.high)
        note=QLabel('Рекомендации используют загруженные данные для выбранных фильтров. Неизвестные расходы и давность цен отмечаются. Опыт и дерево прокачки будут доработаны отдельно.');note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.Save).setText(tr('Сохранить'));buttons.button(QDialogButtonBox.Cancel).setText(tr('Отмена'))
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject)
        fit_window(self)
    def filter(self,text):
        self.proxy.setFilterFixedString(text)
    def clear(self):
        self.item_model.clear()
    def save(self):
        if self.low.value()>self.high.value():QMessageBox.warning(self,'ROI','Нижняя граница должна быть не выше верхней.');return
        self.excluded=sorted(self.item_model.checked)
        self.recommendations=dict(stale_hours=self.hours.value(),roi_min=str(self.low.value()),roi_max=str(self.high.value()))
        self.accept()
