"""Run a dated daily workflow through replay or explicitly authorized REST acquisition.

Replay is the offline default. Live REST uses fixed allowlisted routes and a strict
request cap. The controller never invokes Codex/MCP, trades, schedules, or publishes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import daily_committee  # noqa: E402
import newsletter  # noqa: E402
import research_desks  # noqa: E402
import research_sources  # noqa: E402
import small_cap_screen  # noqa: E402
import universe_builder  # noqa: E402


class OrchestrationError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _write_json(directory: Path, name: str, value: Any) -> dict[str, str]:
    data = _canonical(value)
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}


def _safe_path(path: Path, *, must_exist: bool) -> Path:
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(ROOT):
        raise OrchestrationError("fixture and output paths must stay inside the project directory")
    if must_exist and not resolved.is_file():
        raise OrchestrationError("replay fixture does not exist or is not a file")
    return resolved


def _read_fixture(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        fixture = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise OrchestrationError(f"cannot read replay fixture: {exc}") from exc
    if isinstance(fixture, list):
        fixture = {"observations": fixture}
    if not isinstance(fixture, dict):
        raise OrchestrationError("replay fixture must be a JSON object or observation array")
    allowed = {"observations", "history", "benchmark_history", "sources", "market"}
    if set(fixture) - allowed:
        raise OrchestrationError("replay fixture contains unsupported fields")
    observations = fixture.get("observations", [])
    if not isinstance(observations, list) or any(not isinstance(row, dict) for row in observations):
        raise OrchestrationError("fixture observations must be an array of objects")
    history = fixture.get("history", {})
    if not isinstance(history, dict) or any(not isinstance(k, str) or not isinstance(v, list) for k, v in history.items()):
        raise OrchestrationError("fixture history must map identity keys to bar arrays")
    return fixture, raw


def _build(run_date: str, fixture_path: Path | None, fixture: dict[str, Any], fixture_hash: str,
           directory: Path, *, mode: str, requests: list[dict[str, str]] | None = None,
           authorized: bool = False, opener=None) -> dict[str, Any]:
    adapter = research_sources.execute(mode, replay_path=fixture_path if mode == "replay" else None,
        requests=requests, authorized=authorized, opener=opener)
    if adapter["status"] == "BLOCKED":
        raise OrchestrationError("live-mcp is blocked until a supported native MCP invocation is verified")
    observations, provenance = [], []
    for item in adapter["observations"]:
        row = dict(item["observation"])
        observations.append(row)
        provenance.append(item["provenance"])
    observations.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
    source_attempts = adapter.get("source_attempts", [])
    live_verified = bool(
        mode == "live-rest" and adapter.get("mode") == "live-rest" and
        adapter.get("live_source_verified") is True and adapter.get("request_count", 0) > 0 and
        source_attempts and all(attempt.get("status") == "VALIDATED" and
                                attempt.get("request_count", 0) > 0 for attempt in source_attempts) and
        provenance and all(item.get("source_status") == "LIVE_RETRIEVED" and
                           item.get("validation") == "PASS" and
                           item.get("request_count", 0) > 0 and
                           item.get("live_source_verified") is True for item in provenance)
    )
    provider_ids = sorted({item.get("source_provider") for item in source_attempts + provenance
                           if isinstance(item.get("source_provider"), str)})
    source_records = []
    if mode == "replay":
        if provenance:
            accessed_utc = max(item["retrieved_at"] for item in provenance)
        else:
            accessed_utc = f"{run_date}T23:59:59Z"
        source_records.append({"id": "local-replay", "label": "Declared local replay fixture",
            "url": "https://example.invalid/local-replay", "accessed_utc": accessed_utc,
            "artifact_keys": ["market", "screening"], "readiness": "READY" if provenance else "DEGRADED",
            "evidence_quality": "SIMULATED_REPLAY", "live_source_verified": False,
            "source_status": "SIMULATED_REPLAY"})
    else:
        for provider in provider_ids:
            attempts = [item for item in source_attempts if item.get("source_provider") == provider]
            matching = [item for item in provenance if item.get("source_provider") == provider]
            provider_validated = bool(
                attempts and matching and all(item.get("status") == "VALIDATED" and
                                              item.get("request_count", 0) > 0 for item in attempts) and
                all(item.get("source_status") == "LIVE_RETRIEVED" and item.get("validation") == "PASS" and
                    item.get("request_count", 0) > 0 and item.get("live_source_verified") is True
                    for item in matching)
            )
            provider_partial = bool(matching and any(item.get("status") != "VALIDATED" for item in attempts))
            attempted_utc = max(item["attempted_at"] for item in attempts)
            accessed_utc = max(item["retrieved_at"] for item in matching) if matching else None
            host = next((item.get("endpoint_host") for item in attempts if item.get("endpoint_host")), "example.invalid")
            source_records.append({"id": provider, "label": provider, "url": f"https://{host}/",
                "accessed_utc": accessed_utc, "attempted_utc": attempted_utc,
                "attempted_operations": sorted(item["operation"] for item in attempts),
                "artifact_keys": ["market", "screening"],
                "readiness": "READY" if provider_validated else "PARTIAL" if provider_partial else "DEGRADED",
                "evidence_quality": "LIVE_RETRIEVAL_PROVIDER_CLAIMS" if provider_validated else
                    "PARTIAL_LIVE_RETRIEVAL" if provider_partial else "NO_USABLE_LIVE_OBSERVATIONS",
                "live_source_verified": provider_validated,
                "source_status": "VALIDATED" if provider_validated else "PARTIAL" if provider_partial else "UNAVAILABLE",
                "attempt_statuses": [item["status"] for item in attempts]})
    source_readiness = {"status": "PARTIAL" if observations and adapter["failures"] else "READY" if observations else "DEGRADED", "mode": mode,
        "successful_observations": len(observations), "failed_operations": len(adapter["failures"]),
        "live_source_verified": live_verified,
        "evidence_quality": "SIMULATED_REPLAY" if mode == "replay" else
            "LIVE_RETRIEVAL_PROVIDER_CLAIMS" if live_verified else
            "PARTIAL_LIVE_RETRIEVAL" if observations else "NO_USABLE_LIVE_OBSERVATIONS",
        "source_attempts": source_attempts,
        "failures": adapter["failures"]}
    for source in source_records:
        source["readiness"] = source_readiness["status"] if mode == "replay" else source["readiness"]
    sources = source_records
    market_rows = []
    for row in observations:
        raw = row.get("raw", row)
        if not isinstance(raw, dict):
            raise OrchestrationError("replayed observation raw value must be an object")
        market_rows.append(raw)
    if mode == "replay":
        market_snapshot_at = max((row.get("retrieved_at") for row in observations if row.get("retrieved_at")),
                                 default=f"{run_date}T23:59:59Z")
        market_regime = "Declared local replay; market characterization limited to supplied observations."
    elif observations:
        market_snapshot_at = max(row.get("retrieved_at") for row in observations if row.get("retrieved_at"))
        market_regime = "Live REST retrieval returned observations; market characterization is limited to provider claims and retrieval-time data."
    else:
        market_snapshot_at = None
        market_regime = "Live REST acquisition was attempted; no usable observations were returned."
    market = fixture.get("market", {"snapshot_at": market_snapshot_at, "regime": market_regime,
                                      "observation_count": len(observations), "source_readiness": source_readiness})
    universe = universe_builder.build_universe(market_rows, snapshot_date=run_date)
    histories = fixture.get("history", {})
    # Accept ticker, address, network:address, or derived asset id keys.
    mapped_history = {}
    for asset in universe["assets"]:
        network, address, ticker, aid = asset.get("network"), asset.get("contract_address"), asset.get("ticker"), asset["asset_id"]
        for key in (aid, ticker, f"{network}:{address}" if network and address else None, address):
            if key is not None and key in histories:
                mapped_history[aid] = histories[key]
                break
    screened = small_cap_screen.screen(universe, mapped_history,
                                       benchmark_history=fixture.get("benchmark_history", {}),
                                       generated_at=f"{run_date}T23:59:59+00:00")
    screened["source_readiness"] = source_readiness
    screened["evidence_quality"] = source_readiness["evidence_quality"]

    # All desk outputs are explicit incomplete records; no findings or evidence are fabricated.
    reports, desk_files = [], []
    for asset in universe["assets"]:
        label = asset.get("name") or asset.get("ticker") or asset["asset_id"]
        identity = {"candidate_id": asset["asset_id"], "name": label, "symbol": asset.get("ticker") or asset["asset_id"]}
        rows = [research_desks.incomplete_result(identity, desk) for desk in research_desks.DESK_IDS]
        report = research_desks.assemble_report(identity, rows)
        reports.append(report)
        desk_files.append([_write_json(directory, f"desks/{asset['asset_id']}-{row['desk_id']}.json", row) for row in report["desk_results"]])
    if not desk_files:
        identity = {"candidate_id": "daily-run", "name": "Daily run without candidates"}
        rows = [research_desks.incomplete_result(identity, desk) for desk in research_desks.DESK_IDS]
        desk_files.append([_write_json(directory, f"desks/no-candidate-{row['desk_id']}.json", row) for row in rows])

    # Candidate records are screening outputs with unknown thesis/review gates, so committee must abstain.
    candidates = []
    report_by_id = {report["candidate_identity"]["candidate_id"]: report for report in reports}
    for record in screened["candidate_evidence"]:
        asset = next(item for item in universe["assets"] if item["asset_id"] == record["asset_id"])
        identity = {"candidate_id": asset["asset_id"], "name": asset.get("name") or asset.get("ticker") or asset["asset_id"], "symbol": asset.get("ticker") or asset["asset_id"],
                    "chain": asset.get("network") or "", "asset_id": asset["asset_id"], "verified": False,
                    "market_cap_usd": asset.get("circulating_market_cap_usd"), "market_cap_tier": asset.get("market_cap_tier"), "evidence_refs": []}
        candidates.append({"candidate_identity": identity, "gates": {},
                           "market_data": {"observed_at": f"{run_date}T23:59:59Z", "evidence_refs": []},
                           "hypothesis": "WATCH", "research_desk_report": report_by_id[asset["asset_id"]],
                           "score_record": {"asset_id": asset["asset_id"], "opportunity_score": record["opportunity_score"],
                                            "score_components": record["score_components"], "evidence": record["evidence"]}})
    committee = None
    if candidates:
        committee = daily_committee.decide({"cutoff_utc": f"{run_date}T23:59:59Z", "candidates": candidates})
    else:
        committee = {"schema_version": 1, "cutoff_utc": f"{run_date}T23:59:59Z", "status": "NO_PICK",
                     "selected_candidate_id": None, "decision_records": [], "strongest_watch_candidates": [],
                     "authorization": "EDITORIAL_REPORTING_ONLY; NO TRADE EXECUTION",
                     "reason": "no candidates were produced by the validated universe and screen"}

    artifacts: dict[str, dict[str, str]] = {}
    artifacts["observations"] = _write_json(directory, "observations.json", observations)
    artifacts["source_provenance"] = _write_json(directory, "source-provenance.json", provenance)
    artifacts["source_snapshot"] = _write_json(directory, "source-snapshot.json", {
        "schema_version": 1, "mode": mode, "readiness": source_readiness,
        "observations_sha256": research_sources._digest(observations),
        "provenance_sha256": research_sources._digest(provenance),
        "request_count": adapter.get("request_count", 0), "live_source_verified": live_verified})
    artifacts["market"] = _write_json(directory, "market.json", market)
    artifacts["universe"] = _write_json(directory, "universe.json", universe)
    artifacts["screening"] = _write_json(directory, "screening.json", screened)
    artifacts["research"] = _write_json(directory, "research.json", {"status": "INCOMPLETE", "reports": reports})
    artifacts["committee"] = _write_json(directory, "committee.json", committee)
    artifacts["watchlist"] = _write_json(directory, "watchlist.json", {"as_of": run_date, "window_days": 7, "ranked_watchlist": []})
    artifacts["accountability"] = _write_json(directory, "accountability.json", {"status": "NOT_REPORTABLE", "reason": "no authorized publication ledger was supplied"})
    retrieval_occurred = adapter.get("request_count", 0) > 0
    if mode == "replay":
        acquisition_disclosure = "No live acquisition occurred; observations came from the declared local replay fixture."
    elif retrieval_occurred:
        acquisition_disclosure = (f"Live REST acquisition occurred ({adapter['request_count']} HTTP request(s)); "
                                  f"{len(observations)} observation(s) passed structural and identity validation. "
                                  "Provider claims were not independently corroborated.")
    else:
        acquisition_disclosure = "Live REST acquisition was requested, but no HTTP request reached a provider."
    artifacts["methodology"] = _write_json(directory, "methodology.json", {"mode": mode, "fixture_sha256": fixture_hash,
        "source_readiness": source_readiness, "acquisition_disclosure": acquisition_disclosure,
        "limitations": [acquisition_disclosure,
                        "All nine research desk results are incomplete because this slice does not execute native specialist research.",
                        "Codex models, MCP tools, publication, and trade execution were not used."]})
    artifacts["desks"] = []
    for files in desk_files:
        artifacts["desks"].extend(files)

    if mode == "replay":
        edition_regime = "Declared local replay; incomplete research; no current market claims."
    elif observations and adapter["failures"]:
        edition_regime = "Live REST retrieval was partial; provider claims are not independently corroborated; research remains incomplete."
    elif observations:
        edition_regime = "Live REST observations were retrieved and structurally validated; provider claims are not independently corroborated; research remains incomplete."
    else:
        edition_regime = "Live REST acquisition was attempted but returned no usable observations; research remains incomplete."
    manifest = {"edition": {"date": run_date, "cutoff_utc": f"{run_date}T23:59:59Z", "status": "draft",
                             "regime": edition_regime},
                "sources": sources,
                "artifacts": {key: (value["path"] if key != "desks" else [x["path"] for x in value]) for key, value in artifacts.items() if key != "observations" and key != "universe" and key != "research"}}
    # Existing newsletter.assemble requires the daily controller's v1 artifact keys.
    manifest["artifacts"].update({"market": "market.json", "screening": "screening.json", "committee": "committee.json",
                                  "watchlist": "watchlist.json", "accountability": "accountability.json", "methodology": "methodology.json",
                                  "desks": [x["path"] for x in artifacts["desks"]]})
    _write_json(directory, "manifest.json", manifest)
    packet = newsletter.assemble(directory / "manifest.json")
    packet["assembly"]["manifest"] = "manifest.json"
    packet["assembly"]["artifacts"] = {key: ((ROOT / Path(value)).resolve().relative_to(directory.resolve()).as_posix() if isinstance(value, str)
                                                else [(ROOT / Path(item)).resolve().relative_to(directory.resolve()).as_posix() for item in value])
                                         for key, value in packet["assembly"]["artifacts"].items()}
    staging_prefix = directory.relative_to(ROOT).as_posix()
    def normalize_staging_paths(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(staging_prefix, "run-artifacts")
        if isinstance(value, list):
            return [normalize_staging_paths(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize_staging_paths(item) for key, item in value.items()}
        return value
    packet = normalize_staging_paths(packet)
    packet_bytes = _canonical(packet)
    (directory / "packet.json").write_bytes(packet_bytes)
    edition = newsletter.render(packet)
    (directory / "edition.md").write_text(edition, encoding="utf-8", newline="\n")
    outputs = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(directory.rglob("*")) if p.is_file()}
    # Current slice never performs the desk research required for a complete edition.
    status = "DEGRADED_NO_PICK" if committee["status"] == "NO_PICK" else "DEGRADED"
    stages = [
        {"name": "RESEARCH_ACQUISITION", "status": "COMPLETED" if observations and not adapter["failures"] else "PARTIAL" if observations else "DEGRADED", "inputs": ["replay fixture" if mode == "replay" else "authorized REST requests"], "outputs": ["observations.json", "source-provenance.json", "source-snapshot.json"], "provenance": f"research_sources.execute mode={mode}; live verified={live_verified}"},
        {"name": "UNIVERSE_CONSTRUCTION", "status": "COMPLETED" if universe["assets"] else "DEGRADED", "inputs": ["observations.json"], "outputs": ["universe.json"], "provenance": "universe_builder.build_universe"},
        {"name": "SCREENING", "status": "COMPLETED", "inputs": ["universe.json", "fixture.history"], "outputs": ["screening.json"], "provenance": "small_cap_screen.screen"},
        {"name": "RESEARCH_ASSESSMENT", "status": "DEGRADED", "inputs": ["screening.json"], "outputs": ["research.json", "desks/"], "provenance": "research_desks.incomplete_result; native execution deferred"},
        {"name": "COMMITTEE_DECISION", "status": "COMPLETED", "inputs": ["research.json", "screening.json"], "outputs": ["committee.json"], "provenance": "daily_committee.decide; evidence gates and empty-funnel no-pick fallback"},
        {"name": "EDITORIAL_ASSEMBLY", "status": "COMPLETED", "inputs": ["manifest.json"], "outputs": ["packet.json", "edition.md"], "provenance": "newsletter.assemble; newsletter.validate; newsletter.render"},
    ]
    run_manifest = {"schema_version": 1, "run_date": run_date, "status": status,
                    "inputs": {"replay_fixture": fixture_path.relative_to(ROOT).as_posix() if fixture_path else None, "sha256": fixture_hash},
                    "fixture_sha256": fixture_hash,
                    "source_readiness": source_readiness,
                    "stages": stages, "artifacts": outputs, "external_effects": {"network": mode == "live-rest" and adapter.get("request_count", 0) > 0, "paid_models": False,
                    "native_agents": False, "mcp": False, "trades": False, "scheduling": False, "publication": False}}
    _write_json(directory, "run-manifest.json", run_manifest)
    return run_manifest


def run(run_date: str, fixture_path: Path | None, output_dir: Path, *, mode: str = "replay",
        requests: list[dict[str, str]] | None = None, authorized: bool = False, opener=None) -> dict[str, Any]:
    try:
        date.fromisoformat(run_date)
    except ValueError as exc:
        raise OrchestrationError("run date must be YYYY-MM-DD") from exc
    if mode == "replay":
        if fixture_path is None:
            raise OrchestrationError("replay mode requires --replay fixture")
        fixture_path = _safe_path(fixture_path, must_exist=True)
    elif fixture_path is not None:
        raise OrchestrationError("live modes do not accept a replay fixture")
    output_dir = _safe_path(output_dir, must_exist=False)
    if fixture_path and (fixture_path == output_dir or fixture_path.is_relative_to(output_dir)):
        raise OrchestrationError("output directory must not contain or replace the fixture")
    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise OrchestrationError("run artifact directory must exist and be empty, or not exist")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    fixture, raw = _read_fixture(fixture_path) if fixture_path else ({}, b"")
    fixture_hash = hashlib.sha256(raw).hexdigest() if fixture_path else None
    stage_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        result = _build(run_date, fixture_path, fixture, fixture_hash, stage_dir, mode=mode,
                        requests=requests, authorized=authorized, opener=opener)
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(stage_dir, output_dir)
        return result
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="declared run date (YYYY-MM-DD)")
    parser.add_argument("--mode", choices=("replay", "live-rest", "live-mcp"), default="replay")
    parser.add_argument("--replay", type=Path, help="local JSON replay fixture (default mode)")
    parser.add_argument("--authorize-live-rest", action="store_true", help="explicitly authorize bounded REST reads")
    parser.add_argument("--request", action="append", default=[], metavar="ROUTE=QUERY", help="fixed REST route/query; repeat within the four-operation cap")
    parser.add_argument("--output", required=True, type=Path, help="empty project-local run artifact directory")
    args = parser.parse_args(argv)
    try:
        requests = []
        for value in args.request:
            route, separator, query = value.partition("=")
            if not separator or not route or not query:
                raise OrchestrationError("--request must use ROUTE=QUERY")
            requests.append({"route": route, "query": query})
        if args.mode == "live-rest" and not args.authorize_live_rest:
            raise OrchestrationError("live-rest requires --authorize-live-rest")
        if args.mode != "live-rest" and (args.authorize_live_rest or requests):
            raise OrchestrationError("REST authorization and requests apply only to live-rest")
        result = run(args.date, args.replay, args.output, mode=args.mode, requests=requests or None,
                     authorized=args.authorize_live_rest)
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
