import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import universe_builder as ub


class UniverseBuilderTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"provider": "a", "provider_asset_id": "one", "name": "Alpha", "ticker": "ABC",
             "network": "ethereum", "contract_address": "0xAbC", "circulating_market_cap_usd": 5_000_000,
             "fully_diluted_valuation_usd": 8_000_000, "circulating_supply": 1_000_000,
             "volume_24h_usd": 50_000, "liquidity_usd": 80_000,
             "venue": {"type": "dex", "name": "Uniswap", "network": "ethereum"}},
            {"provider": "b", "provider_asset_id": "another-id", "name": "Alpha Token", "ticker": "ABC",
             "network": "ethereum", "contract_address": "0xabc", "circulating_market_cap_usd": 5_200_000,
             "circulating_supply": 1_050_000, "volume_24h_usd": 45_000, "liquidity_usd": 75_000},
            {"provider": "a", "provider_asset_id": "two", "name": "Other ABC", "ticker": "ABC",
             "network": "base", "contract_address": "0xdef", "circulating_market_cap_usd": 20_000_000,
             "circulating_supply": 4_000_000},
        ]

    def test_deterministic_reconciliation_and_versioned_snapshot(self):
        first = ub.build_universe(self.records, snapshot_date="2026-10-11")
        second = ub.build_universe(list(reversed(copy.deepcopy(self.records))), snapshot_date="2026-10-11")
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], ub.VERSION)
        self.assertEqual(2, len(first["assets"]))
        merged = next(a for a in first["assets"] if a["name"] == "Alpha")
        self.assertEqual(["a", "b"], merged["providers"])
        self.assertEqual("MICRO", merged["market_cap_tier"])
        self.assertEqual(8_000_000, merged["fully_diluted_valuation_usd"])
        self.assertEqual("cross_provider_agreement; chain state not independently verified", merged["identity_verification"])

    def test_ticker_collision_does_not_merge_and_is_flagged(self):
        result = ub.build_universe(self.records, snapshot_date="2026-10-11")
        self.assertEqual(2, len(result["assets"]))
        for asset in result["assets"]:
            self.assertIn("ticker_collision", asset["flags"])
        self.assertEqual({"MICRO", "SMALL"}, {a["market_cap_tier"] for a in result["assets"]})

    def test_missing_market_cap_and_supply_remain_unknown(self):
        row = {"provider": "source", "provider_asset_id": "x", "ticker": "MISS", "network": "solana",
               "contract_address": "So111", "circulating_supply": None}
        asset = ub.build_universe([row], snapshot_date="2026-10-11")["assets"][0]
        self.assertIsNone(asset["circulating_market_cap_usd"])
        self.assertIsNone(asset["market_cap_tier"])
        self.assertEqual("UNKNOWN", asset["supply_confidence"])
        self.assertFalse(asset["included"])
        self.assertIn("missing_market_cap", asset["flags"])
        self.assertIn("no tier assigned", asset["eligibility_explanation"])

    def test_conflicting_identity_claims_are_excluded(self):
        row = {"provider": "source", "provider_asset_id": "x", "canonical_id": "same",
               "ticker": "X", "network": "ethereum", "contract_address": "0x1",
               "circulating_market_cap_usd": 1_000_000}
        conflicting = dict(row, provider="other", provider_asset_id="y", network="base", contract_address="0x2")
        asset = ub.build_universe([row, conflicting], snapshot_date="2026-10-11")["assets"][0]
        self.assertFalse(asset["included"])
        self.assertIn("identity_claim_disagreement", asset["flags"])
        self.assertIn("conflicting network or contract claims", asset["eligibility_explanation"])

    def test_cap_source_disagreement_is_preserved_and_flagged(self):
        rows = [dict(self.records[0]), dict(self.records[1], circulating_market_cap_usd=20_000_000)]
        asset = ub.build_universe(rows, snapshot_date="2026-10-11")["assets"][0]
        self.assertIn("market_cap_source_disagreement", asset["flags"])
        self.assertEqual([5_000_000, 20_000_000], asset["market_cap_observations_usd"])

    def test_tier_boundaries_and_legacy_observation_fields(self):
        rows = []
        for index, cap in enumerate((9_999_999, 10_000_000, 100_000_000, 100_000_001, 1_000_000_000)):
            rows.append({"provider": "fixture", "provider_asset_id": str(index), "ticker": f"T{index}",
                         "chain": "ethereum", "contract_address": f"0x{index}", "market_cap": cap,
                         "volume": 100, "liquidity": 200, "exchange": "Venue X"})
        assets = ub.build_universe(rows, snapshot_date="2026-10-11")["assets"]
        self.assertEqual(["MICRO", "SMALL", "SMALL", "EXPANDED", None], [a["market_cap_tier"] for a in assets])
        self.assertEqual("Venue X", assets[0]["venues"][0]["name"])
        self.assertEqual(200, assets[0]["liquidity_usd"])

    def test_policy_exclusions_and_cli_snapshot(self):
        row = dict(self.records[0], stablecoin=True, wrapped=True, active=False)
        asset = ub.build_universe([row], snapshot_date="2026-10-11")["assets"][0]
        self.assertFalse(asset["included"])
        self.assertTrue({"stablecoin", "wrapped_token", "inactive"}.issubset(asset["flags"]))
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp) / "in.json", Path(tmp) / "out.json"
            inp.write_text(json.dumps(self.records), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(ROOT / "tools" / "universe_builder.py"), str(inp),
                                   "--date", "2026-10-11", "--output", str(out)], capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertEqual("2026-10-11", json.loads(out.read_text(encoding="utf-8"))["snapshot_date"])


if __name__ == "__main__":
    unittest.main()
