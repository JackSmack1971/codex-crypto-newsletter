import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from weekly_watchlist import Watchlist


START = date(2026, 10, 1)


def stamp(day):
    return f"{day.isoformat()}T12:00:00Z"


def candidate():
    return {"identity": {"chain": "DemoChain", "asset_id": "0xAbC", "symbol": "ABC"},
            "thesis": "Original thesis remains immutable.", "catalyst": {"description": "Protocol launch", "window": "2026-10-08"},
            "market_cap_tier": "micro-cap", "liquidity_classification": "thin DEX",
            "entry_trigger": "Daily close above 1.25", "invalidation_trigger": "Launch cancelled",
            "confidence": 0.72, "risk_assessment": {"level": "high", "items": ["thin liquidity"]},
            "next_review_date": START.isoformat(),
            "discovery_evidence": [{"source_id": "screen-1", "observed_at": stamp(START), "locator": "rank 1"}]}


class WeeklyWatchlistTests(unittest.TestCase):
    def test_seven_day_replay_persists_history_and_never_readds_expired_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "watchlist.sqlite"
            item = candidate()
            states = [None, "RESEARCHING", "WATCHING", "TRIGGERED", "PROMOTED", None, None, None]
            for offset, advance in enumerate(states):
                day = START + timedelta(days=offset)
                store = Watchlist(db)  # restart between every daily run
                refreshes = []
                if offset:
                    refreshes.append({"identity": item["identity"], "observations": [
                        {"source_id": f"daily-{offset}", "observed_at": stamp(day), "value": offset}],
                        "advance_to": advance,
                        "triggered": offset == 3, "eligible_for_committee": offset == 4,
                        "transition_evidence": [{"source_id": f"daily-{offset}", "observed_at": stamp(day), "value": offset}],
                        "next_review_date": day.isoformat()})
                packet = {"as_of": stamp(day), "refreshes": refreshes,
                          "screened_candidates": [item] if offset in (0, 7) else []}
                result = store.daily_run(packet)
                if offset == 0:
                    self.assertEqual("DISCOVERED", result["ranked_watchlist"][0]["state"])
                if offset == 4:
                    self.assertEqual("PROMOTED", result["ranked_watchlist"][0]["state"])
                    self.assertEqual("Original thesis remains immutable.", result["ranked_watchlist"][0]["thesis"])
                if offset == 7:
                    self.assertEqual([], result["ranked_watchlist"])
                store.close()
            store = Watchlist(db)
            history = store.history(item["identity"])
            self.assertEqual(["DISCOVERED", "RESEARCHING", "WATCHING", "TRIGGERED", "PROMOTED", "EXPIRED"],
                             [x["to_state"] for x in history])
            self.assertTrue(all(x["transitioned_at"] and x["evidence"] for x in history))
            self.assertEqual("seven-day window elapsed", history[-1]["reason"])
            self.assertEqual([], store.ranked((START + timedelta(days=7)).isoformat())["ranked_watchlist"])
            store.close()

    def test_transition_requires_evidence_and_invalid_edges_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Watchlist(Path(temp) / "db.sqlite")
            item = candidate()
            store.add(item, stamp(START))
            with self.assertRaisesRegex(ValueError, "evidence"):
                store.daily_run({"as_of": stamp(START + timedelta(days=1)), "refreshes": [{
                    "identity": item["identity"], "advance_to": "RESEARCHING"}], "screened_candidates": []})
            evidence = [{"source_id": "s", "observed_at": stamp(START + timedelta(days=1))}]
            store.daily_run({"as_of": stamp(START + timedelta(days=1)), "refreshes": [{
                "identity": item["identity"], "advance_to": "RESEARCHING", "transition_evidence": evidence}], "screened_candidates": []})
            with self.assertRaisesRegex(ValueError, "invalid state transition"):
                store.daily_run({"as_of": stamp(START + timedelta(days=1)), "refreshes": [{
                    "identity": item["identity"], "advance_to": "PROMOTED", "transition_evidence": [
                        {"source_id": "s", "observed_at": stamp(START + timedelta(days=1))}]}], "screened_candidates": []})
            store.close()

    def test_material_thesis_change_is_appended_without_rewriting_original(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Watchlist(Path(temp) / "db.sqlite")
            item = candidate()
            store.add(item, stamp(START))
            day = START + timedelta(days=1)
            row = store.daily_run({"as_of": stamp(day), "refreshes": [{"identity": item["identity"],
                "material_thesis_change": "Catalyst delayed", "change_evidence": [{"source_id": "s", "observed_at": stamp(day)}],
                "observations": [{"source_id": "s", "observed_at": stamp(day), "value": "delay"}]}], "screened_candidates": []})["ranked_watchlist"][0]
            self.assertEqual(item["thesis"], row["thesis"])
            self.assertEqual("Catalyst delayed", row["material_changes"][0]["change"])
            self.assertEqual(1, len(row["observations"]))
            store.close()


if __name__ == "__main__":
    unittest.main()
