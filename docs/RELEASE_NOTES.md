# AlbionCraft 0.5.2 Beta — daily sales and discounted batches

- Fixes local history ingestion for all three game views: 24 hours, seven days and
  four weeks. Views are saved separately; the latest viewed snapshot drives demand.
- Sales volume is always units per day. Tooltips show period and bucket coverage;
  short/long windows describe different evidence, not sale-probability guarantees.
  Incomplete buckets and duplicate points are excluded; missing buckets remain unknown.
- New **Recommendations → Discounted batches** tab: observed offer-price gaps,
  quantities to buy, purchase cost, after-fee resale profit, cash limits and demand.
  Double-click to inspect all seen levels and formulas. Defaults: 10% gap, 15-minute age.
- Volume archives preserve period/bucket size so overlapping views are not added.
  Existing settings and observations are retained.

A resale scenario buys the entire cheap prefix and lists one silver below the
next observed price. That offer is not proven demand or guaranteed fair value.
The full market, fresh competition and disappeared orders may change the result.
Reopen four-week history previously discarded by the older version.

Validation: 257 Python tests; RU/EN layout checks at 1100 × 720; isolated Windows
checks for all history views, discounted-batch calculations, background market
responsiveness, optimizer, backups, bank OCR and Cyrillic bonus OCR.

Exit the previous version completely, extract the entire Windows ZIP and run
`AlbionCraft.exe`. Your existing profile is retained. Save the Windows-startup
setting again if moving the installation folder. The binary is unsigned.

[Usage details](https://github.com/TortVkusite/AlbionCraft/blob/v0.5.2/docs/DECISION_TOOLS.md)

---

История рынка теперь принимается за сутки, неделю и 4 недели. В таблице всегда
показаны продажи за день, под числом — период; при наведении — полнота данных.
В рекомендациях добавлены «Дешёвые партии»: разрывы между увиденными уровнями
цен, количество, закупка, комиссии, прибыль и подробный расчёт по двойному клику.

Проверены 257 тестов, оба языка и Windows-сборка. Старую историю за 4 недели нужно
открыть в игре заново: предыдущая версия её не сохраняла. Высокая следующая цена
является сценарием перепродажи, а не обещанием прибыли или быстрой продажи.
