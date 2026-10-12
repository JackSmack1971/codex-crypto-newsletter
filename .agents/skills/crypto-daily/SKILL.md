---
name: crypto-daily
description: "Orchestrate a complete evidence-led Small-Cap Crypto Daily edition. Use for the full daily newsletter packet, candidate review, or research appendix. Do not use for a single research desk workflow, external publication, or trade execution."
---

# Small-Cap Crypto Daily

The active Codex CLI session is the research coordinator and final author. Use native Codex subagents for bounded independent specialist tasks when useful, and retain runtime evidence before claiming delegation. Python utilities perform deterministic data handling and validation; they do not orchestrate AI research. Never treat local replay output as current market evidence.

Use this entry point for the complete newsletter workflow. For one bounded desk request, route to its focused skill instead.

## Inputs and outputs

Input: requested edition date/cutoff, source permissions, available research records, and prior decision/watchlist records where available. Output: evidence manifest, candidate funnel, pick/no-pick decision, and a validated thirteen-section local newsletter packet.

## Workflow

1. Read [shared research evidence contract](references/research-evidence.md), [editorial contract](references/editorial-contract.md), [release checklist](references/release-checklist.md), and `docs/edition-contract.md`.
2. Confirm source permissions in `.codex/source-policy.json`; default is deny. Never treat tool availability as authorization. No trade, account access, external messages, or external publication is authorized by this workflow.
3. Complete only applicable desk workflows, preserving their named input/output artifacts: [universe discovery](../crypto-universe-discovery/SKILL.md), [market-data validation](../market-data-validation/SKILL.md), [small-cap screening](../small-cap-screening/SKILL.md), [technical analysis](../technical-analysis/SKILL.md), [liquidity analysis](../liquidity-analysis/SKILL.md), [on-chain intelligence](../onchain-intelligence/SKILL.md), [tokenomics diligence](../tokenomics-diligence/SKILL.md), and [catalyst research](../catalyst-research/SKILL.md).
4. For finalists, run [investment falsification](../investment-falsification/SKILL.md), then [daily pick selection](../daily-pick-selection/SKILL.md). Missing evidence or independent review means NO PICK.
5. Develop and persist the seven-day watchlist with evidence, review milestones, risks, and invalidation conditions. Retain source/candidate records, source manifest, methodology, and decision rationale.
6. Ask an independent native reviewer to challenge material claims, candidate ranking, conflicts, and the PICK/NO PICK decision. Keep its input appropriately separate from the conclusions it reviews. Ask an editorial reviewer to assess the finished issue. Record reviewer execution evidence and findings.
7. Codex writes and revises all thirteen sections. Use `python tools/newsletter.py assemble`, `fact-check`, `check`, and `render` as deterministic support where their input contracts apply. Resolve all fact-check failures and clearly disclose evidence gaps before saving the local draft.
8. Save the edition and evidence under `.codex/results/<run-id>/` for operator review. No external publishing or trading is part of this workflow.

For offline contract testing only, `tools/daily_orchestrator.py` can build a replay edition from `tests/fixtures/market-observations.json`. Its output is simulated, produces incomplete desk handoffs, and does not perform native Codex research or delegation.

## Evidence and failure behavior

Keep source identity, observation/retrieval times, units, windows, transformations, and coverage. Preserve conflicts and unknowns. Missing permission, invalid identity, unavailable evidence, or failed validation produces a clearly scoped partial edition and no investment-cleared pick. Do not claim independent execution unless a genuinely independent reviewer supplied a recorded verdict.
