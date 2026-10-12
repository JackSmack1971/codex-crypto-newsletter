---
name: crypto-universe-discovery
description: "Build or reconcile a scoped crypto asset universe. Use for universe coverage, identity resolution, or inclusion rules. Do not use for price validation, candidate ranking, or newsletter assembly."
---

# Crypto Universe Discovery

## Inputs and outputs

Input: requested universe, cutoff, allowed source evidence, and inclusion rules. Output: universe manifest with stable asset identifiers, inclusion/exclusion reasons, coverage counts, and unresolved identities.

## Workflow

1. Read the requested scope and source permissions. 2. Collect only authorized universe/identity observations. 3. Resolve chain, contract/provider ID, asset, and ticker; preserve ambiguous records separately. 4. Apply explicit inclusion rules and report coverage against the requested scope. 5. Save or return the manifest; stop if source permission or identity evidence is insufficient.

## Evidence and failure behavior

Evidence: source IDs, retrieval and observation times, query/scope, stable identifiers, exclusion reasons, and coverage denominator. Failure: `BLOCKED` when retrieval is unauthorized; `INSUFFICIENT EVIDENCE` for unresolved identity or incomplete coverage.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
