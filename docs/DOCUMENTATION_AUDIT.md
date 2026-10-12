# Documentation alignment audit

**Audit date:** 2026-10-12
**Scope:** repository Markdown, Codex TOML/configuration and agent definitions, JSON acceptance/evidence reports, examples, workflow contracts, and relevant implementation. Operational code, MCP permissions, and configuration were inspected but not changed by this documentation alignment.
**Canonical product architecture:** [ARCHITECTURE.md](ARCHITECTURE.md).
**Product acceptance status:** [MVP_ROADMAP.md](MVP_ROADMAP.md).

## Ground-truth findings

- The accepted native MVP-1 package is `.codex/results/native-mvp1-2026-10-11/`. Its edition is a 13-section local draft authored and revised in the active Codex CLI session from a local replay fixture. The acceptance report, research/editorial review findings, fact-check report, execution metadata, path validation, hashes, and before/after protected-content comparison are retained.
- MVP-1's `NO PICK` decision and empty seven-day watchlist are supported by the saved packet. Its reviewers found no remaining material factual/clarity or editorial blocker for that fixture edition. This is editorial acceptance, not live market intelligence.
- The run manifest labels acquisition `SIMULATED_REPLAY`, records two fixture observations, `live_source_verified: false`, all external effects false, and the research assessment stage as degraded with incomplete desk handoffs. Codex execution metadata records no crypto market network requests and no live MCP/provider research.
- The active Codex session used model reasoning to author/revise the issue. Execution metadata says the pipeline launched no additional model session and made no separate model API invocation. Model ID, session ID, token totals, and cost are unknown.
- The run's native independent reviewer and newsletter editor reviewed the offline edition. This does not demonstrate the full MVP-3 live specialist research delegation and independent synthesis workflow. Role TOMLs are instructions, not execution evidence.
- `tools/daily_orchestrator.py` is a deterministic replay pipeline. It builds artifacts with Python and emits incomplete simulated desk records; it is not the product's AI orchestrator and is not evidence of native Codex delegation.
- `.codex/config.toml`, `docs/native-mcp-execution.md`, and CP-003B acceptance records describe configuration and offline adapter evidence. The retained acceptance record does not include live crypto market data. MCP configuration or invocation metadata alone cannot establish accurate/fresh data.
- CP-001 through CP-004 are supporting engineering workstreams and audit findings. The control-plane backlog is not a prerequisite to Codex authoring an MVP-1 fixture newsletter and is not equivalent to MVP-2 through MVP-4 product acceptance.

## Inventory and classification

Classifications describe the role after alignment: **CURRENT** is operative and architecture-consistent; **HISTORICAL** preserves past findings or immutable acceptance evidence; **GENERATED** is a machine-readable retained artifact; **STALE** needs an explicit current-status caveat; **CONTRADICTORY** directly conflicts with the canonical architecture. Historical records are preserved rather than rewritten.

### Instructions and root documentation

| Path | Class | Finding / disposition |
| --- | --- | --- |
| `README.md` | CURRENT (rewritten) | Replaced Python launcher/packet workflow as product entry point with native Codex workflow, quick start, honest status, offline utility boundary, and roadmap links. |
| `AGENTS.md` | CURRENT (rewritten) | Reduced to actionable architecture, evidence, authorization, and engineering rules; detailed workflows route to skills/docs. |
| `.gitattributes` | CURRENT (new; evidence integrity) | Disables newline conversion only for the accepted replay fixture and MVP-1 evidence bundle so recorded raw-byte hashes survive checkout. |
| `examples/synthetic-workspace/AGENTS.md` | GENERATED / FIXTURE | Kept as a synthetic instruction-discovery fixture only; not a newsletter runtime policy. |
| `examples/synthetic-workspace/README.md` | FIXTURE | Synthetic workspace context for local launcher tests. |

### Canonical and workflow documentation

