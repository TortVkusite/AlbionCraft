# AlbionCraft 0.3.0 Beta — servers, Brecilien and responsive lists

- Select Europe, Americas or Asia. Prices, orders, stock and progression are isolated per server; existing Europe profiles stay in place.
- Brecilien is available in city selectors, quotes, own orders and production bonuses. Transport comparisons require a separate opt-in; route expenses remain part of your scenario.
- Main scans, haul optimization, build variants, recommendations and Fame Credit allocation run in background processes. Changing filters cancels stale calculations.
- Large tables load in batches. Armor navigation follows material → equipment slot → specialization; weapons follow family → item. Only the selected progress card is created.
- History lookup reads recent records for selected items. Sorting and optimization include all selected items, across every page.
- Updated local capture client attaches server identity. Data from an unknown or mismatched game server is rejected before storage.

Extract the entire Windows ZIP into a new folder and run `AlbionCraft.exe`.
Python is not required. Your existing Windows profile is reused from
`%LOCALAPPDATA%/AlbionCraft`. Close the previous version before updating.
Use the bundled client through **Connect client…**; Npcap remains a separate installation.

Validation: 221 Python tests, Go client tests, 24 interface states in both languages,
and an offline stress check with all armor and 5,000 orders. On the development
computer, the armor scan took about 2 seconds and order loading about 2.3 seconds;
UI events continued throughout. Performance depends on your computer and selection.
Live game capture on Americas/Asia has not been exercised here.

This remains a beta. Quotes and observed volumes may be incomplete or outdated.
Profit and sale times are estimates. The Windows binary is unsigned.

---

Добавлены **Europe / Americas / Asia** и **Brecilien**. Данные серверов разделены,
прежний профиль Europe сохраняется. Тяжёлые расчёты выполняются в фоне,
таблицы заполняются порциями. Броня разделена по материалу и части экипировки;
специализация открывается при выборе. Поиск и страницы сохраняют доступ ко всем узлам.

Для обновления закрой старую версию и распакуй ZIP целиком в отдельную папку.
Запускай обновлённый клиент через приложение. Сервер игры должен совпадать с выбранным:
данные другого или неизвестного сервера в текущий профиль не записываются.
Для Brecilien расходы и доступность перевозки учитывай в своём сценарии.
