# Native research agents

> This file specifies native Codex specialist role contracts and evidence expectations. Codex CLI's active session is the product coordinator, evidence evaluator, editor, and writer. Static agent files and simulated Python desk records are not evidence that native delegation occurred. Product acceptance levels are defined in [MVP_ROADMAP.md](MVP_ROADMAP.md).

## Runtime and configuration

This project defines nine logical research desks: market-data, discovery, technicals, liquidity, on-chain, tokenomics, catalysts, risk, and falsification. Existing specialist agents implement market-data, on-chain, and risk; six desk-specific agents implement the remaining desks. The installed CLI observed for this slice is `codex-cli 0.162.1`; its feature list reports `multi_agent` as stable and enabled. The project config limits spawned agent threads to two at a time. Each role uses `sandbox_mode = "read-only"`; models are inherited from the parent session so this project does not pin a model or assume account availability.

## Desk handoff and report assembly

Each desk returns one JSON object validated by `tools/research_desks.py`. Required fields include schema version, candidate identity, desk ID, completion state, delegation mode and verification, evidence-backed findings, calculations with observation times, confidence, unresolved questions, assessment, and reject/escalate reasons. Finding references include source ID, locator, and an ISO-8601 timestamp with timezone. A desk may cite at most five distinct source IDs; the report may cite at most eighteen. These are citation-source budgets, not provider request quotas.

The coordinator runs no more than two independent native desks at once. It fixes candidate identity before running dependent desks. Falsification receives the original thesis and common source index without other desk conclusions. Desk outputs are separate immutable handoffs; only the coordinator assembles the final artifact. `assemble_report` orders desks consistently, fills missing results with explicit incomplete/inconclusive records, preserves findings, and lists claims where desks assigned opposing assessments. Reassembling the same inputs produces byte-stable JSON under the CLI's standard pretty-print format.

`NATIVE_DELEGATION_VERIFIED` is only valid when all nine desks are complete in native mode and the coordinator supplies observed runtime child IDs for all nine. A boolean inside model-produced desk JSON is not runtime proof. The file-based CLI has no runtime event feed and therefore records simulated/degraded execution. A simulated placeholder is not research evidence and cannot be promoted to a completed desk.

The definitions are role instructions, not proof that a task delegated. Codex must be asked to delegate (or applicable project instructions must request it), and a runtime trace showing a spawned child is required before reporting `NATIVE_DELEGATION_VERIFIED`. A TOML parse or `codex --version` only establishes configuration syntax, not agent loading or execution.

Codex custom agent files support instructions, model selection, and session config such as sandbox and MCP config. This project uses only the read-only sandbox and inherited model. The documented CLI custom-agent schema does not provide a hard arbitrary tool allowlist. Agents inherit the parent's permission mode and tool availability; therefore role instructions do not replace the parent session's sandbox, approval policy, MCP configuration, or user oversight. The project roles cannot authorize trades, payments, account actions, or external publication; the final coordinator must stop and escalate such requests.

The independent reviewer must be launched with only the original brief and the shared primary-source corpus/index. Withhold all candidate findings, summaries, rankings, and draft recommendations until its report is complete. If the runtime/context handoff exposes candidate conclusions, label the review `REVIEW_CONTAMINATED` and do not describe it as independent. This separation is a coordinator handoff rule, not a tool-enforced confidentiality boundary.

## Role contracts

Every role file defines its responsibility, required input, output format, read-only permissions, and escalation conditions. When used, the `chief-research-officer` role is a native Codex coordinator contract; it is not a Python orchestrator or a separate model service. The active Codex session owns the final decision. Specialists return evidence and analysis, never final decisions.

## Degraded execution fallback

If Codex delegation is disabled, custom agents fail to load, or spawned-thread evidence is unavailable, execute the same nine desk contracts sequentially in the coordinator context. Label every desk `DEGRADED_EXECUTION — simulated role pass`; do not claim an agent was spawned, do not call falsification independent if it saw desk conclusions, and preserve the same no-action boundaries. Stop if required evidence or authorization is unavailable.

## Verification labels

- `STATIC_CONFIG_VALIDATED`: files parse and required role contracts are present.
- `NATIVE_DELEGATION_VERIFIED`: an actual Codex runtime event or child-thread record proves at least one named custom agent was spawned and returned.
- `DEGRADED_EXECUTION`: sequential role prompts were used without native child agents.
- `UNVERIFIED`: neither runtime delegation nor a complete degraded pass was observed.

Do not promote static validation or a simulated test to native delegation evidence.
