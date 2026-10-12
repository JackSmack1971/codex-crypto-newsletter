Codex Control Plane — Comprehensive Architecture & Implementation Audit
=======================================================================

October 11, 2026 | Artifact: `newsletter.zip` | Official Codex documentation and release history
Executive assessment
--------------------

Major remediation required

CURRENT — The uploaded system is a partially implemented crypto-newsletter research platform, not yet a fully functioning, verified Codex-native research control plane.

The archive contains genuine Python implementations, research workflows, custom agents, skills, source controls, and tests. This is substantially more than an instructions-only scaffold.

However, the implementation has several structural weaknesses:

* The native Codex agents and the deterministic Python research pipeline are not demonstrated to execute as one integrated daily workflow.

* The daily workflow primarily validates existing research artifacts rather than autonomously acquiring and investigating fresh market evidence.

* The MCP configuration exposes some research capabilities, but the offline Python pipeline does not invoke those MCP tools.

* Skill routing and CLI launch verification have measurable problems.

* The claimed ability to produce a daily newsletter depends on research inputs, operational steps, and scheduling that are not yet verified end-to-end.

RECOMMENDED — Do not classify this control plane as operationally accepted until it can independently produce a reproducible, evidence-backed daily edition from a declared starting state, with no undocumented manual handoffs.

### Audit scope and evidence

I extracted and inspected the supplied ZIP, examined its Codex configuration, all 13 custom-agent definitions, skill structure, launcher, Python research and newsletter modules, and supporting tests and documentation.

I also checked current official Codex documentation and the GitHub release history. The official release listings include the October 9, 2026 `0.162.1` release and subsequent prerelease activity. These are documentation/release observations, not verification of the Codex version installed on your Windows machine.

