---
name: newsletter-production
description: "Assemble validated research artifacts into the Small-Cap Crypto Daily edition. Use for drafting, validating, or rendering the newsletter packet. Do not use as a substitute for missing research, independent review, editorial approval, or external publication."
---

# Newsletter Production

Codex CLI's active session is the editor and author. It drafts from the validated evidence, resolves reviewer feedback, and owns the final narrative. The Python packet utilities below supply deterministic assembly, numerical checks, structure validation, and rendering; the `newsletter-editor` agent definition is an optional native reviewer/editor role and is not required as a separate service or launcher.

## Inputs and outputs

Input: validated research evidence, decision and watchlist records, provenance, and methodology. Output: a Codex-authored v1 13-section edition, deterministic fact-check/structure results, and local Markdown draft. When using the Python assembler, its input manifest additionally requires persisted market/screening snapshots, exactly nine desk reports, committee decision, seven-day watchlist state, prior-pick accountability, sources, and methodology.

## Workflow

1. Confirm evidence cutoff, source permission, and provenance. 2. Ask Codex to write all thirteen sections, preserving the exact section order and evidence gaps. 3. If assembling persisted evidence with Python, run `python tools/newsletter.py assemble <manifest.json> --output <packet.json>`. 4. Register material numerical claims with `editorial_claims`, then run `python tools/newsletter.py fact-check <packet.json> --manifest <manifest.json>` and `check`. 5. Incorporate independent research and editorial reviewer findings; retain review records. 6. Render and save the Markdown draft locally. No publish action is available or authorized by this workflow.

## Evidence and failure behavior

Evidence: packet source IDs/timestamps, validation output, and rendered artifact. Failure: report a partial edition if required inputs are missing; never fabricate findings or publish externally.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
