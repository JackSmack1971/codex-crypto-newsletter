---
name: daily-pick-selection
description: "Apply the daily candidate eligibility gates and choose a research pick or no-pick outcome. Use for final candidate qualification after diligence artifacts exist. Do not use to discover candidates, substitute a score for gates, or authorize a trade."
---

# Daily Pick Selection

## Inputs and outputs

Input: dated candidate funnel, identity/data validation, liquidity, supply, security, catalyst, value-capture, risk, and independent review records. Output: pick decision record with every gate, rationale, horizon, reviewer status, and missing conditions.

## Workflow

1. Confirm all inputs refer to the same asset and cutoff. 2. Evaluate each non-compensable gate as PASS, FAIL, or UNKNOWN. 3. Block selection for any FAIL/UNKNOWN or missing independent reviewer PASS. 4. If all gates pass, state the bounded research thesis and invalidation; otherwise record NO PICK and the decisive blocker. 5. Preserve the decision record.

## Evidence and failure behavior

Evidence: linked diligence artifacts and actual independent reviewer record. Failure: default to NO PICK for missing or conflicting evidence; a score cannot offset a failed gate, and no output authorizes an order or allocation.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
