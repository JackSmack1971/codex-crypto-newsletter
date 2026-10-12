# Control-plane progress log

## Iteration 1 — packet-to-edition slice

- **Criterion:** Render a no-pick newsletter from a bounded local packet without source fetching or external publication.
- **Result:** Implemented project-local `crypto-daily` workflow, evidence contract, no-pick fixture, validator, renderer, approval gates.
- **Verification:** Eight original newsletter tests and packet check passed.

## Iteration 2 — local control-plane vertical path

- **Criterion:** Join read-only doctor, actual skill discovery, deterministic recommendation, check-only launch validation, mocked process, and an inspectable result artifact.
- **Result:** Implemented `tools/controlplane.py` with doctor, route/eval, policy-check, launch check-only/mock/explicit-execute modes, bounded subprocess, and synthetic offline acceptance. Project policy defaults to deny; publisher is disabled.
- **Verification:** 28 tests passed; py_compile passed; doctor PASS; routing fixtures 4/4; offline acceptance PASS; no-pick packet PASS; unknown source DENY; installed Codex CLI help confirms launcher flags.
- **Review:** Self-review only. No `.git` metadata is present, so Git status/diff checks are unavailable. No paid/live model session was started.
- **Remaining limits:** No live retrieval provider or enabled sources; therefore no current-news issue was researched or generated. External publication and runtime skill-trigger behavior remain unverified.

## Status

The offline control surface acceptance path is implemented and tested. The newly approved CoinGecko and DexPaprika sources are configured for zero-cost reads only; paid operations and external publication remain disabled. No model launch or market/news retrieval has been performed in this iteration.

## Iteration 4 — CP-001A deterministic daily replay orchestrator

- **Criterion:** Generate a controller-compatible draft edition from a declared local replay fixture in one command, with explicit no-pick/degraded outcomes and traceable stage/artifact provenance.
- **Result:** Added `tools/daily_orchestrator.py`. It runs existing source replay validation, universe construction, screen, nine incomplete desk handoffs, committee decision, and newsletter assembly/validation/rendering. Outputs are staged transactionally into a new or empty project-local directory. `run-manifest.json` records stage status, declared inputs, outputs, provenance, hashes, and disabled external effects. Empty input preserves explicit degraded/NO PICK; generated committee evidence cannot qualify a pick. Native Codex agents and MCP calls are not simulated.
- **Verification:** `python -m pytest tests/test_daily_orchestrator.py tests/test_daily_run.py tests/test_newsletter.py -q` — PASS, 26 tests. `python -m pytest -q --disable-warnings` — PASS, 113 tests. `python -m py_compile tools/daily_orchestrator.py tests/test_daily_orchestrator.py` — PASS. Actual command `python tools/daily_orchestrator.py --date 2026-10-11 --replay tests/fixtures/market-observations.json --output .codex/results/cp001a-run-verified` — exit 0, `DEGRADED_NO_PICK`; existing `daily_run.py` consumed its manifest and wrote a valid packet/edition with expected `DEGRADED` status. `git diff --check` — PASS (line-ending warnings only).
- **Limits:** Live acquisition, native agent research, MCP research, live daily production, scheduling, trades, and publication remain disabled and unaccepted. Final review was performed from the Git diff/status; untracked generated acceptance artifacts are retained under `.codex/results/cp001a-*`.

## Iteration 3 — project MCP source setup

- **Criterion:** Configure approved, project-level, read-only crypto data MCPs without adding credentials, paid tools, or write-capable tools.
- **Result:** Added trusted-project Codex configuration for CoinGecko (`execute` only) and DexPaprika (market-data reads only). Added exact-host, zero-cost read entries to `.codex/source-policy.json`. CoinPaprika was not selected because its hosted tool schema says query rationales are logged for provider review. The listed hosted news endpoint returned HTTP 404 during MCP initialization and was not configured.
- **Verification:** Offline suite passed (28 tests); Python compilation passed; doctor reported PASS; policy checks allowed the two approved hosts and denied an unapproved host and trade operation; `codex mcp list` and `codex mcp get --json` confirmed project-scoped server registration and tool allowlists. MCP initialization/tools-list metadata was inspected, but no market/news data tools were called and no live newsletter research was performed. Shared provider quotas apply; there is no project-enforced per-run call count. Git metadata is absent, so Git status/diff checks are unavailable.
