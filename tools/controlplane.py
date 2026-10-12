"""Offline-first project control surface for the Small-Cap Crypto Daily workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CONTROL_FILE = ROOT / ".codex" / "control-plane.json"
SOURCE_POLICY_FILE = ROOT / ".codex" / "source-policy.json"
ROUTING_CASES_FILE = ROOT / "examples" / "routing-cases.json"
MOCK_CODEX = ROOT / "tests" / "fixtures" / "mock_codex.py"
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SAFE_SANDBOX = "read-only"
SAFE_APPROVAL = "on-request"
ALLOWED_SANDBOXES = {"read-only", "workspace-write"}
SAFE_SOURCE_OPERATIONS = {"read", "fetch", "search", "capabilities", "query-read"}


class ControlPlaneError(ValueError):
    """A safe-to-report validation or execution failure."""


def _inside_project(path: Path, *, must_exist: bool = False) -> Path:
    resolved = path.resolve(strict=must_exist)
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ControlPlaneError("path must stay inside the project directory") from exc
    return resolved


def _project_path(path: str | Path) -> Path:
    value = Path(path)
    if not value.is_absolute():
        value = ROOT / value
    return _inside_project(value)


def _read_json(path: Path, label: str) -> object:
    try:
        _inside_project(path, must_exist=True)
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ControlPlaneError) as exc:
        # Never echo file contents or parser snippets; a config may contain sensitive strings.
        reason = "invalid JSON" if isinstance(exc, json.JSONDecodeError) else "unreadable or outside project"
        raise ControlPlaneError(f"{label}: {reason}") from exc


def load_config(path: Path = CONTROL_FILE) -> dict:
    raw = _read_json(path, "control-plane config")
    errors = validate_config(raw)
    if errors:
        raise ControlPlaneError("control-plane config invalid: " + "; ".join(errors))
    return raw


def validate_config(raw: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["must be an object"]
    if raw.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if set(raw) != {"schema_version", "skill_roots", "profiles", "routes"}:
        errors.append("top-level fields must be schema_version, skill_roots, profiles, routes")
    roots = raw.get("skill_roots")
    if not isinstance(roots, list) or not roots or any(r not in {"project", "user", "codex_home"} for r in roots):
        errors.append("skill_roots must list project, user, and/or codex_home")
    elif len(set(roots)) != len(roots):
        errors.append("skill_roots contains duplicates")
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        errors.append("profiles must be a non-empty object")
    else:
        for profile_name, profile in profiles.items():
            if not isinstance(profile_name, str) or not NAME_PATTERN.fullmatch(profile_name):
                errors.append("profile names must be lowercase identifiers")
                continue
            if not isinstance(profile, dict) or set(profile) != {"sandbox", "approval", "timeout_seconds"}:
                errors.append(f"profile {profile_name} must define sandbox, approval, timeout_seconds")
                continue
            if profile.get("sandbox") not in ALLOWED_SANDBOXES:
                errors.append(f"profile {profile_name} requests unsupported or elevated sandbox")
            if profile.get("approval") != SAFE_APPROVAL:
                errors.append(f"profile {profile_name} requests unsupported approval policy")
            timeout = profile.get("timeout_seconds")
            if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 900:
                errors.append(f"profile {profile_name} timeout_seconds must be 1..900")
    routes = raw.get("routes")
    if not isinstance(routes, list):
        errors.append("routes must be an array")
    else:
        route_ids: set[str] = set()
        for index, route in enumerate(routes):
            if not isinstance(route, dict) or set(route) != {"id", "match_any", "skill", "reason"}:
                errors.append(f"routes[{index}] must define id, match_any, skill, reason")
                continue
            route_id = route.get("id")
            if not isinstance(route_id, str) or not NAME_PATTERN.fullmatch(route_id):
                errors.append(f"routes[{index}].id must be a lowercase identifier")
            elif route_id in route_ids:
                errors.append(f"duplicate route id: {route_id}")
            else:
                route_ids.add(route_id)
            phrases = route.get("match_any")
            if not isinstance(phrases, list) or not phrases or any(not isinstance(p, str) or not p.strip() for p in phrases):
                errors.append(f"routes[{index}].match_any must contain non-empty phrases")
            if not isinstance(route.get("skill"), str) or not NAME_PATTERN.fullmatch(route["skill"]):
                errors.append(f"routes[{index}].skill must be a skill name")
            if not isinstance(route.get("reason"), str) or not route["reason"].strip():
                errors.append(f"routes[{index}].reason must be non-empty")
    return errors


def validate_source_policy(raw: object) -> list[str]:
    if not isinstance(raw, dict):
        return ["must be an object"]
    errors: list[str] = []
    if set(raw) != {"schema_version", "default_decision", "sources", "paid_operations", "external_publication"}:
        errors.append("source policy has unexpected or missing fields")
    if raw.get("schema_version") != 1 or raw.get("default_decision") != "DENY":
        errors.append("schema_version must be 1 and default_decision must be DENY")
    if not isinstance(raw.get("paid_operations"), bool):
        errors.append("paid_operations must be boolean")
    if raw.get("external_publication") is not False:
        errors.append("external publication is unsupported and must remain false")
    sources = raw.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be an array")
        return errors
    ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or set(source) != {
            "id", "enabled", "domains", "operations", "max_cost_per_operation_usd"
        }:
            errors.append(f"sources[{index}] has unexpected or missing fields")
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not NAME_PATTERN.fullmatch(source_id):
            errors.append(f"sources[{index}].id must be a lowercase identifier")
        elif source_id in ids:
            errors.append(f"duplicate source id: {source_id}")
        else:
            ids.add(source_id)
        if not isinstance(source.get("enabled"), bool):
            errors.append(f"sources[{index}].enabled must be boolean")
        domains = source.get("domains")
        if not isinstance(domains, list) or any(
            not isinstance(domain, str) or not domain.strip() or "/" in domain or "*" in domain
            for domain in domains
        ):
            errors.append(f"sources[{index}].domains must be exact hostnames, without paths or wildcards")
        operations = source.get("operations")
        if not isinstance(operations, list) or any(not isinstance(op, str) or op not in SAFE_SOURCE_OPERATIONS for op in operations):
            errors.append(f"sources[{index}].operations contain unsupported or non-read-only operations")
        amount = source.get("max_cost_per_operation_usd")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            errors.append(f"sources[{index}].max_cost_per_operation_usd must be a non-negative number")
    return errors


def load_source_policy(path: Path = SOURCE_POLICY_FILE) -> dict:
    raw = _read_json(path, "source policy")
    errors = validate_source_policy(raw)
    if errors:
        raise ControlPlaneError("source policy invalid: " + "; ".join(errors))
    return raw


def authorize_source(policy: dict, source_id: str, operation: str, url: str, estimated_cost: float = 0) -> dict:
    if isinstance(estimated_cost, bool) or not math.isfinite(estimated_cost) or estimated_cost < 0:
        raise ControlPlaneError("estimated cost must be a finite non-negative number")
    if operation not in SAFE_SOURCE_OPERATIONS:
        return {"status": "DENY", "reason": "operation is not supported by this control surface"}
    if estimated_cost > 0 and not policy["paid_operations"]:
        return {"status": "DENY", "reason": "paid operations are not explicitly enabled"}
    source = next((entry for entry in policy["sources"] if entry["id"] == source_id), None)
    if source is None:
        return {"status": "DENY", "reason": "source id is not configured"}
    if not source["enabled"]:
        return {"status": "DENY", "reason": "source is disabled"}
    if operation not in source["operations"]:
        return {"status": "DENY", "reason": "operation is not allowed for this source"}
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        return {"status": "DENY", "reason": "source URL must use HTTPS"}
    try:
        port = parsed.port
    except ValueError:
        return {"status": "DENY", "reason": "source URL contains an invalid port"}
    if port not in (None, 443):
        return {"status": "DENY", "reason": "non-standard URL ports are not allowed"}
    host = parsed.hostname.casefold().rstrip(".")
    allowed_hosts = {domain.casefold().rstrip(".") for domain in source["domains"]}
    if host not in allowed_hosts:
        return {"status": "DENY", "reason": "URL host is not explicitly allowlisted"}
    if estimated_cost > source["max_cost_per_operation_usd"]:
        return {"status": "DENY", "reason": "estimated cost exceeds the per-operation limit"}
    return {"status": "ALLOW", "reason": "source, operation, HTTPS host, and cost match the active allowlist"}


def _skill_roots(names: list[str]) -> list[tuple[str, Path]]:
    profile = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", str(profile / ".codex"))).expanduser()
    paths = {
        "project": ROOT / ".agents" / "skills",
        "user": profile / ".agents" / "skills",
        "codex_home": codex_home / "skills",
    }
    return [(name, paths[name]) for name in names]


def _parse_manifest(path: Path) -> tuple[str, str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ControlPlaneError("manifest unreadable") from exc
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ControlPlaneError("front matter missing")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise ControlPlaneError("front matter unterminated") from exc
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"name", "description"}:
            fields[key.strip()] = value.strip().strip("\"'")
    name = fields.get("name", "")
    description = fields.get("description", "")
    if not NAME_PATTERN.fullmatch(name) or not description:
        raise ControlPlaneError("manifest name or description invalid")
    return name, description


def _safe_manifest_label(root_name: str, skill_name: str) -> str:
    if root_name == "project":
        return f".agents/skills/{skill_name}/SKILL.md"
    return f"<{root_name.upper()}>/skills/{skill_name}/SKILL.md"


def discover_skills(roots: list[tuple[str, Path]]) -> dict:
    skills: dict[str, list[dict]] = {}
    issues: list[dict] = []
    root_status: list[dict] = []
    for root_name, root_path in roots:
        available = root_path.is_dir()
        root_status.append({"root": root_name, "status": "PASS" if available else "UNVERIFIED"})
        if not available:
            continue
        try:
            children = sorted((child for child in root_path.iterdir() if child.is_dir()), key=lambda child: child.name.casefold())
        except OSError:
            issues.append({"root": root_name, "status": "UNVERIFIED", "reason": "skill root inaccessible"})
            continue
        for child in children:
            try:
                manifests = [item for item in child.iterdir() if item.is_file() and item.name.casefold() == "skill.md"]
            except OSError:
                issues.append({"root": root_name, "status": "UNVERIFIED", "reason": "skill directory inaccessible"})
                continue
            if len(manifests) != 1:
                if len(manifests) > 1:
                    issues.append({"root": root_name, "directory": child.name, "status": "FAIL", "reason": "multiple SKILL.md manifests"})
                continue
            try:
                name, _description = _parse_manifest(manifests[0])
            except ControlPlaneError as exc:
                issues.append({"root": root_name, "directory": child.name, "status": "FAIL", "reason": str(exc)})
                continue
            skills.setdefault(name, []).append({"root": root_name, "label": _safe_manifest_label(root_name, name)})
    duplicates = sorted(name for name, entries in skills.items() if len(entries) > 1)
    return {"skills": skills, "duplicates": duplicates, "issues": issues, "roots": root_status}


def route_task(task: str, config: dict, catalog: dict, override: str | None = None) -> dict:
    if not isinstance(task, str) or not task.strip() or len(task) > 6000:
        raise ControlPlaneError("task must contain 1..6000 characters")
    skills = catalog["skills"]
    if override is not None:
        if not NAME_PATTERN.fullmatch(override):
            raise ControlPlaneError("skill override must be an exact lowercase skill name")
        entries = skills.get(override, [])
        if len(entries) != 1:
            raise ControlPlaneError("skill override must resolve to exactly one discovered manifest")
        return {
            "status": "RECOMMEND", "skill": override, "route_id": "user-override",
            "reason": f"Explicit user override selected {override}.",
            "manifest": entries[0]["label"], "rejected_candidates": [],
        }
    text = task.casefold()
    explicit = re.search(r"\b(?:use|invoke|run)\s+(?:the\s+)?skill\s*[:=]?\s*([a-z0-9][a-z0-9-]{0,63})\b", text)
    if explicit:
        skill_name = explicit.group(1)
        entries = skills.get(skill_name, [])
        if len(entries) == 1:
            return {
                "status": "RECOMMEND", "skill": skill_name, "route_id": "explicit-skill-invocation",
                "reason": f"Explicit skill invocation selected {skill_name}.",
                "manifest": entries[0]["label"], "rejected_candidates": [],
            }
        return {
            "status": "ABSTAIN", "skill": None, "route_id": "explicit-skill-invocation",
            "reason": "explicit skill invocation does not resolve to exactly one discovered manifest",
            "rejected_candidates": [{"route_id": "explicit-skill-invocation", "skill": skill_name, "reason": "missing or ambiguous manifest"}],
        }
    matched = [route for route in config["routes"] if any(phrase.casefold() in text for phrase in route["match_any"])]
    unmatched = [
        {"route_id": route["id"], "skill": route["skill"], "reason": "none of this route's match phrases appeared"}
        for route in config["routes"] if route not in matched
    ]
    if not matched:
        return {"status": "ABSTAIN", "skill": None, "reason": "no configured route matched", "rejected_candidates": unmatched}
    if len(matched) > 1:
        return {
            "status": "ABSTAIN", "skill": None, "reason": "multiple routes matched; provide an explicit skill override",
            "matched_routes": [route["id"] for route in matched],
            "rejected_candidates": unmatched + [
                {"route_id": route["id"], "skill": route["skill"], "reason": "competing route; no automatic selection"}
                for route in matched
            ],
        }
    selected = matched[0]
    entries = skills.get(selected["skill"], [])
    if len(entries) != 1:
        reason = "mapped skill manifest missing" if not entries else "mapped skill name is ambiguous"
        return {
            "status": "ABSTAIN", "skill": None, "route_id": selected["id"], "reason": reason,
            "rejected_candidates": unmatched + [{"route_id": selected["id"], "skill": selected["skill"], "reason": reason}],
        }
    return {
        "status": "RECOMMEND", "skill": selected["skill"], "route_id": selected["id"],
        "reason": selected["reason"], "manifest": entries[0]["label"], "rejected_candidates": unmatched,
    }


def evaluate_routes(config: dict, catalog: dict, cases: list) -> dict:
    if not isinstance(cases, list) or not cases:
        raise ControlPlaneError("routing cases must be a non-empty array")
    rows: list[dict] = []
    for case in cases:
        if not isinstance(case, dict) or not {"id", "kind", "task", "expected_skill"}.issubset(case):
            raise ControlPlaneError("each routing case requires id, kind, task, expected_skill")
        result = route_task(case["task"], config, catalog)
        predicted = result["skill"] if result["status"] == "RECOMMEND" else None
        rows.append({"id": case["id"], "kind": case["kind"], "expected": case["expected_skill"], "predicted": predicted, "correct": predicted == case["expected_skill"]})
    true_positive = sum(row["predicted"] is not None and row["predicted"] == row["expected"] for row in rows)
    predicted_positive = sum(row["predicted"] is not None for row in rows)
    expected_positive = sum(row["expected"] is not None for row in rows)
    negative_rows = [row for row in rows if row["kind"] == "negative"]
    false_positive_negative = sum(row["predicted"] is not None for row in negative_rows)
    inappropriate = sum(
        row["predicted"] is not None and row["predicted"] != row["expected"]
        for row in rows
    )
    missed = sum(
        row["expected"] is not None and row["predicted"] != row["expected"]
        for row in rows
    )
    abstentions = sum(row["predicted"] is None for row in rows)

    def ratio(numerator: int, denominator: int) -> dict:
        return {"numerator": numerator, "denominator": denominator, "value": numerator / denominator if denominator else None}

    return {
        "cases": rows,
        "metrics": {
            "precision": ratio(true_positive, predicted_positive),
            "recall": ratio(true_positive, expected_positive),
            "inappropriate_invocation_rate": ratio(inappropriate, predicted_positive),
            "missed_invocation_rate": ratio(missed, expected_positive),
            "false_positive_rate": ratio(false_positive_negative, len(negative_rows)),
            "abstention_rate": ratio(abstentions, len(rows)),
        },
    }


def _instruction_chain(workspace: Path) -> list[str]:
    dirs = list(reversed([ROOT, *ROOT.parents]))
    nested = workspace.relative_to(ROOT)
    cursor = ROOT
    for part in nested.parts:
        if part == ".":
            continue
        cursor = cursor / part
        dirs.append(cursor)
    found: list[str] = []
    for directory in dirs:
        for name in ("AGENTS.md", "AGENTS.override.md"):
            path = directory / name
            if path.is_file():
                try:
                    found.append(path.relative_to(ROOT).as_posix())
                except ValueError:
                    ancestor = path.parent.name or "<drive-root>"
                    found.append("../" + ancestor + "/" + name)
    return found


def _check(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def doctor(workspace: Path | str = ROOT) -> dict:
    try:
        resolved_workspace = _project_path(workspace)
        if not resolved_workspace.is_dir():
            raise ControlPlaneError("workspace must be an existing directory")
        workspace_check = _check("PASS", resolved_workspace.relative_to(ROOT).as_posix() or ".")
    except ControlPlaneError:
        resolved_workspace = ROOT
        workspace_check = _check("FAIL", "workspace missing or outside project")

    config: dict | None = None
    try:
        config = load_config()
        config_check = _check("PASS", "project control config parsed; values withheld")
    except ControlPlaneError:
        config_check = _check("FAIL", "project control config invalid or inaccessible")

    try:
        source_policy = load_source_policy()
        enabled_sources = sum(1 for source in source_policy["sources"] if source["enabled"])
        source_check = _check("PASS", f"deny-by-default policy parsed; {enabled_sources} source(s) enabled")
    except ControlPlaneError:
        source_check = _check("FAIL", "source policy invalid or inaccessible")

    codex = shutil.which("codex")
    if not codex:
        codex_check = _check("FAIL", "codex executable not found on PATH")
    else:
        try:
            result = subprocess.run([codex, "--version"], capture_output=True, text=True, timeout=5, check=False, shell=False)
            version_match = re.search(r"codex-cli\s+([0-9][\w.+-]*)", result.stdout + result.stderr, re.IGNORECASE)
            if result.returncode == 0 and version_match:
                codex_check = _check("PASS", f"codex-cli {version_match.group(1)} at PATH ({Path(codex).name})")
            else:
                codex_check = _check("FAIL", "codex version probe failed")
        except (OSError, subprocess.TimeoutExpired):
            codex_check = _check("FAIL", "codex version probe failed or timed out")

    profile = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", str(profile / ".codex"))).expanduser()
    config_path = codex_home / "config.toml"
    if not config_path.exists():
        user_config_check = _check("UNVERIFIED", "selected Codex config.toml not present")
    else:
        try:
            tomllib.loads(config_path.read_text(encoding="utf-8"))
            user_config_check = _check("PASS", "selected Codex config.toml parsed; values withheld")
        except (OSError, tomllib.TOMLDecodeError):
            user_config_check = _check("FAIL", "selected Codex config.toml invalid or inaccessible")

    roots = _skill_roots(config["skill_roots"] if config else ["project"])
    catalog = discover_skills(roots)
    if catalog["duplicates"]:
        skills_check = _check("FAIL", "duplicate skill names: " + ", ".join(catalog["duplicates"]))
    elif catalog["issues"]:
        skills_check = _check("FAIL", "one or more skill manifests are invalid or inaccessible")
    elif config and any(len(catalog["skills"].get(route["skill"], [])) != 1 for route in config["routes"]):
        skills_check = _check("FAIL", "a configured route maps to a missing or ambiguous skill")
    else:
        skills_check = _check("PASS", f"{len(catalog['skills'])} unique skill name(s) discovered")

    chain = _instruction_chain(resolved_workspace)
    instructions_check = _check("PASS" if chain else "UNVERIFIED", f"{len(chain)} instruction file(s) in ancestor chain")
    checks = {
        "codex_cli": codex_check,
        "codex_user_config": user_config_check,
        "project_config": config_check,
        "source_policy": source_check,
        "workspace_boundary": workspace_check,
        "instruction_chain": instructions_check,
        "skill_catalog": skills_check,
        "model_session": _check("NOT_APPLICABLE", "doctor never starts a model session"),
        "paid_operations": _check("NOT_APPLICABLE", "doctor performs no paid operations"),
        "external_publication": _check("NOT_APPLICABLE", "no external publisher is configured"),
    }
    statuses = [item["status"] for item in checks.values()]
    overall = "FAIL" if "FAIL" in statuses else "UNVERIFIED" if "UNVERIFIED" in statuses else "PASS"
    return {
        "schema_version": 1,
        "overall": overall,
        "checks": checks,
        "instruction_files": chain,
        "skills": sorted(catalog["skills"]),
        "side_effects": "none; no model session started and no config written",
    }


def _validated_workspace(path: str | Path) -> Path:
    workspace = _project_path(path)
    if not workspace.is_dir():
        raise ControlPlaneError("workspace must be an existing project-contained directory")
    return workspace


def resolve_codex_executable() -> str | None:
    """Resolve Codex using the host platform's PATH/PATHEXT rules."""
    return shutil.which("codex")


