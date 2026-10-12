---
name: technical-analysis
description: "Assess price structure, momentum, and chart-derived conditions for named crypto assets. Use for technical analysis on supplied or authorized time series. Do not use for on-chain claims, fundamentals, or trade execution."
---

# Technical Analysis

## Inputs and outputs

Input: identified assets, time-series observations, aligned windows, and question/horizon. Output: technical analysis note with calculations, scenarios, invalidation observations, and data limitations.

## Workflow

1. Validate instrument identity and series continuity. 2. State windows, sampling, and indicator formulas. 3. Calculate only supported measures and describe observable structure. 4. Present bullish, bearish, and neutral readings with contrary evidence. 5. State what observation would invalidate each scenario.

## Evidence and failure behavior

Evidence: source, timestamps, timeframe, formulas/parameters, and enough values to reproduce each calculation. Failure: `INSUFFICIENT EVIDENCE` for sparse or misaligned series; no unsupported price targets or execution instructions.

Use the shared [research evidence contract](../crypto-daily/references/research-evidence.md) for source permissions, evidence labels, and common failure handling.
