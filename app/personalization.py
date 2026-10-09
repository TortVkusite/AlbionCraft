from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,
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
        self.items=QListWidget();body.addWidget(self.items)
        names={}
        for r in recipes:names.setdefault(exclusion_key(r),r.name.split(' (')[0])
        selected=set(settings.get('excluded_items',[]))
        for key,name in sorted(names.items(),key=lambda x:x[1]):
            item=QListWidgetItem(name);item.setData(Qt.UserRole,key);item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if key in selected else Qt.Unchecked);self.items.addItem(item)
        self.search.textChanged.connect(self.filter)
        clear=QPushButton('Снять все исключения');body.addWidget(clear);clear.clicked.connect(self.clear)
        options=QWidget();form=QFormLayout(options);tabs.addTab(options,'Рекомендации')
        prefs=settings.get('recommendations',{})
        self.hours=QSpinBox();self.hours.setRange(1,720);self.hours.setValue(int(prefs.get('stale_hours',6)));self.hours.setSuffix(' ч');form.addRow('Напоминать о ценах старше:',self.hours)
        self.low=QDoubleSpinBox();self.low.setRange(0,100000);self.low.setSuffix(' %');self.low.setValue(float(prefs.get('roi_min',5)));form.addRow('Кандидаты: ROI от:',self.low)
        self.high=QDoubleSpinBox();self.high.setRange(0,100000);self.high.setSuffix(' %');self.high.setValue(float(prefs.get('roi_max',200)));form.addRow('Кандидаты: ROI до:',self.high)
        note=QLabel('Рекомендации используют загруженные данные для выбранных фильтров. Неизвестные расходы и давность цен отмечаются. Опыт и дерево прокачки будут доработаны отдельно.');note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.Save).setText('Сохранить');buttons.button(QDialogButtonBox.Cancel).setText('Отмена')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject)
        fit_window(self)
    def filter(self,text):
        for n in range(self.items.count()):
            item=self.items.item(n);item.setHidden(text.casefold() not in item.text().casefold())
    def clear(self):
        for n in range(self.items.count()):self.items.item(n).setCheckState(Qt.Unchecked)
    def save(self):
        if self.low.value()>self.high.value():QMessageBox.warning(self,'ROI','Нижняя граница должна быть не выше верхней.');return
        self.excluded=sorted(self.items.item(n).data(Qt.UserRole) for n in range(self.items.count()) if self.items.item(n).checkState()==Qt.Checked)
        self.recommendations=dict(stale_hours=self.hours.value(),roi_min=str(self.low.value()),roi_max=str(self.high.value()))
        self.accept()
