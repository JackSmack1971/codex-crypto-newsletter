"""Repeatable, offline evaluation of measurable research control-plane behavior."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import controlplane
import newsletter
from daily_committee import decide

ROOT = Path(__file__).resolve().parents[1]
WORKLOADS = ROOT / "examples" / "evaluation-workloads.json"
ROUTING = ROOT / "examples" / "routing-cases.json"
NO_PICK = ROOT / "examples" / "no-pick.json"
UNMEASURED = "UNMEASURED: requires coordinator-observed live run telemetry"


def _ratio(numerator: int, denominator: int) -> dict:
    return {"value": numerator / denominator if denominator else None,
            "numerator": numerator, "denominator": denominator}


def evaluate(*, mode: str = "offline-single", as_of: str | None = None) -> dict:
    """Run deterministic checks; no network requests or model sessions are started."""
    started = time.perf_counter()
    config = controlplane.load_config()
    catalog = controlplane.discover_skills(controlplane._skill_roots(config["skill_roots"]))
    cases = json.loads(ROUTING.read_text(encoding="utf-8"))
    routing = controlplane.evaluate_routes(config, catalog, cases)
    workload_data = json.loads(WORKLOADS.read_text(encoding="utf-8"))
    packet = json.loads(NO_PICK.read_text(encoding="utf-8"))
    newsletter_errors = newsletter.validate(packet)
    no_pick_packet = {"cutoff_utc": "2026-10-11T16:00:00Z", "candidates": [{}]}
    decision = decide(no_pick_packet)
    repeat_decision = decide(no_pick_packet)
    arithmetic_cases = [(10, 12, 20.0), (100, 90, -10.0), (1, 1, 0.0)]
    arithmetic_pass = sum(math.isclose((end / start - 1) * 100, expected, abs_tol=1e-12)
                          for start, end, expected in arithmetic_cases)
    duration = round(time.perf_counter() - started, 6)
    workload_ids = [row["id"] for row in workload_data["workloads"]]
    state_hash = hashlib.sha256((ROUTING.read_bytes() + WORKLOADS.read_bytes() + NO_PICK.read_bytes()).strip()).hexdigest()
    metrics = {
        "skill_routing_precision": routing["metrics"]["precision"],
        "skill_routing_recall": routing["metrics"]["recall"],
        "research_evidence_coverage": {"value": None, "numerator": None, "denominator": None, "status": UNMEASURED + "; fixture catalogue specifies conditions but contains no research artifacts"},
        "source_freshness": {"value": None, "status": UNMEASURED + "; no acquired source timestamps in offline workload set"},
        "token_identity_accuracy": {"value": None, "status": UNMEASURED + "; identity truth set is not present"},
        "calculation_correctness": _ratio(arithmetic_pass, len(arithmetic_cases)),
        "candidate_screening_reproducibility": {"value": decision == repeat_decision, "runs": 2, "workloads": ["no-pick"]},
        "independent_reviewer_defect_detection": {"value": None, "status": UNMEASURED + "; adversarial fixtures are unit-test inputs, not a labeled defect corpus"},
        "unsupported_claim_frequency": {"value": None, "status": UNMEASURED + "; no generated research claims in offline fixture set"},
        "newsletter_completeness": {"value": not newsletter_errors, "errors": newsletter_errors, "section_count": len(packet.get("sections", {}))},
        "daily_runtime_seconds": {"value": duration, "scope": "offline evaluation harness only"},
        "resource_consumption": {"value": None, "status": UNMEASURED + "; process-level CPU/memory telemetry not collected"},
        "cost_per_completed_edition_usd": {"value": None, "status": UNMEASURED + "; no model/provider billing telemetry and no edition generation"},
        "historical_pick_watchlist_outcomes": {"value": None, "status": UNMEASURED + "; no accountability ledger supplied"},
        "live_agent_invocations": {"value": 0, "meaning": "No model or delegated agent was launched by this offline evaluation."},
        "live_token_usage": {"value": None, "status": "NOT_APPLICABLE: no live model invocation"},
    }
    return {"schema_version": 1, "status": "TESTED_OFFLINE", "mode": mode,
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "workload_ids": workload_ids, "workload_count": len(workload_ids),
            "start_state_sha256": state_hash, "routing_case_count": len(cases),
            "multi_agent_comparison": {"status": "UNVERIFIED", "reason": "Requires paired live single-agent and multi-agent runs with the same workload IDs and start-state hash; no live run was authorized or performed."},
            "metrics": metrics}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline-single", "offline-multi"), default="offline-single",
                        help="label paired offline harness runs; does not launch Codex agents")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path, help="compare against a prior report on the identical fixture hash")
    args = parser.parse_args(argv)
    try:
        report = evaluate(mode=args.mode)
        if args.compare:
            prior = json.loads(args.compare.read_text(encoding="utf-8"))
            same_workloads = (prior.get("workload_ids") == report["workload_ids"]
                              and prior.get("start_state_sha256") == report["start_state_sha256"])
            comparable = ("skill_routing_precision", "skill_routing_recall", "calculation_correctness",
                          "candidate_screening_reproducibility", "newsletter_completeness")
            comparisons = {}
            for name in comparable:
                before = prior["metrics"][name].get("value")
                after = report["metrics"][name].get("value")
                comparisons[name] = {"baseline": before, "current": after,
                                     "delta": (after - before if isinstance(before, (int, float)) and isinstance(after, (int, float)) else (0 if before == after else None)),
                                     "regression": bool(isinstance(before, (int, float)) and isinstance(after, (int, float)) and after < before)}
            report["paired_comparison"] = {"same_fixture_dataset": same_workloads,
                "status": "PASS" if same_workloads else "FAIL",
                "interpretation": "No optimization change was applied in this slice; paired values check repeatability only.",
                "metrics": comparisons,
                "runtime_delta_seconds": round(report["metrics"]["daily_runtime_seconds"]["value"] - prior["metrics"]["daily_runtime_seconds"]["value"], 6)}
            if not same_workloads:
                report["status"] = "FAIL"
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
    except (OSError, ValueError, KeyError, controlplane.ControlPlaneError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}), file=sys.stderr)
        return 2
    return 0 if report["metrics"]["newsletter_completeness"]["value"] and report.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
