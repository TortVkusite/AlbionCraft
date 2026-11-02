# Peer exchange architecture / 0.6

Opt-in Iroh 1.2.0 Python FFI, QUIC/TLS. No AlbionCraft-hosted server. The public
Iroh discovery/relay infrastructure can be used and has no uptime guarantee.
An offline-only test uses the minimal preset and explicit loopback addresses.

One private group per region profile. Invitations contain a group ID, a random
256-bit group key and an Iroh endpoint ticket. Challenge-response HMAC proofs
bind the group secret to a random server nonce, roles and both TLS endpoint IDs.
Invitations are credentials; do not post them publicly. Local endpoint seed and
group credentials are protected with the current Windows user's DPAPI. Neither
credential is written to logs, outgoing market records or backup exports.

An immutable record contains version, group, origin endpoint ID, persistent
sequence, region, kind, original observation time and an allowlisted market page.
The origin signs the canonical JSON using its Iroh Ed25519 key. ID is SHA256 of
the signed envelope. Forwarders preserve the entire original envelope. This
authenticates origin and integrity, not the correctness of an observed price.

Only local_quotes and local_history_windows are read, through a read-only SQLite
connection. No raw client packets, screenshots, bank, player DB, personal order
table or settings payload are accepted by the market schema. Published/received
records and durable receipts use a separate peer-sync.sqlite WAL database.

Peers pull inventories before payloads, paging 128 IDs at a time. A receiver
reserves each in-flight ID across connections; the event primary key makes
duplicate application idempotent even if redundant network delivery races occur.
ACK follows validation and commit. Missing ACK does not discard the source copy.
Peers exchange authenticated contact lists (up to 32) to permit forwarding when
the original sender goes offline. Contacts retry every few seconds.

Inventory advertises only the newest observed version of each region/item/city/
quality/side page (or history period). Observation time, then ID, deterministically
break ties across origins. Sequence numbers are only meaningful within an origin;
forward/receive time never replaces observation time. Empty/expired orders do not
become claims of a fully empty book; captured pages remain partial observations.

Keep market pages for 24h, up to 10,000 current pages and 64 MiB of payload;
discard superseded versions and expired receipts. Bounds describe payload, not
SQLite file size or WAL overhead. One envelope is capped at 900 KB and each
length-prefixed network frame at 1 MB. Read/write and connect operations time out;
at most four outgoing synchronizations and 40 tracked tasks are allowed.

Network and publishing run in a dedicated QThread/asyncio loop. GUI notifications
are coalesced; local database reads use short timeouts and retry. Calculators
merge observations by original time and show P2P sources without overwriting
the player's local capture. Already-open calculator snapshots require refresh.

Blocking is local direct-connection denial; it is not global membership
revocation or deletion of distributed copies. Replace the group secret by
leaving/recreating the group if membership must change. Historical data received
from an origin may be forwarded by another group member.

## Repeatable checks

```
.venv/Scripts/python.exe -m unittest tests.test_peer_exchange -v
.venv/Scripts/python.exe scripts/peer_sandbox.py build/peer-sandbox-report.json
```

Frozen Windows build:

```
AlbionCraft.exe --peer-sandbox C:/path/to/report.json
```

The sandbox creates three temporary profiles, accepts a real loopback HTTP market
upload through the application's parser, runs three independent encrypted Iroh
processes, stops/restarts peers and validates forwarding, persistence and
idempotence. It never uses the user's real data or public relays. Multi-provider
NAT traversal and sustained public-relay availability require separate field tests.