| Path | Class | Finding / disposition |
| --- | --- | --- |
| `docs/ARCHITECTURE.md` | CURRENT (new) | Canonical native Codex responsibility boundaries, workflow, evidence labels, and live/replay distinction. |
| `docs/MVP_ROADMAP.md` | CURRENT (new) | MVP-1 through MVP-4 scope, acceptance gates, evidence-based statuses, and supporting CP work. |
| `docs/DOCUMENTATION_AUDIT.md` | CURRENT (new) | This inventory and reconciliation record. |
| `docs/agent-roles.md` | CURRENT (updated) | Reclassified Codex roles and skills for newsletter runtime; Python engineering utilities are supporting infrastructure. |
| `docs/daily-run.md` | CURRENT (updated) | Clarifies replay/controller commands are deterministic local utilities, not native Codex production. |
| `docs/daily-committee.md` | CURRENT / SUPPORTING | Describes deterministic committee gate; its runtime event limitation remains relevant. |
| `docs/edition-contract.md` | CURRENT (updated) | Preserves machine contract while clarifying Codex authors and deterministic Python validates/renders. |
| `docs/native-research-agents.md` | CURRENT (updated) | Keeps role/runtime evidence rules while aligning Codex as coordinator and removing ambiguity that file roles prove execution. |
| `docs/native-mcp-execution.md` | CURRENT / SUPPORTING | Records the opt-in adapter implementation and offline protocol evidence; live acceptance remains NOT RUN. |
| `docs/provider-integration.md` | CURRENT / SUPPORTING | Provider requirements and source boundaries; check against each live operation before use. |
| `docs/provider-catalog/crypto-data-tools-deduped.md` | HISTORICAL / RESEARCH | Provider discovery notes, not evidence that a source is configured or live-ready. |
| `docs/research-accountability.md` | CURRENT / SUPPORTING | Describes local immutable-style accountability utility and its limits. |
| `docs/weekly-watchlist.md` | CURRENT / SUPPORTING | Describes local watchlist state utility; input provenance remains caller responsibility. |
| `docs/evaluation-report.md` | HISTORICAL | Records prior routing/task evaluation. Fixture metrics do not establish native skill triggering or editorial quality. |

### Plans and audit records

| Path | Class | Finding / disposition |
| --- | --- | --- |
| `.codex/GOAL.md` | CURRENT (updated) | Reframed active product objective around native Codex newsletter delivery; CP work remains supporting. |
| `.codex/IMPLEMENTATION_PLAN.md` | CURRENT (updated) | Retains exact CP implementation/verification history, adds current product milestone gates and clarifies CPs are supporting. |
| `.codex/PROGRESS.md` | HISTORICAL + current status update | Preserves original dated CP entries; appended MVP-1 evidence and current MVP status without rewriting historical results. |
| `control-plane-audit.md` | HISTORICAL (marked) | Preserves findings/backlog. Newer native Codex architecture and product gates supersede its old product framing. |

### Skills, config, role definitions, and machine-readable evidence

| Paths / group | Class | Finding / disposition |
| --- | --- | --- |
| `.agents/skills/crypto-daily/SKILL.md` and `references/*.md` | CURRENT (updated) | Native active-session workflow; focused skills, independent review, deterministic support, source policy and local artifact boundaries are maintained. |
| `.agents/skills/newsletter-production/SKILL.md` | CURRENT (updated) | Codex is author/editor; Python's check/fact-check/render operations are supporting deterministic stages. |
| Other `.agents/skills/*/SKILL.md` | CURRENT / PROCEDURAL | Domain-specific research procedures. They must follow the native architecture and do not independently authorize sources. |
| `.codex/agents/catalysts-desk.toml`, `chief-research-officer.toml`, `discovery-desk.toml`, `falsification-desk.toml`, `independent-reviewer.toml`, `liquidity-desk.toml`, `market-data-researcher.toml`, `newsletter-editor.toml`, `onchain-analyst.toml`, `quantitative-analyst.toml`, `risk-analyst.toml`, `technicals-desk.toml`, `tokenomics-desk.toml` | CURRENT / INSTRUCTIONS | Static native role definitions. They do not prove Codex loaded or ran an agent. No configuration was modified. |
| `.codex/config.toml`, `.codex/control-plane.json`, `.codex/source-policy.json` | OPERATIONAL CONFIG (unchanged) | Machine-readable contracts/settings remain untouched; their presence alone is not live-source or policy-delivery evidence. |
| `docs/cp003b1-acceptance.json` | GENERATED / HISTORICAL | Immutable offline adapter evidence; no live provider execution is established. |
| `.codex/results/acceptance-summary.md`, `offline-acceptance.json`, `offline-acceptance.md`, `next-slice-acceptance.json`, `next-slice-acceptance.md`, `evaluation-baseline.json`, `evaluation-current.json`, `routing-before.json`, `routing-after.json`, `linux-cp011-integration.json` | GENERATED / HISTORICAL | Retained prior acceptance/evaluation artifacts. They describe their own exact test modes and do not establish newsletter product maturity. |
| `.codex/results/native-mvp1-2026-10-11/*` | GENERATED / ACCEPTED EVIDENCE | Preserved MVP-1 edition, packets, reports, run metadata, hashes, comparisons, and validation evidence. The `*.previous.json` file is retained as prior comparison evidence; current comparison is authoritative per the run's reconciliation metadata. |
| `examples/adversarial-candidate.json`, `examples/evaluation-workloads.json`, `examples/no-pick.json`, `examples/routing-cases.json`, `tests/fixtures/market-observations.json` | FIXTURE / CONTRACT EXAMPLES | Input examples and replay fixture; not current market evidence. |

