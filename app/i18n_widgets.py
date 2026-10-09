"""Qt presentation adapters. User input and item data remain untouched."""
from PySide6 import QtWidgets as _qt
from .i18n import tr

class _Presentation:
    def setToolTip(self,text):super().setToolTip(tr(text))
    def setWindowTitle(self,text):super().setWindowTitle(tr(text))
    def setStatusTip(self,text):super().setStatusTip(tr(text))
    def setWhatsThis(self,text):super().setWhatsThis(tr(text))
    def setPlaceholderText(self,text):super().setPlaceholderText(tr(text))
    def setPrefix(self,text):super().setPrefix(tr(text))
    def setSuffix(self,text):super().setSuffix(tr(text))
    def setSpecialValueText(self,text):super().setSpecialValueText(tr(text))
    def setFormat(self,text):super().setFormat(tr(text))

class _Text(_Presentation):
    def __init__(self,*args,**kwargs):
        if args and isinstance(args[0],str):args=(tr(args[0]),)+args[1:]
        for key in ('text','title'):
            if key in kwargs:kwargs[key]=tr(kwargs[key])
        super().__init__(*args,**kwargs)
    def setText(self,text):super().setText(tr(text))
    def setTitle(self,text):super().setTitle(tr(text))

for _name in ('QLabel','QPushButton','QCheckBox','QRadioButton','QGroupBox','QTableWidgetItem','QListWidgetItem'):
    _native=getattr(_qt,_name)
    globals()[_name]=type(_native)(_name,(_Text,_native),{'__module__':__name__})
for _name in ('QDialog','QMainWindow','QLineEdit','QSpinBox','QDoubleSpinBox','QProgressBar'):
    _native=getattr(_qt,_name)
    globals()[_name]=type(_native)(_name,(_Presentation,_native),{'__module__':__name__})

class QComboBox(_Presentation,_qt.QComboBox):
    def displayText(self,text):return text if self.property('userText') else tr(text)
    def addItem(self,*args,**kwargs):
        args=list(args)
        index=0 if args and isinstance(args[0],str) else 1
        if len(args)>index:args[index]=self.displayText(args[index])
        if 'text' in kwargs:kwargs['text']=self.displayText(kwargs['text'])
        super().addItem(*args,**kwargs)
    def insertItem(self,index,*args,**kwargs):
        args=list(args);position=0 if args and isinstance(args[0],str) else 1
        if len(args)>position:args[position]=self.displayText(args[position])
        super().insertItem(index,*args,**kwargs)
    def addItems(self,texts):super().addItems([self.displayText(text) for text in texts])
    def setItemText(self,index,text):super().setItemText(index,self.displayText(text))
    def findText(self,text,*args):return super().findText(self.displayText(text),*args)
    def setCurrentText(self,text):
        # Editable fields can contain personal container/preset names.
        super().setCurrentText(text if self.isEditable() else self.displayText(text))

class QTableWidget(_Presentation,_qt.QTableWidget):
    def setHorizontalHeaderLabels(self,texts):
        for index,text in enumerate(texts):self.setHorizontalHeaderItem(index,QTableWidgetItem(text))
    def setVerticalHeaderLabels(self,texts):
        for index,text in enumerate(texts):self.setVerticalHeaderItem(index,QTableWidgetItem(text))

class QListWidget(_Presentation,_qt.QListWidget):
    def addItem(self,item):super().addItem(tr(item) if isinstance(item,str) else item)
    def addItems(self,texts):super().addItems([tr(text) for text in texts])

class QTabWidget(_Presentation,_qt.QTabWidget):
    def addTab(self,*args):return super().addTab(*args[:-1],tr(args[-1]))
    def setTabText(self,index,text):super().setTabText(index,tr(text))

class QFormLayout(_qt.QFormLayout):
    def addRow(self,*args):
        if args and isinstance(args[0],str):args=(tr(args[0]),)+args[1:]
        super().addRow(*args)

class QMenu(_Text,_qt.QMenu):
    def addAction(self,*args,**kwargs):
        args=tuple(tr(arg) if isinstance(arg,str) else arg for arg in args)
        return super().addAction(*args,**kwargs)
    def addMenu(self,menu):return super().addMenu(tr(menu) if isinstance(menu,str) else menu)

class QMessageBox(_Text,_qt.QMessageBox):
    @staticmethod
    def about(parent,title,text):return _qt.QMessageBox.about(parent,tr(title),tr(text))
    @staticmethod
    def information(parent,title,text,*args,**kwargs):return _qt.QMessageBox.information(parent,tr(title),tr(text),*args,**kwargs)
    @staticmethod
    def warning(parent,title,text,*args,**kwargs):return _qt.QMessageBox.warning(parent,tr(title),tr(text),*args,**kwargs)
    @staticmethod
    def critical(parent,title,text,*args,**kwargs):return _qt.QMessageBox.critical(parent,tr(title),tr(text),*args,**kwargs)
    @staticmethod
    def question(parent,title,text,*args,**kwargs):return _qt.QMessageBox.question(parent,tr(title),tr(text),*args,**kwargs)

class QFileDialog(_qt.QFileDialog):
    @staticmethod
    def getOpenFileName(parent=None,caption='',directory='',filter='',*args,**kwargs):
        return _qt.QFileDialog.getOpenFileName(parent,tr(caption),directory,tr(filter),*args,**kwargs)

class QInputDialog(_qt.QInputDialog):
    @staticmethod
    def getItem(parent,title,label,items,current=0,editable=True,*args,**kwargs):
        translated=[tr(item) for item in items]
        value,ok=_qt.QInputDialog.getItem(parent,tr(title),tr(label),translated,current,editable,*args,**kwargs)
        # Callers map the returned choice to stable original domain labels.
        if ok and value in translated:value=items[translated.index(value)]
        return value,ok

class QDialogButtonBox(_Presentation,_qt.QDialogButtonBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        flags=_qt.QDialogButtonBox.StandardButton
        for flag,label in ((flags.Ok,'ОК'),(flags.Cancel,'Отмена'),(flags.Save,'Сохранить'),(flags.Close,'Закрыть')):
            if button:=self.button(flag):button.setText(tr(label))

def __getattr__(name):return getattr(_qt,name)
