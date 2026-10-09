# Сторонние компоненты

MIT в корне относится к исходному коду и собственному оформлению AlbionCraft.
Игровые данные, изображения, Python и сторонние библиотеки сохраняют свои лицензии
и уведомления об авторских правах. Полные тексты для Windows-сборки включены в
`_internal/licenses`; перечень версий находится в `DEPENDENCIES.txt` внутри этой папки.

| Компонент | Источник / условия |
|---|---|
| Python | [PSF license](https://docs.python.org/3/license.html) |
| PySide6 / Shiboken / Qt | [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html), LGPLv3 и лицензии отдельных компонентов |
| SciPy / NumPy | [SciPy](https://github.com/scipy/scipy), [NumPy](https://github.com/numpy/numpy), BSD и уведомления встроенных библиотек |
| RapidOCR / ONNX Runtime | [RapidOCR](https://github.com/RapidAI/RapidOCR), [ONNX Runtime](https://github.com/microsoft/onnxruntime), Apache-2.0 / MIT и уведомления моделей |
| PyInstaller | [Лицензия с исключением для собранных приложений](https://pyinstaller.org/en/stable/license.html) |
| Локальный клиент захвата | Модификация [Albion Data Client](https://github.com/ao-data/albiondata-client), MIT; исходники в `vendor/albion-data-client`, исходная лицензия сохранена |
| Рецепты, названия, прогрессия | [ao-bin-dumps](https://github.com/ao-data/ao-bin-dumps); игровые данные Albion Online, права соответствующих правообладателей |
| Цены и история | [Albion Online Data Project](https://www.albion-online-data.com/) |
| Иконки предметов | Загружаются по запросу с `render.albiononline.com`; игровые материалы Sandbox Interactive, не MIT-код AlbionCraft |

Qt поставляется как динамические DLL в папке `_internal/PySide6`: их можно заменить
совместимыми версиями и пересобрать приложение из опубликованного исходного кода.
AlbionCraft не ограничивает изменение библиотек и обратную разработку для отладки
таких изменений. Исходный код Qt/PySide доступен через
[Qt 6.11](https://download.qt.io/archive/qt/6.11/) и
[PySide 6.11](https://download.qt.io/official_releases/QtForPython/pyside6/).

Npcap не включён в архив. По запросу пользователя приложение загружает официальный
установщик и открывает мастер; его отдельная лицензия применяется при установке.
AlbionCraft — независимый проект, не официальный продукт Sandbox Interactive.
