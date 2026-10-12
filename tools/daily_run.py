"""Durable, local controller for assembling a daily newsletter from saved research."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import newsletter

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("INGESTING", "SCREENING", "RESEARCHING", "REVIEWING", "COMPOSING", "VALIDATING")
TERMINAL = {"COMPLETED", "DEGRADED"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class RunError(RuntimeError):
    pass


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunError(f"cannot read JSON input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunError(f"expected a JSON object: {path}")
    return value


def _provider_report(config: dict) -> tuple[dict, list[str]]:
    configured = config.get("providers", [])
    if not isinstance(configured, list) or any(not isinstance(p, dict) or not p.get("name") for p in configured):
        raise RunError("config.providers must be an array of objects with name fields")
    reports, missing = [], []
    for provider in configured:
        health = provider.get("health", "UNVERIFIED")
        quota = provider.get("quota", "UNVERIFIED")
        reports.append({"name": provider["name"], "health": health, "quota": quota,
                        "requests": provider.get("requests"), "cost_usd": provider.get("cost_usd"),
                        "model_usage": provider.get("model_usage")})
        if health not in ("HEALTHY", "PASS", "OK"):
            missing.append(f"provider {provider['name']} health={health}")
    return {"providers": reports}, missing


def run(manifest: Path, *, state_dir: Path | None = None, config_path: Path | None = None,
        stage_timeout: float = 120.0, today: str | None = None) -> dict:
    if stage_timeout <= 0:
        raise RunError("stage timeout must be positive")
    manifest = manifest.resolve()
    if not manifest.is_file():
        raise RunError(f"manifest does not exist: {manifest}")
    state_dir = (state_dir or ROOT / ".codex" / "daily-runs").resolve()
    if not manifest.is_relative_to(ROOT) or not state_dir.is_relative_to(ROOT):
        raise RunError("manifest and state directory must stay inside the project directory")
    state_dir.mkdir(parents=True, exist_ok=True)
    config = _read_json(config_path.resolve()) if config_path else {}
    day = today or datetime.now(timezone.utc).date().isoformat()
    try:
        date.fromisoformat(day)
    except ValueError as exc:
        raise RunError("run date must be YYYY-MM-DD") from exc
    lock = state_dir / f"{day}.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RunError(f"another daily run owns the lock: {day}") from exc
    os.close(fd)
    try:
        checkpoint_path = state_dir / f"{day}.json"
        checkpoint = _read_json(checkpoint_path) if checkpoint_path.exists() else {
            "run_id": f"{day}-{uuid.uuid4().hex}", "run_date": day, "cutoff_utc": utc_now(),
            "status": "CREATED", "manifest": str(manifest), "stages": {}, "diagnostics": [],
            "created_utc": utc_now(), "usage": {"cost_usd": 0, "model_usage": []},
        }
        if checkpoint["manifest"] != str(manifest):
            raise RunError("idempotency conflict: this UTC date already uses a different manifest")
        if checkpoint["status"] in TERMINAL:
            return checkpoint
        providers, provider_issues = _provider_report(config)
        checkpoint["providers"] = providers
        configured_schedule = config.get("schedule", {}) if isinstance(config.get("schedule", {}), dict) else {}
        checkpoint["schedule"] = {"enabled": False, "requested_enabled": bool(configured_schedule.get("enabled", False)),
                                  "daily_local_time": configured_schedule.get("daily_local_time"),
                                  "scheduler_registered": False}
        checkpoint["usage"] = {"cost_usd": sum((p.get("cost_usd") or 0) for p in providers["providers"]),
                               "model_usage": [p["model_usage"] for p in providers["providers"] if p.get("model_usage") is not None]}
        atomic_json(checkpoint_path, checkpoint)
        packet_path = state_dir / f"{day}-packet.json"
        edition_path = state_dir / f"{day}-edition.md"
        operations = {
            "INGESTING": lambda: _read_json(manifest),
            "SCREENING": lambda: _require_manifest_artifact(manifest, "screening"),
            "RESEARCHING": lambda: _research_diagnostics(manifest),
            "REVIEWING": lambda: _require_manifest_artifact(manifest, "committee"),
            "COMPOSING": lambda: _compose(manifest, packet_path),
            "VALIDATING": lambda: _validate(packet_path, edition_path),
        }
        for stage in STAGES:
            if checkpoint["stages"].get(stage, {}).get("status") == "COMPLETED":
                continue
            checkpoint["status"] = stage
            atomic_json(checkpoint_path, checkpoint)
            started = time.monotonic()
            try:
                result = operations[stage]()
                elapsed = time.monotonic() - started
                if elapsed > stage_timeout:
                    raise RunError(f"stage exceeded timeout of {stage_timeout:g}s")
                checkpoint["stages"][stage] = {"status": "COMPLETED", "elapsed_seconds": round(elapsed, 3), "result": result}
                checkpoint["diagnostics"] = [item for item in checkpoint["diagnostics"]
                                              if not item.startswith(f"{stage}: ")]
                _log(state_dir, checkpoint, stage, "COMPLETED")
            except Exception as exc:
                checkpoint["stages"][stage] = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
                checkpoint["diagnostics"].append(f"{stage}: {type(exc).__name__}: {exc}")
                checkpoint["status"] = "FAILED"
                _log(state_dir, checkpoint, stage, "FAILED", str(exc))
                atomic_json(checkpoint_path, checkpoint)
                return checkpoint
            atomic_json(checkpoint_path, checkpoint)
        checkpoint["diagnostics"].extend(provider_issues)
        research = checkpoint["stages"].get("RESEARCHING", {}).get("result", {})
        checkpoint["diagnostics"].extend(research.get("incomplete", []))
        checkpoint["status"] = "DEGRADED" if checkpoint["diagnostics"] else "COMPLETED"
        checkpoint["completed_utc"] = utc_now()
        _log(state_dir, checkpoint, "RUN", checkpoint["status"])
        atomic_json(checkpoint_path, checkpoint)
        _prune(state_dir, int(config.get("retention_days", 30)))
        return checkpoint
    finally:
        lock.unlink(missing_ok=True)


def _require_manifest_artifact(manifest: Path, key: str) -> dict:
    data = _read_json(manifest)
    value = data.get("artifacts", {}).get(key)
    if not isinstance(value, str):
        raise RunError(f"manifest.artifacts.{key} is missing")
    target = (manifest.parent / value).resolve()
    if not target.is_file():
        raise RunError(f"research artifact unavailable: {key}")
    return {"artifact": key, "available": True}


def _research_diagnostics(manifest: Path) -> dict:
    data = _read_json(manifest)
    paths = data.get("artifacts", {})
    issues = []
    desks = paths.get("desks")
    if not isinstance(desks, list) or len(desks) != 9:
        issues.append("incomplete research: expected nine persisted research desk records")
    else:
        for index, relative in enumerate(desks):
            try:
                record = _read_json((manifest.parent / relative).resolve())
            except (RunError, TypeError):
                issues.append(f"incomplete research: desk {index + 1} record is unavailable")
                continue
            if record.get("status") != "complete":
                issues.append(f"incomplete research: desk {record.get('desk_id', index + 1)} status={record.get('status', 'missing')}")
    return {"incomplete": issues, "records_created": 0}


def _compose(manifest: Path, packet: Path) -> dict:
    packet_data = newsletter.assemble(manifest)
    atomic_json(packet, packet_data)
    return {"packet": str(packet)}


def _validate(packet: Path, edition: Path) -> dict:
    data = newsletter.load_packet(packet)
    errors = newsletter.validate(data)
    if errors:
        raise RunError("; ".join(errors))
    content = newsletter.render(data)
    edition.parent.mkdir(parents=True, exist_ok=True)
    temp = edition.with_name(edition.name + ".tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, edition)
    return {"packet_valid": True, "edition": str(edition)}


def _log(directory: Path, checkpoint: dict, stage: str, result: str, detail: str = "") -> None:
    record = {"utc": utc_now(), "run_id": checkpoint["run_id"], "stage": stage, "result": result}
    if detail:
        record["detail"] = detail
    with (directory / f"{checkpoint['run_date']}.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _prune(directory: Path, retention_days: int) -> None:
    if retention_days < 1:
        raise RunError("retention_days must be at least 1")
    cutoff = time.time() - retention_days * 86400
    for path in directory.iterdir():
        if path.is_file() and not path.name.endswith(".lock") and path.stat().st_mtime < cutoff:
            path.unlink()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".codex" / "daily-runs")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--stage-timeout", type=float, default=120)
    parser.add_argument("--date", help="UTC run date (defaults to today's UTC date)")
    args = parser.parse_args(argv)
    try:
        result = run(args.manifest, state_dir=args.state_dir, config_path=args.config,
                     stage_timeout=args.stage_timeout, today=args.date)
    except RunError as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("COMPLETED", "DEGRADED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
