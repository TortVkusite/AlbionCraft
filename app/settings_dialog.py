import json
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,
    QDialogButtonBox,QFormLayout,QLineEdit,QComboBox,QSpinBox,QMessageBox)
from .models import CITIES
from .calculator import DEMAND_SCALE
from .scanner import number
from PySide6.QtCore import Qt
from .ui_layout import explanation,readable_table,compact_combos,fit_window

def key(recipe): return recipe.item_id+'|'+recipe.path+'|'+str(recipe.variant)

class SettingsDialog(QDialog):
    def __init__(self,parent,recipes,settings,path):
        super().__init__(parent)
        self.setWindowTitle('RRR и расходы — ваши значения из игры')
        self.resize(900,700); self.path=path; self.settings=json.loads(json.dumps(settings))
        self.previous=None
        layout=QVBoxLayout(self)
        text=QLabel('Общий профиль применяется ко всем рецептам; индивидуальные значения имеют приоритет.\n'
                    'Заполните фактические расходы. Пустое поле означает «неизвестно».\n'
                    'RRR — итоговый процент возврата из окна крафта, уже с городским бонусом.\n'
                    'Станция — серебро за один полный рецепт. Для пути через зачарование — за крафт .0.\n'
                    'Настройки города сохраняются отдельно для каждого рецепта: уровень и зачарование влияют на расходы.')
        text.setWordWrap(True); layout.addWidget(text)
        if settings.get('auto_rules'):
            text.setText('Авто-правила включены: пустой RRR берётся из игровых городских бонусов, пустые комиссии — из справочного профиля.\n'
                'Пустая станция не считается бесплатной: выводится верхняя граница прибыли. Тариф за 100 питания задаётся в главном окне.\n'
                'Заполненные ручные значения имеют приоритет. Прочие расходы укажите явно; 0 — расходы не предусмотрены.')
        self.recipe=QComboBox()
        self.recipe.addItem('Общий профиль — для всех выбранных предметов',None)
        for r in recipes: self.recipe.addItem(f'{r.name} • {r.item_id} • {r.path} • #{r.variant+1}',r)
        layout.addWidget(self.recipe)
        self.grid=QTableWidget(6,4); self.grid.setHorizontalHeaderLabels(['Город крафта','RRR без Focus, %','RRR с Focus, %','Станция, серебро'])
        layout.addWidget(self.grid)
        form=QFormLayout(); layout.addLayout(form)
        self.fields={}
        for k,label in [('setup','Размещение любого ордера, % (buy / sell)'),('tax','Налог продажи, %'),('other','Прочие расходы за предмет / транспорт, серебро')]:
            field=QLineEdit(str(settings.get(k,''))); field.setPlaceholderText('Введите подтверждённое значение; 0 — явно без расходов')
            form.addRow(label,field); self.fields[k]=field
        explanation(layout,DEMAND_SCALE+'\nНеполная история не доказывает отсутствие продаж.','Шкала объёма продаж')
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Сохранить')
        buttons.button(QDialogButtonBox.Cancel).setText('Отмена')
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.recipe.currentIndexChanged.connect(self.change); self.change()
        readable_table(self.grid);self.grid.horizontalHeader().setStretchLastSection(True)
        compact_combos(self);fit_window(self)
    def store(self):
        if self.previous is None:return
        cities={}
        for n,city in enumerate(CITIES):
            cities[city]={k:self.grid.item(n,c).text().strip() if self.grid.item(n,c) else '' for c,k in [(1,'rrr'),(2,'focus_rrr'),(3,'station')]}
        if self.previous=='__general__':self.settings['general']=cities
        else:self.settings.setdefault('profiles',{})[self.previous]=cities
    def change(self):
        self.store(); r=self.recipe.currentData()
        self.previous=key(r) if r is not None else '__general__'
        cities=self.settings.get('profiles',{}).get(self.previous,{}) if r is not None else self.settings.get('general',{})
        for n,city in enumerate(CITIES):
            self.grid.setItem(n,0,QTableWidgetItem(city))
            self.grid.item(n,0).setFlags(self.grid.item(n,0).flags() & ~Qt.ItemIsEditable)
            for c,k in [(1,'rrr'),(2,'focus_rrr'),(3,'station')]:self.grid.setItem(n,c,QTableWidgetItem(cities.get(city,{}).get(k,'')))
        self.grid.resizeColumnsToContents()
    def save(self):
        self.store()
        for field in self.fields.values():
            if field.text().strip() and number(field.text()) is None:
                QMessageBox.warning(self,'Значение','Расходы должны быть неотрицательными числами.');return
        for profile in list(self.settings.get('profiles',{}).values())+[self.settings.get('general',{})]:
            for city in profile.values():
                for k,value in city.items():
                    n=number(value)
                    if value and (n is None or (k!='station' and n>=100)):
                        QMessageBox.warning(self,'Значение','RRR: от 0 до менее 100%; станция: неотрицательная сумма.');return
                a,b=number(city.get('rrr')),number(city.get('focus_rrr'))
                if a is not None and b is not None and b<a:
                    QMessageBox.warning(self,'Значение','RRR с Focus не может быть ниже RRR без Focus.');return
        self.settings.update({k:f.text().strip() for k,f in self.fields.items()})
        a,b=number(self.settings.get('setup')),number(self.settings.get('tax'))
        if (a is not None and a>=100) or (b is not None and b>=100) or (a is not None and b is not None and a+b>=100):
            QMessageBox.warning(self,'Комиссии','Сумма комиссий должна быть меньше 100%.');return
        self.path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
        self.accept()