def build_plan(task: str, profile_name: str, workspace: str | Path = ".", override: str | None = None, sandbox: str | None = None) -> dict:
    config = load_config()
    profile = config["profiles"].get(profile_name)
    if profile is None:
        raise ControlPlaneError("unknown profile")
    if sandbox is not None and sandbox != profile["sandbox"]:
        raise ControlPlaneError("requested sandbox differs from the profile; escalation is denied")
    if profile["sandbox"] not in ALLOWED_SANDBOXES or profile["approval"] != SAFE_APPROVAL:
        raise ControlPlaneError("profile does not meet the safe execution policy")
    resolved_workspace = _validated_workspace(workspace)
    catalog = discover_skills(_skill_roots(config["skill_roots"]))
    route = route_task(task, config, catalog, override)
    if route["status"] != "RECOMMEND":
        raise ControlPlaneError("skill routing abstained; provide an explicit valid --skill-override")
    prompt = f"Use the {route['skill']} project skill if available.\n\nTask:\n{task}"
    argv = [
        "exec", "--json", "--ephemeral", "--sandbox", profile["sandbox"],
        "--config", f'approval_policy="{profile["approval"]}"',
    ]
    # The installed help is checked immediately before live execution, and the
    # approval syntax is adapted there when this version exposes the legacy flag.
    argv.extend(["--cd", str(resolved_workspace), "--skip-git-repo-check", prompt])
    display_argv = [*argv[:-1], "<TASK_PROMPT_REDACTED>"]
    display_argv = [
        (resolved_workspace.relative_to(ROOT).as_posix() or ".") if arg == str(resolved_workspace) else arg
        for arg in display_argv
    ]
    return {
        "profile": profile_name,
        "workspace": resolved_workspace.relative_to(ROOT).as_posix() or ".",
        "timeout_seconds": profile["timeout_seconds"],
        "route": route,
        "argv_template": display_argv,
        "_argv": argv,
        "_workspace": resolved_workspace,
    }


