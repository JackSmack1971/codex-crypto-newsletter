# Research control-plane evaluation

Run the deterministic, offline suite with:

```powershell
python tools/evaluate_research.py --mode offline-single --output .codex/results/evaluation-baseline.json
python tools/evaluate_research.py --mode offline-single --compare .codex/results/evaluation-baseline.json --output .codex/results/evaluation-current.json
```

The fixed workload catalogue is `examples/evaluation-workloads.json`: normal day, quiet market, speculative rally, manipulation, provider outage, conflicting data, missing token supply, and NO PICK. The evaluator also runs the 44-case skill-routing corpus and validates the saved NO PICK newsletter. The fixture hash and workload IDs are included in each report; comparison fails if either differs. Reports use observed values where available and explicit `UNMEASURED` statuses elsewhere.

## Baseline and paired rerun

Baseline was recorded before evaluating any tuning in this slice. The current rerun uses the same workload IDs and fixture SHA-256 `936fac692b9f9c5e20af775160d207b6614336900b248b5e1de4917f8dcf4581`.

| Measure | Baseline | Paired rerun | Result |
|---|---:|---:|---|
| Routing precision | 27/27 = 100% | 27/27 = 100% | 0 pp |
| Routing recall | 27/27 = 100% | 27/27 = 100% | 0 pp |
| Calculation checks | 3/3 = 100% | 3/3 = 100% | no change |
| Screening repeatability | reproducible | reproducible | no change |
| Newsletter completeness | valid, 13 sections | valid, 13 sections | no change |
| Offline evaluator time | 0.016738 s | 0.015671 s | -0.001067 s; too small and noisy to claim an optimization |

This is repeatability evidence, not an optimization uplift: no routing, context, cache, concurrency, or agent activation setting was changed. No tuning is recommended from these observations.

## Requested metrics and evidence status

| Metric | Status |
|---|---|
| Skill routing precision/recall | Measured against 44 labeled cases; 27 positive route decisions, 27/27 precision and recall |
| Delegation success / unnecessary delegation | Unmeasured live; simulated roles are not counted as native agent launches |
| Research evidence coverage / source freshness | Unmeasured; workload descriptions do not contain a labeled research corpus |
| Token identity accuracy | Unmeasured; no identity ground-truth corpus |
| Calculation correctness | 3/3 fixed arithmetic checks |
| Candidate-screening reproducibility | Same NO PICK input yields identical decisions across two runs |
| Independent reviewer defect detection | Unmeasured; no labeled injected-defect evaluation corpus |
| Unsupported-claim frequency | Unmeasured; offline suite generates no research claims |
| Newsletter completeness | Valid NO PICK fixture; 13 sections |
| Daily runtime/resources | Evaluator only: 0.015671 s on paired run; CPU/memory not collected |
| Cost per completed edition | Unmeasured; no edition run or billing telemetry |
| Historical pick/watchlist outcomes | Unmeasured; no accountability ledger supplied |

Single-agent versus multi-agent performance remains **UNVERIFIED**. The `offline-multi` mode is only a run label and does not activate agents; valid comparison needs coordinator-observed invocation/thread records, token usage where available, elapsed time, cost, and quality outputs for both modes on the exact same workload IDs and starting-state hash. No model session or paid research was launched. Reports record zero live invocations for this offline suite.
