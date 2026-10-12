"""Provider-neutral, read-only market observations with deterministic replay."""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from controlplane import authorize_source, load_source_policy

TIMEOUT_SECONDS = 12
MAX_QUERY_LENGTH = 96
MAX_RESPONSE_BYTES = 500_000
MAX_RETRIES = 2
CACHE_TTL_SECONDS = 30

# Registry is descriptive. An adapter is callable only when active and policy-enabled.
PROVIDERS = {
    "coingecko": {"source": "coingecko-market-data", "interface": "project-mcp", "active": True, "capabilities": ["price", "market_cap", "volume", "discovery"], "authentication": "MCP-configured", "fees": "zero-cost read configured; terms/quota unverified", "quota": "provider/MCP managed; unverified", "health": "UNVERIFIED", "operations": ["read"]},
    "dexpaprika": {"source": "dexpaprika-dex-data", "interface": "project-mcp", "active": True, "capabilities": ["price", "volume", "liquidity", "chain", "contract", "discovery"], "authentication": "MCP-configured", "fees": "zero-cost read configured; terms/quota unverified", "quota": "provider/MCP managed; unverified", "health": "UNVERIFIED", "operations": ["read"]},
    "coinpaprika": {"source": "coinpaprika-public-api", "interface": "rest", "active": True, "capabilities": ["price", "market_cap", "volume", "exchange", "discovery"], "authentication": "none for public route", "fees": "zero-cost read configured", "quota": "provider quota unverified", "health": "UNVERIFIED", "operations": ["read"]},
    "dexscreener": {"source": "dexscreener-market-data", "interface": "rest", "active": True, "capabilities": ["price", "volume", "liquidity", "exchange", "chain", "contract", "discovery"], "authentication": "none", "fees": "zero-cost read configured", "quota": "provider quota unverified", "health": "UNVERIFIED", "operations": ["read"]},
    "defillama": {"source": "defillama-market-data", "interface": "rest-candidate", "active": False, "capabilities": ["market_cap", "volume", "liquidity", "discovery"], "authentication": "API access plan dependent", "fees": "Open plan data listed free; API plan $300/month; not enabled", "quota": "API plan 1,000/minute, 1M/month", "health": "NOT_CHECKED", "operations": []},
    "geckoterminal": {"source": "geckoterminal-market-data", "interface": "rest-candidate", "active": False, "capabilities": ["price", "volume", "liquidity", "chain", "contract", "discovery"], "authentication": "public endpoints", "fees": "public API documented; higher/stable rate limits require paid CoinGecko plan", "quota": "free limit not verified", "health": "NOT_CHECKED", "operations": []},
    "ccxt-public": {"source": "ccxt-public-market-data", "interface": "library-candidate", "active": False, "capabilities": ["price", "volume", "exchange", "discovery"], "authentication": "none for exchange public methods", "fees": "library free/open source; exchange terms and quotas vary", "quota": "exchange specific; typically throttled", "health": "NOT_CHECKED", "operations": []},
    "hyperliquid": {"source": "hyperliquid-info", "interface": "rest-candidate", "active": False, "capabilities": ["price", "volume", "exchange"], "authentication": "none for public info requests", "fees": "public Info API; no request charge documented", "quota": "IP aggregate weight 1200/minute", "health": "NOT_CHECKED", "operations": []},
}

# Search routes are explicitly discovery. Observation routes require a stable provider ID.
ROUTES = {
    "dex-pair-search": ("dexscreener", "https://api.dexscreener.com/latest/dex/search", "q", "discovery"),
    "coinpaprika-search": ("coinpaprika", "https://api.coinpaprika.com/v1/search", "q", "discovery"),
    "coinpaprika-ticker": ("coinpaprika", "https://api.coinpaprika.com/v1/tickers", None, "observation"),
}
_CACHE = {}
_FAILURES = {}
_OPEN_UNTIL = {}
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_SECONDS = 30
MAX_ADAPTER_REQUESTS = 4


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def registry():
    return json.loads(json.dumps(PROVIDERS))


