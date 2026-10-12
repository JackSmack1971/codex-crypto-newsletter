---
name: liquidity-analysis
description: "Assess whether a named asset has measurable venue liquidity and plausible execution capacity. Use for depth, turnover quality, concentration, and slippage analysis. Do not use for wallet-flow attribution, shortability claims, or trade execution."
---

# Liquidity Analysis

## Inputs and outputs

Input: resolved asset and venues, order-size assumptions, snapshots/trades, and horizon. Output: venue-level liquidity assessment with depth, concentration, slippage estimates, and caveats.

## Workflow

1. Resolve asset and instrument per venue. 2. Check observation time and market state. 3. Separate reported volume from executable depth and estimate slippage only where book data supports it. 4. Compare venues and identify concentration/withdrawal constraints. 5. Report tested notionals and unsupported conclusions.

## Evidence and failure behavior

Evidence: venue/source, timestamp, units, order-size assumptions, book depth or trade method, and reproducible calculations. Failure: `UNVERIFIED` without book or comparable data; spot liquidity does not establish shortability.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
