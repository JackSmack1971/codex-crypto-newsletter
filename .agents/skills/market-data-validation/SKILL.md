---
name: market-data-validation
description: "Validate supplied crypto market observations for identity, freshness, units, and consistency. Use for feed QA or price/volume reconciliation. Do not use to discover a universe, interpret charts, or rank candidates."
---

# Market Data Validation

## Inputs and outputs

Input: asset identifiers, market observations, timestamp/window metadata, and source policy. Output: validation record with per-field status, aligned comparisons, discrepancies, and usable/withheld fields.

## Workflow

1. Confirm identity keys match across records. 2. Check source observation time, retrieval time, window, units, and missingness. 3. Align comparable fields and quantify disagreement. 4. Mark each field PASS, FAIL, or UNVERIFIED with reason. 5. Withhold invalid fields from downstream calculations.

## Evidence and failure behavior

Evidence: raw supplied values or source references, units, timestamps, comparison method, and discrepancy thresholds. Failure: `BLOCKED` on unauthorized retrieval; `UNVERIFIED` where timestamps, identity, or comparable units are absent.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
