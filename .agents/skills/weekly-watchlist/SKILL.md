---
name: weekly-watchlist
description: "Create or refresh a dated crypto watchlist with explicit validation milestones. Use for recurring monitoring priorities. Do not use for a daily pick decision, open-ended universe discovery, or price alerts presented as active orders."
---

# Weekly Watchlist

## Inputs and outputs

Input: prior watchlist if available, current candidate/evidence records, monitoring horizon, and cutoff. Output: weekly watchlist with thesis, milestone, evidence needed, expiry/review date, and avoid list.

## Workflow

1. Reconcile prior entries and outcomes; mark unavailable history. 2. Recheck identity, thesis status, and dated catalysts from available evidence. 3. Define observable milestones and expiry/review dates. 4. Remove invalidated entries or state why they remain. 5. Publish the refreshed artifact with evidence gaps.

## Evidence and failure behavior

Evidence: dated sources, original entry where available, current status, and testable milestone. Failure: `PARTIAL` if prior history or current evidence is missing; no fabricated continuity or implied live alert.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
