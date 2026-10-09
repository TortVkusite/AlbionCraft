"""Render the project's own SVG assets with Qt (no game artwork)."""
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFontDatabase,QFont
from PySide6.QtSvg import QSvgRenderer

root=Path(__file__).resolve().parents[1]
app=QApplication([])
for filename in ('segoeui.ttf','segoeuib.ttf','seguisym.ttf'):
    path=Path('C:/Windows/Fonts')/filename
    if path.exists():QFontDatabase.addApplicationFont(str(path))
app.setFont(QFont('Segoe UI',10))
for source,target,width,height in [
    ('app/assets/albioncraft.svg','app/assets/albioncraft.ico',256,256),
    ('docs/banner.svg','docs/banner.png',1280,400)]:
    image=QImage(width,height,QImage.Format_ARGB32);image.fill(0)
    painter=QPainter(image);QSvgRenderer(str(root/source)).render(painter);painter.end()
    assert image.save(str(root/target)),target
print('Brand assets rendered')
