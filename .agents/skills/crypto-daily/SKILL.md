---
name: crypto-daily
description: "Orchestrate a complete evidence-led Small-Cap Crypto Daily edition. Use for the full daily newsletter packet, candidate review, or research appendix. Do not use for a single research desk workflow, external publication, or trade execution."
---

# Small-Cap Crypto Daily

Use this entry point for the complete newsletter workflow. For one bounded desk request, route to its focused skill instead.

## Inputs and outputs

Input: requested edition date/cutoff, source permissions, available research records, and prior decision/watchlist records where available. Output: evidence manifest, candidate funnel, pick/no-pick decision, and a validated thirteen-section local newsletter packet.

## Workflow

1. Read [shared research evidence contract](references/research-evidence.md), [editorial contract](references/editorial-contract.md), [release checklist](references/release-checklist.md), and `docs/edition-contract.md`.
2. Confirm source permissions in `.codex/source-policy.json`; default is deny. Never treat tool availability as authorization. No trade, account access, external messages, or external publication is authorized by this workflow.
3. Complete only applicable desk workflows, preserving their named input/output artifacts: [universe discovery](../crypto-universe-discovery/SKILL.md), [market-data validation](../market-data-validation/SKILL.md), [small-cap screening](../small-cap-screening/SKILL.md), [technical analysis](../technical-analysis/SKILL.md), [liquidity analysis](../liquidity-analysis/SKILL.md), [on-chain intelligence](../onchain-intelligence/SKILL.md), [tokenomics diligence](../tokenomics-diligence/SKILL.md), and [catalyst research](../catalyst-research/SKILL.md).
4. For finalists, run [investment falsification](../investment-falsification/SKILL.md), then [daily pick selection](../daily-pick-selection/SKILL.md). Missing evidence or independent review means NO PICK.
5. Include the [weekly watchlist](../weekly-watchlist/SKILL.md) only when a watchlist update is in scope. Persist market/screening snapshots, all nine desk outputs, the committee decision, watchlist state, accountability record, source manifest, and methodology record. Assemble these with `python tools/newsletter.py assemble <manifest.json> --output <packet.json>`.
6. Hand the assembled packet and artifact index to the read-only `newsletter-editor`. Require the editorial checklist and every material numerical claim's JSON Pointer/source-ID evidence record, then run `python tools/newsletter.py fact-check <packet.json> --manifest <manifest.json>`.
7. Run `python tools/newsletter.py check <packet.json>` and render a local preview. Release requires the existing human editorial approval contract; rendering is local only.

## Evidence and failure behavior

Keep source identity, observation/retrieval times, units, windows, transformations, and coverage. Preserve conflicts and unknowns. Missing permission, invalid identity, unavailable evidence, or failed validation produces a clearly scoped partial edition and no investment-cleared pick. Do not claim independent execution unless a genuinely independent reviewer supplied a recorded verdict.
