"""Deterministic, evidence-gated daily crypto pick committee (editorial only)."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adversarial_review import ReviewError, validate_report
from newsletter import GATES
from research_desks import DeskValidationError, assemble_report

HYPOTHESES = {"LONG", "SHORT", "MARKET-NEUTRAL", "WATCH", "CASH"}
PICK_HYPOTHESES = {"LONG", "SHORT", "MARKET-NEUTRAL"}
SCENARIOS = {"bull", "base", "bear"}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _refs(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(ref, dict) and all(_nonempty(ref.get(k)) for k in ("source_id", "locator", "observed_at"))
        for ref in value
    )


def _age_hours(value: Any, cutoff: datetime) -> float | None:
    if not _nonempty(value):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return (cutoff - stamp.astimezone(timezone.utc)).total_seconds() / 3600
    except (ValueError, TypeError):
        return None


def _candidate_record(candidate: Any, cutoff: datetime, max_age_hours: float,
                      reviewer_runtime_event_ids: set[str]) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {"candidate_id": None, "status": "INELIGIBLE", "reasons": ["candidate must be an object"]}
    identity = candidate.get("candidate_identity")
    cid = identity.get("candidate_id") if isinstance(identity, dict) else None
    reasons: list[str] = []
    gates = candidate.get("gates")
    gate_record = {}
    if not isinstance(gates, dict):
        gates = {}
    for gate in GATES:
        value = gates.get(gate)
        if isinstance(value, dict):
            state = value.get("status")
            if state == "PASS" and not _refs(value.get("evidence_refs")):
                state = "UNKNOWN"
                reasons.append(f"{gate}: PASS lacks supporting source references")
        else:
            state = value
        if state not in {"PASS", "FAIL", "UNKNOWN"}:
            state = "UNKNOWN"
        gate_record[gate] = state
        if state != "PASS":
            reasons.append(f"{gate}: {state}")

    if not isinstance(identity, dict) or not all(_nonempty(identity.get(k)) for k in ("candidate_id", "name", "symbol", "chain", "asset_id")) or identity.get("verified") is not True:
        reasons.append("verified asset identity with candidate_id, name, symbol, chain, and asset_id is required")
    cap = identity.get("market_cap_usd") if isinstance(identity, dict) else None
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap <= 0 or not _nonempty(identity.get("market_cap_tier")) or not _refs(identity.get("evidence_refs", [])):
        reasons.append("verified market-cap tier, positive market cap, and source references are required")

    market = candidate.get("market_data")
    market_age = _age_hours(market.get("observed_at"), cutoff) if isinstance(market, dict) else None
    if not isinstance(market, dict) or market_age is None or market_age < 0 or market_age > max_age_hours or not _refs(market.get("evidence_refs")):
        reasons.append(f"current market data must have dated evidence no older than {max_age_hours:g} hours")

    thesis = candidate.get("thesis")
    horizon = candidate.get("horizon_days")
    if not _nonempty(thesis) or not _refs(candidate.get("thesis_evidence_refs")):
        reasons.append("evidence-backed opportunity thesis is required")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 7 or horizon > 28 or (horizon > 21 and not _nonempty(candidate.get("horizon_justification"))):
        reasons.append("thesis horizon must be 7–21 days, or up to 28 with explicit justification")
    catalyst = candidate.get("catalyst")
    if not isinstance(catalyst, dict) or not _nonempty(catalyst.get("description")) or not _nonempty(catalyst.get("expected_window")) or not _refs(catalyst.get("evidence_refs")):
        reasons.append("catalyst, expected date/window, and supporting source references are required")
    for field in ("entry_conditions", "invalidation_conditions", "downside_risks", "liquidity_risks"):
        if not isinstance(candidate.get(field), list) or not candidate[field] or any(not _nonempty(item) for item in candidate[field]):
            reasons.append(f"{field} must contain explicit conditions")
    scenarios = candidate.get("scenarios")
    if not isinstance(scenarios, dict) or not SCENARIOS.issubset(scenarios) or any(not _nonempty(scenarios.get(k)) for k in SCENARIOS):
        reasons.append("bull, base, and bear scenarios are required")

    hypothesis = candidate.get("hypothesis")
    if hypothesis not in HYPOTHESES:
        reasons.append("hypothesis must be LONG, SHORT, MARKET-NEUTRAL, WATCH, or CASH")
    elif hypothesis in {"SHORT", "MARKET-NEUTRAL"} and not _refs(candidate.get("instrument_evidence_refs")):
        reasons.append(f"{hypothesis} requires evidence for an available instrument")

    desks = candidate.get("research_desk_report")
    desk_complete = False
    try:
        if not isinstance(desks, dict) or not isinstance(desks.get("desk_results"), list):
            raise DeskValidationError("research desk report is required")
        checked_desks = assemble_report(identity, desks["desk_results"])
        desk_complete = checked_desks["complete"] and checked_desks["candidate_identity"] == identity
        if not desk_complete:
            reasons.append("all research desk outputs must be complete and bound to this identity")
    except (DeskValidationError, ValueError) as exc:
        reasons.append(f"research desk report invalid: {exc}")

    score_record = candidate.get("score_record")
    score = score_record.get("opportunity_score") if isinstance(score_record, dict) else None
    if (not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score)
            or score < 0 or score > 100 or not isinstance(score_record.get("score_components"), dict)
            or not isinstance(score_record.get("evidence"), dict)):
        score = None
        reasons.append("small-cap screen score record (0–100) with components and evidence is required")
    elif score_record.get("asset_id") != (identity.get("asset_id") if isinstance(identity, dict) else None):
        score = None
        reasons.append("score record asset_id does not match candidate identity")

    review_status = "MISSING"
    review = candidate.get("review")
    try:
        if not isinstance(review, dict):
            raise ReviewError("independent reviewer record is required")
        checked = validate_report(review.get("frozen_inputs"), review.get("challenge_report"),
                                  runtime_event_ids=reviewer_runtime_event_ids)
        if checked.get("candidate_identity") != identity or checked.get("verdict") != "PASS":
            raise ReviewError("independent review must PASS for this exact candidate")
        review_status = "PASS"
    except (ReviewError, KeyError, TypeError) as exc:
        review_status = "INELIGIBLE"
        reasons.append(f"independent reviewer: {exc}")

    eligible = not reasons and all(value == "PASS" for value in gate_record.values()) and hypothesis in PICK_HYPOTHESES
    if not eligible and hypothesis in {"WATCH", "CASH"} and not reasons:
        reasons.append(f"{hypothesis} hypothesis is recorded for editorial context, not selected as a PICK")
    return {
        "candidate_id": cid, "asset_id": identity.get("asset_id") if isinstance(identity, dict) else None,
        "hypothesis": hypothesis, "score": score, "gates": gate_record,
        "research_desks_complete": desk_complete, "reviewer_verdict": review_status,
        "research_desk_report": desks,
        "status": "ELIGIBLE" if eligible else "INELIGIBLE", "reasons": sorted(set(reasons)),
        "thesis": thesis, "horizon_days": horizon,
        "horizon_justification": candidate.get("horizon_justification"),
        "market_data": market,
        "catalyst": catalyst,
        "entry_conditions": candidate.get("entry_conditions"),
        "invalidation_conditions": candidate.get("invalidation_conditions"),
        "downside_risks": candidate.get("downside_risks"),
        "liquidity_risks": candidate.get("liquidity_risks"),
        "scenarios": scenarios,
        "evidence": {"identity": identity.get("evidence_refs", []) if isinstance(identity, dict) else [],
                     "market_data": market.get("evidence_refs", []) if isinstance(market, dict) else [],
                     "thesis": candidate.get("thesis_evidence_refs", []),
                     "catalyst": catalyst.get("evidence_refs", []) if isinstance(catalyst, dict) else [],
                     "review_input_sha256": review.get("frozen_inputs", {}).get("sha256") if isinstance(review, dict) and isinstance(review.get("frozen_inputs"), dict) else None},
    }


def decide(packet: Any, *, reviewer_runtime_event_ids=()) -> dict[str, Any]:
    """Return a stable decision and a record for every candidate in the funnel."""
    if not isinstance(packet, dict):
        raise ValueError("committee input must be an object")
    try:
        cutoff = datetime.fromisoformat(packet.get("cutoff_utc", "").replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("cutoff_utc must be ISO 8601 with timezone") from exc
    max_age = packet.get("max_market_data_age_hours", 24)
    if isinstance(max_age, bool) or not isinstance(max_age, (int, float)) or max_age <= 0 or not math.isfinite(max_age):
        raise ValueError("max_market_data_age_hours must be a positive finite number")
    candidates = packet.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a non-empty array")
    records = [_candidate_record(c, cutoff, float(max_age), set(reviewer_runtime_event_ids)) for c in candidates]
    # Score orders eligible candidates only; candidate_id provides stable tie-breaking.
    records.sort(key=lambda r: (r["candidate_id"] or "", r["asset_id"] or ""))
    records.sort(key=lambda r: (r["score"] if r["score"] is not None else float("-inf")), reverse=True)
    eligible = [r for r in records if r["status"] == "ELIGIBLE"]
    winner = eligible[0] if eligible else None
    watches = [r for r in records if r["status"] != "ELIGIBLE"][:5]
    return {"schema_version": 1, "cutoff_utc": packet["cutoff_utc"],
            "status": "PICK" if winner else "NO_PICK",
            "selected_candidate_id": winner["candidate_id"] if winner else None,
            "decision_records": records, "strongest_watch_candidates": watches,
            "authorization": "EDITORIAL_REPORTING_ONLY; NO TRADE EXECUTION"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
        decision = decide(packet)
        rendered = json.dumps(decision, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
