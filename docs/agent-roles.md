# Agent roles and instruction scope

## Native newsletter runtime

The product is operated by the active Codex CLI session under root [`AGENTS.md`](../AGENTS.md) and the `crypto-daily` / `newsletter-production` skills. Codex owns research planning, evidence evaluation, PICK/NO PICK, synthesis, fact checking, editing, and authorship. It may delegate bounded specialist work to native subagents. Role definitions in `.codex/agents/` describe responsibilities; only runtime evidence establishes that a role was actually invoked.

The skills contain conditional research, evidence, review, and release procedures. The [edition contract](edition-contract.md) defines the deterministic 13-section packet checks. Source policy and explicit operator authorization govern external reads. No instruction file or skill authorizes publication or trading.

## Engineering/runtime boundary

Python tools provide deterministic supporting functions: replay and allowed acquisition adapters, screening, report/schema validation, committee gates, watchlist persistence, provenance, packet assembly, fact checks, and rendering. The CP control plane helps inspect or guard specific local execution paths. It is not a separate AI chief research officer and is not required before Codex can write a fixture edition.

`tools/daily_orchestrator.py` and `tools/daily_run.py` are currently deterministic replay/artifact workflows. Their completion must not be reported as native Codex research or delegation. The synthetic instruction file at `examples/synthetic-workspace/AGENTS.md` exists only for instruction-discovery tests.

Codex discovers project instructions from the repository root through the active working directory, with more specific nested instructions applying later in the chain. See the current [Codex AGENTS.md documentation](https://developers.openai.com/codex/guides/agents-md). This project has no separate nested newsletter-runtime `AGENTS.md`.
