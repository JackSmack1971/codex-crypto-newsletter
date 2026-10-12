# Control-plane implementation plan

Objective: build a local-first, project-level Codex control surface for Small-Cap Crypto Daily from authorized research through a locally reviewable newsletter artifact. External publication and paid Codex runs remain explicit opt-ins.

| Phase | Acceptance criteria | Status / evidence |
|---|---|---|
| P0 — local substrate and doctor | Read-only structured doctor reports CLI/version, config parse, workspace/instruction boundary, and actual skill manifests without starting a model or echoing credentials. | IMPLEMENTED; TESTED_OFFLINE. `python tools/controlplane.py doctor` reports overall PASS, Codex CLI 0.162.1, valid config, project boundary, instruction chain, and 44 unique skill names. |
| P1 — manifest-backed routing | Resolver detects missing/duplicate/ambiguous manifests, validates overrides, records reasons/rejections, and emits metrics from executed fixtures with counts/denominators. | IMPLEMENTED; TESTED_OFFLINE. `python tools/controlplane.py eval-routing` passes 4/4 fixtures (precision 2/2, recall 2/2, false positives 0/1, abstentions 2/4); every configured route resolves to one manifest. |
| P2 — safe orchestration | Check-only default; fail closed on unsafe profile/path/skill; argument-array launch, bounded timeout, exit propagation, mocked end-to-end artifact. | IMPLEMENTED; TESTED_OFFLINE. `python tools/controlplane.py accept` passes synthetic nested-workspace acceptance through mocked process and artifact readback. Installed CLI help confirms used `exec` flags. |
| CP-001A — deterministic daily replay orchestrator | One local command validates replay input, builds universe, screens, persists incomplete research assessment, decides NO PICK where evidence is insufficient, assembles a controller-compatible packet/edition, and records provenance/hashes. | IMPLEMENTED; TESTED_OFFLINE. Current source provenance regression checks and repository suite pass: `python -m pytest tests/test_daily_orchestrator.py tests/test_newsletter.py tests/test_research_sources.py -q` — 44 passed; `python -m pytest -q` — 126 passed. Native agent, MCP, and live research execution remain deferred. |
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
