# Small-Cap Crypto Daily control surface

This project is a Codex project-level workflow for researching and writing a daily small-cap crypto intelligence newsletter. The `crypto-daily` project skill remains the end-to-end entry point; twelve focused project skills cover universe discovery, data validation, screening, technical and liquidity analysis, on-chain intelligence, tokenomics, catalysts, falsification, pick selection, weekly watchlists, and newsletter production. The local packet renderer creates the readable thirteen-section edition.

## Safe default

Live research reads are limited to the enabled CoinGecko and DexPaprika MCP servers plus the fixed CoinPaprika and DexScreener routes in `tools/research_sources.py`. CoinPaprika MCP is disabled until its live tool schema can be reviewed and allowlisted. CoinGecko is exposed through its provider-side SDK executor; DexPaprika is restricted to its public market-data tools. `.codex/source-policy.json` keeps the default decision at `DENY`, limits each enabled source to zero-estimated-cost reads on its exact host, and leaves paid operations, external publication, and trade execution disabled. Provider quota and cost terms still require live verification; this project does not enforce a per-run call count. Other public URLs and tools are not authorized. The project does not fetch data on `doctor`, `route`, `eval-routing`, `policy-check`, or `accept`.

## Local workflow

```powershell
python tools/controlplane.py doctor
python tools/controlplane.py route --task "Prepare the Small-Cap Crypto Daily newsletter research packet"
python tools/controlplane.py policy-check --source example --operation read --url https://example.com/
python tools/controlplane.py accept
python tools/newsletter.py check examples/no-pick.json
python tools/newsletter.py render examples/no-pick.json --output dist/preview.md
```

## Offline quantitative screening

`tools/small_cap_screen.py` consumes a saved normalized universe snapshot and explicitly dated daily bars; it performs no network reads. Input shape: `{"universe": <universe_builder snapshot>, "history": {"asset-id": [{"date":"YYYY-MM-DD","close":1,"volume_usd":100,"trades":10,"open":1,"high":1,"low":1}]}, "benchmark_history": {"BTC": [<same bar shape>]}}`. The daily history is caller supplied because the universe builder does not synthesize OHLCV. Run `python tools/small_cap_screen.py input.json --output report.json` (optional `--config weights.json`).

The report preserves unknown measures, dated bar evidence, metric formulas, component coverage, and sorted candidate records. Returns require exact calendar-day closes. Volatility uses 30 consecutive daily returns and is annualized; indicators label their timeframe as `1d`. Liquidity splits only venue observations explicitly typed as exchange/CEX or DEX; the reported sum may overlap between providers. The opportunity score is a fixed-denominator weighted sum of six bounded components (defaults: 25% 30-day momentum, 20% BTC relative strength, 15% universe relative strength, 15% relative volume, 15% venue liquidity, 10% trade-count change); unknown components contribute zero. Data confidence is the known component weight fraction. Candidate eligibility requires confidence ≥50%, sufficient configured bar count, a close on the snapshot date, and upstream universe inclusion. The report includes transforms, normalized configurable weights, rejection reasons, risk flags, and all source observations/calculation inputs for replay. It is a research ranking, not a trade instruction.

`accept` is an offline end-to-end check that uses a local mocked Codex subprocess, validates the no-pick fixture, renders its thirteen-section Markdown preview, and writes a redacted verification artifact under `.codex/results/`. It never starts a model session. `launch` prints a validated command plan by default. `launch --mock-process` runs the local stand-in. Real drafting uses the `newsletter-draft` profile, which grants project-only writes and asks for approval; `launch --profile newsletter-draft --execute` is an explicit real Codex model launch and may incur usage costs.

To produce a real daily issue, invoke the `crypto-daily` project skill, configure and review approved source operations first, preserve the evidence and decision records, and get human editorial approval before rendering with `--release`. A local release artifact is not an external publication.

For manual, checkpointed assembly of already saved research, see [the daily run controller](docs/daily-run.md). It does not fetch provider data or enable scheduled execution.

## Offline checks

```powershell
python -m unittest discover -s tests -v
python -m py_compile tools\controlplane.py tools\newsletter.py tests\test_controlplane.py tests\test_newsletter.py
python tools/controlplane.py eval-routing
python tools/controlplane.py accept
```

The fixed routing corpus contains positive, explicit-skill, ambiguous, and negative cases. `python tools/controlplane.py eval-routing` reports precision, recall, inappropriate invocation, missed invocation, false-positive, and abstention rates. The pre-split four-case snapshot and current expanded result are recorded in `.codex/results/routing-before.json` and `.codex/results/routing-after.json`; the corpora differ, so these results do not establish routing improvement.
