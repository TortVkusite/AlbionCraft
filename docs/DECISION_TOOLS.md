# Local decision tools (0.5.0)

## Background operation

Open **Help → Background operation**. Tray, client autoconnect and Windows startup
are off until enabled. Windows startup enables tray mode, autoconnect and game
detection together. The app waits for `albion-online.exe` or `albion-online-be.exe`;
it does not launch the game. A second app launch opens the existing window.
Keep the installation folder in place after enabling startup; moving it requires
saving the startup setting again. Exit through the tray menu to close completely.

Market observations still require viewing market pages in the game. The bundled
client passively reads network messages and posts to the local receiver; Npcap is
required. Automatic connection never installs Npcap. Pause collection from the
tray. Bank/image recognition is a separate explicit action. This is not an
in-game bot: it neither places orders nor reads game process memory.

## Trip decisions

**Budget includes all expenses** is enabled by default. Available silver covers
new purchases, station charges, setup fees, per-output costs and fixed trip costs.
Sales tax is paid from sale revenue rather than reserved twice. A silver reserve
stays unspent. The alternative purchase-only budget remains available for users
who keep a separate cash balance for fees. In either case the budget is a ceiling,
not a requirement to spend everything.

The result reports required cash, cash left, break-even sale-price change,
limiting resources, and an explicit stress scenario: purchases +5%, net proceeds
−5%. This scenario is not a probability forecast. Existing stock is valued at its
saved cost; when a current bid exists, processing it is compared with selling
those used resources immediately after tax. Missing bids stay unknown.

Saving a trip in **Plan vs actual** reserves its selected stock for that character
and server. Other trips see only unreserved quantities. Release the reservation
when abandoning a plan. Completing the batch consumes stock and records XP;
closing a reconciled trip releases its reservation. Reread the bank after real
inventory changes: a reconciliation amount alone does not prove physical stock.

After partial purchases, update **Stock / bank reader** and record actual purchase
amounts in the saved trip. **Recalculate with current stock** uses current quotes,
subtracts entered spending from a full cash budget, and preserves the original
plan. Recalculations are stored as revisions. If reserve plus remaining fees no
longer fits, reduce the reserve or add available cash rather than counting future
sales as already received.

## Market history and production bonuses

Open **Help → Market history and bonuses**. Quotes and trade-volume observations
are archived locally from normal API and capture updates, separately by server,
city, item and quality. Archiving starts when this version is installed; gaps are
not interpolated. Quotes are offers, while volume history describes completed
trades. Repeated observations do not count sales twice. A median comparison needs
at least five quotes spanning seven days and does not predict future appreciation.

There is no confirmed AODP endpoint or capture message for the current bonus
calendar. Copy the game's event screenshot, use **Read clipboard image**, then
review the category, percentage, start and expiry and **Confirm bonus**. OCR is
local, includes a bundled Cyrillic model, and never applies an unreviewed result.
The reader suggests a percentage only when it is unambiguous; dates and categories
remain reviewed fields. Remove a mistaken entry before confirming its replacement.

Daily bonuses and longer events are distinct. Confirmed overlapping bonuses add;
confirming the same category and time interval again replaces that entry. Expired
bonuses stop applying automatically. Enable tray reminders for known start/end
dates. No future cycle or bonus is invented. Manual return-rate profiles retain
priority; a manually entered trip bonus replaces the automatic bonus selection.

In a trip's market window set your market share and next check-in time. Faster
and slower scenarios use twice and half the selected selling rate; the remaining
quantity assumes a stable market share. These are assumptions, not calibrated
probabilities. Observed order arrival rates are based on seen pages; an order's
disappearance does not prove a trade. Relisting fees show remaining stock × current
price × setup rate × the selected relist count; record actual fees and sale duration
when closing a trip.

After ten completed reconciliations for the same route, a median actual/planned
profit correction appears. Sequential validation uses only trips completed earlier
than the prediction being tested. Purchases, proceeds, stock, station fees and
other costs explain differences. No automatic sale-time probability is claimed.

## Island planning

Choose plot purposes first: crops, herbs, pasture or kennel. Enable **Levels from
character profile** to use recorded farming mastery/specialization. **Island plan
and payback** opens an original schematic with clickable plots; it is not a game
map. Unassigned plots are empty. The suggested count changes with island level,
but the count is editable and should be checked against the game.

Select a specific product or let the planner compare products of that purpose by
profit per day. Mark buildings already present; only new ones add construction
resources. Enter the island/upgrade purchase price separately. The comparison
without Focus also identifies faster payback; apply the selected plots to the
main calculator to allocate your Focus budget. Missing construction prices leave
total payback unknown. Daily figures assume collecting no more than once per day,
and long animal growth cycles use their actual duration.

Kennel animals use game growth, feed, offspring and care parameters. Their profit
distribution uses independent offspring outcomes and fixed prices: probability
of a profitable cycle plus 10th/50th/90th percentiles. Retained offspring replace
next-cycle purchases. Double-click a kennel result for each offspring-count outcome,
its probability and profit. This does not model future market prices. Feed remains
editable; milk, eggs, butchering and saddling are outside this calculation.
City farming bonuses are generated from a bundled `farmingmodifiers.json` snapshot.

## Backup and diagnostics

Use **Help → Backup and diagnostics**. Backups include all three server profiles,
prices/history, orders, stock and progression. Keep the ZIP private. SQLite files
are copied using the database backup API; large operations run in a subprocess.
Restores validate checksums, paths and databases, then apply on the next full
restart before opening the profile. `before-restore.zip` keeps the prior state in
the data folder. Restore preserves current background/startup consent.

A diagnostic JSON contains app/Qt versions, database health and record counts from
known tables. It excludes player names, tokens, orders, raw logs and local paths.
It is saved locally and is not uploaded. AlbionCraft has no user-to-user data
sharing or new hosted analytics service.
