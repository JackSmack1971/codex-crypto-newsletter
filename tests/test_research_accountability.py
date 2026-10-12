import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from research_accountability import append_observation, append_update, calculate, publish, read_ledger


def publication(record_id, expires="2026-02-01T00:00:00Z"):
    return {"record_id": record_id, "kind": "daily_pick", "published_at": "2026-01-01T00:00:00Z",
        "identity": {"chain": "Demo", "asset_id": record_id, "symbol": record_id.upper()},
        "thesis": "Original thesis", "direction": "LONG", "reference_price": 10,
        "venue": "Fixture venue", "confirmation": {"type": "price_at_or_above", "value": 11},
        "invalidation": {"type": "price_at_or_below", "value": 8}, "expires_at": expires,
        "catalyst": "Launch"}


class ResearchAccountabilityTests(unittest.TestCase):
    def test_success_invalidated_and_unresolved_records_and_reproducible_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "accountability.jsonl"
            publish(ledger, publication("success"))
            append_observation(ledger, "success", {"observed_at": "2026-01-08T00:00:00Z", "price": 12,
                "high": 13, "low": 9, "venue": "Fixture venue"})
            publish(ledger, publication("failed"))
            append_observation(ledger, "failed", {"observed_at": "2026-01-05T00:00:00Z", "price": 7, "venue": "Fixture venue"})
            publish(ledger, publication("open"))
            as_of = "2026-01-10T00:00:00Z"
            report = calculate(read_ledger(ledger), as_of)
            rows = {r["record_id"]: r for r in report["records"]}
            self.assertEqual("VALIDATED", rows["success"]["outcome"])
            self.assertEqual("INVALIDATED", rows["failed"]["outcome"])
            self.assertEqual("UNRESOLVED", rows["open"]["outcome"])
            self.assertEqual(20.0, rows["success"]["performance"]["7d"]["return_pct"])
            self.assertEqual("INSUFFICIENT_DATA", rows["failed"]["performance"]["7d"]["status"])
            self.assertEqual("OBSERVED", rows["success"]["excursions"]["status"])
            self.assertEqual(1, report["statistics"]["7d"]["observed_count"])
            self.assertEqual(3, report["statistics"]["7d"]["cohort_count"])
            self.assertEqual(report, calculate(read_ledger(ledger), as_of))

    def test_invalidation_and_expiration_are_independent(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "ledger.jsonl"
            publish(ledger, publication("status"))
            append_update(ledger, "status", thesis_status="INVALIDATED", at="2026-01-02T00:00:00Z")
            publish(ledger, publication("expires", expires="2026-01-03T00:00:00Z"))
            rows = {r["record_id"]: r["outcome"] for r in calculate(read_ledger(ledger), "2026-01-04T00:00:00Z")["records"]}
            self.assertEqual("INVALIDATED", rows["status"])
            self.assertEqual("EXPIRED", rows["expires"])

    def test_original_publication_cannot_be_replaced_and_edits_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "ledger.jsonl"
            publish(ledger, publication("fixed"))
            changed = publication("fixed")
            changed["thesis"] = "rewritten"
            with self.assertRaisesRegex(ValueError, "immutable"):
                publish(ledger, changed)
            raw = ledger.read_text(encoding="utf-8").replace("Original thesis", "Rewritten thesis")
            ledger.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity failure"):
                read_ledger(ledger)


if __name__ == "__main__":
    unittest.main()
