"""Validate and render a local crypto newsletter packet; performs no network I/O."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from adversarial_review import ReviewError, validate_report
from research_accountability import calculate as calculate_accountability, read_ledger


SECTIONS = (
    ("small-cap-crypto-daily", "SMALL-CAP CRYPTO DAILY"),
    ("market-in-90-seconds", "MARKET IN 90 SECONDS"),
    ("market-dashboard", "MARKET DASHBOARD"),
    ("whats-moving", "WHAT'S MOVING"),
    ("under-the-radar", "UNDER THE RADAR"),
    ("todays-deep-dive", "TODAY'S DEEP DIVE"),
    ("small-cap-leaderboard", "SMALL-CAP LEADERBOARD"),
    ("pick-of-the-day", "PICK OF THE DAY"),
    ("risk-desk", "RISK DESK"),
    ("previous-pick-accountability", "PREVIOUS PICK — ACCOUNTABILITY"),
    ("watchlist", "WATCHLIST"),
    ("bottom-line", "BOTTOM LINE"),
    ("sources-method-and-research-appendix", "SOURCES, METHOD AND RESEARCH APPENDIX"),
)
GATES = (
    "identity", "market_data", "liquidity", "supply", "security", "catalyst",
    "token_value_capture", "risk",
)
ROOT = Path(__file__).resolve().parents[1]
NUMERIC_TOKEN = re.compile(r"(?<![A-Za-z0-9_])(?:\$\s*)?\d+(?:\.\d+)?\s*(?:%|bps|x)?(?![A-Za-z0-9_])", re.I)


class PacketError(ValueError):
    pass


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value: object, field: str, errors: list[str]) -> None:
    if not _nonempty(value):
        errors.append(f"{field} must be an ISO 8601 timestamp")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError):
        errors.append(f"{field} must include a timezone (ISO 8601)")


def validate(packet: object, release: bool = False, *, reviewer_runtime_event_ids=()) -> list[str]:
    if not isinstance(packet, dict):
        return ["packet must be a JSON object"]
    errors: list[str] = []
    edition = packet.get("edition")
    if not isinstance(edition, dict):
        errors.append("edition must be an object")
        edition = {}
    try:
        date.fromisoformat(edition.get("date", ""))
    except (ValueError, TypeError):
        errors.append("edition.date must be YYYY-MM-DD")
    _timestamp(edition.get("cutoff_utc"), "edition.cutoff_utc", errors)
    if edition.get("status") not in ("draft", "approved"):
        errors.append("edition.status must be draft or approved")
    if not _nonempty(edition.get("regime")):
        errors.append("edition.regime must be non-empty")

    sources = packet.get("sources")
    source_ids: set[str] = set()
    if not isinstance(sources, list):
        errors.append("sources must be an array")
        sources = []
    for index, source in enumerate(sources):
        prefix = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        source_id = source.get("id")
        if not _nonempty(source_id):
            errors.append(f"{prefix}.id must be non-empty")
        elif source_id in source_ids:
            errors.append(f"duplicate source id: {source_id}")
        else:
            source_ids.add(source_id)
        if not _nonempty(source.get("label")):
            errors.append(f"{prefix}.label must be non-empty")
        url = source.get("url")
        parsed_url = urlparse(url if isinstance(url, str) else "")
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            errors.append(f"{prefix}.url must be an absolute HTTP(S) URL")
        if source.get("source_status") == "UNAVAILABLE":
            if source.get("accessed_utc") is not None:
                _timestamp(source.get("accessed_utc"), f"{prefix}.accessed_utc", errors)
            _timestamp(source.get("attempted_utc"), f"{prefix}.attempted_utc", errors)
        else:
            _timestamp(source.get("accessed_utc"), f"{prefix}.accessed_utc", errors)

    sections = packet.get("sections")
    if not isinstance(sections, dict):
        errors.append("sections must be an object")
        sections = {}
    expected = {slug for slug, _ in SECTIONS}
    for slug, _heading in SECTIONS:
        section = sections.get(slug)
        if not isinstance(section, dict):
            errors.append(f"sections.{slug} is required")
            continue
        if not _nonempty(section.get("content")):
            errors.append(f"sections.{slug}.content must be non-empty")
        refs = section.get("source_ids")
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            errors.append(f"sections.{slug}.source_ids must be an array of source ids")
        else:
            for ref in refs:
                if ref not in source_ids:
                    errors.append(f"sections.{slug} references unknown source id: {ref}")
    extras = set(sections) - expected
    if extras:
        errors.append("unknown section slug(s): " + ", ".join(sorted(extras)))

    pick = packet.get("pick")
    if not isinstance(pick, dict):
        errors.append("pick must be an object")
        pick = {}
    status = pick.get("status")
    if status == "PICK":
        if not _nonempty(pick.get("asset")) or not _nonempty(pick.get("ticker")):
            errors.append("PICK requires non-empty asset and ticker")
        gates = pick.get("gates")
        if not isinstance(gates, dict):
            errors.append("PICK requires all eight eligibility gates set to PASS")
            gates = {}
        for gate in GATES:
            if gates.get(gate) != "PASS":
                errors.append(f"PICK gate {gate} must be PASS")
        review = pick.get("review")
        if not isinstance(review, dict) or not isinstance(review.get("frozen_inputs"), dict) or not isinstance(review.get("challenge_report"), dict):
            errors.append("PICK requires frozen review inputs and a structured adversarial challenge report")
        else:
            try:
                checked = validate_report(review["frozen_inputs"], review["challenge_report"], runtime_event_ids=reviewer_runtime_event_ids)
                if checked["verdict"] != "PASS":
                    errors.append(f"PICK adversarial review must be PASS; got {checked['verdict']}")
            except ReviewError as exc:
                errors.append(f"PICK adversarial review invalid: {exc}")
    elif status != "NO_PICK":
        errors.append('pick.status must be "PICK" or "NO_PICK"')

    if packet.get("editorial_approval") not in (True, False):
        errors.append("editorial_approval must be a boolean")
    if release:
        if edition.get("status") != "approved":
            errors.append("release requires edition.status = approved")
        if packet.get("editorial_approval") is not True:
            errors.append("release requires editorial_approval = true")
    return errors


def load_packet(path: Path) -> dict:
    try:
        _check_workspace_path(path)
        with path.open("r", encoding="utf-8") as stream:
            packet = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise PacketError(f"cannot read packet: {exc}") from exc
    errors = validate(packet)
    if errors:
        raise PacketError("\n".join(errors))
    return packet


def _check_workspace_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise PacketError("input and output paths must stay inside the project directory") from exc
    return resolved


def render(packet: dict, release: bool = False) -> str:
    errors = validate(packet, release=release)
    if errors:
        raise PacketError("\n".join(errors))
    edition = packet["edition"]
    mode = "EDITION" if release else "DRAFT PREVIEW"
    lines = [f"# {mode} — {edition['date']}", ""]
    for slug, heading in SECTIONS:
        section = packet["sections"][slug]
        lines.extend((f"## {heading}", "", section["content"].strip(), ""))
        refs = section["source_ids"]
        if refs:
            citation = " · ".join(
                f"[{source['label']}]({source['url']})"
                for source in packet["sources"] if source["id"] in refs
            )
            lines.extend((f"Sources: {citation}", ""))
    lines.extend((f"Cutoff: {edition['cutoff_utc']}", f"Regime: {edition['regime']}", ""))
    return "\n".join(lines)


def assemble(manifest_path: Path) -> dict:
    """Assemble a v1 packet from persisted, project-local research artifacts."""
    manifest_path = _check_workspace_path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PacketError(f"cannot read assembly manifest: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("artifacts"), dict):
        raise PacketError("manifest.artifacts must be an object")
    artifacts: dict[str, object] = {}
    paths: dict[str, str] = {}

    def read_artifact(name: str, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise PacketError(f"manifest artifact {name} must be a project-relative JSON path")
        path = _check_workspace_path(manifest_path.parent / value)
        try:
            if name == "accountability" and path.suffix.lower() == ".jsonl":
                ledger = read_ledger(path)
                result = calculate_accountability(ledger, manifest.get("edition", {}).get("cutoff_utc"))
            else:
                result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PacketError(f"cannot read artifact {name}: {exc}") from exc
        paths[name] = path.relative_to(ROOT).as_posix()
        artifacts[name] = result
        return result

    spec = manifest["artifacts"]
    required = ("market", "screening", "committee", "watchlist", "accountability", "methodology")
    for name in required:
        if name not in spec:
            raise PacketError(f"manifest.artifacts.{name} is required")
        read_artifact(name, spec[name])
    desk_paths = spec.get("desks")
    if not isinstance(desk_paths, list) or len(desk_paths) != 9:
        raise PacketError("manifest.artifacts.desks must contain nine persisted desk report paths")
    desks = [read_artifact(f"desk-{i + 1}", path) for i, path in enumerate(desk_paths)]
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise PacketError("manifest.sources must be an array of source records")
    source_ids = [s.get("id") for s in sources if isinstance(s, dict)]
    if len(source_ids) != len(sources) or len(source_ids) != len(set(source_ids)):
        raise PacketError("manifest.sources must contain unique source records")
    known_source_ids = set(source_ids)
    artifact_source_ids: dict[str, set[str]] = {name: set() for name in artifacts}
    for source in sources:
        keys = source.get("artifact_keys", [])
        if keys and (not isinstance(keys, list) or any(key not in artifact_source_ids for key in keys)):
            raise PacketError(f"source {source['id']} has invalid artifact_keys")
        for key in keys:
            artifact_source_ids[key].add(source["id"])

    for artifact_name, payload in artifacts.items():
        def collect_for_artifact(value: object) -> None:
            if isinstance(value, dict):
                ref = value.get("source_id")
                if ref in known_source_ids:
                    artifact_source_ids[artifact_name].add(ref)
                for child in value.values(): collect_for_artifact(child)
            elif isinstance(value, list):
                for child in value: collect_for_artifact(child)
        collect_for_artifact(payload)

    def excerpt(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)

    def accountability_text(report: object) -> str:
        if not isinstance(report, dict) or not isinstance(report.get("records"), list):
            return excerpt(report)
        lines = ["Historical directional forecast accountability (price change only; no realizable profit implied).", ""]
        if not report["records"]:
            lines.append("No immutable historical publication records are available.")
        for item in report["records"]:
            identity = item.get("identity", {})
            label = identity.get("symbol") or identity.get("asset_id") or item["record_id"]
            lines.append(f"- **{label}** ({item['kind']}; {item['direction']}): {item['outcome']}; reference {item['reference_price']} at {item['reference_venue']}; published {item['published_at']}; expires {item['expires_at']}.")
            measured = [f"{period}: {data['return_pct']}%" for period, data in item.get("performance", {}).items() if data.get("status") == "OBSERVED"]
            missing = [period for period, data in item.get("performance", {}).items() if data.get("status") == "INSUFFICIENT_DATA"]
            lines.append(f"  Thesis: {item['thesis']}")
            lines.append("  Performance: " + (", ".join(measured) if measured else "no supported horizon observations") + ("; missing: " + ", ".join(missing) if missing else "") + ".")
            lines.append(f"  Excursions: {item['excursions']['status']} (MFE {item['excursions']['max_favorable_pct']}; MAE {item['excursions']['max_adverse_pct']}).")
        lines.extend(("", "Hit rates below disclose observed denominator / publication cohort; missing prices are excluded.", ""))
        for horizon, stats in report.get("statistics", {}).items():
            hit = stats.get("directional_hit_rate")
            hit_text = "insufficient observations" if hit is None else f"{hit:.1%} ({stats['observed_count']}/{stats['cohort_count']}; coverage {stats['coverage']:.1%})"
            lines.append(f"- {horizon} directional hit rate: {hit_text}.")
        return "\n".join(lines)

    committee = artifacts["committee"]
    committee_status = committee.get("status") if isinstance(committee, dict) else None
    committee_pick_unrepresentable = committee_status == "PICK"
    if committee_status not in ("PICK", "NO_PICK"):
        raise PacketError("committee artifact status must be PICK or NO_PICK")
    descriptions = {
        "small-cap-crypto-daily": "Daily edition assembled from the persisted artifacts listed below. Commentary remains subject to editorial review.",
        "market-in-90-seconds": excerpt(artifacts["market"]),
        "market-dashboard": excerpt(artifacts["market"]),
        "whats-moving": excerpt(artifacts["market"]),
        "under-the-radar": excerpt(artifacts["market"]),
        "todays-deep-dive": "Deep-dive evidence from the nine research desks:\n\n" + "\n\n".join(excerpt(d) for d in desks),
        "small-cap-leaderboard": excerpt(artifacts["screening"]),
        "pick-of-the-day": ("NO PICK — the committee recorded a candidate, but this artifact lacks packet-level frozen reviewer evidence required to publish it as a pick. See the decision record and evidence gap in the appendix." if committee_pick_unrepresentable else "NO PICK — the persisted investment committee decision is NO_PICK. See its decision records and explicit blockers in the appendix."),
        "risk-desk": excerpt([d for d in desks if isinstance(d, dict) and d.get("desk_id") == "risk"]),
        "previous-pick-accountability": accountability_text(artifacts["accountability"]),
        "watchlist": excerpt(artifacts["watchlist"]),
        "bottom-line": "NO PICK. Review the persisted market, screening, committee, and watchlist evidence before drawing a directional conclusion.",
        "sources-method-and-research-appendix": "Persisted artifact index:\n\n" + excerpt(paths) + "\n\nMethodology:\n\n" + excerpt(artifacts["methodology"]) + "\n\nCommittee decision:\n\n" + excerpt(committee),
    }
    section_artifacts = {
        "small-cap-crypto-daily": ("market", "screening", "committee"),
        "market-in-90-seconds": ("market",), "market-dashboard": ("market",),
        "whats-moving": ("market",), "under-the-radar": ("market", "desk-7"),
        "todays-deep-dive": tuple(f"desk-{i}" for i in range(1, 10)),
        "small-cap-leaderboard": ("screening",), "pick-of-the-day": ("committee",),
        "risk-desk": ("desk-8",), "previous-pick-accountability": ("accountability",),
        "watchlist": ("watchlist",), "bottom-line": ("market", "committee", "watchlist"),
        "sources-method-and-research-appendix": tuple(artifacts),
    }
    packet = {
        "edition": manifest.get("edition"), "sources": sources,
        "sections": {slug: {"content": descriptions[slug], "source_ids": (source_ids[:] if slug == "sources-method-and-research-appendix" else sorted(set().union(*(artifact_source_ids[name] for name in section_artifacts[slug]))))}
                     for slug, _ in SECTIONS},
        "pick": {"status": "NO_PICK"}, "editorial_approval": False,
        "assembly": {"manifest": manifest_path.relative_to(ROOT).as_posix(), "artifacts": paths},
    }
    errors = validate(packet)
    if errors:
        raise PacketError("assembled packet is invalid:\n" + "\n".join(errors))
    return packet


def fact_check(packet: object, manifest_path: Path) -> list[str]:
    """Check editor-registered numerical claims against exact persisted JSON values."""
    errors = validate(packet)
    if errors:
        return ["packet invalid: " + item for item in errors]
    checklist = packet.get("editorial_checklist") if isinstance(packet, dict) else None
    required_checks = (
        "opening_summary", "market_sector_context", "watchlist_opportunities",
        "entry_confirmation_and_invalidation", "risk_discussion", "traceable_citations",
        "missing_stale_contradictory_evidence",
    )
    if not isinstance(checklist, dict):
        errors.append("editorial_checklist is required before fact-check")
    else:
        for key in required_checks:
            if checklist.get(key) is not True:
                errors.append(f"editorial_checklist.{key} must be true")
    try:
        assembled = assemble(manifest_path)
    except PacketError as exc:
        return [f"evidence manifest invalid: {exc}"]
    values: set[str] = set()
    for relative in assembled["assembly"]["artifacts"].values():
        payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        def collect(item: object) -> None:
            if isinstance(item, bool) or item is None:
                return
            if isinstance(item, (int, float)):
                values.add(str(item))
                values.add(f"{item:g}")
            elif isinstance(item, dict):
                for child in item.values(): collect(child)
            elif isinstance(item, list):
                for child in item: collect(child)
        collect(payload)
    claims = packet.get("editorial_claims", []) if isinstance(packet, dict) else []
    if not isinstance(claims, list):
        return ["editorial_claims must be an array"]
    registered: dict[str, list[dict]] = {}
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not all(_nonempty(claim.get(k)) for k in ("section", "text", "value", "artifact", "json_pointer")):
            errors.append(f"editorial_claims[{index}] requires section, text, value, artifact, and json_pointer")
            continue
        section = claim["section"]
        if section not in packet["sections"]:
            errors.append(f"editorial_claims[{index}].section is unknown")
        elif claim["text"] not in packet["sections"][section]["content"]:
            errors.append(f"editorial_claims[{index}].text must appear in its section")
        if claim["value"] not in claim["text"]:
            errors.append(f"editorial_claims[{index}].value must appear in its claim text")
        if not isinstance(claim.get("source_ids"), list) or not claim["source_ids"] or any(ref not in {s["id"] for s in packet["sources"]} for ref in claim.get("source_ids", [])):
            errors.append(f"editorial_claims[{index}] must cite known source_ids")
        artifact_path = assembled["assembly"]["artifacts"].get(claim["artifact"])
        if artifact_path is None:
            errors.append(f"editorial_claims[{index}] references unknown artifact: {claim['artifact']}")
            continue
        try:
            target = json.loads((ROOT / artifact_path).read_text(encoding="utf-8"))
            for part in claim["json_pointer"].lstrip("/").split("/"):
                target = target[int(part)] if isinstance(target, list) else target[part.replace("~1", "/").replace("~0", "~")]
            actual = str(target)
            if actual != claim["value"]:
                errors.append(f"editorial claim value mismatch at {claim['artifact']}#{claim['json_pointer']}: expected {actual}")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, OSError):
            errors.append(f"editorial claim reference does not resolve: {claim['artifact']}#{claim['json_pointer']}")
        registered.setdefault(section, []).append(claim)
    for slug, section in packet["sections"].items():
        numbers = {re.sub(r"[$,\s]|%|bps|x", "", token.strip(), flags=re.I) for token in NUMERIC_TOKEN.findall(section["content"])}
        claims_for_section = registered.get(slug, [])
        for number in numbers:
            if number not in values:
                errors.append(f"unsupported numerical claim in sections.{slug}: {number}")
            if not any(claim["value"] == number and number in claim["text"] for claim in claims_for_section):
                errors.append(f"unregistered numerical claim in sections.{slug}: {number}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    assemble_parser = subparsers.add_parser("assemble", help="assemble a v1 packet from persisted research artifacts")
    assemble_parser.add_argument("manifest", type=Path)
    assemble_parser.add_argument("--output", type=Path, required=True)
    fact_parser = subparsers.add_parser("fact-check", help="reconcile material numerical claims with persisted artifacts")
    fact_parser.add_argument("packet", type=Path)
    fact_parser.add_argument("--manifest", type=Path, required=True)
    for command in ("check", "render"):
        sub = subparsers.add_parser(command)
        sub.add_argument("packet", type=Path)
        if command == "render":
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--release", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "assemble":
            packet = assemble(args.manifest)
            output = _check_workspace_path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"PASS: assembled v1 packet from persisted artifacts to {output.relative_to(ROOT)}")
            return 0
        if args.command == "fact-check":
            packet_path = _check_workspace_path(args.packet)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            errors = fact_check(packet, args.manifest)
            if errors:
                raise PacketError("\n".join(errors))
            print("PASS: registered numerical claims resolve to persisted evidence and citations")
            return 0
        packet = load_packet(args.packet)
        if args.command == "check":
            print("PASS: packet structure and pick gates are valid")
            return 0
        content = render(packet, release=args.release)
        output = _check_workspace_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"PASS: wrote local {'release' if args.release else 'draft preview'} to {output.relative_to(ROOT)}")
        return 0
    except (PacketError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
