"""Contract checks for project-local Codex research-agent definitions."""

from pathlib import Path
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
AGENT_DIR = ROOT / ".codex" / "agents"
EXPECTED = {
    "chief-research-officer",
    "market-data-researcher",
    "quantitative-analyst",
    "onchain-analyst",
    "risk-analyst",
    "independent-reviewer",
    "newsletter-editor",
    "discovery-desk",
    "technicals-desk",
    "liquidity-desk",
    "tokenomics-desk",
    "catalysts-desk",
    "falsification-desk",
}
DESK_IDS = {"market-data", "discovery", "technicals", "liquidity", "on-chain", "tokenomics", "catalysts", "risk", "falsification"}


class NativeResearchAgentTests(unittest.TestCase):
    def test_all_project_agents_parse_and_have_complete_contracts(self):
        definitions = {
            tomllib.loads(path.read_text(encoding="utf-8"))["name"]: tomllib.loads(
                path.read_text(encoding="utf-8")
            )
            for path in AGENT_DIR.glob("*.toml")
        }
        self.assertEqual(EXPECTED, set(definitions))
        self.assertEqual(len(EXPECTED), len(list(AGENT_DIR.glob("*.toml"))))
        for name, definition in definitions.items():
            with self.subTest(agent=name):
                self.assertTrue(definition.get("description"))
                self.assertTrue(definition.get("developer_instructions"))
                self.assertEqual("read-only", definition.get("sandbox_mode"))
                instructions = definition["developer_instructions"].casefold()
                for required_boundary in ("trading", "payments", "external publication"):
                    self.assertIn(required_boundary, instructions)
                if not name.endswith("-desk"):
                    for required in ("input", "output", "escalate"):
                        self.assertIn(required, instructions)

    def test_project_config_caps_concurrency_and_keeps_model_inherited(self):
        config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(2, config["agents"]["max_concurrent_threads_per_session"])
        # No model is pinned at project level or on a role; availability remains account-specific.
        self.assertNotIn("default_subagent_model", config["agents"])
        for path in AGENT_DIR.glob("*.toml"):
            self.assertNotIn("model", tomllib.loads(path.read_text(encoding="utf-8")))

    def test_coordinator_owns_decisions_and_reviewer_handoff_is_isolated(self):
        coordinator = tomllib.loads((AGENT_DIR / "chief-research-officer.toml").read_text(encoding="utf-8"))
        reviewer = tomllib.loads((AGENT_DIR / "independent-reviewer.toml").read_text(encoding="utf-8"))
        coordinator_instructions = coordinator["developer_instructions"].casefold()
        reviewer_instructions = reviewer["developer_instructions"].casefold()
        self.assertIn("sole coordinator", coordinator_instructions)
        self.assertIn("do not give it candidate-agent conclusions", coordinator_instructions)
        self.assertIn("original brief", coordinator_instructions)
        self.assertIn("review_contaminated", reviewer_instructions)
        self.assertIn("do not use candidate agents' conclusions", reviewer_instructions)

    def test_nine_desk_contracts_and_coordinator_scheduling_are_present(self):
        from research_desks import DESK_IDS
        self.assertEqual(9, len(DESK_IDS))
        definitions = {
            tomllib.loads(path.read_text(encoding="utf-8-sig"))["name"]: tomllib.loads(path.read_text(encoding="utf-8-sig"))
            for path in AGENT_DIR.glob("*.toml")
        }
        desk_names = {name for name in definitions if name.endswith("-desk")}
        self.assertEqual({"discovery-desk", "technicals-desk", "liquidity-desk", "tokenomics-desk", "catalysts-desk", "falsification-desk"}, desk_names)
        coordinator = definitions["chief-research-officer"]["developer_instructions"].casefold()
        for required in ("market-data", "discovery", "technicals", "liquidity", "on-chain", "tokenomics", "catalysts", "risk", "falsification", "at most two", "five distinct source ids", "eighteen", "simulated", "immutable handoff"):
            self.assertIn(required, coordinator)

    def test_nine_desk_outputs_have_common_schema_fields(self):
        from research_desks import DESK_IDS, incomplete_result, validate_desk_result
        identity = {"candidate_id": "fixture:1", "name": "Fixture"}
        for desk_id in DESK_IDS:
            with self.subTest(desk=desk_id):
                output = validate_desk_result(incomplete_result(identity, desk_id))
                self.assertEqual(desk_id, output["desk_id"])
                self.assertEqual("inconclusive", output["assessment"])

    def test_static_or_simulated_checks_are_not_native_delegation_evidence(self):
        docs = (ROOT / "docs" / "native-research-agents.md").read_text(encoding="utf-8")
        self.assertIn("STATIC_CONFIG_VALIDATED", docs)
        self.assertIn("NATIVE_DELEGATION_VERIFIED", docs)
        self.assertIn("DEGRADED_EXECUTION", docs)
        self.assertIn("runtime trace showing a spawned child", docs)
        self.assertIn("do not claim an agent was spawned", docs)


if __name__ == "__main__":
    unittest.main()
