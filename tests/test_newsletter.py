import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import newsletter
from research_accountability import publish, append_observation


class NewsletterTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads((ROOT / "examples" / "no-pick.json").read_text(encoding="utf-8"))

    def test_fixture_checks_and_renders_all_sections_in_order(self):
        self.assertEqual([], newsletter.validate(self.packet))
        rendered = newsletter.render(self.packet)
        positions = [rendered.index(f"## {heading}") for _, heading in newsletter.SECTIONS]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("NO PICK", rendered)
        self.assertIn("[Example source record (fixture)](https://example.com/research-method)", rendered)

    def test_unsupported_pick_is_rejected(self):
        packet = copy.deepcopy(self.packet)
        packet["pick"] = {"status": "PICK", "asset": "Example", "ticker": "EX", "gates": {}, "review": {}}
        errors = newsletter.validate(packet)
        self.assertIn("PICK gate identity must be PASS", errors)
        self.assertIn("PICK requires frozen review inputs and a structured adversarial challenge report", errors)

    def test_unknown_citation_is_rejected(self):
        packet = copy.deepcopy(self.packet)
        packet["sections"]["watchlist"]["source_ids"] = ["missing"]
        self.assertTrue(any("unknown source id: missing" in item for item in newsletter.validate(packet)))

    def test_release_requires_editorial_approval_and_approved_state(self):
        errors = newsletter.validate(self.packet, release=True)
        self.assertIn("release requires edition.status = approved", errors)
        self.assertIn("release requires editorial_approval = true", errors)

    def test_approved_no_pick_can_render_as_a_local_release_artifact(self):
        packet = copy.deepcopy(self.packet)
        packet["edition"]["status"] = "approved"
        packet["editorial_approval"] = True
        rendered = newsletter.render(packet, release=True)
        self.assertTrue(rendered.startswith("# EDITION — 2026-10-11"))
        self.assertIn("NO PICK", rendered)

    def test_cli_rejects_missing_packet(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "newsletter.py"), "check", str(ROOT / "missing.json")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("FAIL:", result.stderr)

    def test_cli_renders_only_to_requested_local_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            output = Path(temp) / "preview.md"
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "newsletter.py"), "render", str(ROOT / "examples" / "no-pick.json"), "--output", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("DRAFT PREVIEW", output.read_text(encoding="utf-8"))

    def test_cli_rejects_output_outside_project(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "newsletter.py"), "render", str(ROOT / "examples" / "no-pick.json"), "--output", str(Path(temp) / "outside.md")],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("must stay inside the project directory", result.stderr)

    def test_complete_persisted_artifact_fixture_assembles_and_renders(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_name:
            base = Path(temp_name)
            artifacts = base / "artifacts"
            artifacts.mkdir()
            stamp = "2026-10-11T16:00:00Z"
            data = {
                "market": {"snapshot_at": stamp, "regime": "mixed; coverage incomplete", "btc_change_24h_pct": -1.2},
                "screening": {"snapshot_date": "2026-10-11", "eligible_count": 0, "rejected_count": 3},
                "committee": {"status": "NO_PICK", "decision_records": [{"status": "INELIGIBLE", "reasons": ["independent review missing"]}]},
                "watchlist": {"as_of": "2026-10-11", "window_days": 7, "ranked_watchlist": [{"identity": {"name": "Fixture Token", "symbol": "FIX"}, "state": "WATCHING", "thesis": "wait for fresh liquidity", "entry_trigger": "daily close above prior range", "invalidation_trigger": "thesis catalyst withdrawn"}]},
                "accountability": {"status": "NOT_REPORTABLE", "reason": "original persisted pick record unavailable"},
                "methodology": {"screen": "offline reproducible snapshot", "limitations": ["fixture only"]},
            }
            for name, payload in data.items():
                (artifacts / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
            for index, desk in enumerate(("market-data", "discovery", "technicals", "liquidity", "on-chain", "tokenomics", "catalysts", "risk", "falsification")):
                (artifacts / f"desk-{index}.json").write_text(json.dumps({"desk_id": desk, "status": "incomplete", "assessment": "inconclusive", "unresolved_questions": ["fixture evidence unavailable"]}), encoding="utf-8")
            names = {key: f"artifacts/{key}.json" for key in data}
            names["desks"] = [f"artifacts/desk-{i}.json" for i in range(9)]
            manifest = {
                "edition": {"date": "2026-10-11", "cutoff_utc": stamp, "status": "draft", "regime": "Mixed, incomplete coverage; synthetic offline fixture."},
                "sources": [{"id": "fixture", "label": "Synthetic research fixture", "url": "https://example.com/fixture", "accessed_utc": stamp}],
                "artifacts": names,
            }
            manifest_path = base / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            packet_path = base / "packet.json"
            assembled = subprocess.run([sys.executable, str(ROOT / "tools" / "newsletter.py"), "assemble", str(manifest_path), "--output", str(packet_path)], capture_output=True, text=True)
            self.assertEqual(0, assembled.returncode, assembled.stderr)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(13, len(packet["sections"]))
            self.assertEqual("NO_PICK", packet["pick"]["status"])
            checked = subprocess.run([sys.executable, str(ROOT / "tools" / "newsletter.py"), "check", str(packet_path)], capture_output=True, text=True)
            self.assertEqual(0, checked.returncode, checked.stderr)
            output = base / "edition.md"
            rendered = subprocess.run([sys.executable, str(ROOT / "tools" / "newsletter.py"), "render", str(packet_path), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(0, rendered.returncode, rendered.stderr)
            markdown = output.read_text(encoding="utf-8")
            self.assertEqual(13, sum(f"## {heading}" in markdown for _, heading in newsletter.SECTIONS))
            self.assertIn("NO PICK", markdown)
            self.assertIn("Synthetic research fixture", markdown)
            data["committee"]["status"] = "PICK"
            (artifacts / "committee.json").write_text(json.dumps(data["committee"]), encoding="utf-8")
            fallback = subprocess.run([sys.executable, str(ROOT / "tools" / "newsletter.py"), "assemble", str(manifest_path), "--output", str(packet_path)], capture_output=True, text=True)
            self.assertEqual(0, fallback.returncode, fallback.stderr)
            fallback_packet = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual("NO_PICK", fallback_packet["pick"]["status"])
            self.assertIn("lacks packet-level frozen reviewer evidence", fallback_packet["sections"]["pick-of-the-day"]["content"])

    def test_assembly_uses_frozen_accountability_ledger_in_existing_section(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_name:
            base = Path(temp_name)
            artifacts = base / "artifacts"
            artifacts.mkdir()
            stamp = "2026-10-11T16:00:00Z"
            for name, payload in {"market": {}, "screening": {}, "committee": {"status": "NO_PICK"},
                                  "watchlist": {}, "methodology": {}}.items():
                (artifacts / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
            ledger = artifacts / "accountability.jsonl"
            publish(ledger, {"record_id": "fixture-pick", "kind": "daily_pick", "published_at": "2026-09-01T00:00:00Z",
                "identity": {"chain": "Demo", "asset_id": "ABC", "symbol": "ABC"}, "thesis": "Original published thesis",
                "direction": "LONG", "reference_price": 10, "venue": "Fixture DEX",
                "confirmation": {"type": "price_at_or_above", "value": 11}, "invalidation": {"type": "price_at_or_below", "value": 8},
                "expires_at": "2026-12-01T00:00:00Z"})
            append_observation(ledger, "fixture-pick", {"observed_at": "2026-09-08T00:00:00Z", "price": 12, "venue": "Fixture DEX"})
            names = {name: f"artifacts/{name}.json" for name in ("market", "screening", "committee", "watchlist", "methodology")}
            names["accountability"] = "artifacts/accountability.jsonl"
            names["desks"] = []
            for index in range(9):
                (artifacts / f"desk-{index}.json").write_text("{}", encoding="utf-8")
                names["desks"].append(f"artifacts/desk-{index}.json")
            manifest = {"edition": {"date": "2026-10-11", "cutoff_utc": stamp, "status": "draft", "regime": "fixture"},
                        "sources": [{"id": "fixture", "label": "Fixture", "url": "https://example.com", "accessed_utc": stamp}], "artifacts": names}
            manifest_path = base / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            packet = newsletter.assemble(manifest_path)
            content = packet["sections"]["previous-pick-accountability"]["content"]
            self.assertIn("VALIDATED", content)
            self.assertIn("Original published thesis", content)
            self.assertIn("directional hit rate", content)
            self.assertIn("no realizable profit implied", content)

    def test_editorial_fact_check_rejects_unsupported_numeric_claim(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_name:
            base = Path(temp_name)
            manifest = json.loads((ROOT / "examples" / "no-pick.json").read_text(encoding="utf-8"))
            # A fully persisted minimal evidence bundle is required even when a claim fails.
            artifacts = base / "artifacts"
            artifacts.mkdir()
            paths = {}
            for name in ("market", "screening", "committee", "watchlist", "accountability", "methodology"):
                payload = {"status": "NO_PICK"} if name == "committee" else ({"btc_change_pct": 1.5} if name == "market" else {"fixture": "offline"})
                (artifacts / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
                paths[name] = f"artifacts/{name}.json"
            paths["desks"] = []
            for index in range(9):
                (artifacts / f"desk-{index}.json").write_text("{}", encoding="utf-8")
                paths["desks"].append(f"artifacts/desk-{index}.json")
            manifest_record = {"edition": self.packet["edition"], "sources": self.packet["sources"], "artifacts": paths}
            manifest_path = base / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_record), encoding="utf-8")
            packet = copy.deepcopy(self.packet)
            packet["editorial_checklist"] = {key: True for key in ("opening_summary", "market_sector_context", "watchlist_opportunities", "entry_confirmation_and_invalidation", "risk_discussion", "traceable_citations", "missing_stale_contradictory_evidence")}
            packet["sections"]["watchlist"]["content"] = "The asset gained 1.5%."
            packet["editorial_claims"] = [{"section": "watchlist", "text": "The asset gained 1.5%.", "value": "1.5", "artifact": "market", "json_pointer": "/btc_change_pct", "source_ids": ["fixture-method"]}]
            packet_path = base / "edited.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            valid = subprocess.run([sys.executable, str(ROOT / "tools" / "newsletter.py"), "fact-check", str(packet_path), "--manifest", str(manifest_path)], capture_output=True, text=True)
            self.assertEqual(0, valid.returncode, valid.stderr)
            packet["sections"]["watchlist"]["content"] = "The asset gained 999%."
            packet["editorial_claims"][0].update({"text": "The asset gained 999%.", "value": "999"})
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "tools" / "newsletter.py"), "fact-check", str(packet_path), "--manifest", str(manifest_path)], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertIn("unsupported numerical claim in sections.watchlist: 999", result.stderr)


if __name__ == "__main__":
    unittest.main()
