import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import daily_run


class DailyRunTests(unittest.TestCase):
    def setup_inputs(self, base):
        files = base / "research"
        files.mkdir()
        artifacts = {}
        for name in ("market", "screening", "committee", "watchlist", "accountability", "methodology"):
            path = files / f"{name}.json"
            path.write_text(json.dumps({"status": "NO_PICK" if name == "committee" else "complete"}), encoding="utf-8")
            artifacts[name] = path.name
        artifacts["desks"] = []
        for i in range(9):
            path = files / f"desk-{i}.json"
            path.write_text(json.dumps({"desk_id": str(i), "status": "complete"}), encoding="utf-8")
            artifacts["desks"].append(path.name)
        manifest = files / "manifest.json"
        stamp = "2026-10-11T12:00:00Z"
        manifest.write_text(json.dumps({"edition": {"date": "2026-10-11", "cutoff_utc": stamp,
                                                       "status": "draft", "regime": "offline fixture"},
                                        "sources": [{"id": "fixture", "label": "Offline fixture",
                                                     "url": "https://example.com", "accessed_utc": stamp}],
                                        "artifacts": artifacts}), encoding="utf-8")
        config = base / "config.json"
        config.write_text(json.dumps({"schedule": {"enabled": True, "daily_local_time": "07:00"},
                                      "providers": [{"name": "primary", "health": "HEALTHY", "quota": "UNVERIFIED",
                                                     "cost_usd": 0.12, "model_usage": {"input_tokens": 10}}]}), encoding="utf-8")
        return manifest, config

    def execute(self, base, manifest, config):
        with patch.object(daily_run.newsletter, "assemble", return_value={"edition": {}}), \
             patch.object(daily_run.newsletter, "load_packet", return_value={"edition": {}}), \
             patch.object(daily_run.newsletter, "validate", return_value=[]), \
             patch.object(daily_run.newsletter, "render", return_value="offline edition"):
            return daily_run.run(manifest, state_dir=base / "state", config_path=config, today="2026-10-11")

    def test_clean_offline_run_checkpoints_all_stages_and_cost_usage(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base = Path(temp)
            manifest, config = self.setup_inputs(base)
            result = daily_run.run(manifest, state_dir=base / "state", config_path=config, today="2026-10-11")
            self.assertEqual("COMPLETED", result["status"])
            self.assertEqual(daily_run.STAGES, tuple(result["stages"]))
            self.assertEqual(0.12, result["usage"]["cost_usd"])
            self.assertFalse(result["schedule"]["enabled"])
            self.assertEqual("Z", result["cutoff_utc"][-1])

    def test_repeat_is_idempotent_and_failed_stage_can_resume(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base = Path(temp)
            manifest, config = self.setup_inputs(base)
            with patch.object(daily_run.newsletter, "assemble", side_effect=RuntimeError("interrupted")):
                failed = daily_run.run(manifest, state_dir=base / "state", config_path=config, today="2026-10-11")
            self.assertEqual("FAILED", failed["status"])
            resumed = self.execute(base, manifest, config)
            repeated = self.execute(base, manifest, config)
            self.assertEqual("COMPLETED", resumed["status"])
            self.assertEqual(resumed["run_id"], repeated["run_id"])
            self.assertEqual("COMPLETED", repeated["status"])

    def test_missing_provider_and_incomplete_research_are_degraded(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base = Path(temp)
            manifest, config = self.setup_inputs(base)
            data = json.loads(config.read_text(encoding="utf-8"))
            data["providers"][0]["health"] = "UNAVAILABLE"
            config.write_text(json.dumps(data), encoding="utf-8")
            first_desk = manifest.parent / "desk-0.json"
            first_desk.write_text('{"desk_id":"market-data","status":"incomplete"}', encoding="utf-8")
            result = self.execute(base, manifest, config)
            self.assertEqual("DEGRADED", result["status"])
            self.assertTrue(any("provider primary" in issue for issue in result["diagnostics"]))
            self.assertTrue(any("incomplete research" in issue for issue in result["diagnostics"]))

    def test_concurrent_owner_lock_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base = Path(temp)
            manifest, config = self.setup_inputs(base)
            state = base / "state"
            state.mkdir()
            (state / "2026-10-11.lock").write_text("held", encoding="utf-8")
            with self.assertRaisesRegex(daily_run.RunError, "another daily run"):
                daily_run.run(manifest, state_dir=state, config_path=config, today="2026-10-11")


if __name__ == "__main__":
    unittest.main()
