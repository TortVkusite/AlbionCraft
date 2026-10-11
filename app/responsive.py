"""Bounded GUI work and virtual lists. No widgets are created in worker threads."""
from time import perf_counter
from PySide6.QtCore import QObject, QTimer, QAbstractListModel, Qt, QModelIndex, Signal
from .i18n import tr


class GuiBatch(QObject):
    finished = Signal()
    failed = Signal(str)

    def __init__(self, parent, milliseconds=8):
        super().__init__(parent)
        self.budget = milliseconds / 1000
        self.timer = QTimer(self)
        self.timer.setInterval(1)
        self.timer.timeout.connect(self.step)
        self.pending = None

    def cancel(self):
        self.timer.stop()
        self.pending = None

    def start(self, iterator):
        self.cancel()
        self.pending = iter(iterator)
        self.timer.start()

    def step(self):
        deadline = perf_counter() + self.budget
        iterator = self.pending
        try:
            while iterator is self.pending and iterator is not None:
                next(iterator)
                if perf_counter() >= deadline:
                    break
        except StopIteration:
            self.cancel()
            self.finished.emit()
        except Exception as exc:
            self.cancel()
            self.failed.emit(str(exc))


class ChoiceModel(QAbstractListModel):
    """A combo contains data rows rather than thousands of QStandardItems."""
    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.entries = tuple(entries)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        label, value = self.entries[index.row()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return tr(label)
        if role == Qt.UserRole:
            return value
        if role == Qt.ToolTipRole:
            return str(value) if value is not None else tr(label)
        return None


class CheckChoiceModel(ChoiceModel):
    def __init__(self, entries, checked=(), parent=None):
        super().__init__(entries,parent)
        self.checked=set(checked)

    def data(self,index,role=Qt.DisplayRole):
        if role==Qt.CheckStateRole and index.isValid():
            return Qt.Checked if self.entries[index.row()][1] in self.checked else Qt.Unchecked
        return super().data(index,role)

    def flags(self,index):
        return super().flags(index)|Qt.ItemIsUserCheckable

    def setData(self,index,value,role=Qt.EditRole):
        if role!=Qt.CheckStateRole or not index.isValid():return False
        key=self.entries[index.row()][1]
        if value in (Qt.Checked,Qt.Checked.value):self.checked.add(key)
        else:self.checked.discard(key)
        self.dataChanged.emit(index,index,[Qt.CheckStateRole]);return True

    def clear(self):
        self.checked.clear()
        if self.entries:self.dataChanged.emit(self.index(0),self.index(len(self.entries)-1),[Qt.CheckStateRole])


def set_choices(combo, entries):
    model = ChoiceModel(entries, combo)
    combo.setModel(model)
