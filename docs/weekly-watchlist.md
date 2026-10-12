# Persistent seven-day watchlist

`tools/weekly_watchlist.py` maintains an editorial watchlist in a local SQLite database. It does not fetch market data or place orders. Refresh and independent-screen inputs are supplied as dated JSON records.

```powershell
python tools/weekly_watchlist.py .codex/watchlist.sqlite daily-packet.json --output weekly-watchlist.json
```

The packet requires `as_of` (timezone-qualified ISO-8601), `refreshes`, and `screened_candidates`. A screened candidate includes stable `identity.chain` plus `identity.asset_id`, thesis, catalyst, market-cap tier, liquidity classification, entry and invalidation triggers, confidence from 0 to 1, risk assessment, next review date, and timestamped `discovery_evidence`. Refresh records match by stable identity and may append observations, risk/confidence updates, material thesis-change annotations, and an evidence-backed transition request.

Transitions are constrained: DISCOVERED → RESEARCHING → WATCHING → TRIGGERED → PROMOTED, with invalidation, expiry, and archival edges defined in the state machine. Evidence with observation timestamps is mandatory for every state transition. The original thesis is immutable; material changes are appended with evidence. A unique chain/asset identity remains stored after expiry or invalidation, so later screened packets cannot re-add it automatically. The seven-day window includes the discovery date and the next six calendar dates; the candidate expires at the next daily run.

The output ranks active records by confidence with stable identity tie-breaking and includes the next review date and monitoring checklist. Transition history remains available through `Watchlist.history(identity)`.
