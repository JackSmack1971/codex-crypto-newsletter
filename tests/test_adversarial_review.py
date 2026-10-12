import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import adversarial_review as ar
import newsletter


class AdversarialReviewTests(unittest.TestCase):
    def setUp(self):
        self.frozen = ar.freeze_inputs(
            {"candidate_id": "chain:0xabc", "name": "Example"},
            "Adoption will drive token demand over the next year.",
            [{"id": "obs-1", "field": "volume", "value": 1000}],
            [{"id": "calc-1", "name": "fdv", "value": 500000, "formula": "price * supply"}],
        )
        self.report = {
            "schema_version": 1, "input_sha256": self.frozen["sha256"],
            "candidate_identity": self.frozen["candidate_identity"],
            "execution": {"agent": "independent-reviewer", "event_id": "event-7"},
            "checks": {key: {"status": "supported", "finding": "Reviewed", "evidence_refs": ["obs-1"]} for key in ar.DIMENSIONS},
            "additional_evidence_needed": [], "verdict": "PASS",
        }

    def test_complete_frozen_review_passes_only_with_observed_runtime_event(self):
        with self.assertRaisesRegex(ar.ReviewError, "not present"):
            ar.validate_report(self.frozen, self.report)
        checked = ar.validate_report(self.frozen, self.report, runtime_event_ids={"event-7"})
        self.assertEqual("PASS", checked["verdict"])
        self.assertEqual(12, len(checked["supported_claims"]))
        packet = json.loads((ROOT / "examples" / "no-pick.json").read_text(encoding="utf-8"))
        packet["pick"] = {"status": "PICK", "asset": "Example", "ticker": "EX",
                          "gates": {gate: "PASS" for gate in newsletter.GATES},
                          "review": {"frozen_inputs": self.frozen, "challenge_report": self.report}}
        self.assertEqual([], newsletter.validate(packet, reviewer_runtime_event_ids={"event-7"}))
        self.assertTrue(any("reviewer event" in error for error in newsletter.validate(packet)))

    def test_reviewer_flag_alone_cannot_approve_pick(self):
        packet = json.loads((ROOT / "examples" / "no-pick.json").read_text(encoding="utf-8"))
        packet["pick"] = {"status": "PICK", "asset": "Example", "ticker": "EX",
                          "gates": {gate: "PASS" for gate in newsletter.GATES},
                          "review": {"verdict": "PASS", "independent": True}}
        errors = newsletter.validate(packet)
        self.assertTrue(any("frozen review inputs" in error for error in errors))

    def test_critical_unknown_and_unresolved_contradiction_block(self):
        unresolved = copy.deepcopy(self.report)
        unresolved["checks"]["holder_concentration"] = {
            "status": "unresolved", "material": True, "finding": "Top holders unknown", "evidence_refs": []}
        unresolved["verdict"] = "INCONCLUSIVE"
        result = ar.validate_report(self.frozen, unresolved, runtime_event_ids={"event-7"})
        self.assertEqual("INCONCLUSIVE", result["verdict"])
        self.assertEqual("holder_concentration", result["unresolved_material_issues"][0]["dimension"])

        contradiction = copy.deepcopy(self.report)
        contradiction["checks"]["token_identity"] = {
            "status": "contradicted", "finding": "Address does not match candidate", "evidence_refs": ["obs-1"]}
        contradiction["verdict"] = "FAIL"
        result = ar.validate_report(self.frozen, contradiction, runtime_event_ids={"event-7"})
        self.assertEqual("FAIL", result["verdict"])
        self.assertEqual("token_identity", result["contradicted_claims"][0]["dimension"])

    def test_report_cannot_change_frozen_inputs_or_omit_a_dimension(self):
        changed = copy.deepcopy(self.frozen)
        changed["observations"][0]["value"] = 1
        with self.assertRaisesRegex(ar.ReviewError, "digest mismatch"):
            ar.validate_report(changed, self.report, runtime_event_ids={"event-7"})
        incomplete = copy.deepcopy(self.report)
        del incomplete["checks"]["wash_trading"]
        with self.assertRaisesRegex(ar.ReviewError, "all twelve"):
            ar.validate_report(self.frozen, incomplete, runtime_event_ids={"event-7"})

    def test_no_pick_remains_valid(self):
        packet = json.loads((ROOT / "examples" / "no-pick.json").read_text(encoding="utf-8"))
        self.assertEqual([], newsletter.validate(packet))

    def test_misleading_candidate_fixture_is_rejected_across_material_dimensions(self):
        candidate = json.loads((ROOT / "examples" / "adversarial-candidate.json").read_text(encoding="utf-8"))
        frozen = ar.freeze_inputs(candidate["candidate_identity"], candidate["thesis"], candidate["observations"], candidate["calculations"])
        bad_evidence = {
            "token_identity": ("contradicted", ["identity-record"]),
            "market_data_freshness": ("contradicted", ["market-snapshot"]),
            "wash_trading": ("unresolved", ["market-snapshot"]),
            "market_cap": ("contradicted", ["headline-market-cap"]),
            "holder_concentration": ("contradicted", ["holder-snapshot"]),
            "dilution_unlocks": ("contradicted", ["unlock-notice"]),
            "security": ("unresolved", []),
            "adverse_liquidity": ("contradicted", ["liquidity-depth"]),
            "catalyst_pricing": ("contradicted", ["catalyst-post"]),
            "tokenholder_value_capture": ("unresolved", []),
            "price_alternatives": ("unresolved", []),
            "thesis_invalidation": ("unresolved", []),
        }
        report = {
            "schema_version": 1, "input_sha256": frozen["sha256"],
            "candidate_identity": frozen["candidate_identity"],
            "execution": {"agent": "independent-reviewer", "event_id": "event-bad-candidate"},
            "checks": {dimension: {"status": status, "finding": "Adversarial fixture finding", "evidence_refs": refs,
                                     "material": status == "unresolved"}
                       for dimension, (status, refs) in bad_evidence.items()},
            "additional_evidence_needed": ["Verify canonical contract", "Reconstruct circulating supply"],
            "verdict": "FAIL",
        }
        result = ar.validate_report(frozen, report, runtime_event_ids={"event-bad-candidate"})
        self.assertEqual("FAIL", result["verdict"])
        self.assertGreaterEqual(len(result["contradicted_claims"]), 5)
        self.assertGreaterEqual(len(result["unresolved_material_issues"]), 2)


if __name__ == "__main__":
    unittest.main()
