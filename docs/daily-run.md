# Deterministic replay and local run controller

> This utility is supporting infrastructure, not the product's AI orchestrator. Codex CLI itself plans and conducts newsletter research, synthesizes evidence, reviews, and writes the issue. This Python path consumes saved fixture/research artifacts and does not establish native Codex agent execution. The accepted product architecture and milestones are in [ARCHITECTURE.md](ARCHITECTURE.md) and [MVP_ROADMAP.md](MVP_ROADMAP.md).

## Build a replay edition in one command

The deterministic replay tool creates local artifacts from a declared replay
fixture, then renders a draft edition without manual artifact assembly:

```powershell
python tools/daily_orchestrator.py --date 2026-10-11 --replay tests/fixtures/market-observations.json --output .codex/results/daily-replay
```

The replay can be a provider-neutral observation array accepted by
`research_sources.replay`, or an object with `observations`, optional `history`,
`benchmark_history`, `sources`, and `market` fields. The output must be a new or
empty project-local directory. The command stages its work and only commits the
directory after successful editorial assembly; interrupted and failed stages
leave no published run directory. Repeated runs require a fresh empty output
directory. `run-manifest.json` records stage status, provenance, artifact hashes,
and disabled external effects. Desk records remain explicitly incomplete until
a separately verified research execution boundary is integrated, so editions
are degraded and committee picks remain subject to existing evidence gates.

To exercise the existing checkpoint controller against that compatible
manifest, run:

```powershell
python tools/daily_run.py .codex/results/daily-replay/manifest.json
```

Neither command fetches live data, starts a Codex session, calls MCP, trades,
schedules, or publishes. Replay output is not current market intelligence;
research desk records remain incomplete and explicitly simulated/degraded.

Run the controller manually from the repository root after saving a newsletter
assembly manifest and all referenced research artifacts inside this project:

```powershell
python tools/daily_run.py path\to\manifest.json
```

The controller writes UTC-date checkpoints, packet/Markdown artifacts, and JSONL
stage logs under `.codex/daily-runs/`. Repeating the same manifest on the same
UTC date returns its existing terminal run. A failed or interrupted stage can
be resumed with the same command; completed stages are checkpointed. A second
writer for that date fails closed on the lock. A different manifest for an
existing date is an idempotency conflict. Research records are never created by
the controller; stages consume the records already named by the manifest.

Optional JSON configuration:

```json
{
  "retention_days": 30,
  "schedule": { "enabled": false, "daily_local_time": "07:00" },
  "providers": [
    { "name": "market-data", "health": "UNVERIFIED", "quota": "UNVERIFIED" }
  ]
}
```

Provider health other than `HEALTHY`, `PASS`, or `OK` yields a `DEGRADED`
outcome. Quota values remain reported as provided; the controller does not
probe providers or infer quota health. Optional `cost_usd` and `model_usage`
fields are recorded when supplied. Schedule time is descriptive only:
`enabled` in configuration is reported as `requested_enabled`, while execution
and Windows Task Scheduler registration remain disabled. There is no background
completion inference. `--stage-timeout` sets the per-stage elapsed-time budget.

All input and state paths must remain under the project root, matching the
newsletter assembler's local artifact boundary.