def normalize_observation(provider, raw, retrieved_at=None):
    """Normalize common fields without discarding provider data or duplicate records."""
    rows = raw if isinstance(raw, list) else [raw]
    normalized = []
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    for item in rows:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes", item)
        if not isinstance(attrs, dict):
            attrs = item
        quotes = attrs.get("quotes", {})
        usd = quotes.get("USD", {}) if isinstance(quotes, dict) else {}
        if isinstance(usd, dict):
            attrs = {**attrs, **{k: v for k, v in {"price": usd.get("price"), "volume_24h": usd.get("volume_24h"), "market_cap": usd.get("market_cap")}.items() if v is not None}}
        base_token = attrs.get("baseToken", {})
        volume = attrs.get("volume", {})
        liquidity = attrs.get("liquidity", {})
        if isinstance(base_token, dict):
            attrs = {**attrs, "contract_address": attrs.get("contract_address") or base_token.get("address"),
                     "token_id": attrs.get("token_id") or base_token.get("address")}
        if isinstance(volume, dict) and volume.get("h24") is not None:
            attrs = {**attrs, "volume_24h": volume["h24"]}
        if isinstance(liquidity, dict) and liquidity.get("usd") is not None:
            attrs = {**attrs, "liquidity_usd": liquidity["usd"]}
        native_time = attrs.get("last_updated", attrs.get("updated_at", attrs.get("timestamp", attrs.get("time"))))
        normalized.append({
            "provider": provider,
            "kind": "market_observation",
            "price": _first(attrs, "price_usd", "priceUsd", "price", "current_price", "last"),
            "market_cap": _first(attrs, "market_cap_usd", "market_cap", "marketCap"),
            "volume": _first(attrs, "volume_usd", "volume_24h", "total_volume", "volume"),
            "liquidity": _first(attrs, "liquidity_usd", "liquidity", "reserve_in_usd"),
            "exchange": _first(attrs, "dex_id", "dexId", "exchange", "exchange_name"),
            "chain": _first(attrs, "chain_id", "chainId", "network", "chain"),
            "contract_address": _first(attrs, "contract_address", "address", "base_token_address"),
            "token_id": _first(attrs, "coin_id", "id", "token_id"),
            "retrieved_at": retrieved_at,
            "native_observation_time": native_time,
            "quality": "native_timestamp" if native_time is not None else "retrieval_time_only",
            "raw": item,
        })
    return normalized


def _first(row, *keys):
    return next((row[k] for k in keys if row.get(k) is not None), None)


def replay(fixture_path, provider=None):
    payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "observations" in payload:
        return payload["observations"]
    if isinstance(payload, list) and all(isinstance(row, dict) and "provider" in row and "retrieved_at" in row for row in payload):
        return payload
    return normalize_observation(provider or "fixture", payload)


def _canonical_identity(row):
    """Return a stable source identity; ticker and provider labels are not identity."""
    canonical_id = row.get("canonical_id")
    if isinstance(canonical_id, str) and canonical_id.strip():
        return {"method": "canonical_id", "value": canonical_id.strip()}
    chain = row.get("network", row.get("chain"))
    address = row.get("contract_address", row.get("address"))
    if isinstance(chain, str) and chain.strip() and isinstance(address, str) and address.strip():
        chain = chain.strip().lower()
        address = address.strip()
        if chain in {"ethereum", "base", "arbitrum", "optimism", "polygon", "bsc", "avalanche"}:
            address = address.lower()
        return {"method": "network_contract", "value": f"{chain}:{address}"}
    provider = row.get("provider")
    asset_id = row.get("provider_asset_id", row.get("asset_id", row.get("token_id")))
    if isinstance(provider, str) and provider.strip() and isinstance(asset_id, str) and asset_id.strip():
        return {"method": "provider_asset_id", "value": f"{provider.strip().lower()}:{asset_id.strip()}"}
    raise ValueError("source observation has unresolved canonical asset identity")


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sanitize_payload(value):
    """Remove common secret/PII fields before provider content enters artifacts."""
    sensitive = ("authorization", "api_key", "apikey", "secret", "password", "bearer", "access_token",
                 "auth_token", "refresh_token", "private_key", "seed_phrase", "email", "phone")
    if isinstance(value, dict):
        return {key: _sanitize_payload(item) for key, item in value.items()
                if not any(word in str(key).casefold() for word in sensitive)}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    return value


