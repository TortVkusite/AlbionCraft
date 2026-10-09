from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from .i18n_widgets import QApplication,QTableWidget

SEARCH_NAME_ROLE=Qt.UserRole+2

class SearchTable(QTableWidget):
    def keyPressEvent(self,event):
        if event.matches(QKeySequence.Copy):
            rows=sorted({index.row() for index in self.selectedIndexes() if index.column()==0})
            names=[cell.data(SEARCH_NAME_ROLE) for n in rows if (cell:=self.item(n,0)) and cell.data(SEARCH_NAME_ROLE)]
            if names:
                QApplication.clipboard().setText('\n'.join(dict.fromkeys(names)));event.accept();return
        super().keyPressEvent(event)
