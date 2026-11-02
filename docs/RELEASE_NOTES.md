# AlbionCraft 0.7.0 Beta — sale forecasts & private market sharing

Plan a batch with its uncertainty visible: this release adds conditional sale-time
forecasts and publishes the private peer-sharing work previously available locally.

## Highlights

- **Batch sale forecasts:** probability of completing a batch by a chosen time,
  median completion, 10–90% time interval, expected remaining units and sensitivity
  to your assumed share of market sales. RU/EN UI with an inspectable probability curve.
- **Evidence gates:** complete non-overlapping buckets, separate 24h/7d/28d windows,
  source/coverage metadata and suppression of sparse or stale estimates.
- **Private peer groups:** encrypted Iroh connections, durable signed observations,
  inventory-first synchronization, offline forwarding and deduplication.
- **A repeatable sandbox:** three separate app processes verify peer exchange on
  one PC without touching the real profile. Numerical simulation checks forecast math.
- **Project presentation:** a new English README, Russian overview, architecture
  diagrams, model equations, reproducible checks and synthetic demo screenshots.

## Start here

Download `AlbionCraft-0.7.0-windows-x64.zip`, extract the entire folder and run
`AlbionCraft.exe`. Python is included. Optional in-game capture requires Npcap.

Open **Help → Batch sale forecast**, or use the button in item/discounted-batch
details. Trip sell-order rows open it on double-click. Refresh market history in
the main workspace or view it in-game with local capture enabled before forecasting.

For sharing, open **Help → Share market data with friends**, create a group and
send its invitation privately. A group ID alone is not a connection invitation.

## What the probabilities mean

Forecasts assume a competitive price and the selected personal market share.
They do not measure your actual queue priority, future competitors or hourly player
activity. Personal accuracy is not calibrated. The simulation verifies the stated
model, not real-world prediction accuracy. See [the methodology](https://github.com/TortVkusite/AlbionCraft/blob/v0.7.0/docs/SALE_FORECAST.md).

## Verification and update notes

- 289 automated tests, seeded 100,000-sample numerical check, RU/EN layout review.
- Source and frozen-EXE checks cover the forecast subprocess, optimizer, OCR,
  private peer sandbox and responsiveness under capture-write contention.
- Close the old application completely before replacing files. Profiles remain
  in `%LOCALAPPDATA%\AlbionCraft`; keep the whole extracted application folder.
- Windows x64 is verified; binaries are unsigned. Cross-provider peer connectivity
  still needs field testing. Public Iroh relays are limited and have no uptime guarantee.
- Source, Windows ZIP and `SHA256SUMS.txt` are attached. No player data, credentials
  or demo peer profiles are included in the release archives.

---

**По-русски:** добавлен прогноз продажи партии: вероятность к сроку, медиана,
диапазон времени и остаток при выбранной доле рынка. При недостатке свежей истории
проценты не показываются. Это условная модель, не подтверждённая точность личных
продаж. Также опубликован закрытый P2P-обмен с друзьями и встроенной песочницей.
Новая документация объясняет устройство проекта, формулы и проверки.
