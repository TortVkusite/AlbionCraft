"""Compact desktop presentation shared by market and planning pages."""
from PySide6.QtCore import Qt
from .i18n_widgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QPushButton,QScrollArea

STYLE = '''
QMainWindow,QDialog,QWidget{background:#10171e;color:#dee7ef;font-family:"Segoe UI";font-size:13px;}
QWidget#navigation{background:#16212b;border-right:1px solid #2b3945;}
QWidget#settingsPanel{background:#18232d;border:1px solid #2b3945;border-radius:8px;}
QLabel{background:transparent;border:0;}
QCheckBox{background:transparent;}
QLabel#pageTitle{font-size:23px;font-weight:600;color:#edf4fa;}
QLabel#sectionTitle{color:#92aabc;font-size:12px;font-weight:600;padding-top:8px;}
QLabel#metricValue{font-size:23px;font-weight:600;color:#65d6bb;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox{background:#202e39;border:1px solid #354957;border-radius:5px;padding:7px;}
QComboBox QAbstractItemView{background:#202e39;selection-background-color:#365567;}
QPushButton{background:#243644;border:1px solid #3b5364;border-radius:6px;padding:9px 12px;}
QPushButton:hover{background:#304a5c;}QPushButton:checked{background:#245449;border-color:#4fb99f;color:#bff9e9;}
QPushButton:disabled{color:#738796;}QPushButton#primary{background:#277960;border-color:#50b89a;font-weight:600;}
QPushButton#navButton{text-align:left;padding:12px;border:0;background:transparent;}
QPushButton#navButton:hover{background:#263946;}QPushButton#navButton:checked{background:#245449;color:#adf0de;}
QTableWidget{background:#101a23;alternate-background-color:#16222c;gridline-color:#293945;border:1px solid #293945;border-radius:6px;}
QHeaderView::section{background:#22313d;color:#aabfcf;padding:10px;border:0;border-bottom:1px solid #3a4e5d;}
QTableWidget::item:selected{background:#31566b;color:white;}
QTabWidget::pane{border:1px solid #2c414f;}QTabBar::tab{background:#1d2d38;padding:9px 15px;}
QTabBar::tab:selected{background:#2b504a;color:#b8f5e2;}
QScrollArea{border:0;}QToolTip{background:#263a48;color:#edf4fa;border:1px solid #536c7e;}
'''

def title(text):
    label=QLabel(text);label.setObjectName('pageTitle');return label

def section(layout,text):
    label=QLabel(text);label.setObjectName('sectionTitle');layout.addWidget(label);return label

def move_widgets(source,target,exclude=()):
    """Transfer an existing layout without recreating its controls/signals."""
    while source.count():
        item=source.takeAt(0)
        if widget:=item.widget():
            if widget not in exclude:
                widget.setMinimumWidth(0);widget.setMaximumWidth(16777215)
                target.addWidget(widget)
        elif child:=item.layout():move_widgets(child,target,exclude)

def panel():
    content=QWidget();content.setObjectName('settingsPanel')
    body=QVBoxLayout(content);body.setContentsMargins(14,12,14,12);body.setSpacing(8)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content)
    scroll.setMinimumWidth(250);scroll.setMaximumWidth(320)
    return scroll,body

def fold(layout,text):
    button=QPushButton(text);button.setCheckable(True);layout.addWidget(button)
    content=QWidget();body=QVBoxLayout(content);body.setContentsMargins(0,0,0,0)
    content.hide();layout.addWidget(content);button.toggled.connect(content.setVisible)
    return body

class Metrics(QWidget):
    def __init__(self,labels,parent=None):
        super().__init__(parent);body=QHBoxLayout(self);body.setContentsMargins(0,4,0,8)
        self.values=[]
        for text in labels:
            card=QWidget();card.setObjectName('settingsPanel');layout=QVBoxLayout(card)
            caption=QLabel(text);caption.setWordWrap(True);layout.addWidget(caption);value=QLabel('—');value.setObjectName('metricValue')
            layout.addWidget(value);body.addWidget(card,1);self.values.append(value)
    def update_values(self,values):
        for label,value in zip(self.values,values):
            label.setText(str(value));label.setStyleSheet('color:#ef8992;' if str(value).startswith('-') else '')
