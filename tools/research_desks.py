"""Validate and reproducibly assemble immutable nine-desk research handoffs."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DESK_IDS = (
    "market-data", "discovery", "technicals", "liquidity", "on-chain",
    "tokenomics", "catalysts", "risk", "falsification",
)
ASSESSMENTS = {"bullish", "bearish", "inconclusive"}
STATUSES = {"complete", "incomplete"}
MODES = {"native", "simulated"}
MAX_SOURCES_PER_DESK = 5
MAX_SOURCES_PER_REPORT = 18
_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$")


class DeskValidationError(ValueError):
    """Raised when a desk handoff is malformed or exceeds its evidence budget."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DeskValidationError(message)


def validate_desk_result(result: object) -> dict:
    """Validate the stable schema shared by native and simulated desks."""
    _require(isinstance(result, dict), "desk result must be an object")
    _require(result.get("schema_version") == 1, "schema_version must be 1")
    identity = result.get("candidate_identity")
    _require(isinstance(identity, dict), "candidate_identity must be an object")
    _require(all(isinstance(identity.get(k), str) and identity[k].strip() for k in ("candidate_id", "name")), "candidate identity requires candidate_id and name")
    _require(result.get("desk_id") in DESK_IDS, "unknown desk_id")
    _require(result.get("status") in STATUSES, "status must be complete or incomplete")
    _require(result.get("delegation_mode") in MODES, "delegation_mode must be native or simulated")
    _require(isinstance(result.get("delegation_verified"), bool), "delegation_verified must be boolean")
    _require(not result["delegation_verified"] or result["delegation_mode"] == "native", "simulated delegation cannot be runtime-verified")
    _require(result.get("assessment") in ASSESSMENTS, "assessment must be bullish, bearish, or inconclusive")
    confidence = result.get("confidence")
    _require(isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0 <= confidence <= 1, "confidence must be between 0 and 1")
    for key in ("findings", "calculations", "unresolved_questions", "reasons_to_reject", "reasons_to_escalate"):
        _require(isinstance(result.get(key), list), f"{key} must be an array")
    sources = set()
    for finding in result["findings"]:
        _require(isinstance(finding, dict) and isinstance(finding.get("claim"), str) and finding["claim"].strip(), "each finding requires a claim")
        refs = finding.get("evidence_refs")
        _require(isinstance(refs, list) and refs, "each finding requires evidence_refs")
        for ref in refs:
            _require(isinstance(ref, dict) and all(isinstance(ref.get(k), str) and ref[k].strip() for k in ("source_id", "locator", "observed_at")), "evidence refs require source_id, locator, and observed_at")
            _require(bool(_TIMESTAMP.fullmatch(ref["observed_at"])), "observed_at must be an ISO-8601 timestamp with timezone")
            sources.add(ref["source_id"])
    _require(len(sources) <= MAX_SOURCES_PER_DESK, f"desk source budget exceeded ({MAX_SOURCES_PER_DESK})")
    for calculation in result["calculations"]:
        _require(isinstance(calculation, dict) and all(k in calculation for k in ("name", "value", "unit", "formula", "observed_at")), "calculations require name, value, unit, formula, and observed_at")
        _require(isinstance(calculation["observed_at"], str) and bool(_TIMESTAMP.fullmatch(calculation["observed_at"])), "calculation observed_at must be ISO-8601 with timezone")
    _require(result["status"] != "incomplete" or result["assessment"] == "inconclusive", "incomplete desks must be inconclusive")
    return result


def incomplete_result(identity: dict, desk_id: str, mode: str = "simulated") -> dict:
    """Create an explicit placeholder for a desk that did not return evidence."""
    result = {
        "schema_version": 1, "candidate_identity": identity, "desk_id": desk_id,
        "status": "incomplete", "delegation_mode": mode,
        "delegation_verified": False, "findings": [], "calculations": [],
        "confidence": 0.0, "unresolved_questions": ["Desk did not return a completed result."],
        "assessment": "inconclusive", "reasons_to_reject": [],
        "reasons_to_escalate": ["Desk output missing; research report is incomplete."],
    }
    return validate_desk_result(result)


def assemble_report(candidate_identity: dict, desk_results: list[dict], *, runtime_verified_desk_ids=()) -> dict:
    """Assemble stable report preserving all desk results, gaps, and conflicts."""
    _require(isinstance(candidate_identity, dict), "candidate_identity must be an object")
    _require(all(isinstance(candidate_identity.get(k), str) and candidate_identity[k].strip() for k in ("candidate_id", "name")), "candidate identity requires candidate_id and name")
    by_desk = {}
    for raw in desk_results:
        result = validate_desk_result(raw)
        _require(result["candidate_identity"] == candidate_identity, "desk candidate identity mismatch")
        _require(result["desk_id"] not in by_desk, "duplicate desk result")
        by_desk[result["desk_id"]] = result
    for desk_id in DESK_IDS:
        by_desk.setdefault(desk_id, incomplete_result(candidate_identity, desk_id))
    all_sources = {ref["source_id"] for result in by_desk.values() for finding in result["findings"] for ref in finding["evidence_refs"]}
    _require(len(all_sources) <= MAX_SOURCES_PER_REPORT, f"report source budget exceeded ({MAX_SOURCES_PER_REPORT})")
    results = [by_desk[desk_id] for desk_id in DESK_IDS]
    claims = {}
    for result in results:
        for finding in result["findings"]:
            key = finding["claim"].strip().casefold()
            claims.setdefault(key, []).append({"desk_id": result["desk_id"], "assessment": result["assessment"], "finding": finding})
    conflicts = [
        {"claim": rows[0]["finding"]["claim"], "positions": rows}
        for rows in claims.values()
        if len({row["assessment"] for row in rows}) > 1
    ]
    modes = {result["delegation_mode"] for result in results if result["status"] == "complete"}
    # Desk supplied booleans are model output and cannot prove a child was spawned.
    # Only the coordinator's observed runtime event IDs can establish that fact.
    runtime_verified_desk_ids = set(runtime_verified_desk_ids)
    verified_native = (
        all(result["status"] == "complete" and result["delegation_mode"] == "native" for result in results)
        and set(DESK_IDS).issubset(runtime_verified_desk_ids)
    )
    report = {
        "schema_version": 1, "candidate_identity": candidate_identity,
        "delegation": {"mode": "native" if verified_native else "simulated", "verified": verified_native,
                       "label": "NATIVE_DELEGATION_VERIFIED" if verified_native else "DEGRADED_EXECUTION"},
        "complete": all(result["status"] == "complete" for result in results),
        "incomplete_desks": [result["desk_id"] for result in results if result["status"] == "incomplete"],
        "conflicts": conflicts,
        "desk_results": results,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and assemble nine-desk research JSON")
    parser.add_argument("candidate_identity", type=Path)
    parser.add_argument("desk_results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        identity = json.loads(args.candidate_identity.read_text(encoding="utf-8"))
        results = [json.loads(path.read_text(encoding="utf-8")) for path in args.desk_results]
        report = assemble_report(identity, results)
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (OSError, json.JSONDecodeError, DeskValidationError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
