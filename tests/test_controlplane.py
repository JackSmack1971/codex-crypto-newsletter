import contextlib
import copy
import io
import json
import tomllib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import controlplane


class ControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self.config = controlplane.load_config()
        self.catalog = controlplane.discover_skills(controlplane._skill_roots(self.config["skill_roots"]))
        self.policy = controlplane.load_source_policy()

    def test_config_and_default_source_policy_are_valid_and_deny(self):
        self.assertEqual([], controlplane.validate_config(self.config))
        self.assertEqual([], controlplane.validate_source_policy(self.policy))
        result = controlplane.authorize_source(self.policy, "public-news", "read", "https://example.com/news")
        self.assertEqual("DENY", result["status"])

    def test_allowlist_requires_source_operation_https_host_and_cost_match(self):
        policy = copy.deepcopy(self.policy)
        policy["sources"] = [{
            "id": "test-source", "enabled": True, "domains": ["news.example.com"],
            "operations": ["read"], "max_cost_per_operation_usd": 0,
        }]
        self.assertEqual([], controlplane.validate_source_policy(policy))
        allow = controlplane.authorize_source(policy, "test-source", "read", "https://news.example.com/item")
        self.assertEqual("ALLOW", allow["status"])
        self.assertEqual("DENY", controlplane.authorize_source(policy, "test-source", "write", "https://news.example.com/item")["status"])
        self.assertEqual("DENY", controlplane.authorize_source(policy, "test-source", "read", "https://evil.example.com/item")["status"])
        self.assertEqual("DENY", controlplane.authorize_source(policy, "test-source", "read", "http://news.example.com/item")["status"])
        self.assertEqual("DENY", controlplane.authorize_source(policy, "test-source", "trade", "https://news.example.com/item")["status"])
        self.assertEqual("DENY", controlplane.authorize_source(policy, "test-source", "read", "https://user:pass@news.example.com/item")["status"])
        self.assertEqual("DENY", controlplane.authorize_source(policy, "test-source", "read", "https://news.example.com:8443/item")["status"])
        self.assertEqual("DENY", controlplane.authorize_source(policy, "test-source", "read", "https://news.example.com:bad/item")["status"])
        policy["sources"][0]["max_cost_per_operation_usd"] = 0.02
        self.assertEqual("DENY", controlplane.authorize_source(policy, "test-source", "read", "https://news.example.com/item", 0.01)["status"])
        policy["paid_operations"] = True
        self.assertEqual("ALLOW", controlplane.authorize_source(policy, "test-source", "read", "https://news.example.com/item", 0.01)["status"])

    def test_discovery_reads_manifests_and_resolver_recommends_exact_skill(self):
        result = controlplane.route_task("Prepare the Small-Cap Crypto Daily newsletter research packet", self.config, self.catalog)
        self.assertEqual("RECOMMEND", result["status"])
        self.assertEqual("crypto-daily", result["skill"])
        self.assertEqual(".agents/skills/crypto-daily/SKILL.md", result["manifest"])

    def test_every_configured_route_resolves_to_one_discovered_manifest(self):
        for route in self.config["routes"]:
            with self.subTest(route=route["id"]):
                result = controlplane.route_task(route["match_any"][0], self.config, self.catalog)
                self.assertEqual("RECOMMEND", result["status"])
                self.assertEqual(route["skill"], result["skill"])
                self.assertTrue(result["manifest"].endswith("/SKILL.md"))

    def test_crypto_daily_references_are_files_and_resolve(self):
        skill_dir = ROOT / ".agents" / "skills" / "crypto-daily"
        self.assertFalse((skill_dir / "references").is_file())
        reference_dir = skill_dir / "references"
        self.assertEqual(
            {"editorial-contract.md", "release-checklist.md", "research-evidence.md"},
            {path.name for path in reference_dir.glob("*.md")},
        )
        manifest = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual("crypto-daily", controlplane._parse_manifest(skill_dir / "SKILL.md")[0])
        for relative_path in ("references/editorial-contract.md", "references/release-checklist.md"):
            self.assertTrue((skill_dir / relative_path).is_file(), relative_path)
        self.assertTrue((skill_dir / "references/research-evidence.md").is_file())
        self.assertTrue((ROOT / "docs" / "edition-contract.md").is_file())
        self.assertIn("references/editorial-contract.md", manifest)
        self.assertIn("references/release-checklist.md", manifest)
        self.assertNotIn("references/editorial-and-release.md", manifest)

    def test_unverified_coinpaprika_mcp_is_disabled_in_runtime_and_policy(self):
        mcp_config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        coinpaprika_mcp = next(source for source in self.policy["sources"] if source["id"] == "coinpaprika-mcp")
        self.assertFalse(mcp_config["mcp_servers"]["coinpaprika"]["enabled"])
        self.assertFalse(coinpaprika_mcp["enabled"])

    def test_all_discovered_skill_manifests_have_valid_frontmatter(self):
        self.assertEqual([], self.catalog["issues"])
        for skill_name in self.catalog["skills"]:
            with self.subTest(skill=skill_name):
                self.assertEqual(1, len(self.catalog["skills"][skill_name]))

    def test_explicit_override_must_resolve_to_one_manifest(self):
        result = controlplane.route_task("unmatched task", self.config, self.catalog, "crypto-daily")
        self.assertEqual("user-override", result["route_id"])
        with self.assertRaisesRegex(controlplane.ControlPlaneError, "exactly one"):
            controlplane.route_task("unmatched task", self.config, self.catalog, "missing-skill")

    def test_router_abstains_for_no_match_and_competing_routes(self):
        no_match = controlplane.route_task("What is the weather in Boston?", self.config, self.catalog)
        self.assertEqual("ABSTAIN", no_match["status"])
        competing = controlplane.route_task("Implement code for the crypto newsletter research control plane", self.config, self.catalog)
        self.assertEqual("ABSTAIN", competing["status"])
        self.assertEqual(2, len(competing["matched_routes"]))
        self.assertTrue(competing["rejected_candidates"])

    def test_missing_and_duplicate_skill_manifests_fail_closed(self):
        self.assertEqual("ABSTAIN", controlplane.route_task("Prepare the Small-Cap Crypto Daily newsletter", self.config, {"skills": {}, "duplicates": [], "issues": [], "roots": []})["status"])
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "one" / "crypto-daily"
            second = Path(temp) / "two" / "crypto-daily"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            manifest = "---\nname: crypto-daily\ndescription: A fixture skill.\n---\n"
            (first / "SKILL.md").write_text(manifest, encoding="utf-8")
            (second / "SKILL.md").write_text(manifest, encoding="utf-8")
            catalog = controlplane.discover_skills([("first", first.parent), ("second", second.parent)])
            self.assertEqual(["crypto-daily"], catalog["duplicates"])
            self.assertEqual("ABSTAIN", controlplane.route_task("Prepare the Small-Cap Crypto Daily newsletter", self.config, catalog)["status"])

    def test_invalid_manifest_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = Path(temp) / "broken"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("No front matter", encoding="utf-8")
            catalog = controlplane.discover_skills([("fixture", Path(temp))])
            self.assertTrue(catalog["issues"])
            self.assertIn("front matter missing", catalog["issues"][0]["reason"])

    def test_inaccessible_skill_root_is_reported_as_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = Path.iterdir

            def inaccessible(path):
                if path == root:
                    raise PermissionError("fixture")
                return original(path)

            with patch.object(Path, "iterdir", inaccessible):
                catalog = controlplane.discover_skills([("fixture", root)])
            self.assertEqual("UNVERIFIED", catalog["issues"][0]["status"])

    def test_routing_metrics_report_executed_counts_and_denominators(self):
        cases = json.loads((ROOT / "examples" / "routing-cases.json").read_text(encoding="utf-8"))
        report = controlplane.evaluate_routes(self.config, self.catalog, cases)
        self.assertGreaterEqual(len(report["cases"]), 40)
        self.assertEqual(1.0, report["metrics"]["precision"]["value"])
        self.assertEqual(1.0, report["metrics"]["recall"]["value"])
        self.assertEqual(0.0, report["metrics"]["inappropriate_invocation_rate"]["value"])
        self.assertEqual(0.0, report["metrics"]["missed_invocation_rate"]["value"])
        self.assertEqual(0.0, report["metrics"]["false_positive_rate"]["value"])
        self.assertTrue(all(row["correct"] for row in report["cases"]))

    def test_focused_skills_have_triggers_artifacts_workflows_and_valid_relative_references(self):
        import re
        expected = {
            "crypto-universe-discovery", "market-data-validation", "small-cap-screening",
            "technical-analysis", "liquidity-analysis", "onchain-intelligence",
            "tokenomics-diligence", "catalyst-research", "investment-falsification",
            "daily-pick-selection", "weekly-watchlist", "newsletter-production",
        }
        self.assertTrue(expected.issubset(self.catalog["skills"]))
        for name in expected:
            manifest = ROOT / ".agents" / "skills" / name / "SKILL.md"
            body = manifest.read_text(encoding="utf-8")
            description = controlplane._parse_manifest(manifest)[1].casefold()
            with self.subTest(skill=name):
                self.assertIn("use for", description)
                self.assertIn("do not use", description)
                self.assertIn("## Inputs and outputs", body)
                self.assertIn("## Workflow", body)
                self.assertIn("## Evidence and failure behavior", body)
                for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
                    if "://" not in target and not target.startswith("#"):
                        self.assertTrue((manifest.parent / target).resolve().is_file(), target)

    def test_critical_negative_routing_cases_never_activate_a_skill(self):
        cases = json.loads((ROOT / "examples" / "routing-cases.json").read_text(encoding="utf-8"))
        report = controlplane.evaluate_routes(self.config, self.catalog, cases)
        critical = [row for row in report["cases"] if row["kind"] in {"negative", "ambiguous"}]
        self.assertTrue(critical)
        self.assertTrue(all(row["predicted"] is None for row in critical))

    def test_explicit_skill_invocation_routes_to_discovered_manifest(self):
        result = controlplane.route_task("Use skill: liquidity-analysis to assess the venues", self.config, self.catalog)
        self.assertEqual("liquidity-analysis", result["skill"])
        self.assertEqual("explicit-skill-invocation", result["route_id"])

    def test_unknown_profile_sandbox_escalation_and_workspace_escape_are_rejected(self):
        with self.assertRaisesRegex(controlplane.ControlPlaneError, "unknown profile"):
            controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "missing-profile")
        with self.assertRaisesRegex(controlplane.ControlPlaneError, "escalation is denied"):
            controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "safe", sandbox="danger-full-access")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(controlplane.ControlPlaneError, "inside the project"):
                controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "safe", temp)

    def test_config_rejects_elevated_profile_and_unknown_fields(self):
        config = copy.deepcopy(self.config)
        config["profiles"]["safe"]["sandbox"] = "danger-full-access"
        self.assertTrue(any("elevated sandbox" in error for error in controlplane.validate_config(config)))
        config = copy.deepcopy(self.config)
        config["unexpected"] = True
        self.assertTrue(any("top-level fields" in error for error in controlplane.validate_config(config)))

    def test_doctor_is_read_only_and_does_not_echo_config_values(self):
        observed = []

        def version_probe(command, **kwargs):
            observed.append(command[1:])
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.162.1\n", "")

        with patch.object(controlplane.subprocess, "run", side_effect=version_probe):
            report = controlplane.doctor()
        self.assertEqual("PASS", report["checks"]["codex_cli"]["status"])
        self.assertEqual([["--version"]], observed)
        self.assertIn("no model session started", report["side_effects"])

    def test_doctor_reports_missing_binary_and_invalid_user_config_without_values(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "config.toml"
            secret = "fixture-secret-must-not-leak"
            config_path.write_text(f'api_key = "{secret}"\ninvalid = [\n', encoding="utf-8")
            with patch.dict("os.environ", {"CODEX_HOME": temp}), patch.object(controlplane.shutil, "which", return_value=None):
                report = controlplane.doctor()
            serialized = json.dumps(report)
            self.assertEqual("FAIL", report["checks"]["codex_cli"]["status"])
            self.assertEqual("FAIL", report["checks"]["codex_user_config"]["status"])
            self.assertNotIn(secret, serialized)
            self.assertNotIn(str(config_path), serialized)

    def test_invalid_project_json_fails_without_echoing_contents(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "bad.json"
            path.write_text('{"secret":"do-not-echo",', encoding="utf-8")
            with self.assertRaisesRegex(controlplane.ControlPlaneError, "invalid JSON") as raised:
                controlplane._read_json(path, "fixture")
            self.assertNotIn("do-not-echo", str(raised.exception))

    def test_launch_plan_is_check_only_until_explicit_mock_or_execute(self):
        plan = controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "safe", "examples/synthetic-workspace")
        self.assertEqual("crypto-daily", plan["route"]["skill"])
        self.assertIn("<TASK_PROMPT_REDACTED>", plan["argv_template"])
        self.assertEqual("read-only", plan["argv_template"][plan["argv_template"].index("--sandbox") + 1])
        draft_plan = controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "newsletter-draft")
        self.assertEqual("workspace-write", draft_plan["argv_template"][draft_plan["argv_template"].index("--sandbox") + 1])
        self.assertIn("--config", draft_plan["argv_template"])
        self.assertIn('approval_policy="on-request"', draft_plan["argv_template"])

    def test_mocked_subprocess_writes_redacted_artifact_and_propagates_failure(self):
        plan = controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter. Private task text must not be retained.", "safe")
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            artifact_path = Path(temp) / "run.json"
            result = controlplane.execute_plan(plan, mode="mock", artifact_path=artifact_path)
            self.assertEqual("PASS", result["verification"]["status"])
            self.assertEqual(0, result["process"]["exit_code"])
            serialized = artifact_path.read_text(encoding="utf-8")
            self.assertNotIn("Private task text", serialized)
            failed = controlplane.execute_plan(plan, mode="mock", artifact_path=Path(temp) / "failed.json", simulate_exit=9)
            self.assertEqual(9, failed["process"]["exit_code"])
            self.assertEqual("FAIL", failed["verification"]["status"])

    def test_mock_subprocess_timeout_is_bounded(self):
        result = controlplane._run_process(
            [sys.executable, str(controlplane.MOCK_CODEX), "--delay", "1"], ROOT, timeout_seconds=0.05,
        )
        self.assertTrue(result["timed_out"])

    def test_paths_with_spaces_are_passed_as_single_argv_values(self):
        with tempfile.TemporaryDirectory(prefix="research workspace ", dir=ROOT) as temp:
            plan = controlplane.build_plan(
                "Prepare the Small-Cap Crypto Daily newsletter", "safe", temp,
            )
            cd_index = plan["_argv"].index("--cd")
            self.assertEqual(temp, plan["_argv"][cd_index + 1])
            with tempfile.TemporaryDirectory(dir=ROOT) as output_dir:
                result = controlplane.execute_plan(plan, mode="mock", artifact_path=Path(output_dir) / "result.json")
                self.assertEqual("PASS", result["verification"]["status"])

    def test_offline_acceptance_runs_discovery_routing_mock_and_artifact_readback(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            artifact_path = Path(temp) / "acceptance.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = controlplane.main(["accept", "--artifact", str(artifact_path)])
            report = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("PASS", report["acceptance"]["status"])
            self.assertTrue(all(report["acceptance"]["checks"].values()))
            self.assertTrue(report["acceptance"]["checks"]["nested_policy_discovered"])
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual("MOCKED_OFFLINE", artifact["mode"])
            self.assertEqual("PASS", artifact["acceptance"]["status"])
            self.assertEqual(13, artifact["newsletter"]["section_count"])
            self.assertTrue(artifact_path.with_suffix(".md").is_file())

    def test_live_launch_is_never_the_default(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = controlplane.main([
                "launch", "--task", "Prepare the Small-Cap Crypto Daily newsletter",
                "--workspace", "examples/synthetic-workspace",
            ])
        report = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("check-only", report["mode"])

    def test_check_only_plan_does_not_require_codex_binary(self):
        plan = controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "safe")
        self.assertNotIn("codex_available", plan)
        self.assertNotIn("_binary", plan)
        with patch.object(controlplane, "resolve_codex_executable", return_value=None):
            self.assertIsNone(controlplane.resolve_codex_executable())

    def test_live_launch_selects_approval_syntax_from_installed_help(self):
        plan = controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "safe")
        help_text = "  -c, --config <key=value>\n      --json\n      --ephemeral\n      --sandbox <MODE>\n  -C, --cd <DIR>\n      --skip-git-repo-check\n"
        help_result = subprocess.CompletedProcess(["codex", "exec", "--help"], 0, help_text, "")
        process_result = {"exit_code": 0, "timed_out": False, "stdout_bytes": 30, "stderr_bytes": 0, "completion_event": True, "duration_seconds": 0.1}
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            with patch.object(controlplane, "resolve_codex_executable", return_value="codex-fixture"), \
                 patch.object(controlplane, "_probe_exec_help", return_value=help_result), \
                 patch.object(controlplane, "_run_process", return_value=process_result) as run_process:
                controlplane.execute_plan(plan, mode="live", artifact_path=Path(temp) / "live-plan.json")
            command = run_process.call_args.args[0]
        self.assertIn('--config', command)
        self.assertIn('approval_policy="on-request"', command)
        self.assertNotIn("--ask-for-approval", command)

    def test_live_launch_adapts_to_legacy_approval_flag_when_advertised(self):
        plan = controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "safe")
        help_text = "  --json\n      --ephemeral\n      --sandbox <MODE>\n      --ask-for-approval <POLICY>\n      --cd <DIR>\n      --skip-git-repo-check\n"
        help_result = subprocess.CompletedProcess(["codex", "exec", "--help"], 0, help_text, "")
        process_result = {"exit_code": 0, "timed_out": False, "stdout_bytes": 30, "stderr_bytes": 0, "completion_event": True, "duration_seconds": 0.1}
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            with patch.object(controlplane, "resolve_codex_executable", return_value="codex-fixture"), \
                 patch.object(controlplane, "_probe_exec_help", return_value=help_result), \
                 patch.object(controlplane, "_run_process", return_value=process_result) as run_process:
                controlplane.execute_plan(plan, mode="live", artifact_path=Path(temp) / "legacy-plan.json")
            command = run_process.call_args.args[0]
        self.assertIn("--ask-for-approval", command)
        self.assertIn("on-request", command)
        self.assertNotIn("--config", command)

    def test_live_launch_fails_closed_when_installed_help_lacks_required_flags(self):
        plan = controlplane.build_plan("Prepare the Small-Cap Crypto Daily newsletter", "safe")
        help_result = subprocess.CompletedProcess(["codex", "exec", "--help"], 0, "  --json\n", "")
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            with patch.object(controlplane, "resolve_codex_executable", return_value="codex-fixture"), \
                 patch.object(controlplane, "_probe_exec_help", return_value=help_result), \
                 patch.object(controlplane, "_run_process") as run_process:
                with self.assertRaisesRegex(controlplane.ControlPlaneError, "incompatible"):
                    controlplane.execute_plan(plan, mode="live", artifact_path=Path(temp) / "blocked.json")
                run_process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
