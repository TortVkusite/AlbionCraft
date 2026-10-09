from .i18n_widgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QGroupBox,QCheckBox,
    QPushButton,QDialogButtonBox,QMessageBox)

QUALITY_NAMES=['Обычное','Хорошее','Выдающееся','Отличное','Шедевр']

class FilterSelection(QDialog):
    def __init__(self,parent,enchantments,qualities,prefer_upgrades=True):
        super().__init__(parent);self.setWindowTitle('Зачарования и качества');self.resize(520,450)
        layout=QVBoxLayout(self);columns=QHBoxLayout();layout.addLayout(columns)
        self.enchants={};self.qualities={}
        for title,options,selected,checks in [('Показывать зачарования',[(f'.{n}',n) for n in range(5)],enchantments,self.enchants),
            ('Использовать качества',[(label,n) for n,label in enumerate(QUALITY_NAMES,1)],qualities,self.qualities)]:
            group=QGroupBox(title);box=QVBoxLayout(group);columns.addWidget(group)
            for label,value in options:
                check=QCheckBox(label);check.setChecked(value in selected);box.addWidget(check);checks[value]=check
            all_button=QPushButton('Все');all_button.setMinimumHeight(32);box.addWidget(all_button)
            all_button.clicked.connect(lambda checked=False,items=checks:[c.setChecked(True) for c in items.values()])
        except_masterpiece=QPushButton('Все качества кроме шедевра');layout.addWidget(except_masterpiece)
        except_masterpiece.clicked.connect(lambda:[c.setChecked(q!=5) for q,c in self.qualities.items()])
        label=QLabel('«Качество неважно» выбирает минимальную цену среди отмеченных качеств.\n'
            'Старшие чары и реагенты подгружаются для сравнения; галочки выше задают только показ строк.');label.setWordWrap(True);layout.addWidget(label)
        self.prefer_upgrades=QCheckBox('Убирать младшие чары, когда старшие выгоднее')
        self.prefer_upgrades.setChecked(prefer_upgrades);layout.addWidget(self.prefer_upgrades)
        self.prefer_upgrades.setToolTip('Сравнение в городе продажи, с тем же или лучшим качеством: цена старших чар ≤ цена младших + стоимость всех ступеней зачарования. Количество рун / душ / реликвий берётся из рецепта предмета. Нужны свежие цены; при любом возрасте цен для сравнения используется 30 минут. Галочка отключает это дополнительное правило.')
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);layout.addWidget(buttons)
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject)
    def save(self):
        self.enchantment_mask=[n for n,c in self.enchants.items() if c.isChecked()]
        self.quality_mask=[n for n,c in self.qualities.items() if c.isChecked()]
        if not self.enchantment_mask or not self.quality_mask:
            QMessageBox.warning(self,'Выбор','Отметьте хотя бы одно зачарование и одно качество.');return
        self.accept()
