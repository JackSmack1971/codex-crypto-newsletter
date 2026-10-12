# Historical research accountability

`tools/research_accountability.py` records published daily picks and watchlist candidates in an append-only JSON Lines ledger. Each publication freezes its timestamp, stable asset identity, original thesis, directional forecast, observed reference price and venue, confirmation and invalidation conditions, catalyst, and expiration. Later price observations and thesis/catalyst outcomes are separate events. Every event is chained to the preceding SHA-256 digest; the reader rejects edits, deletions, or reordering. This detects accidental or unsophisticated rewriting, but is not a signature or protection against an operator who rewrites and rehashes the whole ledger.

```powershell
python tools/research_accountability.py publish .codex/accountability.jsonl publication.json
python tools/research_accountability.py observe .codex/accountability.jsonl pick-2026-10-11 observation.json
python tools/research_accountability.py update .codex/accountability.jsonl pick-2026-10-11 outcome.json
python tools/research_accountability.py report .codex/accountability.jsonl --as-of 2026-11-08T00:00:00Z
```

`publish` rejects a reused record ID. A publication contains `record_id`, `kind` (`daily_pick` or `watchlist_candidate`), timezone-qualified `published_at` and `expires_at`, `identity`, `thesis`, `direction` (`LONG`, `SHORT`, or `NEUTRAL`), positive `reference_price`, `venue`, and structured `confirmation` and `invalidation` conditions. Price conditions currently use `{"type":"price_at_or_above","value":N}` or `price_at_or_below`. Observation events require `observed_at`, positive `price`, and `venue`; optional `high` and `low` enable excursion calculations. Update events append `at`, optional `thesis_status` (`ACTIVE`, `VALIDATED`, `INVALIDATED`), and/or `catalyst_outcome`.

Reports calculate directional price change at 7, 14, 21, and 28 days only when an observation is within 12 hours of that horizon. Missing prices are `INSUFFICIENT_DATA` and excluded from hit-rate numerators and denominators; cohort count and observation coverage are shown. MFE/MAE is emitted only from observations containing both high and low. These are directional forecast measures, not executable strategy returns or realizable profit. No fills, fees, spread, liquidity, or slippage are modeled.

To place the report in the existing newsletter accountability section, set `manifest.artifacts.accountability` to the project-relative `.jsonl` ledger path. Assembly verifies the chain and calculates outcomes as of `edition.cutoff_utc`, then renders outcomes, horizon coverage, and excursion availability in `previous-pick-accountability`. Existing JSON accountability artifacts remain supported as-is.
