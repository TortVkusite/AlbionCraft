from PySide6.QtCore import Qt
from .i18n_widgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QPushButton,QAbstractItemView
from .ui_layout import fit_window,readable_table
from .item_names import item_name
from .formatting import money,timestamp
from .calculator import demand_text,demand_tip
from .trip_market import turnover


class GapDetails(QDialog):
    def __init__(self,parent,row):
        super().__init__(parent);self.setWindowTitle('Дешёвая партия — '+item_name(row['item_id']));self.resize(920,690)
        body=QVBoxLayout(self)
        def text(value):
            label=QLabel(value);label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextSelectableByMouse);body.addWidget(label);return label
        text(item_name(row['item_id'])+' • '+row['city']+' • '+f'Качество: {row["quality"]}'+'\n'+'Увидено UTC: '+timestamp(row['stamp']))
        text(f'Купить всю дешёвую часть: {row["quantity"]} шт. за {money(row["purchase"])}; цена за штуку: {money(row["average"])}.\n'
            f'Следующая цена: {money(row["reference"])}; на этом уровне увидено: {row["remaining_quantity"]} шт.\n'
            f'Продажа: {money(row["target"])} × {row["quantity"]} = {money(row["revenue"])}.\n'
            f'Комиссии продажи: {money(row["fees"])}; прочие расходы: {money(row["other"])}.\n'
            f'Прибыль партии: {"≤ " if row["pending"] else ""}{money(row["profit"])} = выручка − комиссии − закупка − прочие расходы.\n'
            f'Нужно серебра до продажи: {money(row["cash"])} (закупка + размещение + прочие расходы).')
        if row['pending']:text('Прочие расходы не заданы: прибыль показана до их вычета.')
        d=row['demand'];rate=turnover(row['quantity'],d,10)
        text(demand_text(d)).setToolTip(demand_tip(d))
        text('При доле 10% продаж рынка: '+('срок неизвестен' if rate['days'] is None else f'{rate["days"]:.1f} дн.')+'. Доля — допущение, не измеренная вероятность продажи.')
        if d.get('average') is not None:text('Цена совершённых сделок за выбранный период: '+money(d['average'])+'. Более высокая цена следующего предложения не гарантирует продажу по ней.')
        table=QTableWidget(len(row['levels']),4);table.setHorizontalHeaderLabels(['Цена','Количество','Сумма','После выкупа']);table.setEditTriggers(QAbstractItemView.NoEditTriggers);readable_table(table);body.addWidget(table,1)
        from .responsive import GuiBatch
        self.paint_batch=GuiBatch(self)
        def paint():
            for n,level in enumerate(row['levels']):
                for c,v in enumerate([money(level['price']),level['quantity'],money(level['price']*level['quantity']),'Выкупить' if n<row['bought_levels'] else 'Остаётся на рынке']):table.setItem(n,c,QTableWidgetItem(str(v)))
                yield
        self.paint_batch.start(paint())
        text('Уровни получены с просмотренной страницы. Перед покупкой обнови рынок: дешёвый ордер мог исчезнуть, а на других страницах могут быть другие предложения. Новые конкуренты и реальные объёмы продаж могут изменить результат.')
        close=QPushButton('Закрыть');close.clicked.connect(self.accept);body.addWidget(close);fit_window(self)
    def done(self,result):
        self.paint_batch.cancel();super().done(result)
