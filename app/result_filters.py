from decimal import Decimal,InvalidOperation
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QComboBox,QDialogButtonBox,QLabel,QMessageBox

def reliability(row):
    problems=[]
    if row['reasons']:problems+=row['reasons']
    if row.get('pending_costs'):problems.append('Не учтены: '+', '.join(row['pending_costs']))
    if problems:return 'Неполный расчёт','\n'.join(dict.fromkeys(problems))
    quotes=[(p['status'],p.get('source','')) for p in row['parts']]+[(row['sale_status'],row.get('sale_source',''))]
    flags=[]
    for status,source in quotes:
        if 'устарело' in status or 'будущем' in status:flags.append('Старые или недопустимые даты котировок')
        if 'UTC требует' in status:flags.append('Часовой пояс котировки не подтверждён')
        if 'NATS' in source:flags.append('Неполный срез наблюдавшихся ордеров NATS')
        if 'Из твоей игры' in source:flags.append('Просмотренные в игре ордера: полнота рынка и доступность объёма не подтверждены')
        if 'сохранённая' in source:flags.append('Использована сохранённая котировка')
    if row['demand']['kind']=='unknown':flags.append('Нет истории продаж')
    if any('справочный профиль' in issue for issue in row.get('issues',[])):flags.append('Комиссии из справочника требуют проверки в игре')
    if any('Общий профиль RRR' in issue for issue in row.get('issues',[])):flags.append('Общий профиль возврата / станции требует проверки для этого рецепта')
    if flags:return 'Требует проверки','\n'.join(dict.fromkeys(flags))
    return 'Данные полные','Цены и расходы заполнены; котировки в пределах заданного возраста. Это оценка полноты данных, а не гарантия сделки.'

def in_bounds(row,settings):
    limits=settings.get('result_limits',{});group=limits.get('scenario','base');x=row.get(group)
    for key,value in [('profit',x.get('profit') if x else None),('roi',x.get('roi') if x else None),('purchase',row.get('purchase_cost') if row.get('purchase_complete',True) else None)]:
        for direction in ['min','max']:
            limit=limits.get(key+'_'+direction)
            if limit in (None,''):continue
            if value is None:return False
            limit=Decimal(str(limit))
            if direction=='min' and value<limit or direction=='max' and value>limit:return False
    return True

class BoundsDialog(QDialog):
    def __init__(self,parent,limits):
        super().__init__(parent);self.setWindowTitle('Диапазоны прибыли и закупки');layout=QVBoxLayout(self)
        label=QLabel('Пустое поле — без ограничения. Границы включены.\nПрибыль и закупка — за один предмет. «≤» остаётся верхней границей до неизвестных расходов.');label.setWordWrap(True);layout.addWidget(label)
        form=QFormLayout();layout.addLayout(form);self.scenario=QComboBox();self.scenario.addItem('Без Focus','base');self.scenario.addItem('С Focus','focus');self.scenario.setCurrentIndex(max(0,self.scenario.findData(limits.get('scenario','base'))));form.addRow('Сценарий:',self.scenario)
        self.fields={}
        for key,label in [('profit','Прибыль, серебро'),('roi','ROI, %'),('purchase','Закупка, серебро')]:
            for suffix,title in [('min','от'),('max','до')]:
                field=QLineEdit(str(limits.get(key+'_'+suffix,'')));field.setPlaceholderText('Не ограничивать');form.addRow(label+' — '+title,field);self.fields[key+'_'+suffix]=field
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);layout.addWidget(b);b.accepted.connect(self.save);b.rejected.connect(self.reject)
    def save(self):
        values={'scenario':self.scenario.currentData()}
        try:
            for key,field in self.fields.items():
                text=field.text().strip().replace(',','.')
                if text:
                    value=Decimal(text)
                    if not value.is_finite() or key.startswith('purchase') and value<0:raise ValueError()
                    values[key]=str(value)
            for key in ['profit','roi','purchase']:
                if key+'_min' in values and key+'_max' in values and Decimal(values[key+'_min'])>Decimal(values[key+'_max']):raise ValueError()
        except (InvalidOperation,ValueError):QMessageBox.warning(self,'Диапазон','Введите числа; нижняя граница должна быть не выше верхней.');return
        self.limits=values;self.accept()
