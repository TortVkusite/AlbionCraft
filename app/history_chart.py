from datetime import datetime
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QPainter,QPen,QColor
from .i18n_widgets import QWidget
from .formatting import money
from .i18n import tr

class HistoryChart(QWidget):
    def __init__(self,parent=None):super().__init__(parent);self.rows=[];self.setMinimumHeight(140);self.setMaximumHeight(180)
    def set_rows(self,rows):self.rows=rows;self.update()
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.fillRect(self.rect(),QColor('#15232c'))
        if not self.rows:painter.setPen(QColor('#aabfcf'));painter.drawText(self.rect(),Qt.AlignCenter,tr('Нет наблюдений'));return
        points=[(datetime.fromisoformat(r['stamp']).timestamp(),r['price'],r['side']) for r in self.rows]
        low=min(p[1] for p in points);high=max(p[1] for p in points);start=min(p[0] for p in points);end=max(p[0] for p in points)
        w=max(1,self.width()-95);h=max(1,self.height()-42)
        painter.setPen(QColor('#aabfcf'));painter.drawText(4,22,money(high));painter.drawText(4,int(h+22),money(low))
        painter.drawText(80,self.height()-4,datetime.fromtimestamp(start).strftime('%d.%m %H:%M'));painter.drawText(self.width()-115,self.height()-4,datetime.fromtimestamp(end).strftime('%d.%m %H:%M'))
        for side,color in [('sell_price_min','#69d9bf'),('buy_price_max','#efb962')]:
            painter.setPen(QColor(color));painter.drawText(85 if side=='sell_price_min' else 220,14,tr('Продажа' if side=='sell_price_min' else 'Покупка'))
            series=sorted((t,v) for t,v,s in points if s==side);painter.setPen(QPen(QColor(color),2));last=None
            for t,value in series:
                point=QPointF(80+(t-start)/max(1,end-start)*w,20+h-(value-low)/max(1,high-low)*h)
                if last is not None:painter.drawLine(last,point)
                painter.drawEllipse(point,2,2);last=point