![](https://www.google.com/s2/favicons?domain=https://github.com&sz=32)

GitHub

+3

The audit distinguishes three evidence levels:

* CURRENT: Directly observed in the supplied archive or confirmed in official documentation.

* DERIVED: An architectural or operational consequence supported by those observations.

* RECOMMENDED: A concrete improvement proposal, not a native Codex capability already proven to exist.
1. Verification results

-----------------------

ARCHIVE TEST RUN — CURRENT
91 / 99
=======

8 failed

91 passed, 8 failed, 60 subtests passed. Executed in the extracted archive using the available Python environment.

The actual command was:
    python -m pytest -q --disable-warnings

The failures include launcher tests that expect a discoverable `codex` executable, a failed doctor check, JSON output assumptions, and a routing-regression failure.

Notably, a routing test expects 100% recall but obtains approximately 96.3%. This contradicts the repository's saved evaluation report, which documents perfect routing recall for its earlier evaluation corpus.

The missing local Codex executable contributes to several failures in this audit environment. It does not establish that Codex is missing on your Windows installation. The routing discrepancy is a separate finding requiring investigation.

No live Codex subagent session, authenticated MCP connection, production research run, or automatic publishing cycle was verified.

2. Control-plane coverage matrix

--------------------------------

The assessment below is based on static inspection and the executed offline tests, not an assertion that every Codex feature was exercised.

| Axis                              | Assessment                                                     | Priority |
| --------------------------------- | -------------------------------------------------------------- | -------- |
| Project identity and trust        | Trust resolution not proven at runtime                         | P1       |
| Configuration compatibility       | Partially validated                                            | P1       |
| Instruction hierarchy             | Strong written guidance, incomplete effective-state proof      | P1       |
| Skills and routing                | Discoverable structure, failed routing regression              | P1       |
| Custom agents                     | Definitions valid as TOML, activation unverified               | P1       |
| Multi-agent orchestration         | Designed but not end-to-end demonstrated                       | P0       |
| MCP/tool registry                 | Partial, with disconnected interfaces                          | P0       |
| Runtime authorization             | Python controls exist; unified enforcement unproven            | P0       |
| Credential and network boundaries | Conservative defaults, incomplete cross-surface enforcement    | P0       |
| Environment/CLI launching         | Executable code, failed tests                                  | P1       |
| Source-control lifecycle          | Instructions present, little executable enforcement            | P2       |
| Research data acquisition         | Partial live adapters, no integrated daily acquisition         | P0       |
| Quantitative research             | Deterministic checks, limited live evaluation                  | P1       |
| Editorial validation              | Substantial implemented gates                                  | P1       |
| Governance and provenance         | Useful records, incomplete live causal evidence                | P1       |
| Scheduling and publication        | Scheduling disabled; external publication intentionally absent | P1       |
| Evaluation and CI                 | Offline tests exist, full suite not passing                    | P0       |
| Reproducibility and snapshots     | Partial checkpointing, incomplete execution identity           | P1       |

3. Detailed findings and concrete fixes

---------------------------------------

### P0 — Critical functional gaps

CP-001

The daily research pipeline is not end-to-end automated

Evidence: `tools/daily_run.py`, `docs/daily-run.md`

The daily controller requires an already assembled manifest and research artifacts. It performs stages named `INGESTING`, `SCREENING`, `RESEARCHING`, `REVIEWING`, `COMPOSING`, and `VALIDATING`, but the early stages primarily read or validate existing material. They do not themselves execute the corresponding live research.

Impact: A successful daily run is not proof that fresh cryptocurrency research happened that day.

Concrete fix: Introduce a bounded research orchestrator that creates its own dated universe snapshot, acquires approved observations, executes screening, dispatches research desks, obtains an independent review, assembles the committee record, and supplies the resulting manifest to the existing daily controller.

Acceptance: Starting with an empty daily-artifact directory and configured approved providers, a single command produces a complete edition or an explicitly degraded/NO PICK edition with every unavailable research stage identified.

CP-002

Native Codex agent execution is not integrated with the daily controller

Evidence: `.codex/agents/*.toml`, `docs/native-research-agents.md`, `tools/daily_run.py`

Thirteen custom-agent definitions are present, including a chief research officer, domain specialists, an independent reviewer, and an editor. The documentation correctly distinguishes simulated research desks from verified native agents.

However, the Python daily controller has no implemented native-agent dispatch and result-collection mechanism. The existence of custom-agent TOML files does not establish that any of them were spawned.

Concrete fix: Add a native Codex execution adapter using a documented CLI or App Server interface. Require explicit task dispatch, child-agent identification, bounded concurrency, completion/error handling, and verified output capture. Maintain degraded single-agent execution as a separate, truthfully labeled mode.

Acceptance: A test run records actual child-thread identifiers, role names, input artifact hashes, completion states, and validated outputs. Simulated records must never satisfy native-delegation acceptance.

Official basis: [Codex subagents documentation](https://developers.openai.com/codex/subagents).

CP-003

MCP tools and the deterministic research engine are disconnected

Evidence: `.codex/config.toml`, `tools/research_sources.py`, `docs/provider-integration.md`

CoinGecko and DexPaprika are enabled in the Codex MCP configuration. Separately, the Python module provides fixed REST routes for CoinPaprika and DexScreener.

The REST adapter does not call the configured MCP servers. The documentation explicitly acknowledges this separation.

Concrete fix: Build a unified research data adapter contract with separate implementations for MCP and approved REST providers. Each adapter should expose a canonical operation, tool/server identity, capability, data freshness, source provenance, timeout, authentication status, quota information, and actual invocation result.

For native MCP operations, use a real Codex-hosted MCP invocation path rather than pretending an MCP tool is a Python import. For Python-only orchestration, introduce an explicit bridge whose invocation is controlled by the runtime.

Acceptance: One controlled research request can retrieve and normalize data through each enabled integration, with its actual tool-call evidence attached.

CP-004

The project source-policy JSON is not a universal security enforcement mechanism

Evidence: `.codex/source-policy.json`, `.codex/config.toml`, `tools/controlplane.py`

The Python REST adapter checks the custom source policy. That is useful application-level enforcement. But native Codex MCP invocations are governed by Codex's own runtime policy, not by the existence of this repository JSON file.

This leaves two independently resolved authorization systems.

Concrete fix: Keep the repository policy as a versioned declarative source, then map approved constraints into the actual enforcement systems: Codex MCP enablement/tool restrictions, applicable managed policy, sandbox and network controls, and the Python adapter's own authorization checks. Refuse to label the policy globally enforced until each execution surface has been tested.

Add negative tests demonstrating that a disallowed provider cannot be reached through either path.

Acceptance: Attempted unauthorized native MCP and Python REST operations are independently denied by their respective enforcement mechanisms, with observable denial evidence.

Official basis: [Codex configuration reference](https://developers.openai.com/codex/config-reference).

CP-005

The test suite fails and saved evaluation results are stale relative to current behavior

Evidence: `tests/test_controlplane.py`, `docs/evaluation-report.md`, `.codex/results/`

The actual offline run produced eight failed tests. Some failures are environment-dependent, but the routing recall failure is a genuine mismatch between the test's expected result and what the current code produces.

Concrete fix: Split the test suite into environment-independent unit tests, CLI integration tests, and opt-in live network/model tests. Mock binary discovery at the correct boundary. Keep the existing assertions intact unless their expected contract is independently proven incorrect. Regenerate evaluation results only after the corresponding checks pass.

Acceptance: All offline unit and contract tests pass in a clean environment; live tests report `SKIPPED` or `BLOCKED` when necessary, rather than masquerading as successful offline checks.

### P1 — High-priority control-plane defects

CP-006

Custom-agent configuration needs runtime discovery proof

Evidence: 13 files in `.codex/agents/`

All 13 standalone files were parsed successfully as TOML and contain role identity, descriptions, sandbox settings, and developer instructions. That is useful static verification.

It does not verify that a real Codex session discovers them or that child threads use their intended settings.

Fix: Add a read-only native-agent smoke test using the installed Codex binary. Compare discovered roles against the expected role inventory. Start one permitted child and inspect its reported configuration and actual execution result.

Acceptance: Each required role is discoverable, and at least one representative native delegation completes with observed evidence.

CP-007

The orchestration topology is too dependent on prose

Evidence: `.codex/agents/chief-research-officer.toml`, `docs/native-research-agents.md`

The repository specifies nine research desks and a two-worker concurrency ceiling. Its documentation describes how they should cooperate, but no deterministic daily dispatch graph was demonstrated.

Fix: Implement a task DAG with explicit stages:

Acquire and validate observations

Universe and candidate screen

Independent research desks

Independent falsification

Reconciliation and committee decision

Editorial validation and local edition

Assign every stage an owner, required inputs, output schema, terminal status, maximum runtime, and failure disposition. Enforce the existing two-child concurrency limit.

Acceptance: A failed child cannot silently produce a completed desk artifact; dependent stages respect their prerequisites.

CP-008

The skill router is not equivalent to Codex-native skill activation

Evidence: `.codex/control-plane.json`, `tools/controlplane.py`

The repository's router maps phrases to skill names and constructs a prompt instructing Codex to use a matching skill. This does not prove that the native runtime actually activated the intended `SKILL.md`.

Fix: Resolve each route to its canonical manifest path, validate its metadata and availability, then verify actual activation through a supported runtime interface. Preserve distinct states for `DISCOVERED`, `SELECTED`, `ACTIVATED`, and `EXECUTED`.

Acceptance: Runtime evidence confirms activation of the requested skill; the router records why close alternatives were rejected. Correct the regression revealed by the 96.3% recall result.

CP-009

The skill library lacks a measured routing-quality baseline for real tasks

Evidence: `.agents/skills/`, `examples/routing-cases.json`, `docs/evaluation-report.md`

Thirteen research-focused skills are present. Their task boundaries are relatively well defined. But the saved routing corpus cannot establish live model selection accuracy or successful workflow activation.

Fix: Extend the evaluation corpus with ambiguous requests, negative examples, overlapping specialties, multi-skill requests, and unrelated engineering tasks. Measure false activations, missed activations, activation correctness, and task completion separately.

Acceptance: The deterministic router passes its contract suite, and a separately labeled live evaluation measures actual skill selection without overstating simulated metrics.

Official basis: [Codex skill authoring and discovery](https://developers.openai.com/codex/skills).

CP-010

Project identity and effective configuration are not fully captured

Evidence: `tools/controlplane.py`, `.codex/config.toml`

The doctor examines local files and the Codex binary when available, but it does not conclusively demonstrate the complete runtime-resolved configuration, including inherited settings, project trust, managed restrictions, and enabled tools.

Fix: Introduce an effective-state report containing the installed Codex version, executable path, project root, selected config files, trust state, permission mode, agent availability, skill inventory, MCP availability, and source provenance. Read values from supported runtime introspection where available; label unobservable fields explicitly.

Acceptance: The diagnostic report differentiates configured, resolved, runtime-verified, and unknown states.

CP-011

The CLI launcher has portability and compatibility uncertainties

Evidence: `tools/controlplane.py`, `tests/test_controlplane.py`

The launcher constructs `codex exec` command arguments, but tests involving binary discovery failed here. The archive targets Windows PowerShell, while this audit executed on Linux.

Fix: Add a platform-aware command resolver and an installed-version compatibility check. Validate argument support against actual `codex exec --help`. Separate launch-plan construction from executable resolution so it can be tested without Codex installed.

Acceptance: Windows PowerShell and Linux integration fixtures pass independently. A real invocation, where authorized, confirms expected JSON event completion and exit handling.

CP-012

Research source capability declarations are not health evidence

Evidence: `tools/research_sources.py`, `docs/provider-integration.md`

Providers marked active can still have `UNVERIFIED` health, quota, and live schema status. The documentation acknowledges this, but the daily workflow needs an operational distinction between configured and usable sources.

Fix: Add a provider readiness state machine: `REGISTERED → CONFIGURED → REACHABLE → SCHEMA_VERIFIED → DATA_VALIDATED`, with `DEGRADED`, `RATE_LIMITED`, and `DISABLED` outcomes.

Acceptance: A provider contributes to an investment-grade research artifact only after a successful, time-bounded observation and data-quality check.

CP-013

Independent-review provenance is not yet demonstrated with native evidence

Evidence: `tools/adversarial_review.py`, `tools/daily_committee.py`, `docs/native-research-agents.md`

The implementation has a valuable fail-closed reviewer contract, including checks against unsupported reviewer assertions. But its native runtime attestation depends on upstream event evidence.

Fix: Capture the actual reviewer invocation, frozen input digest, child identity, output digest, and temporal ordering. Enforce reviewer isolation from candidate rankings through a separately constructed context. Store the review result before committee selection.

Acceptance: Missing, contaminated, or non-native review evidence prevents an artifact from being labeled independently reviewed. No model-generated flag can substitute for execution evidence.

CP-014

Snapshots do not yet identify the entire effective execution

Evidence: `tools/daily_run.py`, `.codex/results/`

The system already has checkpoints and some artifact hashes, which is a strong foundation. It does not demonstrate one immutable manifest binding together the exact model/session configuration, instruction sources, agent definitions, tool identities and schemas, policy revision, data inputs, and output artifacts.

Fix: Add a versioned execution manifest containing canonical identifiers and SHA-256 digests of relevant resolved inputs. Create a new immutable revision whenever a dependency is refreshed.

Acceptance: Every daily edition can be traced to its declared source/configuration snapshot, and unchanged inputs reproduce deterministic stages with matching hashes.

CP-015

The audit trail does not fully reconstruct runtime causality

Evidence: `tools/daily_run.py`, `docs/research-accountability.md`, `.codex/results/`

Stage logs and publication-accountability records exist, but these do not themselves prove what native agent or MCP operations occurred.

Fix: Introduce correlation identifiers connecting research run, stage, agent invocation, tool call, authorization decision, data observation, reviewer result, and final claim. Ingest native telemetry where supported and enrich it with locally observable events, while keeping invented governance fields distinct from native Codex telemetry.

Acceptance: From any material newsletter claim, an auditor can trace backward to the calculation, supporting observations, tool calls, and applicable policy decision without relying on model narration.

### P1/P2 — Operational completeness and maintainability

CP-016

No active daily scheduler

Evidence: `tools/daily_run.py`, `docs/daily-run.md`

Scheduling is explicitly disabled, and no Windows Task Scheduler registration is implemented. This is an intentional limitation, not a hidden defect.

Fix: Add an opt-in PowerShell scheduler installer that registers a task using the verified Codex executable and repository path. Include duplicate-run protection, time-zone handling, log retention, retries, and a removal command.

Acceptance: A scheduled local run executes at its configured time, or produces a structured failure. No external publication occurs automatically.

CP-017

Provider coverage is substantially narrower than the supplied catalog

Evidence: `docs/provider-catalog/crypto-data-tools-deduped.md`, `tools/research_sources.py`, `.codex/config.toml`

The project contains a large financial-data tool catalog, but its operational integration consists of two enabled MCP servers and a few fixed REST routes.

Fix: Turn the catalog into a capability matrix, with provider, operation, supported asset class, freshness, historical coverage, authentication, cost, rate limit, runtime interface, and operational state.

Prioritize capabilities needed for the actual newsletter: market breadth, on-chain flows, token supply, unlocks, liquidity, order-book depth, and derivatives positioning. Integrate one verified provider for each essential coverage gap before expanding to redundant sources.

Acceptance: Each research gate has a mapped, tested data source or an explicit unavailable-data disposition.

CP-018

Model selection and research-cost accounting are incomplete

Evidence: `.codex/agents/*.toml`, `tools/daily_run.py`

The custom agents inherit the parent model, which avoids relying on unavailable model identifiers. But the research run does not yet demonstrate actual per-agent model usage or cost accounting.

Fix: Define a version-compatible model policy, with higher reasoning budgets for the chief research officer and independent reviewer, and lower-cost routing for mechanical extraction or screening when supported. Record actual usage returned by the runtime; keep estimated and observed costs separate.

Acceptance: Each verified agent invocation records its model, reasoning setting, duration, usage when exposed, and any unresolved billing uncertainty.

CP-019

Git change identity and release hygiene are incomplete

Evidence: Archive contents, `AGENTS.md`

The instructions correctly require preserving unrelated changes and checking Git status/diffs. The ZIP, however, does not supply Git history or a known source-control baseline, so branch cleanliness and exact change ancestry cannot be verified.

The archive also contains `.pytest_cache` and compiled Python artifacts, which should normally be excluded from a source release.

Fix: Add a `.gitignore`, an archive packaging validator, and a source-control evidence record identifying baseline SHA, dirty-state summary, intended delta, verification, and review target. Keep publishing, committing, and pushing as separate authorized operations.

Acceptance: A clean release package excludes incidental caches, and every engineering change has a known baseline and diff.

CP-020

Research quality is evaluated more narrowly than newsletter reliability requires

Evidence: `tools/evaluate_research.py`, `docs/evaluation-report.md`

The existing offline evaluations measure useful deterministic properties. They do not measure live evidence coverage, token-identity accuracy, research hallucination rate, catalyst-date accuracy, source conflicts, or the quality of the final daily pick.

Fix: Build a versioned, labeled evaluation corpus with historical snapshots, disputed token identities, false catalysts, supply discrepancies, fake-volume cases, unavailable providers, and candidate-selection traps.

Compare a single-agent baseline against the multi-agent workflow under the same inputs, research cutoff, source permissions, and quality rubric.

Acceptance: Report reproducible denominators and actual results for identity precision, claim support, source freshness, pick-gate correctness, reviewer defect detection, output completeness, execution time, and cost.

4. Important corrections from the latest official Codex documentation

---------------------------------------------------------------------

These distinctions matter because an audit can accidentally prescribe changes that make the implementation worse.

CURRENT — Your `agents.max_concurrent_threads_per_session = 2` setting is valid. The current configuration reference explicitly recognizes it and describes `agents.max_threads` as a legacy alias. It should not be replaced with the legacy name merely because older engineering guides use it.

![](https://www.google.com/s2/favicons?domain=https://developers.openai.com&sz=32)

ChatGPT Learn

CURRENT — Your MCP `enabled_tools` approach is supported. The official reference provides allowlists and denylists, per-tool approval settings, server startup behavior, and timeouts. However, a declared allowlist is not evidence that the remote server currently exposes all those exact tool names.

![](https://www.google.com/s2/favicons?domain=https://developers.openai.com&sz=32)

ChatGPT Learn

CURRENT — Codex permission profiles and legacy sandbox settings require careful compatibility handling. The project agents use `sandbox_mode = "read-only"`, a documented setting. I would not recommend a speculative migration to permission profiles without checking the actual resolved user and managed configuration first.

![](https://www.google.com/s2/favicons?domain=https://developers.openai.com&sz=32)

ChatGPT Learn

CURRENT — The project should not be required to implement its own replacement for the entire Codex control plane. Codex already owns model-facing tool exposure, execution authorization, native agent lifecycle, and sandbox enforcement. The repository should integrate these capabilities, not duplicate them in an untrusted Python policy imitation.

5. Remediation blueprint

------------------------

Recommended sequencing, with measurable exit criteria

P0

Establish trustworthy execution

Fix CP-005, CP-010, and CP-011 first. Restore the offline suite, validate the installed Codex configuration, and produce an effective-state report. No live model session is necessary for the initial fixes.

Exit: Offline tests pass and the runtime compatibility report identifies exactly what remains unverified.

P1

Connect the research data plane

Fix CP-003, CP-004, CP-012, and CP-017. Build the research adapter interface and test authorization, provider availability, schema validation, freshness, and provenance.

Exit: A research request produces normalized, attributable market observations through a verified provider, while forbidden operations are denied.

P2

Implement real specialist orchestration

Fix CP-002, CP-006, CP-007, CP-008, CP-009, and CP-013. Add native invocation evidence, bounded delegation, independent falsification, and validated specialist handoffs.

Exit: An actual specialist produces research evidence that the committee consumes, with native runtime provenance.

P3

Complete the investment-intelligence lifecycle

Fix CP-001 and CP-020. Connect acquisition, screening, research, review, committee selection, watchlist updates, and editorial validation in a single run.

Exit: A complete daily edition or justified NO PICK result can be produced without pre-populated research artifacts.

P4

Harden operations and provenance

Fix CP-014, CP-015, CP-016, CP-018, and CP-019. Add immutable execution manifests, correlated audit records, cost tracking, scheduling, and release checks.

Exit: A daily research run is reproducible, reviewable, operationally schedulable, and distinguishable from a simulated execution.

6. What I would preserve

------------------------

Several parts of this repository should not be rewritten merely to modernize the architecture.

The strongest existing implementations are the deterministic small-cap committee, evidence-gated candidate selection, separation of research from trade authorization, NO PICK fallback, structured desk contracts, controlled REST request bounds, and partial daily-run checkpointing.

The `crypto-daily` skill already has a coherent editorial sequence. The custom agents also have reasonably specialized responsibilities rather than being thirteen copies of the same generic prompt. The best improvements will connect these pieces with actual execution evidence.

RECOMMENDED — Preserve the existing research-domain models and build the missing integration interfaces around them. Replacing everything with a large custom orchestration framework would introduce unnecessary complexity and likely weaken existing safeguards.

7. Acceptance standard for the finished system

----------------------------------------------

I would use the following final acceptance criteria:

Proposed acceptance checklist

2 of 8 evidenced as of October 11, 2026 (current worktree verification)

- [x] All offline unit and contract tests pass

- [x] No weakened assertions or hidden test skips

- [ ] Codex runtime compatibility is demonstrated

Version, configuration, agents, skills and required interfaces

- [ ] Approved data providers return validated observations

With identities, timestamps, source provenance and failure handling

- [ ] Native research delegation is proven

Runtime child IDs and actual specialist outputs

- [ ] An independent reviewer produces an attributable result

Frozen input and output hashes

- [ ] The full daily workflow runs from a declared starting state

No manually prepared research records required

- [ ] The final newsletter is supported by evidence

All material claims traceable; NO PICK remains valid

- [ ] The complete execution is auditable

Configuration, authorization, effects, artifacts and verification captured

Selections are for planning and review, not a representation that any criterion has passed. Copy checklist

Implementation follow-up — CP-011 launcher compatibility slice (October 11, 2026)
----------------------------------------------------------------------------------

Implemented in `tools/controlplane.py`: check-only plan construction is separate from host executable resolution, which uses the platform's `PATH`/`PATHEXT` behavior. An explicit live launch resolves Codex, probes the installed `codex exec --help`, checks required options before starting a session, chooses the advertised `--config`/`-c` approval-policy override or legacy `--ask-for-approval`, and fails closed if the required interface is missing. The probe uses argument arrays and a five-second bound. No live model session was started.

Regression coverage: `tests/test_controlplane.py` checks missing-binary check-only planning, modern and legacy approval syntax selection from help fixtures, and incompatible-help rejection before subprocess execution. Verification on the current Windows PowerShell worktree: `python -m pytest tests/test_controlplane.py -q` (31 passed); `python -m pytest -q --disable-warnings` (102 passed); `python -m py_compile tools/controlplane.py tests/test_controlplane.py` (exit 0); `python tools/controlplane.py launch --task "Prepare the Small-Cap Crypto Daily newsletter" --workspace examples/synthetic-workspace` (exit 0, `check-only`); `python tools/controlplane.py accept --artifact .codex/results/next-slice-acceptance.json` (exit 0, `PASS`). Installed `codex-cli 0.162.1` and actual `codex exec --help` exposed the required JSON, sandbox, workspace, ephemeral, config, and approval-policy interfaces; `python tools/controlplane.py doctor --workspace examples/synthetic-workspace` returned overall `PASS`. Linux/WSL: four focused portability tests passed using `python3 tests/test_controlplane.py ControlPlaneTests.test_check_only_plan_does_not_require_codex_binary ControlPlaneTests.test_live_launch_selects_approval_syntax_from_installed_help ControlPlaneTests.test_live_launch_adapts_to_legacy_approval_flag_when_advertised ControlPlaneTests.test_live_launch_fails_closed_when_installed_help_lacks_required_flags`; `python3 tools/controlplane.py launch --task "Prepare the Small-Cap Crypto Daily newsletter" --workspace examples/synthetic-workspace --mock-process --artifact .codex/results/linux-cp011-integration.json` also returned exit 0 with a captured JSON completion event. `python3 -m unittest discover -s tests -p "test_*.py"` ran 102 tests and failed 4 environment-sensitive assertions: missing Codex affects doctor and offline acceptance; routing/discovery assumptions cause a configured-route failure and recall of 0.96296 versus 1.0. Linux `pytest` is not installed. These broader Linux-suite failures are recorded, not represented as passes. No live model session was started.

The two checked criteria are supported by the current Windows full offline test run and focused assertion review. The other six remain unchecked. Linux portability evidence is limited to the focused fixture tests and mocked end-to-end launch; the broader Linux suite did not pass. This slice does not establish native agent execution, provider readiness, live Codex behavior, or full workflow acceptance. The original archive-run figures above remain historical audit evidence; the current worktree result is recorded here separately.
Final determination
-------------------

The project has the right foundational ideas and some meaningful executable research controls. Its weakness is integration maturity: native Codex, MCP research tools, deterministic validation, and daily newsletter production are still separate execution surfaces with incomplete operational evidence.

The most valuable next engineering change is not adding more agents or more skills. It is building and verifying one complete vertical research path:

Approved data source → validated observation → specialist analysis → independent review → committee decision → newsletter artifact.

Once that path works with real runtime evidence, additional research desks and financial-data providers become worthwhile rather than adding complexity to an unproven orchestration layer.

Implementation follow-up files changed: `tools/controlplane.py`, `tests/test_controlplane.py`, and this audit checklist. Offline acceptance artifacts: `.codex/results/next-slice-acceptance.json` and `.codex/results/next-slice-acceptance.md`.

Verification: Archive extraction and inspection completed; TOML parsing succeeded for all 13 custom agents; pytest completed with 91 passed and 8 failed, plus 60 passing subtests. Live Codex/MCP execution, Windows behavior, and scheduled operation remain unverified.

Unresolved: Actual Windows Codex installation/version, project trust, inherited managed/user configuration, authenticated provider accessibility, and native delegation evidence. These require verification on the target runtime before acceptance.
