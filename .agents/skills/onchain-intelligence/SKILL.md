---
name: onchain-intelligence
description: "Analyze supplied or authorized on-chain activity and its attribution limits. Use for contract, transaction, and wallet-level observations. Do not use turnover as proof of accumulation or identify owners without evidence."
---

# Onchain Intelligence

## Inputs and outputs

Input: chain, contract, block/time window, query or dataset, and research question. Output: on-chain observation brief separating direct measurements, entity labels, and hypotheses.

## Workflow

1. Verify chain and contract identity. 2. Record query scope, block range, and data coverage. 3. Reproduce activity/count/value measures. 4. Evaluate address labels and alternative explanations. 5. Separate measured activity from inferred intent and state what cannot be attributed.

## Evidence and failure behavior

Evidence: chain, contract, block range, query provenance, units, label provenance, and reconciliation method. Failure: `BLOCKED` if query access is unauthorized; `UNVERIFIED` if labels or coverage cannot be validated.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