def _source_rows(result, route):
    if result.get("kind") == "observation":
        return result.get("observations", [])
    payload = result.get("data")
    if isinstance(payload, list):
        return normalize_observation(result["provider"], payload, result.get("retrieved_at"))
    if isinstance(payload, dict):
        for key in ("pairs", "coins", "currencies", "tokens", "data"):
            values = payload.get(key)
            if isinstance(values, list):
                return normalize_observation(result["provider"], values, result.get("retrieved_at"))
    return []


def execute(mode, *, replay_path=None, requests=None, authorized=False, policy_path=None, opener=None,
            max_requests=MAX_ADAPTER_REQUESTS, now=None):
    """Execute the research adapter contract. Replay is offline; REST is explicitly authorized.

    MCP is intentionally blocked: this adapter has no verified native, deterministic
    tool-call mechanism that avoids an unapproved model invocation.
    """
    if mode not in ("replay", "live-rest", "live-mcp"):
        raise ValueError("unknown research execution mode")
    if mode == "live-mcp":
        return {"mode": mode, "status": "BLOCKED", "reason": "native Codex MCP invocation is not verified for this adapter", "observations": [], "failures": []}
    if isinstance(max_requests, bool) or not isinstance(max_requests, int) or not 0 <= max_requests <= MAX_ADAPTER_REQUESTS:
        raise ValueError("request budget must be between 0 and 4")
    if mode == "replay":
        if replay_path is None or requests:
            raise ValueError("replay requires a fixture and does not accept REST requests")
        source = Path(replay_path)
        rows = replay(source)
        retrieved = datetime.now(timezone.utc).isoformat()
        observations = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError("replay observation must be an object")
            identity = _canonical_identity(row)
            provider = row.get("provider")
            if not isinstance(provider, str) or not provider.strip():
                raise ValueError("replay source provider is unresolved")
            normalized = _sanitize_payload(dict(row))
            observations.append({
                "observation": normalized,
                "provenance": {"canonical_asset_identity": identity, "source_provider": provider,
                    "operation": "replay", "endpoint_or_tool": "local-fixture", "retrieved_at": row.get("retrieved_at", retrieved),
                    "provider_observed_at": row.get("native_observation_time"), "source_status": "SIMULATED_REPLAY",
                    "schema_status": "VALIDATED", "content_sha256": _digest(row), "normalized_artifact_sha256": _digest(normalized),
                    "request_count": 0, "quota_cost": "not_applicable_local_replay", "validation": "PASS",
                    "research_usability": "REPLAY_ONLY", "live_source_verified": False, "observation_index": index}})
        return {"mode": mode, "status": "OK" if observations else "DEGRADED", "observations": observations,
                "failures": [], "request_count": 0, "source_attempts": [],
                "live_source_verified": False, "mode": mode}
    if authorized is not True:
        raise PermissionError("live-rest requires explicit operator authorization")
    if replay_path is not None or not isinstance(requests, list) or not requests:
        raise ValueError("live-rest requires one or more fixed route/query requests")
    if len(requests) > max_requests:
        raise PermissionError("live-rest request budget exceeded")
    observations, failures, source_attempts = [], [], []
    attempted_requests = 0
    for spec in requests:
        if not isinstance(spec, dict) or set(spec) != {"route", "query"}:
            raise ValueError("REST request must contain only route and query")
        route, query = spec["route"], spec["query"]
        if not isinstance(route, str) or route not in ROUTES:
            raise ValueError("unsupported research operation")
        provider_id = ROUTES[route][0]
        provider = PROVIDERS[provider_id]["source"]
        source_attempt = {
            "provider_id": provider_id,
            "source_provider": provider,
            "operation": route,
            "endpoint_host": urlparse(ROUTES[route][1]).hostname,
            "attempted_at": datetime.now(timezone.utc).isoformat(),
            "status": "ATTEMPTED",
            "request_count": 0,
        }
        source_attempts.append(source_attempt)
        observations_before = len(observations)
        try:
            # One attempt per explicitly budgeted operation; callers may raise the
            # budget by selecting more operations, never through hidden retries.
            result = fetch(route, query, policy_path=policy_path, opener=opener, retries=0, now=now, use_cache=False)
            attempted_requests += result.get("request_count", 0)
            source_attempt["request_count"] = result.get("request_count", 0)
            if result.get("status") != "OK":
                source_attempt["status"] = "FAILED"
                failures.append({"operation": route, "status": result.get("status", "UNKNOWN"),
                                 "reason": result.get("reason", "provider unavailable"),
                                 "source_provider": provider,
                                 **({"error_type": result["error_type"]} if result.get("error_type") else {})})
                continue
            meta = PROVIDERS[result["provider"]]
            endpoint_host = urlparse(ROUTES[route][1]).hostname
            source_rows = _source_rows(result, route)
            if not source_rows:
                source_attempt["status"] = "UNAVAILABLE"
                failures.append({"operation": route, "status": "NO_USABLE_OBSERVATIONS",
                    "source_provider": provider,
                    "schema_status": "VALIDATED_EMPTY" if result.get("data") in ([], {"pairs": []}, {"currencies": []}, {"coins": []}) else "UNEXPECTED_RESPONSE_SHAPE"})
            for row in source_rows:
                identity = _canonical_identity(row)
                content = row.get("raw", row)
                normalized = _sanitize_payload(dict(row))
                observations.append({"observation": normalized, "provenance": {
                    "canonical_asset_identity": identity, "source_provider": meta["source"], "operation": "read",
                    "endpoint_or_tool": route, "retrieved_at": result["retrieved_at"],
                    "provider_observed_at": row.get("native_observation_time"), "source_status": "LIVE_RETRIEVED",
                    "schema_status": "VALIDATED", "content_sha256": _digest(content),
                    "normalized_artifact_sha256": _digest(normalized),
                    "quota_cost": "zero_cost_configured; provider quota/cost unverified", "validation": "PASS",
                    "research_usability": "USABLE_WITH_PROVIDER_CLAIM_LIMITS", "live_source_verified": True,
                    "request_count": result.get("request_count", 0),
                    "endpoint_host": endpoint_host}})
            if len(observations) > observations_before:
                source_attempt["status"] = "VALIDATED"
        except (ValueError, PermissionError, RuntimeError, TimeoutError) as exc:
            # Error details can contain provider-controlled material; keep only type.
            failed_request_count = getattr(exc, "request_count", 0)
            attempted_requests += failed_request_count
            source_attempt["request_count"] = failed_request_count
            source_attempt["status"] = "FAILED"
            failures.append({"operation": str(route), "status": "FAILED", "source_provider": provider,
                             "error_type": type(exc).__name__})
    status = "OK" if observations and not failures else "PARTIAL" if observations else "DEGRADED"
    live_source_verified = bool(
        status == "OK" and attempted_requests > 0 and source_attempts and
        all(item["status"] == "VALIDATED" and item["request_count"] > 0 for item in source_attempts) and
        observations and all(item["provenance"].get("validation") == "PASS" and
                             item["provenance"].get("source_status") == "LIVE_RETRIEVED" and
                             item["provenance"].get("request_count", 0) > 0 for item in observations)
    )
    return {"mode": mode, "status": status, "observations": observations, "failures": failures,
            "request_count": attempted_requests, "source_attempts": source_attempts,
            "live_source_verified": live_source_verified}


