"""Build a deterministic, offline small-cap universe from provider observations.

Inputs are provider claims, not independently authenticated chain state. Records
are reconciled only by an explicit provider crosswalk or exact network/address.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

VERSION = "1.0.0"
TIERS = ((0, 10_000_000, "MICRO"), (10_000_000, 100_000_000, "SMALL"),
         (100_000_000, 1_000_000_000, "EXPANDED"))
DEFAULT_SUPPORTED_NETWORKS = {"ethereum", "solana", "base", "arbitrum", "optimism", "polygon", "bsc", "avalanche", "bitcoin"}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 and result < float("inf") else None


def _norm_network(value: Any) -> str | None:
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def _norm_address(network: str | None, address: Any) -> str | None:
    if not isinstance(address, str) or not address.strip():
        return None
    value = address.strip()
    # EVM addresses are case-insensitive. Other chain address encodings are not.
    return value.lower() if network in {"ethereum", "base", "arbitrum", "optimism", "polygon", "bsc", "avalanche"} else value


def _stable_id(identity: str) -> str:
    return "asset-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _identity_key(record: dict[str, Any]) -> tuple[str, str]:
    network = _norm_network(record.get("network", record.get("chain")))
    address = _norm_address(network, record.get("contract_address", record.get("address")))
    crosswalk = record.get("canonical_id")
    if isinstance(crosswalk, str) and crosswalk.strip():
        return ("crosswalk", crosswalk.strip())
    if network and address:
        return ("contract", f"{network}:{address}")
    provider, provider_id = record.get("provider"), record.get("provider_asset_id", record.get("asset_id"))
    if provider and provider_id:
        return ("provider", f"{str(provider).strip().lower()}:{str(provider_id).strip()}")
    # An unidentifiable observation gets its own stable identity; ticker is never a key.
    return ("unresolved", json.dumps(record, sort_keys=True, separators=(",", ":"), default=str))


def _tier(cap: float | None) -> str | None:
    if cap is None:
        return None
    if cap < 10_000_000:
        return "MICRO"
    if cap <= 100_000_000:
        return "SMALL"
    if cap < 1_000_000_000:
        return "EXPANDED"
    return None


def build_universe(records: list[dict[str, Any]], *, snapshot_date: str,
                   supported_networks: set[str] | None = None) -> dict[str, Any]:
    """Return a versioned snapshot; all ordering and aggregation are deterministic."""
    date.fromisoformat(snapshot_date)
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("records must be an array of objects")
    supported = {x.lower() for x in (supported_networks or DEFAULT_SUPPORTED_NETWORKS)}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        groups[_identity_key(row)].append(row)

    # Tickers are labels only. Flag every distinct identity sharing a ticker.
    ticker_ids: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for key, rows in groups.items():
        for row in rows:
            ticker = row.get("ticker", row.get("symbol"))
            if isinstance(ticker, str) and ticker.strip():
                ticker_ids[ticker.strip().upper()].add(key)

    assets = []
    for key, rows in groups.items():
        rows = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, separators=(",", ":"), default=str))
        networks = sorted({_norm_network(r.get("network", r.get("chain"))) for r in rows if _norm_network(r.get("network", r.get("chain")))})
        addresses = sorted({_norm_address(_norm_network(r.get("network", r.get("chain"))), r.get("contract_address", r.get("address"))) for r in rows if _norm_address(_norm_network(r.get("network", r.get("chain"))), r.get("contract_address", r.get("address")))})
        tickers = sorted({str(r.get("ticker", r.get("symbol"))).strip().upper() for r in rows if r.get("ticker", r.get("symbol"))})
        ticker = tickers[0] if tickers else None
        caps = sorted(x for r in rows if (x := _number(r.get("circulating_market_cap_usd", r.get("market_cap_usd", r.get("market_cap"))))) is not None)
        fdvs = sorted(x for r in rows if (x := _number(r.get("fully_diluted_valuation_usd", r.get("fdv_usd", r.get("fdv"))))) is not None)
        volumes = sorted(x for r in rows if (x := _number(r.get("volume_24h_usd", r.get("volume_usd", r.get("volume"))))) is not None)
        supplies = [_number(r.get("circulating_supply")) for r in rows]
        supply_known = [x for x in supplies if x is not None]
        venues = {}
        for row in rows:
            venue = row.get("venue")
            if isinstance(venue, dict) and venue.get("name"):
                venue_key = (str(venue.get("type", "unknown")).lower(), str(venue["name"]).strip())
                venues[venue_key] = {"type": venue_key[0], "name": venue_key[1], "network": _norm_network(venue.get("network"))}
            elif isinstance(row.get("exchange"), str) and row["exchange"].strip():
                venue_key = (str(row.get("venue_type", "unknown")).lower(), row["exchange"].strip())
                venues[venue_key] = {"type": venue_key[0], "name": venue_key[1], "network": _norm_network(row.get("venue_network"))}
        liquidity_rows = []
        for row in rows:
            val = _number(row.get("liquidity_usd", row.get("liquidity")))
            if val is not None:
                liquidity_rows.append((val, str(row.get("provider", "")), str(row.get("venue", {}).get("name", "")) if isinstance(row.get("venue"), dict) else ""))
        cap = caps[len(caps)//2] if caps else None
        fdv = fdvs[len(fdvs)//2] if fdvs else None
        # Provider rows can describe overlapping venues/time windows. Keep the
        # raw observations and use a conservative single observed value summary.
        volume = volumes[len(volumes)//2] if volumes else None
        liquidity = max((x[0] for x in liquidity_rows), default=None)
        flags = []
        exclusions = []
        if len(networks) > 1 or len(addresses) > 1:
            flags.append("identity_claim_disagreement")
            exclusions.append("conflicting network or contract claims within identity group")
        provider_asset_refs = [(str(r.get("provider", "")), str(r.get("provider_asset_id", r.get("asset_id", "")))) for r in rows]
        if len(provider_asset_refs) != len(set(provider_asset_refs)):
            flags.append("duplicate_provider_observation")
        if ticker and len(ticker_ids[ticker]) > 1:
            flags.append("ticker_collision")
        if any(r.get("wrapped") is True or r.get("is_wrapped") is True for r in rows):
            flags.append("wrapped_token")
        if any(r.get("stablecoin") is True or r.get("is_stablecoin") is True for r in rows):
            flags.append("stablecoin")
            exclusions.append("stablecoin excluded by universe policy")
        if any(r.get("active") is False or r.get("inactive") is True for r in rows):
            flags.append("inactive")
            exclusions.append("provider marks asset inactive")
        if not networks:
            flags.append("missing_network")
            exclusions.append("network is unknown")
        elif any(n not in supported for n in networks):
            flags.append("unsupported_network")
            exclusions.append("network is outside configured supported set")
        if networks and not addresses and key[0] != "crosswalk":
            flags.append("missing_contract")
            exclusions.append("contract address or explicit crosswalk is required")
        if not caps:
            flags.append("missing_market_cap")
            exclusions.append("circulating market cap is unknown; no tier assigned")
        if len(caps) > 1 and caps[-1] > 0 and (caps[-1] - caps[0]) / caps[-1] > 0.20:
            flags.append("market_cap_source_disagreement")
        if not supply_known:
            flags.append("missing_circulating_supply")
        if len(supply_known) and len(supply_known) < len(rows):
            flags.append("partial_circulating_supply")
        tier = _tier(cap)
        if tier is None and cap is not None:
            exclusions.append("observed circulating market cap is outside configured tiers")
        if not liquidity_rows:
            flags.append("missing_liquidity")
        elif liquidity < 100_000:
            flags.append("low_reported_liquidity")
        if volume is None:
            flags.append("missing_volume")
        elif volume == 0:
            flags.append("zero_reported_volume")
        if any(r.get("volume_quality") in ("suspect", "low") for r in rows):
            flags.append("volume_quality_concern")
        if any(r.get("liquidity_quality") in ("suspect", "low") for r in rows):
            flags.append("liquidity_quality_concern")
        if key[0] == "unresolved":
            exclusions.append("provider identity is insufficient for cross-provider reconciliation")
        eligible = tier is not None and not exclusions
        if eligible:
            explanation = f"included: observed circulating market cap maps to {tier}; identity and policy checks passed"
        else:
            explanation = "excluded: " + "; ".join(sorted(set(exclusions)))
        identity_claims = sorted({f"{r.get('provider', 'unknown')}:{r.get('provider_asset_id', r.get('asset_id', 'unknown'))}" for r in rows})
        distinct_providers = {str(r.get("provider", "unknown")) for r in rows}
        identity_verification = ("cross_provider_agreement; chain state not independently verified"
                                 if len(distinct_providers) > 1 and len(networks) == 1 and len(addresses) == 1
                                 else "provider_claims_only; chain state not independently verified")
        assets.append({
            "asset_id": _stable_id(key[0] + ":" + key[1]), "identity_method": key[0],
            "identity_key": key[1], "identity_claims": identity_claims,
            "identity_verification": identity_verification,
            "name": sorted({str(r.get("name")).strip() for r in rows if r.get("name")})[0] if any(r.get("name") for r in rows) else None,
            "ticker": ticker, "ticker_claims": tickers, "network": networks[0] if len(networks) == 1 else networks or None,
            "contract_address": addresses[0] if len(addresses) == 1 else addresses or None,
            "circulating_market_cap_usd": cap, "market_cap_observations_usd": caps,
            "fully_diluted_valuation_usd": fdv, "fdv_observations_usd": fdvs,
            "market_cap_tier": tier, "circulating_supply": sorted(supply_known)[len(supply_known)//2] if supply_known else None,
            "supply_confidence": "MEDIUM" if len(supply_known) == len(rows) else "LOW" if supply_known else "UNKNOWN",
            "liquidity_usd": liquidity, "liquidity_summary_method": "maximum single reported observation; not venue-aggregated", "liquidity_observations": [{"usd": v, "provider": p, "venue": n} for v, p, n in sorted(liquidity_rows)],
            "volume_24h_usd": volume, "volume_summary_method": "median provider observation; overlapping reports not summed", "volume_observations_usd": volumes,
            "venues": [venues[v] for v in sorted(venues)], "providers": sorted({str(r.get("provider", "unknown")) for r in rows}),
            "flags": sorted(set(flags)), "included": eligible,
            "eligibility_explanation": explanation, "exclusion_reasons": sorted(set(exclusions)),
        })
    assets.sort(key=lambda a: (a["ticker"] or "", a["asset_id"]))
    included = [a for a in assets if a["included"]]
    return {"schema_version": VERSION, "snapshot_date": snapshot_date,
            "snapshot_id": f"small-cap-universe:{VERSION}:{snapshot_date}",
            "policy": {"tiers_usd": [
                {"name": "MICRO", "min_inclusive": 0, "max_exclusive": 10_000_000},
                {"name": "SMALL", "min_inclusive": 10_000_000, "max_inclusive": 100_000_000},
                {"name": "EXPANDED", "min_exclusive": 100_000_000, "max_exclusive": 1_000_000_000}],
                       "supported_networks": sorted(supported), "identity_rule": "explicit canonical_id or exact network plus contract; ticker never identifies assets"},
            "counts": {"assets": len(assets), "included": len(included), "excluded": len(assets)-len(included)},
            "assets": assets}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--date", required=True, help="snapshot date in YYYY-MM-DD")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        records = payload.get("observations", payload) if isinstance(payload, dict) else payload
        result = build_universe(records, snapshot_date=args.date)
        encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
