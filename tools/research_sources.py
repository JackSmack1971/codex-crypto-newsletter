"""Provider-neutral, read-only market observations with deterministic replay."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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


def fetch(route: str, query: str, *, policy_path=None, opener=None, retries=MAX_RETRIES, now=None):
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
    if cached and clock() - cached[0] <= CACHE_TTL_SECONDS:
        return json.loads(json.dumps(cached[1]))
    if _OPEN_UNTIL.get(provider, 0) > clock():
        return {"status": "UNKNOWN", "provider": provider, "reason": "circuit_open"}
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "small-cap-crypto-daily/1.0"})
    client = opener if opener is not None else build_opener(NoRedirect)
    error = None
    for attempt in range(retries + 1):
        try:
            with client.open(request, timeout=TIMEOUT_SECONDS) as response:
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
                      "data_quality": "unparsed_native_payload", "data": data}
            if kind == "observation":
                result["observations"] = normalize_observation(provider, data, result["retrieved_at"])
            _FAILURES[provider] = 0
            _CACHE[cache_key] = (clock(), result)
            return result
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            error = exc
            if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                break
            if attempt < retries:
                time.sleep(min(0.1 * (2 ** attempt), 0.4))
    _FAILURES[provider] = _FAILURES.get(provider, 0) + 1
    if _FAILURES[provider] >= _CIRCUIT_THRESHOLD:
        _OPEN_UNTIL[provider] = clock() + _CIRCUIT_SECONDS
    if isinstance(error, (ValueError, json.JSONDecodeError)):
        raise error
    return {"status": "UNKNOWN", "provider": provider, "reason": "provider_unavailable", "error_type": type(error).__name__ if error else "unknown"}


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
        output = json.dumps(result, ensure_ascii=False, indent=2)
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
