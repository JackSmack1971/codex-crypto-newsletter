# Daily pick committee

`tools/daily_committee.py` evaluates a dated finalist packet and emits one
decision record per candidate. It consumes the output from the offline
small-cap scoring engine (`score_record`), the assembled research desk report,
and the independent review artifact. It does not fetch data or create a price
target or trade setup.

Run a packet as an editorial decision preview:

```powershell
python tools/daily_committee.py examples/finalists.json --output examples/committee-decision.json
```

The packet has `cutoff_utc`, optional `max_market_data_age_hours` (default 24),
and a `candidates` array. Each candidate supplies:

- `candidate_identity`: verified identity, chain, asset ID, positive
  `market_cap_usd`, documented `market_cap_tier`, and `evidence_refs`;
- `market_data`: `observed_at` and `evidence_refs`;
- all eight `gates` (`identity`, `market_data`, `liquidity`, `supply`,
  `security`, `catalyst`, `token_value_capture`, `risk`), each `PASS`, `FAIL`,
  or `UNKNOWN` (an evidence-bearing object may be used for each gate);
- thesis text and `thesis_evidence_refs`, `horizon_days`, catalyst description,
  expected window and references, entry and invalidation conditions, downside
  and liquidity risks, and bull/base/bear scenario text;
- `research_desk_report.desk_results`, `score_record` from
  `small_cap_screen.screen`, and `review.frozen_inputs` plus
  `review.challenge_report`;
- `hypothesis`: `LONG`, `SHORT`, `MARKET-NEUTRAL`, `WATCH`, or `CASH`. SHORT
  and MARKET-NEUTRAL also require `instrument_evidence_refs`.

The program sorts records by numerical score, then stable candidate and asset
IDs for ties. A score ranks candidates but cannot override any missing or
failed gate, stale data, incomplete research desks, missing reviewer execution
event, or missing thesis condition. A horizon above 21 days and up to 28 days
requires `horizon_justification`. The callable `decide(packet,
reviewer_runtime_event_ids=...)` accepts reviewer event IDs only from the
coordinator's observed runtime events; the standalone CLI has no such runtime
feed and therefore cannot validate a PICK reviewer event. Missing proof yields
NO PICK. WATCH and CASH remain editorial alternatives and are not token PICKs.

Output authorization is always `EDITORIAL_REPORTING_ONLY; NO TRADE EXECUTION`.
NO PICK output includes the highest-scored ineligible candidates and their
specific blockers for the watchlist.
