---
name: newsletter-production
description: "Assemble validated research artifacts into the Small-Cap Crypto Daily edition. Use for drafting, validating, or rendering the newsletter packet. Do not use as a substitute for missing research, independent review, editorial approval, or external publication."
---

# Newsletter Production

## Inputs and outputs

Input: an edition manifest with persisted market/screening snapshots, exactly nine desk reports, committee decision, seven-day watchlist state, prior-pick accountability, sources, and methodology. Output: assembled v1 13-section evidence packet, an editorial draft from the `newsletter-editor` specialist, a fact-check result, and local Markdown preview.

## Workflow

1. Confirm evidence cutoff, source permission, and required input artifacts. 2. Assemble with `python tools/newsletter.py assemble <manifest.json> --output <packet.json>`. 3. Give the packet and artifact index to the read-only `newsletter-editor`; preserve the exact section order and evidence gaps. 4. Require `editorial_claims` and `editorial_checklist`, then run `python tools/newsletter.py fact-check <packet.json> --manifest <manifest.json>`. 5. Run `check`, then render a local preview; release only under the existing explicit human approval contract.

## Evidence and failure behavior

Evidence: packet source IDs/timestamps, validation output, and rendered artifact. Failure: report a partial edition if required inputs are missing; never fabricate findings or publish externally.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
