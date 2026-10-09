"""Responsive control rows and consistent readable tables."""
from PySide6.QtCore import QRect,QSize,Qt
from PySide6.QtWidgets import QLayout,QLabel,QSizePolicy,QComboBox,QScrollArea


class FlowLayout(QLayout):
    def __init__(self,parent=None,spacing=8):
        super().__init__(parent);self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(spacing)
    def addItem(self,item):self.items.append(item)
    def addWidget(self,widget,stretch=0):super().addWidget(widget)
    def addStretch(self,*args):pass
    def count(self):return len(self.items)
    def itemAt(self,n):return self.items[n] if 0<=n<len(self.items) else None
    def takeAt(self,n):return self.items.pop(n) if 0<=n<len(self.items) else None
    def expandingDirections(self):return Qt.Horizontal
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),False)
    def minimumSize(self):
        visible=[i for i in self.items if not i.isEmpty()]
        return QSize(max((i.minimumSize().width() for i in visible),default=0),max((i.minimumSize().height() for i in visible),default=0))
    def sizeHint(self):return QSize(sum(i.sizeHint().width()+self.spacing() for i in self.items),self.heightForWidth(1400))
    def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect,True)
    def arrange(self,rect,apply):
        rows=[];row=[];width=0;spacing=self.spacing()
        for item in self.items:
            if item.isEmpty():continue
            size=item.sizeHint().expandedTo(item.minimumSize()).boundedTo(item.maximumSize())
            w=min(size.width(),rect.width())
            if row and width+spacing+w>rect.width():rows.append(row);row=[];width=0
            row.append((item,w,size.height()));width+=w+(spacing if len(row)>1 else 0)
        if row:rows.append(row)
        y=rect.y()
        for row in rows:
            used=sum(w for _,w,_ in row)+spacing*(len(row)-1)
            remaining=max(0,rect.width()-used);row=[list(entry) for entry in row]
            while remaining:
                expanding=[entry for entry in row if entry[0].expandingDirections()&Qt.Horizontal and entry[1]<entry[0].maximumSize().width()]
                if not expanding:break
                share=max(1,remaining//len(expanding))
                for entry in expanding:
                    delta=min(share,remaining,entry[0].maximumSize().width()-entry[1]);entry[1]+=delta;remaining-=delta
            x=rect.x()
            height=max(max(h,item.heightForWidth(w) if item.hasHeightForWidth() else h) for item,w,h in row)
            for item,w,h in row:
                if apply:item.setGeometry(QRect(x,y,w,height))
                x+=w+spacing
            y+=height+spacing
        return max(0,y-rect.y()-spacing)


def explanation(layout,text,title='Как это работает'):
    """Keep full guidance accessible without consuming the whole window."""
    from PySide6.QtWidgets import QPushButton
    button=QPushButton('+ '+title);button.setToolTip(text)
    label=QLabel(text);label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    panel=QScrollArea();panel.setWidgetResizable(True);panel.setWidget(label)
    panel.setMinimumHeight(60);panel.setMaximumHeight(120);panel.hide()
    button.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Fixed)
    button.clicked.connect(lambda: (panel.setVisible(not panel.isVisible()),button.setText(('− ' if panel.isVisible() else '+ ')+title)))
    layout.addWidget(button);layout.addWidget(panel)
    return label


def readable_table(table):
    header=table.horizontalHeader();header.setMinimumSectionSize(72)
    header.setDefaultSectionSize(130)
    for col in range(table.columnCount()):
        item=table.horizontalHeaderItem(col)
        if item:
            text=item.text();item.setToolTip(text)
            width=max(table.fontMetrics().horizontalAdvance(line) for line in text.splitlines())+28
            table.setColumnWidth(col,min(360,max(95,width)))
    table.setMinimumHeight(100)
    table.setWordWrap(True);table.setTextElideMode(Qt.ElideRight)
    table.verticalHeader().setDefaultSectionSize(38)


def compact_combos(window):
    """Long item names stay available without widening the entire dialog."""
    for combo in window.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(16)
        combo.setToolTip(combo.currentText())
        combo.currentTextChanged.connect(combo.setToolTip)


def fit_window(window,width=None,height=None):
    screen=window.screen()
    if not screen:return
    area=screen.availableGeometry()
    window.resize(min(width or window.width(),max(640,area.width()-32)),min(height or window.height(),max(480,area.height()-64)))
