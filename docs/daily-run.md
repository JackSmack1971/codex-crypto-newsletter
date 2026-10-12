# Local daily run controller

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
