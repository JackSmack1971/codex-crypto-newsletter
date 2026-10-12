# Native Codex newsletter MVP roadmap

Status reflects retained repository evidence reviewed for this documentation alignment. A capability is not accepted because it is planned, configured, or covered only by a mocked test. Reassess status when new evidence is accepted.

## Milestones

| MVP | Scope and acceptance gate | Status |
| --- | --- | --- |
| **MVP-1 — Fixture edition** | Codex CLI authors and revises a complete 13-section newsletter from a declared local fixture; the edition clearly discloses fixture limits; decision and seven-day watchlist are evidence-bounded; native research/editorial reviewers return findings; numerical/provenance/path/hash checks pass; final draft is saved locally. | **ACCEPTED — editorial workflow only.** Edition, reviewer findings, execution metadata, fact check, protected-content comparison, and root-relative path validation are retained in `.codex/results/native-mvp1-2026-10-11/`. It reports NO PICK and an empty seven-day watchlist. Fixture data does not represent current market conditions. |
| **MVP-2 — Verified live research** | Using specifically authorized sources, Codex retrieves fresh market and catalyst evidence; preserves source identity, retrieval/observation timestamps, units, transformations, and provenance; validates identity and freshness; corroborates material claims across independent sources where available; records unavailable/conflicting evidence; and produces a live-evidence-backed PICK or NO PICK. Acceptance requires a dated run with inspectable source operations and output validation. | **NOT ACCEPTED.** No live crypto market/news retrieval is established by MVP-1 or the retained live MCP acceptance record. MCP registration, static policy files, and mocked response tests do not pass this gate. |
| **MVP-3 — Native specialist research** | In an interactive native Codex run, Codex delegates bounded research tasks to named native subagents; runtime evidence identifies the child executions and their inputs/outputs; Codex independently synthesizes disagreements and evidence; and an independent reviewer receives a suitably separated input, completes a challenge, and influences the final decision/report. Retain a complete end-to-end trace and review artifacts for a dated live research run. | **NOT ACCEPTED.** MVP-1's native independent reviewer and newsletter editor activity establish review of a fixture edition only. The deterministic daily replay emitted incomplete simulated desk handoffs. Neither demonstrates live specialist research delegation and independent research synthesis end to end. |
| **MVP-4 — Reliable daily production** | One operator command or documented native Codex action produces a complete dated live research run, PICK/NO PICK decision, seven-day watchlist, independent research and editorial validation, fact-checked 13-section draft, and local delivery. Acceptance covers repeated runs, partial-source failures, safe recovery, stale-data rejection, reproducible provenance, and artifact completeness. No automatic publishing or trading. | **NOT ACCEPTED.** Current replay command is deterministic and offline, not a live daily production workflow. Scheduling and operational reliability remain unaccepted. |

## Acceptance record for MVP-1

The accepted edition is `.codex/results/native-mvp1-2026-10-11/edition.md`; the concise decision record is `.codex/results/native-mvp1-2026-10-11/acceptance-summary.md`. Root-relative artifact validation reports 37 references resolved, claim pointers resolved, protected evidence structurally equal before and after, renderer output matching the Markdown, 13 sections, newsletter schema PASS, numerical fact check PASS, research reviewer PASS, and editorial reviewer PASS. The protected-content bundle digest matched before and after.

The reviewer report documents offline-only scopes, corrections, and no remaining findings/blockers. The edition's saved source is an offline fixture with two provider-shaped observations and a declared replay timestamp. Execution metadata states no crypto market network requests, no live MCP/provider research, and no current market intelligence. Active Codex session reasoning authored and revised the edition; metadata says no additional model session or separate model API invocation was launched by the pipeline. Model identifier, session ID, token totals, and cost are unknown and are not asserted.

The acceptance run's targeted suite is recorded as `python -m pytest -q tests/test_newsletter.py tests/test_adversarial_review.py` — 17 passed. This is an edition-specific MVP-1 record, not verification of the current repository suite or future editions.

## Supporting control-plane infrastructure

CP-001 through CP-004 are supporting engineering workstreams and audit findings. Their status belongs in the [implementation plan](../.codex/IMPLEMENTATION_PLAN.md), [progress log](../.codex/PROGRESS.md), and [historical control-plane audit](../control-plane-audit.md). Completion of any control-plane item does not equal MVP-2, MVP-3, or MVP-4 product acceptance. The entire control-plane backlog need not be complete before Codex can write and review a fixture-based issue.

Relevant known limits:

- Project MCP settings and `.codex/source-policy.json` are configuration inputs; neither proves a live source operation or data quality. Verify the effective tool set and operation boundary for the actual host before any authorized live run.
- `tools/native_mcp.py` and its acceptance record document an opt-in App Server adapter. No live provider invocation or fresh crypto market evidence is accepted in the retained MVP-1 artifact.
- The separate CP-003B.2 live MCP acceptance gate is recorded as NOT RUN in the implementation plan. Any later source operation still needs current authorization and independent data-quality checks.
- The one-command `tools/daily_orchestrator.py` currently consumes declared replay fixtures and creates degraded simulated desk handoffs. It is not live research orchestration and does not demonstrate native Codex agent delegation.
- Independent reviewer activity in one native session can support that edition's editorial acceptance; it does not automatically prove the separate specialist delegation/synthesis gate in MVP-3.

## Gate discipline

For every milestone, retain the exact dated input and output paths, execution mode, source attempts, checks, reviewer findings, and unverified behavior. Report observed runtime traces separately from instructions and static role files. A successful MCP call is only retrieval evidence; validate its payload. A passing test proves only the tested contract. Acceptance reports remain immutable evidence; corrections and superseding evidence must be separate artifacts linked from the documentation.