The only operational TOML file is `.codex/config.toml`, classified as **OPERATIONAL CONFIG (unchanged)**. `.codex/control-plane.json` and `.codex/source-policy.json` are unchanged JSON contracts/configuration rather than acceptance reports. No workflow YAML was found.

The source inventory also found no repository-root workflow YAML/JSON files beyond the listed project JSON contracts and fixtures. Documentation links are checked after changes; machine-readable schemas and operational TOML were not changed for consistency.

## Principal contradictions reconciled

1. Old README language made `crypto-daily` plus a Python packet pipeline the product's operative authoring/orchestration path and presented a separate `codex exec` launch as “real drafting.” It now describes native interactive Codex as the primary workflow and Python as deterministic support.
2. Root instructions described this project only as a control-plane engineering task and excluded newsletter execution by default. They now identify the native Codex newsletter product and retain concise engineering/evidence boundaries.
3. `docs/agent-roles.md`, replay documentation, and some skill language could imply the chief research officer/Python pipeline was the active AI orchestrator. They now distinguish native Codex judgment and subagent execution from replay fixtures and deterministic processing.
4. Static roles, configured MCP sources, completed tool lifecycle events, and passing tests can be misread as capability acceptance. The architecture and roadmap now require runtime/source evidence and separate data validation.
5. MVP-1 reviewer/editor activity could be generalized into MVP-3 delegation acceptance. The roadmap explicitly limits it to the fixture edition and requires end-to-end specialist research delegation and synthesis for MVP-3.
6. Historical audits and old acceptance reports contain former goals/statuses. They are marked historical and preserved; their own dated facts and exact results are not edited into apparent current outcomes.

## Unresolved questions and delivery gaps

- Live retrieval, effective source authorization, freshness, and corroboration lack an accepted end-to-end research run. Resolve effective tool authorization and retain live source evidence before marking MVP-2 complete.
- Exact authorized source operations, quotas, freshness rules, and corroboration coverage need an accepted MVP-2 run record; provider catalog/config presence is insufficient.
- MVP-3 needs retained native runtime evidence for specialist research child tasks, independent evidence synthesis, reviewer separation, and the final decision chain. MVP-1's two review roles do not satisfy it.
- MVP-4 needs a reliability/partial-failure/recovery acceptance run and a local delivery contract for the one-command daily workflow. Scheduling remains unaccepted.
- Documentation status is reconciled to artifacts and code inspected on 2026-10-12. Later implementation may supersede it; update the roadmap from new evidence rather than changing historical acceptance records.
- The alignment change is maintained as a documentation/evidence PR separate from live research implementation. Do not include operational MCP changes, code refactors, or live provider calls in that PR.

## Validation plan and results

The alignment gates are: search for obsolete architecture claims; resolve local links from repository root; verify every MVP-1 path and mode against metadata; inspect `.codex/config.toml` and JSON without changing schemas; run existing documentation/configuration checks and `git diff --check`; inspect the final diff and ensure unrelated pre-existing code changes are excluded from any documentation-only commit.
