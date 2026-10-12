# Market data provider integration

> Codex CLI is the research coordinator and synthesis engine. This document describes supporting Python acquisition/replay adapters and potential sources. Source configuration does not itself prove live retrieval, authorization for an operation, or output accuracy. Product acceptance gates are in [ARCHITECTURE.md](ARCHITECTURE.md) and [MVP_ROADMAP.md](MVP_ROADMAP.md).

`tools/research_sources.py` contains a read-only provider registry, fixed REST routes, common observation envelope, bounded retrieval behavior, fixture replay, and the provider-neutral `execute(mode, ...)` adapter. Discovery routes are tagged `discovery`; the CoinPaprika ticker route is tagged `observation`. Search output is never automatically promoted into a verified asset identity. Normalization retains every original row and its provider payload, including duplicate or conflicting reports.

## Provider registry

| Provider | State/interface | Capabilities | Authentication, fees, quota and health |
|---|---|---|---|
| CoinGecko | Project MCP configured | market cap, price, volume, discovery | Configuration does not establish invocation; provider quota/terms and live health unverified |
| DexPaprika | Project MCP configured | pools, price, volume, liquidity, chain and contract identity | Configuration does not establish invocation; provider quota/terms and live health unverified |
| CoinPaprika | Active fixed REST search and ticker routes; MCP remains disabled | discovery, price, market cap, volume, exchange | Public keyless routes; configured zero-cost reads; quota and live health unverified |
| DexScreener | Active fixed REST pair search | price, volume, liquidity, exchange, chain and contract identity | Public route; configured zero-cost read; quota and live health unverified |
| DefiLlama | Candidate, disabled | TVL/fees/prices data | Its official pricing page lists Open-plan data, but distinct API access at $300/month (1,000 requests/minute and 1M calls/month); no paid plan authorized: [pricing](https://docs.llama.fi/pro-api) |
| GeckoTerminal | Candidate, disabled | pools, token prices, volume, liquidity and identity | Public API documented; higher/stable rate limits require a paid CoinGecko plan; free quota not validated: [API docs](https://api.geckoterminal.com/docs/index.html) |
| CCXT public exchange data | Candidate, disabled | exchange tickers, trades, books, OHLCV | Public methods need no API key per CCXT, but each exchange controls its own quota and terms. CCXT describes variable endpoint weights and warns about bans; no library dependency or exchange activated: [manual](https://github.com/ccxt/ccxt/wiki/manual) |
| Hyperliquid Info API | Candidate, disabled | exchange mids and market metadata | Public `/info` reads are documented. Shared REST limit is weighted at 1,200/minute; no request fee was found in the official API docs, but live access/cost/terms are unverified: [Info endpoint](https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint), [limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits) |

Registry `active` indicates an explicitly supported route/MCP integration, not proven live health. The four candidates remain disabled and have no authorized operation. `--execute` can only use fixed routes whose source and HTTPS host are allowed by `.codex/source-policy.json`; no arbitrary URLs, credentials, payment, or trading operations are exposed. The daily controller defaults to `replay`; `live-rest` requires both `--mode live-rest` and `--authorize-live-rest`, accepts only fixed route/query operations, and caps each run at four requests with retries disabled. Its source snapshot records per-observation identity, provider, route, timestamps, digests, validation, request count, and explicit uncertainty about quotas/cost. Replay is marked `SIMULATED_REPLAY` and never counts as live-source verification.

The opt-in `live-mcp` adapter uses a Codex App Server model turn and requires its explicit authorization flag. Its protocol checks and offline tests do not establish live provider availability or market-data accuracy. No live call is established by the retained MVP-1 evidence; Codex still evaluates and writes the product issue in its active session.

## Retrieval and replay

```powershell
python tools/research_sources.py dex-pair-search "SOL/USDC"
python tools/research_sources.py dex-pair-search "SOL/USDC" --execute
python tools/research_sources.py coinpaprika-ticker sol-solana --execute
python tools/research_sources.py dex-pair-search replay --replay tests/fixtures/market-observations.json
```

The normal CLI path is dry-run. Live retrieval uses HTTPS, fixed host routes, default-deny source policy, 12-second timeout, at most two retries, 500 KB body bound, redirect refusal, 30-second in-memory cache and a per-provider circuit breaker. Repeated provider failures return `UNKNOWN`; this does not silently substitute another source. Health remains `UNVERIFIED` unless an operator separately performs an opt-in live check.

Every acquired result carries provider/source, retrieval time, route kind and raw data. Normalized observations carry native observation time when present and mark quality as `native_timestamp` or `retrieval_time_only`. A missing native timestamp is not inferred from retrieval time. Saved JSON can be replayed offline with `--replay`; replay keeps already-normalized rows intact so conflicting observations remain available for reconciliation.

The CoinGecko and DexPaprika MCP integrations are not invoked by the REST adapter; actual MCP tool invocation, server availability, and result provenance remain unverified. Live checks are intentionally not run during offline acceptance.
