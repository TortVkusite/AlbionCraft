# AlbionCraft 0.5.0 Beta — local decision tools

- Opt-in tray mode, client autoconnect, Windows startup and game-process detection.
  A second launch opens the existing app. Capture still requires viewing market
  pages and a separately installed Npcap driver.
- Trip cash budgets include station charges, listing fees, fixed/per-output costs
  and a silver reserve. Results show break-even and stress scenarios, limiting
  resources and the alternative of selling existing stock.
- Saved trips reserve stock. Re-reading moved/merged stacks preserves reserved
  item quantities. Replanning after partial purchases retains the original plan
  and stores revisions; completing a batch consumes physical stock and records XP.
- Local quote, volume and observed-order history, isolated by server/city/item/quality.
  Median comparisons require observations over at least seven days. Sale-rate
  ranges, next check-in stock and relisting fees are explicit scenarios.
- Production bonuses can be read from a clipboard screenshot with local Cyrillic
  OCR, then reviewed and confirmed. Overlapping bonuses add, repeated confirmation
  replaces the same interval, expiry is automatic, and tray reminders are opt-in.
- Plan-versus-actual calibration after ten completed trips on the same route.
  Sequential validation uses completion order and only earlier completed results.
- Island plot purposes, a clickable original schematic, product comparisons,
  new-building costs, payback and profile-linked farming levels. Kennels include
  offspring outcome probabilities and an expected-profit distribution.
- City farming bonuses generated from game modifiers; confirmed prototype/hidden
  catalog items removed without hiding ordinary untranslated items.
- Private profile backups, validated staged restore, a pre-restore recovery copy
  and diagnostics without player names, tokens, orders, raw logs or local paths.

No user-to-user sharing or hosted analytics service was added. There is no verified
automatic bonus-calendar feed: screenshots require confirmation. Sale times are
scenarios, not calibrated probabilities. Kennel probabilities describe offspring
outcomes with fixed prices, not future market-price risk. Milk, eggs, butchering
and saddling remain outside the farming calculation.

Validation: 244 Python tests; Russian and English UI checks at 1440 × 850 and
1100 × 720; offline Windows executable checks for catalog, localization, background
scans/trips/recommendations/islands, full cash budgets, backup/diagnostics, MILP,
bank OCR and Cyrillic bonus OCR.

Extract the **entire** Windows ZIP into a new folder and run `AlbionCraft.exe`.
Python is not required. Fully exit the old version before updating. Your existing
profile remains in `%LOCALAPPDATA%/AlbionCraft`. If Windows startup is enabled,
save that setting again after moving the installation folder. The binary is unsigned.

[Usage details](https://github.com/TortVkusite/AlbionCraft/blob/v0.5.0/docs/DECISION_TOOLS.md) · [Privacy](https://github.com/TortVkusite/AlbionCraft/blob/v0.5.0/PRIVACY.md)

---

Добавлены локальная история рынка и подтверждённые бонусы со сроком действия,
фоновая работа в трее по выбору пользователя, бюджет всей ходки и резерв серебра,
резервирование запасов, повторный расчёт с сохранением исходного плана,
проверка прибыли по факту, схема острова с окупаемостью и питомник с исходами
возврата детёнышей. Есть резервные копии и обезличенная диагностика.

Обмена данными между пользователями нет. Бонусы после OCR нужно проверить и
подтвердить; автоматический календарь не заявлен. Сроки продаж — сценарии.
Проверены 244 теста, оба языка на двух размерах окна и готовая Windows-сборка.

Для обновления полностью выйди из старой версии и распакуй ZIP целиком в новую
папку. Личный профиль сохраняется. Подробности: `USER_GUIDE.md` в архиве.