def _probe_exec_help(codex: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [codex, "exec", "--help"], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=5, check=False, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControlPlaneError("installed codex exec help probe failed or timed out") from exc


def _supported_exec_flags(result: subprocess.CompletedProcess) -> set[str]:
    flags: set[str] = set()
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        if line[:1].isspace():
            flags.update(re.findall(r"(?<![\w])(?:--[a-z][a-z0-9-]*|-[A-Za-z])(?=,|\s|$)", line))
    return flags


def _run_process(command: list[str], cwd: Path, timeout_seconds: int) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_seconds,
            check=False, shell=False,
        )
        stdout = result.stdout
        stderr = result.stderr
        completion_event = any(
            isinstance(event, dict) and event.get("type") == "turn.completed"
            for line in stdout.splitlines()
            if _is_json(line) for event in [json.loads(line)]
        )
        return {
            "exit_code": result.returncode, "timed_out": False,
            "stdout_bytes": len(stdout.encode("utf-8")), "stderr_bytes": len(stderr.encode("utf-8")),
            "completion_event": completion_event, "duration_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "timed_out": True, "stdout_bytes": 0, "stderr_bytes": 0, "completion_event": False, "duration_seconds": round(time.monotonic() - started, 3)}
    except OSError:
        return {"exit_code": None, "timed_out": False, "stdout_bytes": 0, "stderr_bytes": 0, "completion_event": False, "duration_seconds": round(time.monotonic() - started, 3)}


def _is_json(value: str) -> bool:
    try:
        json.loads(value)
        return True
    except json.JSONDecodeError:
        return False


def _redact_argv(argv: list[str], prompt: str, mock: bool, workspace: Path) -> list[str]:
    redacted: list[str] = []
    for arg in argv:
        if arg == prompt:
            redacted.append("<TASK_PROMPT_REDACTED>")
        elif mock and arg == str(MOCK_CODEX):
            redacted.append("tests/fixtures/mock_codex.py")
        elif arg == str(workspace):
            redacted.append(workspace.relative_to(ROOT).as_posix() or ".")
        else:
            redacted.append(arg)
    return redacted


def _write_artifact(path: str | Path, artifact: dict) -> Path:
    output = _project_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def execute_plan(plan: dict, *, mode: str, artifact_path: str | Path, simulate_exit: int = 0, simulate_delay: float = 0) -> dict:
    prompt = plan["_argv"][-1]
    if mode == "mock":
        command = [sys.executable, str(MOCK_CODEX), "--exit-code", str(simulate_exit), "--delay", str(simulate_delay), *plan["_argv"]]
        binary_label = "python-mock"
    elif mode == "live":
        codex = resolve_codex_executable()
        if not codex:
            raise ControlPlaneError("codex executable not found")
        help_result = _probe_exec_help(codex)
        flags = _supported_exec_flags(help_result)
        required = {"--json", "--ephemeral", "--sandbox", "--skip-git-repo-check"}
        missing = sorted(required - flags)
        if not ({"--cd", "-C"} & flags):
            missing.append("--cd/-C")
        if not ({"--config", "-c"} & flags or "--ask-for-approval" in flags):
            missing.append("approval policy option (--config/-c or --ask-for-approval)")
        if help_result.returncode != 0 or missing:
            raise ControlPlaneError("installed codex exec is incompatible with this launch plan" + (f"; missing: {', '.join(missing)}" if missing else ""))
        argv = list(plan["_argv"])
        approval_index = argv.index("--sandbox") + 2
        if "--ask-for-approval" in flags:
            approval_value = argv[argv.index("--config") + 1].split("=", 1)[1].strip('"')
            del argv[argv.index("--config"):argv.index("--config") + 2]
            argv[approval_index:approval_index] = ["--ask-for-approval", approval_value]
        else:
            if "--config" not in flags:
                argv[argv.index("--config")] = "-c"
        cd_index = argv.index("--cd")
        if "--cd" not in flags:
            argv[cd_index] = "-C"
        command = [codex, *argv]
        binary_label = Path(codex).name
    else:
        raise ControlPlaneError("execution mode must be mock or live")
    process = _run_process(command, plan["_workspace"], plan["timeout_seconds"])
    process_ok = process["exit_code"] == 0 and not process["timed_out"] and process["completion_event"]
    artifact = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "MOCKED_OFFLINE" if mode == "mock" else "LIVE_CODEX",
        "profile": plan["profile"],
        "workspace": plan["workspace"],
        "skill_recommendation": {key: plan["route"][key] for key in ("status", "skill", "route_id", "reason", "manifest")},
        "command": [binary_label, *_redact_argv(command[1:], prompt, mode == "mock", plan["_workspace"])],
        "process": process,
        "verification": {
            "status": "PASS" if process_ok else "FAIL",
            "checks": {
                "subprocess_exit_zero": process["exit_code"] == 0,
                "not_timed_out": not process["timed_out"],
                "codex_completion_event": process["completion_event"],
            },
        },
    }
    output = _write_artifact(artifact_path, artifact)
    artifact["artifact_path"] = output.relative_to(ROOT).as_posix()
    return artifact


