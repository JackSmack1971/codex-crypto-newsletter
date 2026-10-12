# Control-plane implementation plan

Product objective: deliver a local-first Small-Cap Crypto Daily edition authored and orchestrated by the active Codex CLI session, with evidence-backed candidate decision, seven-day watchlist, independent review, deterministic validation, and local draft delivery. Python is deterministic support. CP-001 through CP-004 are supporting workstreams; see [architecture](../docs/ARCHITECTURE.md) and [MVP roadmap](../docs/MVP_ROADMAP.md).

## Product acceptance status

| MVP | Gate | Status |
|---|---|---|
| MVP-1 | Native Codex authors a complete fixture-based 13-section edition; offline native reviewer/editor findings and deterministic fact/provenance/path checks pass; save locally. | ACCEPTED for this edition only. `.codex/results/native-mvp1-2026-10-11/acceptance-summary.md`. Editorial acceptance does not establish current market intelligence. |
| MVP-2 | Authorized live retrieval, freshness, identity, provenance, corroboration, and evidence-backed decision in a retained dated run. | NOT ACCEPTED; no live crypto research run or current-market intelligence is in retained acceptance evidence. |
| MVP-3 | Runtime-evidenced native specialist research delegation and independent evidence synthesis end to end, with reviewer separation. | NOT ACCEPTED; MVP-1 native reviewer/editor activity is edition review, not specialist research delegation. |
| MVP-4 | Reliable daily workflow produces live research, validated decision/watchlist, independent review, fact-checked edition, and local delivery with recovery evidence. | NOT ACCEPTED; replay orchestrator is offline and no daily reliability acceptance exists. |

The engineering rows below retain their original CP acceptance scope. They are supporting evidence and do not substitute for these product gates.

| Phase | Acceptance criteria | Status / evidence |
|---|---|---|
| P0 — local substrate and doctor | Read-only structured doctor reports CLI/version, config parse, workspace/instruction boundary, and actual skill manifests without starting a model or echoing credentials. | IMPLEMENTED; TESTED_OFFLINE. `python tools/controlplane.py doctor` reports overall PASS, Codex CLI 0.162.1, valid config, project boundary, instruction chain, and 44 unique skill names. |
| P1 — manifest-backed routing | Resolver detects missing/duplicate/ambiguous manifests, validates overrides, records reasons/rejections, and emits metrics from executed fixtures with counts/denominators. | IMPLEMENTED; TESTED_OFFLINE. `python tools/controlplane.py eval-routing` passes 4/4 fixtures (precision 2/2, recall 2/2, false positives 0/1, abstentions 2/4); every configured route resolves to one manifest. |
| P2 — safe orchestration | Check-only default; fail closed on unsafe profile/path/skill; argument-array launch, bounded timeout, exit propagation, mocked end-to-end artifact. | IMPLEMENTED; TESTED_OFFLINE. `python tools/controlplane.py accept` passes synthetic nested-workspace acceptance through mocked process and artifact readback. Installed CLI help confirms used `exec` flags. |
| CP-001A — deterministic daily replay orchestrator | One local command validates replay input, builds universe, screens, persists incomplete research assessment, decides NO PICK where evidence is insufficient, assembles a controller-compatible packet/edition, and records provenance/hashes. | IMPLEMENTED; TESTED_OFFLINE. Current source provenance regression checks and repository suite pass: `python -m pytest tests/test_daily_orchestrator.py tests/test_newsletter.py tests/test_research_sources.py -q` — 44 passed; `python -m pytest -q` — 126 passed. Native agent, MCP, and live research execution remain deferred. |
| CP-003B.1 — native Codex MCP protocol adapter | Use Codex App Server events and installed protocol schema to require correlated, approved, read-only MCP completion before normalizing provider output; preserve redacted lifecycle evidence and hashes in CP-003A provenance. | IMPLEMENTED; TESTED_OFFLINE; INDEPENDENT_REVIEW_CLEARED. Original and PR follow-up changes were independently reviewed; focused tests (59 passed), full offline suite (152 passed). CP-003B.2 live model/MCP acceptance remains NOT RUN and separately gated. |
| CP-003B.2 — live native MCP acceptance | One explicitly authorized model session captures one approved read-only MCP invocation, validated output, and a versioned execution record. | NOT RUN; requires explicit operator authorization for model usage and network access. |
| Newsletter research and release workflow | Project skill describes evidence-led daily research, source policy, no-pick path, eligibility and independent-review gates, fixed 13-section edition, local-only rendering. | IMPLEMENTED; TESTED_OFFLINE for packet validation/rendering. CoinGecko and DexPaprika MCPs are enabled with read-only scope; CoinPaprika MCP is disabled pending tool-schema review, while the bounded CoinPaprika REST and DexScreener routes remain policy-controlled. No live market/news data has been fetched; paid operations and external publication remain disabled. |

## Verification record

- `python -m unittest discover -s tests -v` — PASS, 36 tests (Windows).
- `python -m py_compile tools\controlplane.py tools\newsletter.py tools\research_sources.py tests\test_controlplane.py tests\test_newsletter.py tests\test_research_sources.py` — PASS.
- `python tools\controlplane.py doctor` — PASS; read-only checks only.
- `python tools\controlplane.py eval-routing` — PASS, 4/4 fixture classifications; metrics are fixture-only.
- `python tools\controlplane.py accept --artifact .codex\results\offline-acceptance.json` — PASS; mocked Codex subprocess, local result artifact and 13-section draft render.
- `python tools\newsletter.py check examples\no-pick.json` — PASS.
- `codex --version`, `codex exec --help`, and `codex mcp list` — PASS; installed CLI 0.162.1 exposes the launcher flags, loads the two enabled MCP entries, and reports CoinPaprika MCP disabled.
- Project `.codex/config.toml` TOML fields `enabled`, `enabled_tools`, `startup_timeout_sec`, and `tool_timeout_sec` — present in the current official Codex configuration reference; Codex project config parses via `codex mcp list`.
- Crypto-daily reference paths and all discovered skill frontmatter — PASS; configured implementation route resolves to the installed user-scope `implementation-slice` manifest.
- `python tools\controlplane.py policy-check --source unknown --operation read --url https://example.com/` — DENY as expected; unknown source is not allowlisted.

## Limits

No live model run, market/news retrieval, current-market newsletter, or external publication was performed or tested in this implementation slice. Two zero-cost read sources are configured, but the project does not enforce a per-run source-call quota; shared provider quotas still apply. The resolver recommends project skills; it does not prove Codex runtime skill-trigger accuracy. The workspace has no Git metadata, so Git status/diff checks cannot run; no independent reviewer was invoked.
