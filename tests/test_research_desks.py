import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from research_desks import (  # noqa: E402
    DESK_IDS, DeskValidationError, assemble_report, incomplete_result, validate_desk_result,
)


IDENTITY = {"candidate_id": "example:0xabc", "name": "Example", "symbol": "EX"}


def result(desk_id, assessment="inconclusive", claim="The evidence is mixed.", mode="simulated"):
    return {
        "schema_version": 1, "candidate_identity": IDENTITY, "desk_id": desk_id,
        "status": "complete", "delegation_mode": mode, "delegation_verified": False,
        "findings": [{"claim": claim, "evidence_refs": [{
            "source_id": f"source-{desk_id}", "locator": "section 1",
            "observed_at": "2026-10-11T12:00:00Z",
        }]}],
        "calculations": [{"name": "ratio", "value": 2, "unit": "x",
                          "formula": "4 / 2", "observed_at": "2026-10-11T12:00:00Z"}],
        "confidence": 0.5, "unresolved_questions": [], "assessment": assessment,
        "reasons_to_reject": [], "reasons_to_escalate": [],
    }


class ResearchDeskTests(unittest.TestCase):
    def test_all_nine_outputs_validate_and_missing_desks_are_explicit(self):
        outputs = [result(desk_id) for desk_id in DESK_IDS[:3]]
        report = assemble_report(IDENTITY, outputs)
        self.assertEqual(DESK_IDS, tuple(row["desk_id"] for row in report["desk_results"]))
        self.assertEqual(list(DESK_IDS[3:]), report["incomplete_desks"])
        self.assertFalse(report["complete"])
        self.assertTrue(all(validate_desk_result(row) for row in report["desk_results"]))
        self.assertEqual("DEGRADED_EXECUTION", report["delegation"]["label"])

    def test_conflicting_assessments_are_retained_and_output_is_reproducible(self):
        rows = [result("market-data", "bullish", "Liquidity is improving."),
                result("risk", "bearish", "Liquidity is improving.")]
        first = assemble_report(IDENTITY, rows)
        second = assemble_report(IDENTITY, list(reversed(rows)))
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, ensure_ascii=False, indent=2), json.dumps(second, ensure_ascii=False, indent=2))
        self.assertEqual(1, len(first["conflicts"]))
        self.assertEqual({"market-data", "risk"}, {p["desk_id"] for p in first["conflicts"][0]["positions"]})

    def test_invalid_or_unverifiable_evidence_fails_closed(self):
        bad = result("market-data")
        bad["findings"][0]["evidence_refs"][0]["observed_at"] = "yesterday"
        with self.assertRaises(DeskValidationError):
            validate_desk_result(bad)
        bad = result("market-data")
        bad["delegation_mode"] = "simulated"
        bad["delegation_verified"] = True
        with self.assertRaises(DeskValidationError):
            validate_desk_result(bad)

    def test_source_caps_and_identity_mismatch_rejected(self):
        bad = result("market-data")
        bad["findings"] = [{"claim": "many sources", "evidence_refs": [
            {"source_id": f"s{i}", "locator": "x", "observed_at": "2026-10-11T12:00:00Z"}
            for i in range(6)
        ]}]
        with self.assertRaises(DeskValidationError):
            validate_desk_result(bad)
        with self.assertRaises(DeskValidationError):
            assemble_report({"candidate_id": "other", "name": "Other"}, [result("market-data")])

    def test_report_source_budget_is_enforced_across_all_desks(self):
        rows = []
        for desk_id in DESK_IDS:
            row = result(desk_id)
            row["findings"] = [{"claim": "source budget fixture", "evidence_refs": [
                {"source_id": f"{desk_id}-source-{i}", "locator": "section", "observed_at": "2026-10-11T12:00:00Z"}
                for i in range(3)
            ]}]
            rows.append(row)
        with self.assertRaises(DeskValidationError):
            assemble_report(IDENTITY, rows)

    def test_native_requires_verified_completion_from_all_nine_desks(self):
        native = [result(desk, "inconclusive", mode="native") for desk in DESK_IDS]
        for row in native:
            row["delegation_verified"] = True
        report = assemble_report(IDENTITY, native, runtime_verified_desk_ids=DESK_IDS)
        self.assertTrue(report["complete"])
        self.assertEqual({"mode": "native", "verified": True, "label": "NATIVE_DELEGATION_VERIFIED"}, report["delegation"])
        report = assemble_report(IDENTITY, native[:-1], runtime_verified_desk_ids=DESK_IDS)
        self.assertFalse(report["delegation"]["verified"])

    def test_cli_writes_reproducible_report_from_separate_handoffs(self):
        with tempfile.TemporaryDirectory(prefix="desk run ") as temp:
            base = Path(temp)
            identity_file = base / "candidate identity.json"
            identity_file.write_text(json.dumps(IDENTITY), encoding="utf-8")
            desk_file = base / "market desk.json"
            desk_file.write_text(json.dumps(result("market-data")), encoding="utf-8")
            output_file = base / "coordinated report.json"
            command = [sys.executable, str(ROOT / "tools" / "research_desks.py"), str(identity_file), str(desk_file), "--output", str(output_file)]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(0, first.returncode, first.stderr)
            first_bytes = output_file.read_bytes()
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(first_bytes, output_file.read_bytes())
            self.assertEqual(list(DESK_IDS[1:]), json.loads(output_file.read_text(encoding="utf-8"))["incomplete_desks"])

    def test_incomplete_result_is_schema_valid_and_inconclusive(self):
        self.assertEqual("incomplete", incomplete_result(IDENTITY, "falsification")["status"])


if __name__ == "__main__":
    unittest.main()
