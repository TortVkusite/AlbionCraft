# Interface localization

AlbionCraft supports `ru` and `en`. The selected language is stored in
`settings.json` under `language`. New installations follow the system language
(Russian on Russian systems, otherwise English); existing settings default to
Russian for compatibility. The menu rebuilds the window after saving the view
and closing its receivers. Switch after an active download finishes.

`app/i18n.py` translates presentation text using the bundled
`app/config/locales/en.json`. It first checks full strings, then known fragments
in dynamic messages. Longest phrases take priority and word boundaries protect
partial words. Add exact phrases or f-string fragments to the catalog when
adding UI text. Preserve whitespace, newlines, placeholders, markup and units.
Translations work offline and do not use a translation service at runtime.

`app/i18n_widgets.py` provides explicit Qt presentation adapters. Import UI widgets
from it when their text must be localized. Text fields preserve their values;
combo item data, game IDs and stored domain keys stay stable. Set `userText=True`
on a combo containing personal names. Translate direct painter text with `tr()`.
Native Qt controls created internally may need explicit localized text.

Item names come from `research/names.json`, using `EN-US` / `RU-RU`. The name cache
is keyed by locale. Russian names in older manually entered orders can be shown
using their official English equivalents. Search can match either language or
an item ID. Recipe path keys remain Russian internally for compatibility.

Verify static labels, dynamic results, tooltips, native dialog buttons, clipboard
item names, saved profile data and language switching. Run:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```
