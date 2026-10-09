"""Readable arrows and no accidental number changes while scrolling."""
from pathlib import Path
from PySide6.QtWidgets import QSpinBox,QDoubleSpinBox

def style(field):
    assets=(Path(__file__).parent/'assets').as_posix()
    name='QDoubleSpinBox' if isinstance(field,QDoubleSpinBox) else 'QSpinBox'
    field.setStyleSheet(f'{name}{{padding-right:24px;}}'
        f'{name}::up-button{{subcontrol-origin:border;subcontrol-position:top right;width:22px;background:#35404c;}}'
        f'{name}::down-button{{subcontrol-origin:border;subcontrol-position:bottom right;width:22px;background:#35404c;}}'
        f'{name}::up-arrow{{image:url("{assets}/up.svg");width:10px;height:6px;}}'
        f'{name}::down-arrow{{image:url("{assets}/down.svg");width:10px;height:6px;}}')

class NumberBox(QSpinBox):
    def __init__(self,*args):super().__init__(*args);style(self)
    def wheelEvent(self,event):event.ignore()

class LargeNumberBox(QDoubleSpinBox):
    def __init__(self,*args):super().__init__(*args);style(self)
    def wheelEvent(self,event):event.ignore()
