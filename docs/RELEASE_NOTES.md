# AlbionCraft 0.4.0 Beta — dashboard and islands

- Left navigation keeps Market, Trips, Orders, Builds, Character, Island and settings in one window. Settings scroll independently from results.
- Crafting rows show material icons, quantity × unit price and purchase subtotals before returns. Artifacts appear separately; detailed columns remain available.
- Trips separate resource selection from the plan and show profit, new purchases, weight and Focus in summary cards. Existing optimization formulas and saved profiles remain compatible.
- Island calculator covers crops, herbs and growing pasture animals for sale. It compares repeat-cycle profit with and without Focus, keeps seeds/offspring for the next cycle and allocates a shared Focus budget. First-cycle purchases are separate.
- Island calculations run in a background process. Missing prices remain unknown; farming settings are saved per server.

For animals, check the editable feed quantity against the game. Milk, eggs,
butchering, saddling and island/building costs are not included.

Validation: 231 Python tests; Russian and English interface checks at 1440 × 850
and 1100 × 720; offline checks in the Windows executable for catalog, localization,
MILP, OCR, market scans, trips, recommendations and island calculations.

Extract the entire Windows ZIP into a new folder and run `AlbionCraft.exe`.
Python is not required. Close the previous version before updating; the existing
profile is reused from `%LOCALAPPDATA%/AlbionCraft`. Use the bundled capture client
through **Connect client…**; Npcap remains a separate installation.

This remains a beta. Profit, yields and sale times are estimates based on available
quotes and your settings. The Windows binary is unsigned.

---

Обновлён интерфейс: разделы слева, настройки отдельно от результатов, материалы
с иконками и ценами прямо в таблице. Ходки разделены на выбор ресурсов и план;
над результатом видны прибыль, закупка, вес и фокус.

Добавлен «Остров»: культуры, травы и выращивание животных на продажу, возврат
семян/приплода, корм, Premium и распределение фокуса. Начальная закупка показана
отдельно от прибыли повторного цикла. Корм на животное сверь с игрой; молоко,
яйца, разделка, седлание и строительство пока не включены.

Для обновления закрой старую версию и распакуй ZIP целиком в отдельную папку.
Личный профиль сохраняется. Проверены 231 тест и оба языка на двух размерах окна.