def _json_output(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    doc = commands.add_parser("doctor", help="read-only local diagnostics")
    doc.add_argument("--workspace", default=".")

    route = commands.add_parser("route", help="recommend a discovered project skill")
    route.add_argument("--task", required=True)
    route.add_argument("--skill-override")

    evaluation = commands.add_parser("eval-routing", help="evaluate fixed routing cases")
    evaluation.add_argument("--cases", default=str(ROUTING_CASES_FILE.relative_to(ROOT)))

    policy = commands.add_parser("policy-check", help="check one source operation against the deny-by-default allowlist")
    policy.add_argument("--source", required=True)
    policy.add_argument("--operation", required=True)
    policy.add_argument("--url", required=True)
    policy.add_argument("--estimated-cost-usd", type=float, default=0)

    launch = commands.add_parser("launch", help="validate by default; explicit live execution costs may apply")
    launch.add_argument("--task", required=True)
    launch.add_argument("--profile", default="safe")
    launch.add_argument("--workspace", default=".")
    launch.add_argument("--skill-override")
    launch.add_argument("--sandbox")
    run_mode = launch.add_mutually_exclusive_group()
    run_mode.add_argument("--execute", action="store_true", help="explicitly start a real Codex model session")
    run_mode.add_argument("--mock-process", action="store_true", help="run the local no-network Codex stand-in")
    launch.add_argument("--artifact", default=".codex/results/launch.json")

    accept = commands.add_parser("accept", help="offline end-to-end policy → route → mocked process → artifact")
    accept.add_argument("--task", default="Prepare the Small-Cap Crypto Daily newsletter research packet")
    accept.add_argument("--workspace", default="examples/synthetic-workspace")
    accept.add_argument("--artifact", default=".codex/results/offline-acceptance.json")

    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            report = doctor(args.workspace)
            _json_output(report)
            return 0 if report["overall"] != "FAIL" else 2
        if args.command == "route":
            config = load_config()
            result = route_task(args.task, config, discover_skills(_skill_roots(config["skill_roots"])), args.skill_override)
            _json_output(result)
            return 0 if result["status"] == "RECOMMEND" else 4
        if args.command == "eval-routing":
            config = load_config()
            cases = _read_json(_project_path(args.cases), "routing cases")
            report = evaluate_routes(config, discover_skills(_skill_roots(config["skill_roots"])), cases)
            _json_output(report)
            return 0 if all(row["correct"] for row in report["cases"]) else 5
        if args.command == "policy-check":
            result = authorize_source(load_source_policy(), args.source, args.operation, args.url, args.estimated_cost_usd)
            _json_output(result)
            return 0 if result["status"] == "ALLOW" else 3
        if args.command == "launch":
            plan = build_plan(args.task, args.profile, args.workspace, args.skill_override, args.sandbox)
            mode = "live" if args.execute else "mock" if args.mock_process else "check-only"
            if mode == "check-only":
                report = {key: value for key, value in plan.items() if not key.startswith("_")}
                report["codex_available"] = resolve_codex_executable() is not None
                report["mode"] = mode
                _json_output(report)
                return 0
            if mode == "live":
                run = execute_plan(plan, mode=mode, artifact_path=args.artifact)
            else:
                run = execute_plan(plan, mode=mode, artifact_path=args.artifact)
            _json_output(run)
            return 0 if run["verification"]["status"] == "PASS" else 6
        if args.command == "accept":
            config = load_config()
            health = doctor(args.workspace)
            source_policy = load_source_policy()
            workspace = _validated_workspace(args.workspace)
            route = route_task(args.task, config, discover_skills(_skill_roots(config["skill_roots"])))
            if route["status"] != "RECOMMEND":
                raise ControlPlaneError("offline acceptance routing abstained")
            plan = build_plan(args.task, "safe", workspace)
            result = execute_plan(plan, mode="mock", artifact_path=args.artifact)
            artifact = _read_json(_project_path(args.artifact), "acceptance artifact")
            verified = (
                health["overall"] != "FAIL"
                and source_policy["default_decision"] == "DENY"
                and artifact["mode"] == "MOCKED_OFFLINE"
                and artifact["verification"]["status"] == "PASS"
                and artifact["skill_recommendation"]["skill"] == route["skill"]
            )
            result["acceptance"] = {
                "status": "PASS" if verified else "FAIL",
                "checks": {
                    "doctor_has_no_failures": health["overall"] != "FAIL",
                    "nested_policy_discovered": "examples/synthetic-workspace/AGENTS.md" in health["instruction_files"],
                    "source_policy_default_deny": source_policy["default_decision"] == "DENY",
                    "route_recommendation_recorded": artifact["skill_recommendation"]["skill"] == route["skill"],
                    "mocked_process_completed": artifact["verification"]["status"] == "PASS",
                    "artifact_read_back": artifact["verification"]["status"] == "PASS",
                },
            }
            import newsletter

            packet = newsletter.load_packet(ROOT / "examples" / "no-pick.json")
            edition_text = newsletter.render(packet)
            edition_path = _project_path(args.artifact).with_suffix(".md")
            edition_path.parent.mkdir(parents=True, exist_ok=True)
            edition_path.write_text(edition_text, encoding="utf-8")
            readback = edition_path.read_text(encoding="utf-8")
            section_count = sum(1 for _slug, heading in newsletter.SECTIONS if f"## {heading}" in readback)
            newsletter_ok = section_count == 13 and "NO PICK" in readback
            artifact["newsletter"] = {
                "status": "PASS" if newsletter_ok else "FAIL",
                "edition": "offline no-pick fixture",
                "section_count": section_count,
                "artifact_path": edition_path.relative_to(ROOT).as_posix(),
            }
            result["newsletter"] = artifact["newsletter"]
            result["acceptance"]["checks"].update({
                "newsletter_packet_valid": True,
                "newsletter_rendered_and_read_back": newsletter_ok,
                "thirteen_sections_present": section_count == 13,
            })
            verified = verified and newsletter_ok
            result["acceptance"]["status"] = "PASS" if all(result["acceptance"]["checks"].values()) else "FAIL"
            artifact["acceptance"] = result["acceptance"]
            _write_artifact(args.artifact, artifact)
            _json_output(result)
            return 0 if verified else 7
    except (ControlPlaneError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
