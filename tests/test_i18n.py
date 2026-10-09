import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
import tempfile
from app.i18n import get_language,set_language,tr,translations
from app.item_names import item_name

class LocalizationTests(unittest.TestCase):
    def setUp(self):self.previous=get_language();set_language('en')
    def tearDown(self):set_language(self.previous)
    def test_exact_and_dynamic_messages(self):
        self.assertEqual(tr('Мои заказы'),'My orders')
        text=tr('Вариантов: 12 • расчётов: 8')
        self.assertIn('12',text);self.assertIn('8',text)
        self.assertFalse(any('\u0400'<=c<='\u04ff' for c in text),text)
        self.assertEqual(tr('Custom username 123'),'Custom username 123')
        self.assertEqual(tr('Журавлёв'),'Журавлёв')
    def test_official_item_names_and_language_cache(self):
        english=item_name('T2_METALBAR',False)
        self.assertEqual(english,'Copper Bar')
        set_language('ru');russian=item_name('T2_METALBAR',False)
        self.assertNotEqual(english,russian)
        set_language('en');self.assertEqual(item_name('T2_METALBAR',False),english)
        self.assertEqual(tr(russian+' • T2.0'),english+' • T2.0')
    def test_catalog_keeps_domain_keys(self):
        from app.catalog import load_catalog
        root=Path(__file__).resolve().parents[1]
        recipe=next(r for r in load_catalog(root) if r.item_id=='T2_METALBAR')
        self.assertEqual(recipe.name,'Copper Bar')
        self.assertEqual(recipe.path,'Прямой крафт')
    def test_widgets_preserve_input_and_data(self):
        from app.i18n_widgets import QApplication,QLabel,QComboBox,QLineEdit,QTableWidget
        from PySide6.QtCore import Qt
        app=QApplication.instance() or QApplication([])
        label=QLabel('Мои заказы');self.assertEqual(label.text(),'My orders')
        label.setText('Вариантов: 12');self.assertEqual(label.text(),'Variants: 12')
        combo=QComboBox();combo.addItem('Покупка','Покупка')
        self.assertEqual(combo.currentText(),'Buy');self.assertEqual(combo.currentData(),'Покупка')
        self.assertEqual(combo.findText('Покупка'),0)
        line=QLineEdit('Мой персонаж');line.setPlaceholderText('Название или ID предмета')
        self.assertEqual(line.text(),'Мой персонаж');self.assertEqual(line.placeholderText(),'Item name or ID')
        table=QTableWidget(0,1);table.setHorizontalHeaderLabels(['Предмет'])
        self.assertEqual(table.horizontalHeaderItem(0).text(),'Item')
        table.horizontalHeaderItem(0).setText('Город');self.assertEqual(table.horizontalHeaderItem(0).text(),'City')
        combo.setProperty('userText',True);combo.clear();combo.addItem('Руда');self.assertEqual(combo.currentText(),'Руда')
        from app.i18n_widgets import QDialogButtonBox
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.assertEqual(buttons.button(QDialogButtonBox.Cancel).text(),'Cancel')
    def test_saved_search_remains_bilingual(self):
        from app.item_names import matches_item
        self.assertTrue(matches_item('T2_METALBAR','Copper'))
        self.assertTrue(matches_item('T2_METALBAR','меди'))
        self.assertFalse(matches_item('T2_METALBAR','Iron'))
    def test_language_switch_preserves_settings_and_reopens(self):
        from app.i18n_widgets import QApplication
        from app.main import Window
        from PySide6.QtCore import QCoreApplication,QEvent
        import json,time
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder,patch('app.main.ROOT',Path(folder)),patch.object(Window,'stream_changed'),patch.object(Window,'local_changed'),patch.object(Window,'fetch'):
            window=Window();window.load_timer.stop();window.stream_timer.stop();window.show()
            client=Mock();client.poll.return_value=None;window.client_process=client
            window.search.setText('меди');window.settings['progress_player']='Руда'
            window.change_language('ru')
            deadline=time.monotonic()+5
            while get_language()!='ru' and time.monotonic()<deadline:app.processEvents()
            new=app._albioncraft_window;new.load_timer.stop();new.stream_timer.stop()
            self.assertEqual(get_language(),'ru');self.assertEqual(new.search.text(),'меди')
            self.assertEqual(new.settings['progress_player'],'Руда')
            self.assertIs(new.client_process,client);client.terminate.assert_not_called()
            self.assertEqual(json.loads((Path(folder)/'settings.json').read_text(encoding='utf-8'))['language'],'ru')
            new.close();new.deleteLater();app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            client.terminate.assert_called_once()
    def test_dynamic_order_time_units(self):
        self.assertEqual(tr('29 д 13 ч'),'29 d 13 h')
    def test_progress_bar_max_level_is_localized(self):
        from app.i18n_widgets import QApplication,QProgressBar
        app=QApplication.instance() or QApplication([])
        bar=QProgressBar();bar.setFormat('Максимальный уровень')
        self.assertEqual(bar.format(),'Maximum level')
    def test_russian_passthrough(self):
        set_language('ru');self.assertEqual(tr('Мои заказы'),'Мои заказы')
    def test_translation_catalog_has_no_missing_values(self):
        self.assertGreater(len(translations()),1200)
        self.assertTrue(all(isinstance(value,str) and value for value in translations().values()))
