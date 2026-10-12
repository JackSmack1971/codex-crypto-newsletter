# Offline acceptance evidence

Date of recorded sample runs: 2026-10-11. Reproducible fixtures remain under `tests/fixtures/`.

## Current regression checks

- `python -m pytest tests/test_daily_orchestrator.py tests/test_newsletter.py tests/test_research_sources.py -q` — 44 passed. Includes mocked successful, partial, failed, and structurally unverified live REST outcomes.
- `python -m pytest -q` — 126 passed.
- Mocked live responses verify acquisition-label behavior only; they do not establish live provider health or data accuracy.

## Daily replay orchestrator (CP-001A)

- Result: `DEGRADED_NO_PICK`; research desk handoffs remain incomplete.
- Controller replay: `DEGRADED`; all six controller stages completed and packet validation passed.
- Recorded external effects: network, paid models, native agents, MCP, trades, scheduling, and publication were all false.

## Source adapter replay (CP-003A)

- Mode: `replay`; two fixture observations; `SIMULATED_REPLAY`; zero HTTP requests; `live_source_verified` false.
- Recorded external effects: network, paid models, native agents, MCP, trades, scheduling, and publication were all false.

The original full editions, packets, per-desk copies, and controller logs were generated verification outputs. They are omitted because the test suite and retained fixture reproduce the checks. No live provider, Codex model, MCP, publication, or trade execution is established by this record.
