from .calculator import demand_tip
from .i18n_widgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QSpinBox,QFormLayout,QAbstractItemView,QPushButton
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from .formatting import money,roi,timestamp
from .scanner import number
from .item_names import item_name,recipe_variant
from .filter_dialog import QUALITY_NAMES

class Details(QDialog):
    def __init__(self,parent,row,quality,settings):
        super().__init__(parent); self.setWindowTitle('Подробный расчёт — '+row['recipe'].name); self.resize(1100,800)
        from .i18n_widgets import QWidget,QScrollArea
        from .ui_layout import fit_window,readable_table
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);outer.addWidget(scroll)
        content=QWidget();layout=QVBoxLayout(content);scroll.setWidget(content);r=row['recipe']
        batch=QPushButton('Партия / опыт / Focus');layout.addWidget(batch)
        def open_batch():
            from .paths import data_root
            from .crafter_dialog import CrafterDialog
            CrafterDialog(parent,getattr(parent,'root',None) or data_root(),parent.recipes,row).exec()
        batch.clicked.connect(open_batch)
        heading=QLabel(f'{item_name(r.item_id)} • {QUALITY_NAMES[quality-1]}\n{r.path}, рецепт #{r.variant+1}: {recipe_variant(r)}\n'
            f'Покупка: {row["buy"]} → '+('зачарование' if row.get('activity')=='enchant' else 'крафт')+f': {row["craft"]} → продажа: {row["sell"]}')
        heading.setWordWrap(True);heading.setToolTip(r.item_id);layout.addWidget(heading)
        output=r.output_count if row.get('activity','craft')=='craft' else 1
        if output>1:layout.addWidget(QLabel(f'Выход рецепта: {output} шт. Ресурсы ниже — на весь рецепт; закупка, прибыль и ROI в основной таблице — на 1 шт.'))
        sources=[p.get('source','') for p in row['parts']]+[row.get('sale_source','')]
        if any(s.startswith('Из твоей игры') for s in sources):layout.addWidget(QLabel('● Получено из твоей игры. Учтены просмотренные ордера; это не полный рынок.'))
        table=QTableWidget(len(row['parts'])+1,7)
        table.setMinimumHeight(min(260,60+32*(len(row['parts'])+1)))
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setHorizontalHeaderLabels(['Ресурс / результат','Кол-во','Цена','Дата','Возврат','Стоимость','Состояние'])
        for n,p in enumerate(row['parts']):
            i=p['ingredient'];name=item_name(i.item_id)
            if i.preserve_quality:name+=' • '+QUALITY_NAMES[p.get('quality',quality)-1]
            values=[name,i.amount,money(p['price']),timestamp(p['date']),'RRR' if i.returnable else 'Нет',money(p['price']*i.amount if p['price'] is not None else None),p['status']]
            for c,v in enumerate(values):
                cell=QTableWidgetItem(str(v));table.setItem(n,c,cell)
                if c in (2,5):cell.setForeground(QColor('#b8bec6'))
                if ('устарело' in p['status'] or 'будущем' in p['status']) and c==3:cell.setForeground(QColor('#ff7777'))
                cell.setToolTip(f'{i.item_id}\n{p.get("source","AODP API")} • {p.get("side","sell_price_min")} • {row["buy"]} • {p["date"]}')
        n=len(row['parts'])
        for c,v in enumerate([item_name(r.item_id),output,money(row['sale']),timestamp(row['sale_date']),'—',money(row['sale']*output if row['sale'] is not None else None),row['sale_status']]):
            cell=QTableWidgetItem(str(v));table.setItem(n,c,cell)
            if c in (2,5):cell.setForeground(QColor('#b8bec6'))
            if ('устарело' in row['sale_status'] or 'будущем' in row['sale_status']) and c==3:cell.setForeground(QColor('#ff7777'))
            cell.setToolTip(f'{r.item_id}\n{row.get("sale_source","AODP API")} • {row["sale_side"]} • {row["sell"]} • {row["sale_date"]}')
        table.resizeColumnsToContents();readable_table(table);table.setColumnWidth(0,280);table.setColumnWidth(3,160)
        table.setMinimumHeight(min(300,60+40*(len(row['parts'])+1)))
        table.horizontalHeader().setStretchLastSection(True);layout.addWidget(table)
        observations=[]
        local_lines=[]
        for uid,p in [(part['ingredient'].item_id,part.get('local')) for part in row['parts']]+[(r.item_id,row.get('sale_local'))]:
            if not p:continue
            for side,label in [('sell_price_min','Предложение продажи'),('buy_price_max','Заказ покупки')]:
                if p.get(side):local_lines.append(f'{item_name(uid)}: {label} {money(p[side])}, количество {p[side+"_amount"]}, увидено {timestamp(p[side+"_date"])} UTC')
        if local_lines:
            label=QLabel('Из твоей игры (просмотренная страница; доступность ордеров требует проверки):\n'+'\n'.join(dict.fromkeys(local_lines)))
            label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(label)
        for uid,p in [(part['ingredient'].item_id,part.get('nats')) for part in row['parts']]+[(r.item_id,row.get('sale_nats'))]:
            if not p:continue
            for side,label in [('sell_price_min','Предложение продажи'),('buy_price_max','Заказ покупки')]:
                if p.get(side):observations.append(f'{item_name(uid)}: {label} {money(p[side])}, количество в ордере {p[side+"_amount"]}, наблюдение {timestamp(p[side+"_date"])}')
        if observations:
            label=QLabel('Дополнительные наблюдения NATS (не весь рынок; ордер мог быть исполнен или отменён):\n'+'\n'.join(dict.fromkeys(observations)))
            label.setWordWrap(True);label.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(label)
        lines=[]
        if output>1:lines.append('Все денежные формулы ниже — на 1 шт. результата. Станция на рецепт делится на выход; прочие расходы заданы на 1 шт.')
        activity=row.get('activity','craft')
        if row.get('pending_costs'):
            lines.append('ВЕРХНЯЯ ГРАНИЦА ПРИБЫЛИ: не вычтены '+', '.join(row['pending_costs'])+'. Фактическая прибыль может быть ниже.')
        for name,key,rrr in [('Без Focus','base','rrr'),('С Focus','focus','focus_rrr')]:
            if activity!='craft' and key=='focus':continue
            x=row[key]
            if x is None:lines.append(name+': расчёт недоступен');continue
            if activity in ('flip','resale'):
                lines.append(f'Покупка {money(x["buy_price"])} + размещение buy order {money(x["buy_setup_fee"])} + прочие расходы {money(x["other"])} = затраты {money(x["cost"])}\n'
                    f'Продажа {money(x["sale"])} − размещение sell order {money(x["setup_fee"])} − налог {money(x["sales_tax"])} − затраты {money(x["cost"])} = чистая прибыль {money(x["profit"])}\n'
                    f'ROI {roi(x["roi"])}; капитал {money(x["capital"])}')
                continue
            rate=number(row['profile'].get(rrr))
            lines.append(f'{name}: RRR '+(f'{rate:.3f}%' if rate is not None else '?')+'\n'+
                f'Материалы {money(x["raw"])} − возврат {money(x["returned"])} = {money(x["effective"])}\n'
                f'+ невозвращаемые / обязательные расходы {money(x["fixed"])} + станция {money(x["station"])} = себестоимость {money(x["cost"])}\n'
                f'Продажа {money(x["sale"])} − комиссии {money(x["fees"])} − себестоимость {money(x["cost"])} = прибыль {money(x["profit"])}; ROI {roi(x["roi"])}\n'
                f'Комиссии: размещение {money(x["setup_fee"])} + налог {money(x["sales_tax"])}\n'
                f'Капитал {money(x["capital"])}; прибыль на 1 млн {money(x["per_million"])}')
        formulas=QLabel('\n\n'.join(lines));formulas.setWordWrap(True);formulas.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(formulas)
        if activity=='craft' and row.get('max_station_fee') is not None:
            text='Порог окупаемости станции без Focus: '+money(row['max_station_fee'])+' серебра на 1 шт.'
            if row.get('max_station_rate') is not None:text+=' / тариф '+money(row['max_station_rate'])+' за 100 питания'
            text+='\nПитание на рецепт: '+(f'{float(r.nutrition):g}' if r.nutrition else 'не подтверждено')+'. Прочие неизвестные расходы уменьшают этот предел.'
            label=QLabel(text);label.setWordWrap(True);layout.addWidget(label)
        form=QFormLayout();layout.addLayout(form)
        focus=QSpinBox();focus.setRange(0,1000000);focus.setSpecialValueText('Не указан');form.addRow('Фактический расход Focus на этот предмет:',focus)
        value=QLabel('');layout.addWidget(value)
        def update():
            n=focus.value()
            focus.setStyleSheet('color:#ff7777;' if n>10000 else '')
            if not n or not row['focus']:value.setText('Прибыль / Focus: нет данных');return
            x=row['focus']['profit']/n;extra=(row['focus']['profit']-row['base']['profit'])/n if row['base'] else None
            value.setText(f'Прибыль / Focus: {x:.2f}; дополнительная прибыль от Focus / Focus: '+(f'{extra:.2f}' if extra is not None else '—'))
        focus.valueChanged.connect(update);update()
        if activity!='craft':focus.hide();value.hide();form.labelForField(focus).hide()
        d=row['demand'];info=QLabel(f'История: {d["total"]} ед. за {d.get("period_days",7)} дн.; {d["per_day"]:.1f}/сутки.\n'+
            demand_tip(d)+'\n'+
            'Sell order — ориентир предложения. Возврат оценивается для повторного использования.\n'
            'Даты без timezone предварительно считаются UTC. Бонусы: авто-правила либо ручной профиль.\n'+
            '\n'.join(dict.fromkeys(row['reasons']+row['issues'])))
        info.setWordWrap(True);layout.addWidget(info)
        close=QPushButton('Закрыть');close.clicked.connect(self.accept);outer.addWidget(close)
        fit_window(self)
