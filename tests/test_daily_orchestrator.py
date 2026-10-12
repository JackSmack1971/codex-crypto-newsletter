import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import daily_orchestrator  # noqa: E402
import daily_run  # noqa: E402
import newsletter  # noqa: E402


class DailyOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.base = Path(self.temp.name)
        self.fixture = self.base / "replay.json"
        self.fixture.write_text(json.dumps({"observations": [
            {"provider": "fixture-a", "retrieved_at": "2026-10-11T12:00:00Z", "native_observation_time": "2026-10-11T11:59:00Z",
             "chain": "ethereum", "contract_address": "0xabc", "token_id": "abc", "ticker": "ABC", "name": "Alpha",
             "market_cap": 5_000_000, "volume": 1_000_000, "liquidity": 500_000, "exchange": "Fixture DEX"}
        ], "history": {}}), encoding="utf-8")
        self.out = self.base / "run"

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_replay_runs_all_stages_and_writes_controller_compatible_edition(self):
        result = daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        self.assertEqual("DEGRADED_NO_PICK", result["status"])
        self.assertEqual(6, len(result["stages"]))
        self.assertEqual("NO_PICK", json.loads((self.out / "packet.json").read_text()) ["pick"]["status"])
        self.assertIn("NO PICK", (self.out / "edition.md").read_text(encoding="utf-8"))
        self.assertTrue((self.out / "manifest.json").is_file())
        self.assertTrue((self.out / "source-snapshot.json").is_file())
        snapshot = json.loads((self.out / "source-snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual("SIMULATED_REPLAY", snapshot["readiness"]["evidence_quality"])
        self.assertFalse(snapshot["live_source_verified"])
        screening = json.loads((self.out / "screening.json").read_text(encoding="utf-8"))
        self.assertEqual("SIMULATED_REPLAY", screening["evidence_quality"])
        packet = json.loads((self.out / "packet.json").read_text(encoding="utf-8"))
        self.assertEqual("SIMULATED_REPLAY", packet["sources"][0]["evidence_quality"])
        self.assertFalse(any(result["external_effects"].values()))
        self.assertRegex(result["artifacts"]["packet.json"], r"^[0-9a-f]{64}$")

    def test_empty_input_is_an_explicit_degraded_no_pick(self):
        self.fixture.write_text(json.dumps({"observations": []}), encoding="utf-8")
        result = daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        self.assertEqual("DEGRADED_NO_PICK", result["status"])
        committee = json.loads((self.out / "committee.json").read_text())
        self.assertEqual("NO_PICK", committee["status"])
        self.assertEqual([], committee["decision_records"])

    def test_bad_fixture_and_date_are_rejected(self):
        self.fixture.write_text("{broken", encoding="utf-8")
        with self.assertRaises(daily_orchestrator.OrchestrationError):
            daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        with self.assertRaises(daily_orchestrator.OrchestrationError):
            daily_orchestrator.run("yesterday", self.fixture, self.out)

    def test_existing_nonempty_directory_rejects_repeat_and_partial_artifact_corruption(self):
        daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        with self.assertRaisesRegex(daily_orchestrator.OrchestrationError, "must exist and be empty"):
            daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        (self.out / "committee.json").write_text("{bad", encoding="utf-8")
        manifest = json.loads((self.out / "manifest.json").read_text())
        (self.out / manifest["artifacts"]["screening"]).unlink()
        with self.assertRaises(newsletter.PacketError):
            newsletter.assemble(self.out / "manifest.json")

    def test_stage_failure_propagates_without_committing_partial_outputs(self):
        with patch.object(daily_orchestrator.small_cap_screen, "screen", side_effect=RuntimeError("screen failed")):
            with self.assertRaisesRegex(RuntimeError, "screen failed"):
                daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        self.assertFalse(self.out.exists())

    def test_interrupted_assembly_leaves_no_artifacts_and_retry_succeeds(self):
        with patch.object(daily_orchestrator.newsletter, "assemble", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        self.assertFalse(self.out.exists())
        daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        self.assertTrue((self.out / "edition.md").is_file())

    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            with self.assertRaisesRegex(daily_orchestrator.OrchestrationError, "stay inside"):
                daily_orchestrator.run("2026-10-11", Path(outside) / "missing.json", self.out)
            with self.assertRaisesRegex(daily_orchestrator.OrchestrationError, "stay inside"):
                daily_orchestrator.run("2026-10-11", self.fixture, Path(outside) / "run")

    def test_outputs_are_byte_deterministic_for_identical_declared_input(self):
        a, b = self.base / "a", self.base / "b"
        daily_orchestrator.run("2026-10-11", self.fixture, a)
        daily_orchestrator.run("2026-10-11", self.fixture, b)
        def digest_tree(root):
            return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(root.rglob("*")) if p.is_file()}
        self.assertEqual(digest_tree(a), digest_tree(b))

    def test_single_command_generates_edition_from_fixture(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "daily_orchestrator.py"), "--date", "2026-10-11",
                                 "--replay", str(self.fixture), "--output", str(self.out)],
                                cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.out / "edition.md").is_file())

    def test_existing_replay_observation_array_is_accepted_by_single_command(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "daily_orchestrator.py"), "--date", "2026-10-11",
                                 "--replay", str(ROOT / "tests" / "fixtures" / "market-observations.json"),
                                 "--output", str(self.out)], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        packet = json.loads((self.out / "packet.json").read_text(encoding="utf-8"))
        self.assertEqual("NO_PICK", packet["pick"]["status"])

    def test_controller_consumes_mocked_live_adapter_and_propagates_readiness(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return "https://api.dexscreener.com/latest/dex/search?q=TEST"
            def read(self, n):
                return b'{"pairs":[{"chainId":"base","baseToken":{"address":"0xabc"},"priceUsd":"1","marketCap":5000000,"volume":{"h24":1000000},"liquidity":{"usd":500000}}]}'[:n]
        class Opener:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                return Response()
        opener = Opener()
        result = daily_orchestrator.run("2026-10-11", None, self.out, mode="live-rest",
            requests=[{"route": "dex-pair-search", "query": "TEST"}], authorized=True, opener=opener)
        self.assertEqual(1, opener.calls)
        self.assertTrue(result["source_readiness"]["live_source_verified"])
        snapshot = json.loads((self.out / "source-snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual("LIVE_RETRIEVAL_PROVIDER_CLAIMS", snapshot["readiness"]["evidence_quality"])
        self.assertTrue(json.loads((self.out / "screening.json").read_text(encoding="utf-8"))["source_readiness"]["live_source_verified"])

    def test_cli_requires_live_rest_opt_in_and_blocks_mcp(self):
        with patch("sys.stderr", new_callable=__import__("io").StringIO):
            self.assertEqual(2, daily_orchestrator.main(["--date", "2026-10-11", "--mode", "live-rest",
                "--request", "dex-pair-search=TEST", "--output", str(self.out)]))
            self.assertEqual(2, daily_orchestrator.main(["--date", "2026-10-11", "--mode", "live-mcp",
                "--output", str(self.out)]))
        self.assertFalse(self.out.exists())

    def test_manifest_and_artifacts_pass_existing_daily_controller(self):
        daily_orchestrator.run("2026-10-11", self.fixture, self.out)
        state = self.base / "controller-state"
        result = daily_run.run(self.out / "manifest.json", state_dir=state, today="2026-10-11")
        self.assertEqual("DEGRADED", result["status"])
        self.assertTrue((state / "2026-10-11-packet.json").is_file())
        self.assertTrue((state / "2026-10-11-edition.md").is_file())


if __name__ == "__main__":
    unittest.main()
