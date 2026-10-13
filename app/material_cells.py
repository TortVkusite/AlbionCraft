"""Paint material breakdowns without creating thousands of cell widgets."""
from decimal import Decimal as D
from PySide6.QtCore import Qt,QRect,QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyledItemDelegate,QStyle
from .formatting import money
from .item_names import item_name
from .i18n import tr

MATERIAL_ROLE=Qt.UserRole+24

def breakdown(row,artefacts=False):
    parts=[]
    for part in row.get('parts',[]):
        ingredient=part['ingredient'];uid=ingredient.item_id
        is_artifact='ARTEFACT_' in uid or 'ARTIFACT_' in uid
        if is_artifact!=artefacts:continue
        amount=D(ingredient.amount)/max(1,row['recipe'].output_count)
        parts.append(dict(uid=uid,amount=amount,price=part.get('price'),quality=part.get('quality',1),
            tooltip=f"{item_name(uid)} • {row.get('buy','')}\n{part.get('date') or '—'} • {part.get('status','')}\n{part.get('source','')}"))
    total=sum((p['amount']*D(p['price']) for p in parts if p['price'] is not None),D(0))
    complete=all(p['price'] is not None for p in parts)
    return dict(parts=parts,total=total,complete=complete)

def tip(data):
    if not data['parts']:return '—'
    return '\n\n'.join(f"{p['tooltip']}\n{p['amount']:g} × {money(p['price'])}" for p in data['parts'])+'\n'+tr('На единицу результата; закупка до возвратов')

class MaterialDelegate(QStyledItemDelegate):
    def __init__(self,icons,parent=None):
        super().__init__(parent);self.icons=icons
        icons.ready.connect(lambda _:parent.viewport().update())
    def paint(self,painter,option,index):
        data=index.data(MATERIAL_ROLE)
        if data is None:return super().paint(painter,option,index)
        painter.save()
        background=index.data(Qt.BackgroundRole)
        painter.fillRect(option.rect,option.palette.highlight() if option.state&QStyle.State_Selected else background or QColor('#16222c'))
        x=option.rect.x()+8;y=option.rect.y()+5
        if not data['parts']:
            painter.setPen(QColor('#aabfcf'));painter.drawText(option.rect.adjusted(10,0,-4,0),Qt.AlignVCenter,'—')
        for part in data['parts']:
            self.icons.get(part['uid'],part['quality']).paint(painter,QRect(x,y,22,22))
            painter.setPen(QColor('#aac1d2'))
            painter.drawText(QRect(x+28,y,option.rect.width()-40,23),Qt.AlignVCenter,f"{part['amount']:g} × {money(part['price'])}")
            y+=25
        if data['parts']:
            font=painter.font();font.setBold(True);painter.setFont(font);painter.setPen(QColor('#edf4fa'))
            painter.drawText(QRect(x,y,option.rect.width()-16,23),Qt.AlignVCenter,('≥ ' if not data['complete'] else '')+money(data['total']) if data['complete'] or any(p['price'] is not None for p in data['parts']) else tr('Неизвестно'))
        painter.restore()
    def sizeHint(self,option,index):
        data=index.data(MATERIAL_ROLE)
        return QSize(155,30+25*len(data['parts'])) if data else super().sizeHint(option,index)
