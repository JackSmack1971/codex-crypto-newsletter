"""Append-only publication ledger and reproducible directional forecast accounting.

The ledger is JSON Lines. Each event includes the digest of the preceding line,
so edits, removals, and reordering are detectable. Forecasts are directional
research records; this module never models fills or reports trading profit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HORIZONS = (7, 14, 21, 28)
OUTCOMES = {"VALIDATED", "INVALIDATED", "EXPIRED", "UNRESOLVED", "INSUFFICIENT_DATA"}
GENESIS = "0" * 64


def stamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamps must be timezone-qualified ISO-8601")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamps must be timezone-qualified ISO-8601") from exc
    if result.tzinfo is None:
        raise ValueError("timestamps must be timezone-qualified ISO-8601")
    return result.astimezone(timezone.utc)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_ledger(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    events: list[dict[str, Any]] = []
    previous = GENESIS
    for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"ledger line {number} is invalid JSON") from exc
        if not isinstance(item, dict) or item.get("previous_hash") != previous:
            raise ValueError(f"ledger integrity failure at line {number}")
        digest = item.pop("hash", None)
        expected = hashlib.sha256(previous.encode("ascii") + b"\n" + _canonical(item)).hexdigest()
        item["hash"] = digest
        if digest != expected:
            raise ValueError(f"ledger integrity failure at line {number}")
        previous = digest
        events.append(item)
    return events


def append_event(path: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    target = Path(path)
    events = read_ledger(target)
    previous = events[-1]["hash"] if events else GENESIS
    record = dict(event, previous_hash=previous)
    record["hash"] = hashlib.sha256(previous.encode("ascii") + b"\n" + _canonical(record)).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return record


def publish(path: str | Path, record: dict[str, Any]) -> dict[str, Any]:
    required = ("record_id", "kind", "published_at", "identity", "thesis", "direction",
                "reference_price", "venue", "confirmation", "invalidation", "expires_at")
    if any(record.get(key) in (None, "") for key in required):
        raise ValueError("publication requires " + ", ".join(required))
    if record["kind"] not in ("daily_pick", "watchlist_candidate"):
        raise ValueError("kind must be daily_pick or watchlist_candidate")
    if record["direction"] not in ("LONG", "SHORT", "NEUTRAL"):
        raise ValueError("direction must be LONG, SHORT, or NEUTRAL")
    if not isinstance(record["identity"], dict) or not isinstance(record["confirmation"], dict) or not isinstance(record["invalidation"], dict):
        raise ValueError("identity, confirmation, and invalidation must be objects")
    if not isinstance(record["thesis"], str) or not record["thesis"].strip():
        raise ValueError("thesis must be non-empty")
    if isinstance(record["reference_price"], bool) or not isinstance(record["reference_price"], (int, float)) or record["reference_price"] <= 0:
        raise ValueError("reference_price must be positive")
    if not isinstance(record["venue"], str) or not record["venue"].strip():
        raise ValueError("venue must identify the observed reference venue")
    published_at, expires_at = stamp(record["published_at"]), stamp(record["expires_at"])
    if expires_at <= published_at:
        raise ValueError("expires_at must follow publication")
    events = read_ledger(path)
    if any(e["type"] == "publication" and e["record_id"] == record["record_id"] for e in events):
        raise ValueError("publication record is immutable; record_id already exists")
    frozen = {key: record[key] for key in required}
    frozen.update({k: record[k] for k in ("catalyst", "source_ids") if k in record})
    return append_event(path, {"type": "publication", **frozen})


def append_observation(path: str | Path, record_id: str, observation: dict[str, Any]) -> dict[str, Any]:
    events = read_ledger(path)
    publication = next((e for e in events if e["type"] == "publication" and e["record_id"] == record_id), None)
    if publication is None:
        raise ValueError("unknown publication record_id")
    when = stamp(observation.get("observed_at"))
    if when < stamp(publication["published_at"]):
        raise ValueError("subsequent observations cannot predate publication")
    price = observation.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        raise ValueError("observation price must be positive")
    if not isinstance(observation.get("venue"), str) or not observation["venue"].strip():
        raise ValueError("observation venue is required")
    for key in ("high", "low"):
        if key in observation and (not isinstance(observation[key], (int, float)) or observation[key] <= 0):
            raise ValueError(f"{key} must be positive")
    return append_event(path, {"type": "price_observation", "record_id": record_id, **observation})


def append_update(path: str | Path, record_id: str, *, catalyst_outcome: Any = None, thesis_status: str | None = None, at: str) -> dict[str, Any]:
    if thesis_status not in (None, "ACTIVE", "VALIDATED", "INVALIDATED"):
        raise ValueError("thesis_status must be ACTIVE, VALIDATED, or INVALIDATED")
    events = read_ledger(path)
    if not any(e["type"] == "publication" and e["record_id"] == record_id for e in events):
        raise ValueError("unknown publication record_id")
    update = {"type": "thesis_update", "record_id": record_id, "at": at}
    stamp(at)
    if catalyst_outcome is not None:
        update["catalyst_outcome"] = catalyst_outcome
    if thesis_status is not None:
        update["thesis_status"] = thesis_status
    if len(update) == 3:
        raise ValueError("an update must contain catalyst_outcome or thesis_status")
    return append_event(path, update)


def _condition_hit(condition: dict[str, Any], observations: list[dict[str, Any]]) -> bool:
    operator = condition.get("type")
    target = condition.get("value")
    if operator not in ("price_at_or_above", "price_at_or_below") or not isinstance(target, (int, float)):
        return False
    return any((o["price"] >= target if operator == "price_at_or_above" else o["price"] <= target) for o in observations)


def calculate(events: list[dict[str, Any]], as_of: str | None = None) -> dict[str, Any]:
    now = stamp(as_of) if as_of else None
    publications = {e["record_id"]: e for e in events if e["type"] == "publication"}
    result = []
    for rid, pub in publications.items():
        observations = [e for e in events if e.get("type") == "price_observation" and e.get("record_id") == rid
                        and (now is None or stamp(e["observed_at"]) <= now)]
        observations.sort(key=lambda o: stamp(o["observed_at"]))
        updates = [e for e in events if e.get("type") == "thesis_update" and e.get("record_id") == rid
                   and (now is None or stamp(e["at"]) <= now)]
        expires = stamp(pub["expires_at"])
        expired = now is not None and now >= expires
        eligible_obs = [o for o in observations if stamp(o["observed_at"]) <= expires]
        eligible_updates = [u for u in updates if stamp(u["at"]) <= expires]
        last_status = next((e["thesis_status"] for e in reversed(eligible_updates) if "thesis_status" in e), "ACTIVE")
        decisive = []
        for observation in eligible_obs:
            if _condition_hit(pub["invalidation"], [observation]):
                decisive.append((stamp(observation["observed_at"]), "INVALIDATED"))
            if _condition_hit(pub["confirmation"], [observation]):
                decisive.append((stamp(observation["observed_at"]), "VALIDATED"))
        for update in eligible_updates:
            if update.get("thesis_status") in ("INVALIDATED", "VALIDATED"):
                decisive.append((stamp(update["at"]), update["thesis_status"]))
        if decisive:
            outcome = min(decisive, key=lambda event: event[0])[1]
        elif expired:
            outcome = "EXPIRED"
        else:
            outcome = "UNRESOLVED"
        if last_status == "INVALIDATED" and outcome == "UNRESOLVED":
            outcome = "INVALIDATED"
        elif last_status == "VALIDATED" and outcome == "UNRESOLVED":
            outcome = "VALIDATED"
        ref = float(pub["reference_price"])
        direction = pub["direction"]
        horizons = {}
        for days in HORIZONS:
            target = stamp(pub["published_at"]) + timedelta(days=days)
            if now is not None and now < target:
                horizons[f"{days}d"] = {"status": "NOT_DUE", "return_pct": None}
                continue
            candidates = [o for o in observations if abs((stamp(o["observed_at"]) - target).total_seconds()) <= 12 * 3600]
            if not candidates or direction == "NEUTRAL":
                horizons[f"{days}d"] = {"status": "INSUFFICIENT_DATA", "return_pct": None}
                continue
            obs = min(candidates, key=lambda o: abs((stamp(o["observed_at"]) - target).total_seconds()))
            raw = (float(obs["price"]) / ref - 1) * 100
            horizons[f"{days}d"] = {"status": "OBSERVED", "return_pct": round(raw if direction == "LONG" else -raw, 6), "observed_at": obs["observed_at"]}
        excursions = {"status": "INSUFFICIENT_DATA", "max_favorable_pct": None, "max_adverse_pct": None}
        ranged = [o for o in observations if "high" in o and "low" in o]
        if ranged and direction != "NEUTRAL":
            favorable = [((o["high"] / ref - 1) if direction == "LONG" else (1 - o["low"] / ref)) * 100 for o in ranged]
            adverse = [((o["low"] / ref - 1) if direction == "LONG" else (1 - o["high"] / ref)) * 100 for o in ranged]
            excursions = {"status": "OBSERVED", "max_favorable_pct": round(max(favorable), 6), "max_adverse_pct": round(min(adverse), 6)}
        result.append({"record_id": rid, "kind": pub["kind"], "published_at": pub["published_at"], "identity": pub["identity"],
            "thesis": pub["thesis"], "direction": direction, "reference_price": ref, "reference_venue": pub["venue"],
            "confirmation": pub["confirmation"], "invalidation": pub["invalidation"], "expires_at": pub["expires_at"],
            "thesis_status": last_status, "outcome": outcome, "observation_count": len(observations),
            "price_observations": observations, "catalyst_outcomes": [e["catalyst_outcome"] for e in updates if "catalyst_outcome" in e],
            "performance": horizons, "excursions": excursions, "performance_type": "directional forecast; no executable strategy or realizable profit implied"})
    stats = {}
    for horizon in HORIZONS:
        eligible = [r for r in result if r["performance"][f"{horizon}d"]["status"] == "OBSERVED"]
        stats[f"{horizon}d"] = {"observed_count": len(eligible), "cohort_count": len(result),
            "coverage": (len(eligible) / len(result) if result else None),
            "directional_hit_rate": (sum(r["performance"][f"{horizon}d"]["return_pct"] > 0 for r in eligible) / len(eligible) if eligible else None)}
    return {"as_of": as_of, "records": result, "statistics": stats,
            "statistics_note": "Denominators are observed records only; missing prices are excluded. Return percentages are directional price changes from the publication reference, not realized profit.",
            "integrity": "hash-chain verified"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("publish"); add.add_argument("ledger", type=Path); add.add_argument("record", type=Path)
    obs = sub.add_parser("observe"); obs.add_argument("ledger", type=Path); obs.add_argument("record_id"); obs.add_argument("observation", type=Path)
    update = sub.add_parser("update"); update.add_argument("ledger", type=Path); update.add_argument("record_id"); update.add_argument("event", type=Path)
    report = sub.add_parser("report"); report.add_argument("ledger", type=Path); report.add_argument("--as-of")
    args = parser.parse_args(argv)
    try:
        if args.command == "publish":
            record = json.loads(args.record.read_text(encoding="utf-8")); publish(args.ledger, record); print("PASS: immutable publication appended")
        elif args.command == "observe":
            observation = json.loads(args.observation.read_text(encoding="utf-8")); append_observation(args.ledger, args.record_id, observation); print("PASS: observation appended")
        elif args.command == "update":
            event = json.loads(args.event.read_text(encoding="utf-8"))
            append_update(args.ledger, args.record_id, catalyst_outcome=event.get("catalyst_outcome"),
                          thesis_status=event.get("thesis_status"), at=event["at"])
            print("PASS: thesis/catalyst update appended")
        else:
            print(json.dumps(calculate(read_ledger(args.ledger), args.as_of), ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
