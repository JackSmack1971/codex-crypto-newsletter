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
- **Limits:** Live acquisition, native agent research, MCP research, live daily production, scheduling, trades, and publication remain disabled and unaccepted. Full generated outputs were later removed from version control; the concise [acceptance summary](results/acceptance-summary.md) and reproducible fixture remain.

## Iteration 5 — provenance review remediation

- **Criterion:** Ensure live-verification labels and source attribution depend on successful invocation and validated observations; make disclosures mode-accurate; retain compact evidence while removing redundant generated artifacts.
- **Result:** Live verification now requires successful recorded request attempts and validated observation provenance. Partial, unavailable, and structurally unverified provider responses remain unverified; failed live requests retain provider identity and are never attributed to `local-replay`. Methodology and edition disclosures reflect actual acquisition outcomes. Removed 76 generated files from five confirmed `.codex/results/cp001a-*` / `cp003a-*` directories; retained `tests/fixtures/market-observations.json` and a compact sanitized summary.
- **Verification:** `python -m pytest tests/test_daily_orchestrator.py tests/test_newsletter.py tests/test_research_sources.py -q` — PASS, 44 tests. `python -m pytest -q` — PASS, 126 tests. `git diff --check` and staged `git diff --cached --check` — PASS.
- **Limits:** Live provider behavior remains unverified; the live REST paths in regression tests use mocked responses. No Codex model, MCP call, trade, scheduling, or publication occurred.

## Iteration 6 — CP-003B.1 native MCP protocol adapter

- **Criterion:** Integrate model-backed MCP reads through Codex App Server only after explicit opt-in; correlate authoritative lifecycle events; validate and normalize provider output; preserve redacted evidence and hashes; keep live acceptance separate.
- **Result:** Added `tools/native_mcp.py` with approved server/tool allowlists, exact configured endpoint and source-policy checks, a 90-second App Server deadline, read-only sandbox, on-request approval behavior, request/execution UUIDs plus native thread/turn/item correlation, terminal-state validation, response size bound, redaction markers, linked event hashes, atomic CLI output, and normalized MCP observations. Runtime and cleanup failures retain versioned evidence; a combined timeout/cleanup failure preserves timeout as the primary reason. `tools/research_sources.py` maps only validated output into CP-003A provenance. `tools/daily_orchestrator.py` exposes separately opted-in `live-mcp` acquisition and records the native execution artifact. Replay and `live-rest` paths are retained. Added protocol mapping and smoke-test docs in `docs/native-mcp-execution.md` and `docs/cp003b1-acceptance.json`.
- **Installed-schema evidence:** `codex --version` reported 0.162.1. `codex app-server generate-json-schema --out <temporary-directory>` succeeded; generated v2 item notification schemas include item ID, thread ID, and turn ID. Generated `McpToolCallThreadItem` requires ID, server, tool, arguments, status, and type; its status enum is `inProgress`, `completed`, `failed`. Result/error/read-only annotation are optional fields. A completed tool item is not treated as data-quality proof. App Server documentation describes item lifecycle events, while the MCP config reference documents per-server enabled tool allowlists and tool timeouts.
- **Verification:** Installed CLI 0.162.1 generated 317 schema files; the sorted-path/file-hash bundle digest is recorded in `docs/cp003b1-acceptance.json`. `python -m pytest tests/test_native_mcp.py tests/test_research_sources.py tests/test_daily_orchestrator.py -q` — PASS, 57 tests. `python -m pytest -q` — PASS, 150 tests. `git diff --check` — PASS. Stubbed adapter RPC and actual JSON-RPC transport checks cover response ID matching, malformed array/string/number/null messages, RPC-established thread/turn cross-checks, malformed early completion, out-of-order/duplicate/conflicting lifecycle, RPC failure, timeout, cleanup failure (including combined timeout plus cleanup), redaction/hash-chain integrity, authorization, normalization, and research mapping. Final independent review CLEAR with zero blocking findings. CP-003B.1 is recorded IMPLEMENTED; TESTED_OFFLINE; INDEPENDENT_REVIEW_CLEARED. The accepted protocol contract is frozen for this slice.
- **Limits:** No live model or provider request was run. CP-003B.2 remains NOT RUN and requires explicit operator authorization for both model usage and network access. MCP accuracy, freshness, and independent corroboration are not proved by runtime lifecycle events. The sanitized-event hash chain proves consistency of retained records, not authenticity of the originating events.

## Iteration 7 — PR #2 review follow-up

- **Criterion:** Ensure malformed post-turn protocol messages retain a structured failure record, and missing enclosing-turn success evidence cannot be treated as successful research completion.
- **Result:** The event-consumption loop now rejects non-object JSON messages after `turn/start`, retaining a sanitized malformed-event marker in the versioned execution record. CP-003A acquisition now defaults missing `turn_success` to false, preserving validated tool observations as `PARTIAL` without claiming enclosing-turn success.
- **Verification:** `python -m pytest tests/test_native_mcp.py tests/test_research_sources.py tests/test_daily_orchestrator.py -q` — PASS, 59 tests. `python -m pytest -q` — PASS, 152 tests. `git diff --check` — PASS. Targeted independent review CLEAR with zero blocking findings. CP-003B.1 remains accepted at the offline protocol boundary; CP-003B.2 remains not run.
- **Limits:** No live MCP/model/network call occurred; CP-003B.2 remains NOT RUN.

## Iteration 3 — project MCP source setup

- **Criterion:** Configure approved, project-level, read-only crypto data MCPs without adding credentials, paid tools, or write-capable tools.
- **Result:** Added trusted-project Codex configuration for CoinGecko (`execute` only) and DexPaprika (market-data reads only). Added exact-host, zero-cost read entries to `.codex/source-policy.json`. CoinPaprika was not selected because its hosted tool schema says query rationales are logged for provider review. The listed hosted news endpoint returned HTTP 404 during MCP initialization and was not configured.
- **Verification:** Offline suite passed (28 tests); Python compilation passed; doctor reported PASS; policy checks allowed the two approved hosts and denied an unapproved host and trade operation; `codex mcp list` and `codex mcp get --json` confirmed project-scoped server registration and tool allowlists. MCP initialization/tools-list metadata was inspected, but no market/news data tools were called and no live newsletter research was performed. Shared provider quotas apply; there is no project-enforced per-run call count. Git metadata is absent, so Git status/diff checks are unavailable.
