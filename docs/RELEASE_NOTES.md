# AlbionCraft 0.5.1 Beta — market capture responsiveness

Fixes a GUI freeze while incoming game-market data writes to SQLite. Reading and
merging live prices now runs in an isolated process. Bursts keep one active job
and one newest pending request; failed updates preserve the displayed prices.
Old results cannot overwrite newer API data or re-enable disabled observations.

Tray bonus polling no longer migrates tables or waits behind long database locks.
Previously confirmed bonuses retain their real expiry while the database is busy.
Receiver restarts are delayed when its port is unavailable, and callback errors
are logged in the Windows build without a console.

Validation: 247 Python tests, including 100 consecutive capture updates during an
exclusive database lock, and offline Windows executable checks with the same
responsiveness scenario, calculations and both OCR models. No game interaction or
personal-profile changes are required for the tests.

Extract the **entire** Windows ZIP into a new folder and run `AlbionCraft.exe`.
Fully exit the old version before updating. Your existing profile is retained.
If Windows startup is enabled, save that setting again after moving the folder.
The binary is unsigned.

[Usage details](https://github.com/TortVkusite/AlbionCraft/blob/v0.5.1/docs/DECISION_TOOLS.md)

---

Исправлена блокировка интерфейса при поступлении данных рынка: чтение базы и
объединение цен выполняются отдельно от окна, частые обновления объединяются.
Старые результаты не подменяют новые данные; временная блокировка базы не
отключает уже подтверждённые бонусы до окончания их срока.

Проверены 247 тестов и готовая Windows-сборка, включая поток из 100 обновлений
при занятой базе. Для обновления закрой предыдущую версию и распакуй ZIP целиком.
Личный профиль сохраняется. Обмен данными между пользователями не добавлялся.