def fetch(route: str, query: str, *, policy_path=None, opener=None, retries=MAX_RETRIES, now=None, use_cache=True):
    if route not in ROUTES:
        raise ValueError("unsupported research route")
    if not isinstance(query, str) or not (1 <= len(query.strip()) <= MAX_QUERY_LENGTH) or any(ord(c) < 32 for c in query):
        raise ValueError("query must contain 1..96 printable characters")
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= MAX_RETRIES:
        raise ValueError("retries must be between 0 and 2")
    provider, base, key, kind = ROUTES[route]
    meta = PROVIDERS[provider]
    if not meta["active"]:
        raise PermissionError("provider is not active")
    value = query.strip()
    if route == "coinpaprika-ticker" and (len(value) > 64 or not all(c.isalnum() or c in "-_" for c in value)):
        raise ValueError("ticker identifier contains unsupported characters")
    url = base + ("/" + value if key is None else "?" + urlencode({key: value}))
    policy = load_source_policy(Path(policy_path)) if policy_path else load_source_policy()
    decision = authorize_source(policy, meta["source"], "read", url, 0)
    if decision["status"] != "ALLOW":
        raise PermissionError(decision["reason"])
    clock = now or time.time
    cache_key = (route, value)
    cached = _CACHE.get(cache_key)
    if use_cache and cached and clock() - cached[0] <= CACHE_TTL_SECONDS:
        return json.loads(json.dumps(cached[1]))
    if _OPEN_UNTIL.get(provider, 0) > clock():
        return {"status": "UNKNOWN", "provider": provider, "reason": "circuit_open"}
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "small-cap-crypto-daily/1.0"})
    client = opener if opener is not None else build_opener(NoRedirect)
    error = None
    request_count = 0
    for attempt in range(retries + 1):
        try:
            request_count += 1
            with client.open(request, timeout=TIMEOUT_SECONDS) as response:
                final_url = response.geturl() if hasattr(response, "geturl") else url
                parsed_final = urlparse(final_url)
                if parsed_final.scheme != "https" or parsed_final.hostname != urlparse(url).hostname:
                    raise PermissionError("provider response redirected outside the authorized HTTPS host")
                if response.status != 200:
                    raise RuntimeError("non-200 provider response")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("provider response exceeds byte limit")
            data = json.loads(raw)
            if not isinstance(data, (dict, list)):
                raise ValueError("unexpected provider JSON type")
            retrieved_at = datetime.now(timezone.utc).isoformat()
            result = {"status": "OK", "provider": provider, "source": meta["source"], "route": route,
                      "kind": kind, "retrieved_at": retrieved_at, "retrieved_at_utc": retrieved_at,
                      "observation_time": None, "native_observation_time": None,
                      "data_quality": "unparsed_native_payload", "data": data, "request_count": request_count}
            if kind == "observation":
                result["observations"] = normalize_observation(provider, data, result["retrieved_at"])
            _FAILURES[provider] = 0
            if use_cache:
                _CACHE[cache_key] = (clock(), result)
            return result
        except (HTTPError, URLError, TimeoutError, RuntimeError, PermissionError, ValueError) as exc:
            error = exc
            if isinstance(exc, ValueError):
                exc.request_count = request_count
            if isinstance(exc, (PermissionError, ValueError)) or isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                break
            if attempt < retries:
                time.sleep(min(0.1 * (2 ** attempt), 0.4))
    _FAILURES[provider] = _FAILURES.get(provider, 0) + 1
    if _FAILURES[provider] >= _CIRCUIT_THRESHOLD:
        _OPEN_UNTIL[provider] = clock() + _CIRCUIT_SECONDS
    if isinstance(error, (ValueError, json.JSONDecodeError)):
        raise error
    return {"status": "UNKNOWN", "provider": provider, "reason": "provider_unavailable", "error_type": type(error).__name__ if error else "unknown", "request_count": request_count}


def main():
    parser = argparse.ArgumentParser(description="Bounded read-only market data retrieval; network is opt-in")
    parser.add_argument("route", choices=sorted(ROUTES))
    parser.add_argument("query")
    parser.add_argument("--execute", action="store_true", help="perform authorized public network read")
    parser.add_argument("--replay", type=Path, help="normalize saved JSON fixture without network access")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.replay:
            result = {"status": "REPLAY", "observations": replay(args.replay)}
        elif not args.execute:
            result = {"status": "DRY_RUN", "route": args.route, "query": args.query, "network": False}
        else:
            result = fetch(args.route, args.query)
        output = json.dumps(_sanitize_payload(result), ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
        return 0 if result.get("status") not in ("UNKNOWN",) else 2
    except (ValueError, PermissionError, RuntimeError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
