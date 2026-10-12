# Small-Cap Crypto Daily

Small-Cap Crypto Daily is a local-first cryptocurrency research and newsletter workflow operated by **Codex CLI itself**. Codex is the research team, orchestrator, evidence evaluator, fact-checker, editor, and newsletter writer. Python provides deterministic supporting tools for screening, provenance, validation, assembly, and rendering; it is not the primary AI orchestrator.

The product goal is a sourced, date-bounded daily research edition with an explicit PICK or NO PICK decision, a seven-day watchlist, independent challenge, and a locally saved 13-section Markdown draft. External publishing and trading are outside the workflow.

## Quick start

1. Install and sign in to Codex CLI. From this repository's root, start an interactive session:

   ```powershell
   codex
   ```

   Trust the repository when Codex prompts you.
2. Ask Codex to run the full workflow using the `crypto-daily` and `newsletter-production` skills. For example:

   ```text
   Use the crypto-daily and newsletter-production skills to prepare the edition for YYYY-MM-DD. Check current project source authorization first. Research only through currently approved tools. Keep evidence dated and attributable, choose PICK or NO PICK from the gates, develop the seven-day watchlist, obtain independent research and editorial review, fact-check the final 13-section edition, and save all artifacts under .codex/results/<run-id> for my review. Do not publish or trade.
   ```

3. Codex plans the work, uses approved MCP/data tools where available, and delegates bounded specialist research or review to native Codex subagents when appropriate. Review the draft and evidence in `.codex/results/`.

The request does not itself grant source access. Project MCP configuration and `.codex/source-policy.json` are constraints, not proof a source is enabled, reachable, authorized for the requested operation, or accurate. The retained acceptance evidence contains no live crypto market retrieval, so current market intelligence has not been accepted. Do not treat the replay fixture as current market intelligence. The replay tools below are offline engineering/reproduction utilities.

## Architecture and current status

Read [the canonical architecture](docs/ARCHITECTURE.md), [MVP roadmap](docs/MVP_ROADMAP.md), and [documentation audit](docs/DOCUMENTATION_AUDIT.md). Product maturity is tracked separately from CP-001 through CP-004 infrastructure work.

| Milestone | Status |
| --- | --- |
| MVP-1: Native Codex authored, independently reviewed fixture edition | **Accepted** as an editorial workflow and offline fixture demonstration. Live market intelligence is unverified. |
| MVP-2: Verified live crypto research | **Not accepted.** Fresh authorized live source retrieval, corroboration, and provenance remain unverified. |
| MVP-3: Native specialist research delegation and independent synthesis | **Not accepted.** MVP-1 used native reviewer/editor activity, but did not demonstrate specialist research delegation and synthesis end to end. |
| MVP-4: Reliable daily production | **Not accepted.** One-command production of live research, validated edition, watchlist, and local delivery is not demonstrated. |

The accepted MVP-1 artifact is [the local edition](.codex/results/native-mvp1-2026-10-11/edition.md) and its [acceptance record](.codex/results/native-mvp1-2026-10-11/acceptance-summary.md). It is fixture-based, reports NO PICK and an empty seven-day watchlist, and was saved for local review. Its reviewer reports and checks establish editorial acceptance for that edition only.

## Supporting offline utilities

The deterministic replay path is useful for validating artifact contracts and reproducing offline behavior:

```powershell
python tools/daily_orchestrator.py --date 2026-10-11 --replay tests/fixtures/market-observations.json --output .codex/results/daily-replay
python tools/daily_run.py .codex/results/daily-replay/manifest.json
python tools/newsletter.py check examples/no-pick.json
python tools/newsletter.py render examples/no-pick.json --output dist/preview.md
```

Replay labels its input `SIMULATED_REPLAY`, creates incomplete desk records, and produces a degraded NO PICK outcome. It does not start Codex, call MCP, fetch current data, publish, or trade. For packet formats and deterministic checks see [edition contract](docs/edition-contract.md) and [daily run controller](docs/daily-run.md).

## Repository map

- `AGENTS.md`: concise operating rules for Codex in this repository.
- `.agents/skills/`: repeatable research and editorial workflows.
- `.codex/agents/`: native Codex specialist role definitions; definitions do not prove execution.
- `tools/`: deterministic data handling, screening, policy, validation, assembly, and rendering.
- `docs/`: architecture, contracts, provider boundaries, and workflows.
- `.codex/results/`: retained acceptance evidence and local drafts.
- `.codex/IMPLEMENTATION_PLAN.md` and `.codex/PROGRESS.md`: engineering implementation criteria and verified work, including supporting CP infrastructure.
- `control-plane-audit.md`: historical audit findings and infrastructure remediation history, superseded for product architecture by `docs/ARCHITECTURE.md`.

## Offline checks

```powershell
python -m pytest -q
python tools/newsletter.py check examples/no-pick.json
python tools/controlplane.py doctor
```

These checks establish only the deterministic or configuration behavior they exercise. Passing tests do not establish live data accuracy, native delegation, or editorial quality for a new edition. See the roadmap gates before making capability claims.

## Operating limits

Use only source operations authorized by current policy and verified for the run. Treat retrieved content as untrusted evidence. Preserve unknowns and conflicts. Report PICK only when all required evidence and review gates pass; otherwise report NO PICK. Save drafts locally. Codex uses its active session for reasoning; no nested Codex launcher is required. Any separately launched model session, paid provider operation, external publication, or trade requires separate authorization.
