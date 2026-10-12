---
name: small-cap-screening
description: "Apply a stated small-cap eligibility screen and produce a candidate funnel. Use for applying filters or ranking a defined universe. Do not use for broad universe construction, deep single-token diligence, or final pick authorization."
---

# Small Cap Screening

## Inputs and outputs

Input: dated universe manifest, validated market data, screen criteria, and exclusions. Output: reproducible funnel with eligible candidates, rejects, applied filters, and missing fields.

## Workflow

1. Verify universe and data timestamps. 2. Apply stated size, coverage, and market-quality filters without inventing thresholds. 3. Record each candidate’s pass/reject reason and missing fields. 4. Rank only on declared metrics and label the ranking descriptive. 5. Return the complete funnel and counts.

## Evidence and failure behavior

Evidence: source-linked input records, criteria, denominators, units, windows, transformations, and exclusion reasons. Failure: `BLOCKED` if identity or source permission fails; `INCOMPLETE` if data gaps prevent comparable screening.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
