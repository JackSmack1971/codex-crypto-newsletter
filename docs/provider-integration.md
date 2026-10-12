# Market data provider integration

`tools/research_sources.py` contains a read-only provider registry, fixed REST routes, common observation envelope, bounded retrieval behavior, and fixture replay. Discovery routes are tagged `discovery`; the CoinPaprika ticker route is tagged `observation`. Search output is never automatically promoted into a verified asset identity. Normalization retains every original row and its provider payload, including duplicate or conflicting reports.

## Provider registry

| Provider | State/interface | Capabilities | Authentication, fees, quota and health |
|---|---|---|---|
| CoinGecko | Active project MCP | market cap, price, volume, discovery | MCP configuration; zero-cost read configured; provider quota/terms and live health unverified |
| DexPaprika | Active project MCP | pools, price, volume, liquidity, chain and contract identity | MCP configuration; zero-cost read configured; provider quota/terms and live health unverified |
| CoinPaprika | Active fixed REST search and ticker routes; MCP remains disabled | discovery, price, market cap, volume, exchange | Public keyless routes; configured zero-cost reads; quota and live health unverified |
| DexScreener | Active fixed REST pair search | price, volume, liquidity, exchange, chain and contract identity | Public route; configured zero-cost read; quota and live health unverified |
| DefiLlama | Candidate, disabled | TVL/fees/prices data | Its official pricing page lists Open-plan data, but distinct API access at $300/month (1,000 requests/minute and 1M calls/month); no paid plan authorized: [pricing](https://docs.llama.fi/pro-api) |
| GeckoTerminal | Candidate, disabled | pools, token prices, volume, liquidity and identity | Public API documented; higher/stable rate limits require a paid CoinGecko plan; free quota not validated: [API docs](https://api.geckoterminal.com/docs/index.html) |
| CCXT public exchange data | Candidate, disabled | exchange tickers, trades, books, OHLCV | Public methods need no API key per CCXT, but each exchange controls its own quota and terms. CCXT describes variable endpoint weights and warns about bans; no library dependency or exchange activated: [manual](https://github.com/ccxt/ccxt/wiki/manual) |
| Hyperliquid Info API | Candidate, disabled | exchange mids and market metadata | Public `/info` reads are documented. Shared REST limit is weighted at 1,200/minute; no request fee was found in the official API docs, but live access/cost/terms are unverified: [Info endpoint](https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint), [limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits) |

Registry `active` indicates an explicitly supported route/MCP integration, not proven live health. The four candidates remain disabled and have no authorized operation. `--execute` can only use fixed routes whose source and HTTPS host are allowed by `.codex/source-policy.json`; no arbitrary URLs, credentials, payment, or trading operations are exposed. Existing MCP configuration remains governed by its own tool allowlists and source policy; this adapter does not perform MCP calls.

## Retrieval and replay

```powershell
python tools/research_sources.py dex-pair-search "SOL/USDC"
python tools/research_sources.py dex-pair-search "SOL/USDC" --execute
python tools/research_sources.py coinpaprika-ticker sol-solana --execute
python tools/research_sources.py dex-pair-search replay --replay tests/fixtures/market-observations.json
```

The normal CLI path is dry-run. Live retrieval uses HTTPS, fixed host routes, default-deny source policy, 12-second timeout, at most two retries, 500 KB body bound, redirect refusal, 30-second in-memory cache and a per-provider circuit breaker. Repeated provider failures return `UNKNOWN`; this does not silently substitute another source. Health remains `UNVERIFIED` unless an operator separately performs an opt-in live check.

Every acquired result carries provider/source, retrieval time, route kind and raw data. Normalized observations carry native observation time when present and mark quality as `native_timestamp` or `retrieval_time_only`. A missing native timestamp is not inferred from retrieval time. Saved JSON can be replayed offline with `--replay`; replay keeps already-normalized rows intact so conflicting observations remain available for reconciliation.

The CoinGecko and DexPaprika MCP integrations cannot be contract-tested through this REST adapter; actual MCP server availability and tool schemas remain unverified. Live checks are intentionally not run during offline acceptance.
