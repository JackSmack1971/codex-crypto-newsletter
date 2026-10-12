import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import small_cap_screen as sc


def bars(asof="2026-10-11", drift=0.002, volume=1000, trades=100):
    end = date.fromisoformat(asof)
    rows = []
    for i in range(101):
        px = 10 * (1 + drift) ** i
        rows.append({"date": (end - timedelta(days=100-i)).isoformat(), "open": px*.99,
                     "high": px*1.02, "low": px*.98, "close": px,
                     "volume_usd": volume, "trades": trades})
    return rows


def source_fixture():
    assets = [
        {"asset_id": "a", "ticker": "A", "included": True, "circulating_market_cap_usd": 2_000_000,
         "fully_diluted_valuation_usd": 3_000_000, "liquidity_usd": 100_000,
         "liquidity_observations": [{"usd": 40_000, "venue": "X", "venue_type": "exchange"},
                                    {"usd": 80_000, "venue": "D", "venue_type": "dex"}], "flags": []},
        {"asset_id": "b", "ticker": "B", "included": True, "circulating_market_cap_usd": 5_000_000,
         "fully_diluted_valuation_usd": 5_000_000, "liquidity_usd": 2_000,
         "liquidity_observations": [{"usd": 2_000, "venue": "thin", "venue_type": "dex"}], "flags": []},
    ]
    return ({"snapshot_id": "fixture-1", "snapshot_date": "2026-10-11", "assets": assets},
            {"a": bars(drift=.004), "b": bars(drift=.001)},
            {"BTC": bars(drift=.0015)})


class SmallCapScreenTests(unittest.TestCase):
    def test_fixed_input_is_deterministic_and_scores_trace_to_evidence(self):
        universe, history, btc = source_fixture()
        one = sc.screen(universe, history, benchmark_history=btc)
        two = sc.screen(universe, copy.deepcopy(history), benchmark_history=btc)
        self.assertEqual(one, two)
        a = one["ranked_candidates"][0]
        self.assertEqual("a", a["asset_id"])
        self.assertEqual(100, a["data_confidence_score"])
        self.assertEqual("KNOWN", a["metrics"]["return_90d"]["status"])
        self.assertEqual("KNOWN", a["metrics"]["relative_strength_btc_30d"]["status"])
        self.assertEqual(101, len(a["evidence"]["daily_bars"]))
        self.assertEqual("1d", a["indicators"]["rsi_14d"]["timeframe"])
        self.assertTrue(a["score_components"]["momentum_30d"]["status"] == "KNOWN")

    def test_missing_history_stays_unknown_and_cannot_improve_score(self):
        universe, history, btc = source_fixture()
        no_history = sc.screen(universe, {"a": [], "b": []}, benchmark_history={}, generated_at="fixed")
        self.assertEqual([], no_history["ranked_candidates"])
        a = next(x for x in no_history["candidate_evidence"] if x["asset_id"] == "a")
        self.assertIsNone(a["metrics"]["return_30d"]["value"])
        self.assertEqual("UNKNOWN", a["metrics"]["relative_strength_btc_30d"]["status"])
        full = sc.screen(universe, history, benchmark_history=btc, generated_at="fixed")
        full_score = next(x for x in full["candidate_evidence"] if x["asset_id"] == "a")["opportunity_score"]
        self.assertLessEqual(a["opportunity_score"], full_score)

    def test_outlier_volume_and_thin_liquidity_are_flagged(self):
        universe, history, btc = source_fixture()
        history["b"][-1]["volume_usd"] = 100_000
        result = sc.screen(universe, history, benchmark_history=btc, generated_at="fixed")
        b = next(x for x in result["candidate_evidence"] if x["asset_id"] == "b")
        self.assertIn("volume_outlier", b["risk_flags"])
        self.assertIn("thin_or_unknown_liquidity", b["risk_flags"])
        self.assertEqual(2_000, b["metrics"]["dex_liquidity_usd"]["value"])

    def test_stale_snapshot_price_is_rejected(self):
        universe, history, btc = source_fixture()
        history["a"] = bars("2026-10-10")
        result = sc.screen(universe, history, benchmark_history=btc, generated_at="fixed")
        a = next(x for x in result["candidate_evidence"] if x["asset_id"] == "a")
        self.assertIn("stale_or_missing_asof_price", a["risk_flags"])
        self.assertIn("latest daily close does not match snapshot date", a["rejection_reasons"])
        self.assertIsNone(a["metrics"]["return_1d"]["value"])

    def test_rank_stability_and_weight_sensitivity(self):
        universe, history, btc = source_fixture()
        base = sc.screen(universe, history, benchmark_history=btc, generated_at="fixed")
        base_order = [x["asset_id"] for x in base["ranked_candidates"]]
        self.assertEqual(base_order, [x["asset_id"] for x in sc.screen(universe, history, benchmark_history=btc, generated_at="fixed")["ranked_candidates"]])
        cfg = {"weights": {"momentum_30d": .01, "relative_strength_btc_30d": .01,
            "relative_strength_universe_30d": .01, "relative_volume": .01, "liquidity": .95, "activity_change": .01}}
        changed_liquidity = copy.deepcopy(universe)
        changed_liquidity["assets"][0]["liquidity_observations"] = [{"usd": 1_000, "venue": "thin", "venue_type": "dex"}]
        changed_liquidity["assets"][1]["liquidity_observations"] = [{"usd": 500_000, "venue": "deep", "venue_type": "dex"}]
        sensitive = sc.screen(changed_liquidity, history, benchmark_history=btc, config=cfg, generated_at="fixed")
        self.assertNotEqual(base_order, [x["asset_id"] for x in sensitive["ranked_candidates"]])

    def test_cli_writes_replayable_json_report(self):
        universe, history, btc = source_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "screen input.json", Path(tmp) / "screen report.json"
            src.write_text(json.dumps({"universe": universe, "history": history, "benchmark_history": btc}), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(ROOT / "tools" / "small_cap_screen.py"), str(src), "--output", str(dst)], capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            report = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual("REPRODUCIBLE_OFFLINE_SCREEN", report["status"])
            self.assertEqual(2, len(report["candidate_evidence"]))


if __name__ == "__main__":
    unittest.main()
