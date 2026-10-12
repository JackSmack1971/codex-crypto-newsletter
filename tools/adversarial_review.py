"""Validate independent challenge reports bound to frozen candidate evidence."""
from __future__ import annotations

import hashlib
import json
from typing import Any


DIMENSIONS = (
    "token_identity", "market_data_freshness", "wash_trading", "market_cap",
    "holder_concentration", "dilution_unlocks", "security", "adverse_liquidity",
    "catalyst_pricing", "tokenholder_value_capture", "price_alternatives",
    "thesis_invalidation",
)
STATUSES = {"supported", "contradicted", "unresolved", "not_applicable"}


class ReviewError(ValueError):
    """Invalid or insufficient independent challenge artifact."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def freeze_inputs(candidate_identity: dict, thesis: str, observations: list, calculations: list) -> dict:
    """Create the exact evidence-only package the independent reviewer receives."""
    if not isinstance(candidate_identity, dict) or not candidate_identity:
        raise ReviewError("candidate_identity must be a non-empty object")
    if not isinstance(thesis, str) or not thesis.strip():
        raise ReviewError("candidate thesis is required")
    if not isinstance(observations, list) or not isinstance(calculations, list):
        raise ReviewError("observations and calculations must be arrays")
    payload = {"schema_version": 1, "candidate_identity": candidate_identity,
               "thesis": thesis.strip(), "observations": observations,
               "calculations": calculations}
    return {**payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}


def validate_report(frozen: object, report: object, *, runtime_event_ids=()) -> dict:
    """Validate report semantics; only coordinator-observed IDs prove execution."""
    if not isinstance(frozen, dict) or frozen.get("schema_version") != 1:
        raise ReviewError("frozen review inputs are missing or invalid")
    payload = {k: frozen[k] for k in ("schema_version", "candidate_identity", "thesis", "observations", "calculations") if k in frozen}
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    if frozen.get("sha256") != digest:
        raise ReviewError("frozen review input digest mismatch")
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ReviewError("challenge report must use schema_version 1")
    if report.get("input_sha256") != digest:
        raise ReviewError("challenge report is not bound to these frozen inputs")
    provenance = report.get("execution")
    if not isinstance(provenance, dict) or provenance.get("agent") != "independent-reviewer" or not isinstance(provenance.get("event_id"), str) or not provenance["event_id"].strip():
        raise ReviewError("reviewer execution provenance is required")
    if provenance["event_id"] not in set(runtime_event_ids):
        raise ReviewError("reviewer event is not present in coordinator-observed runtime events")
    if report.get("candidate_identity") != frozen.get("candidate_identity"):
        raise ReviewError("review candidate identity mismatch")
    checks = report.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(DIMENSIONS):
        raise ReviewError("all twelve adversarial dimensions must be assessed exactly once")
    evidence_ids = {row.get("id") for row in frozen["observations"] + frozen["calculations"] if isinstance(row, dict) and isinstance(row.get("id"), str)}
    supported, contradicted, unresolved = [], [], []
    material_open = False
    for dimension in DIMENSIONS:
        row = checks[dimension]
        if not isinstance(row, dict) or row.get("status") not in STATUSES:
            raise ReviewError(f"{dimension} needs a valid status")
        if not isinstance(row.get("finding"), str) or not row["finding"].strip():
            raise ReviewError(f"{dimension} needs a non-empty finding")
        refs = row.get("evidence_refs")
        if not isinstance(refs, list) or any(ref not in evidence_ids for ref in refs):
            raise ReviewError(f"{dimension} evidence_refs must reference frozen observation/calculation IDs")
        if row["status"] in {"supported", "contradicted"} and not refs:
            raise ReviewError(f"{dimension} {row['status']} finding requires frozen evidence")
        if row["status"] == "not_applicable" and not (isinstance(row.get("rationale"), str) and row["rationale"].strip()):
            raise ReviewError(f"{dimension} not_applicable status requires rationale")
        entry = {"dimension": dimension, "finding": row.get("finding", ""), "evidence_refs": refs}
        if row["status"] == "supported":
            supported.append(entry)
        elif row["status"] == "contradicted":
            resolution = row.get("resolution")
            if isinstance(resolution, dict) and resolution.get("status") == "resolved" and resolution.get("evidence_refs") and all(ref in evidence_ids for ref in resolution["evidence_refs"]):
                continue
            contradicted.append(entry)
            material_open = True
        elif row["status"] == "unresolved":
            unresolved.append(entry)
            material_open |= row.get("material") is True
    additional = report.get("additional_evidence_needed")
    if not isinstance(additional, list):
        raise ReviewError("additional_evidence_needed must be an array")
    expected = "FAIL" if contradicted else "INCONCLUSIVE" if unresolved or material_open else "PASS"
    if report.get("verdict") != expected:
        raise ReviewError(f"verdict must be derived from findings ({expected})")
    result = {**report, "supported_claims": supported, "contradicted_claims": contradicted,
              "unresolved_material_issues": [item for item in unresolved if checks[item["dimension"]].get("material") is True],
              "additional_evidence_needed": additional, "verdict": expected}
    return result
