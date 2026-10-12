import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import adversarial_review as ar
import daily_committee as committee
from newsletter import GATES
from research_desks import DESK_IDS


REF = {"source_id": "src", "locator": "record-1", "observed_at": "2026-10-11T11:00:00Z"}


def eligible_candidate(candidate_id="x", score=90):
    identity = {"candidate_id": candidate_id, "name": "Example", "symbol": "EX", "chain": "chain",
                "asset_id": f"chain:{candidate_id}", "verified": True, "market_cap_usd": 5_000_000,
                "market_cap_tier": "small-cap", "evidence_refs": [REF]}
    desk_rows = []
    for desk in DESK_IDS:
        desk_rows.append({"schema_version": 1, "candidate_identity": identity, "desk_id": desk,
                          "status": "complete", "delegation_mode": "simulated", "delegation_verified": False,
                          "assessment": "inconclusive", "confidence": 0.5, "findings": [{"claim": "Reviewed evidence.",
                          "evidence_refs": [{"source_id": f"{desk}-source", "locator": "section 1",
                                             "observed_at": "2026-10-11T11:00:00Z"}]}],
                          "calculations": [], "unresolved_questions": [], "reasons_to_reject": [], "reasons_to_escalate": []})
    frozen = ar.freeze_inputs(identity, "Evidence-backed thesis for the next two weeks.",
                              [{"id": "obs", "value": "evidence"}], [])
    challenge = {"schema_version": 1, "input_sha256": frozen["sha256"], "candidate_identity": identity,
                 "execution": {"agent": "independent-reviewer", "event_id": f"review-{candidate_id}"},
                 "checks": {dimension: {"status": "supported", "finding": "Checked", "evidence_refs": ["obs"]}
                            for dimension in ar.DIMENSIONS},
                 "additional_evidence_needed": [], "verdict": "PASS"}
    return {"candidate_identity": identity, "hypothesis": "LONG", "gates": {g: "PASS" for g in GATES},
            "market_data": {"observed_at": "2026-10-11T11:30:00Z", "evidence_refs": [REF]},
            "thesis": "Evidence-backed thesis for the next two weeks.", "thesis_evidence_refs": [REF],
            "horizon_days": 14, "catalyst": {"description": "Scheduled event", "expected_window": "2026-10-20",
                                                "evidence_refs": [REF]},
            "entry_conditions": ["Confirm listed condition"], "invalidation_conditions": ["Invalidate on stated event"],
            "downside_risks": ["Market risk"], "liquidity_risks": ["Depth can deteriorate"],
            "scenarios": {"bull": "Adoption improves", "base": "Current trend persists", "bear": "Thesis fails"},
            "research_desk_report": {"desk_results": desk_rows},
            "score_record": {"asset_id": identity["asset_id"], "opportunity_score": score,
                             "score_components": {}, "evidence": {}},
            "review": {"frozen_inputs": frozen, "challenge_report": challenge}}


class DailyCommitteeTests(unittest.TestCase):
    def setUp(self):
        self.packet = {"cutoff_utc": "2026-10-11T12:00:00Z", "candidates": [eligible_candidate()]}

    def test_complete_candidate_can_be_picked_and_record_preserves_thesis_conditions(self):
        result = committee.decide(self.packet, reviewer_runtime_event_ids={"review-x"})
        self.assertEqual("PICK", result["status"])
        row = result["decision_records"][0]
        self.assertEqual(8, len(row["gates"]))
        self.assertEqual(14, row["horizon_days"])
        self.assertTrue(row["entry_conditions"] and row["invalidation_conditions"])
        self.assertEqual("EDITORIAL_REPORTING_ONLY; NO TRADE EXECUTION", result["authorization"])

    def test_any_missing_gate_blocks_pick_even_when_score_is_highest(self):
        candidate = eligible_candidate()
        candidate["gates"]["security"] = "UNKNOWN"
        result = committee.decide({**self.packet, "candidates": [candidate]}, reviewer_runtime_event_ids={"review-x"})
        self.assertEqual("NO_PICK", result["status"])
        self.assertIn("security: UNKNOWN", result["decision_records"][0]["reasons"])

    def test_higher_score_never_overrides_gates_and_lower_eligible_candidate_can_win(self):
        unsafe = eligible_candidate("unsafe", 99)
        unsafe["gates"]["security"] = "FAIL"
        safe = eligible_candidate("safe", 10)
        result = committee.decide({**self.packet, "candidates": [unsafe, safe]},
                                  reviewer_runtime_event_ids={"review-unsafe", "review-safe"})
        self.assertEqual("PICK", result["status"])
        self.assertEqual("safe", result["selected_candidate_id"])
        self.assertEqual("INELIGIBLE", result["decision_records"][0]["status"])

    def test_reviewer_event_must_be_observed_and_determinism_holds(self):
        a = committee.decide(self.packet, reviewer_runtime_event_ids={"review-x"})
        b = committee.decide(copy.deepcopy(self.packet), reviewer_runtime_event_ids={"review-x"})
        self.assertEqual(a, b)
        self.assertEqual("NO_PICK", committee.decide(self.packet)["status"])

    def test_stale_data_missing_thesis_conditions_or_long_horizon_block(self):
        candidate = eligible_candidate()
        candidate["market_data"]["observed_at"] = "2026-10-01T00:00:00Z"
        candidate["horizon_days"] = 28
        candidate["horizon_justification"] = ""
        candidate["entry_conditions"] = []
        result = committee.decide({**self.packet, "candidates": [candidate]}, reviewer_runtime_event_ids={"review-x"})
        self.assertEqual("NO_PICK", result["status"])
        reasons = result["decision_records"][0]["reasons"]
        self.assertTrue(any("market data" in r for r in reasons))
        self.assertTrue(any("horizon" in r for r in reasons))
        self.assertTrue(any("entry_conditions" in r for r in reasons))

    def test_score_tie_breaking_and_every_candidate_has_record(self):
        self.packet["candidates"] = [eligible_candidate("z", 50), eligible_candidate("a", 50)]
        result = committee.decide(self.packet, reviewer_runtime_event_ids={"review-z", "review-a"})
        self.assertEqual("a", result["selected_candidate_id"])
        self.assertEqual({"a", "z"}, {row["candidate_id"] for row in result["decision_records"]})

    def test_long_horizon_requires_explicit_justification_and_short_needs_instrument_evidence(self):
        candidate = eligible_candidate()
        candidate["horizon_days"] = 28
        result = committee.decide({**self.packet, "candidates": [candidate]}, reviewer_runtime_event_ids={"review-x"})
        self.assertEqual("NO_PICK", result["status"])
        candidate["horizon_justification"] = "Catalyst has a documented four-week resolution window."
        candidate["hypothesis"] = "SHORT"
        result = committee.decide({**self.packet, "candidates": [candidate]}, reviewer_runtime_event_ids={"review-x"})
        self.assertEqual("NO_PICK", result["status"])
        self.assertTrue(any("available instrument" in reason for reason in result["decision_records"][0]["reasons"]))


if __name__ == "__main__":
    unittest.main()
