# AlbionCraft

An independent Windows desktop companion for **Albion Online Europe, Americas and Asia**.
Available in **English and Russian**. Plan refining trips, compare crafting/trading
opportunities, track orders and character progression, and price personal loadouts.

[Download the Windows ZIP](https://github.com/TortVkusite/AlbionCraft/releases/download/v0.5.1/AlbionCraft-0.5.1-windows-x64.zip), extract the whole folder and run
`AlbionCraft.exe`. Python is not required. Use **Language / Язык → English** in the menu.
Your language is saved; new installations follow the system language. Existing
Russian profiles keep Russian until you change it. Item names use the game's
official English localization, and search accepts English, Russian and item IDs.

[Quick start](QUICK_START_EN.md) · [Русский](../README.md) · [Releases](https://github.com/TortVkusite/AlbionCraft/releases)

![Haul planner with synthetic demo prices](screenshots/trip-en.png)

Navigate between Market, Trips, Orders, Builds, Character and Island in the left sidebar.
Settings scroll independently from results, and switching pages preserves your input.
Crafting rows show material icons, quantity × unit price and the purchase subtotal
before resource returns; artifacts have a separate column.

The Island calculator covers crops, herbs and growing pasture animals for sale.
It compares repeat-cycle profit with and without Focus, reserves seeds or offspring
for the next cycle and distributes a shared Focus budget. First-cycle purchases are
shown separately. Enter feed per animal to match the game; milk, eggs, butchering,
saddling are not included. The island layout planner separately compares new
building costs and payback, and kennel animals show offspring risk. Missing prices
remain unknown. See [local decision tools](DECISION_TOOLS.md).

Source installation requires Python 3.14 x64:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m app.main
```

The trip optimizer considers carry weight, purchase budget, focus, station fees,
material chains, repeated returns, existing stock and observed market order depth.
The default budget covers the full cash operation and a silver reserve. Saved trips
reserve stock; recalculation preserves the original plan. Break-even, stress and
plan-versus-actual evidence help evaluate a result.
Sales horizons use historical daily volumes and a user-selected market share;
they are estimates, not a guarantee. Missing data stays unknown.

Select **Europe / Americas / Asia** in the main window. Each server has its own
prices, orders, stock and progression. Existing Europe profiles stay in place.
Brecilien is available, with a separate opt-in for transport comparisons.
Account for access and transport expenses in your plan.

Calculations run in background processes and large tables populate in batches.
The Destiny Board opens armor by material, equipment slot and specialization;
only the selected progress card is created. Pagination never limits calculations.

Prices come from the [Albion Online Data Project](https://www.albion-online-data.com/).
Optional local capture requires a separate Npcap installation. AlbionCraft does
not perform in-game actions or request your game password. Bank recognition is
local and covers only complete visible cells in the selected area.

Help includes opt-in tray/autoconnect/Windows startup, local market history,
reviewed production bonuses with expiry reminders, and backup/restore/diagnostics.
Bonus screenshots use local OCR and require confirmation; there is no invented
calendar or calibrated sale-time probability. No user-to-user sharing is enabled.

The Windows build stores data in `%LOCALAPPDATA%\AlbionCraft`; source installations
store data beside the source. Do not publish settings, databases or unredacted logs.
See [privacy](../PRIVACY.md), [building](BUILDING.md) and [notices](../THIRD_PARTY_NOTICES.md).

AlbionCraft's own code is MIT licensed. Third-party software and game data retain
their own terms. This project is not affiliated with Sandbox Interactive.
