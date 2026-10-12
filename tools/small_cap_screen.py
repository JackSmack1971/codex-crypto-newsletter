"""Deterministic offline screening for a normalized universe plus dated daily bars.

Input JSON: {"universe": <universe snapshot>, "history": {asset_id: [daily OHLCV rows]},
"benchmark_history": {"BTC": [...]}}. Bars use date, close, and optional open/high/low/volume_usd/trades.
Missing observations remain UNKNOWN. Scoring weights and rubric are included in each report.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any

VERSION = "1.0.0"
DEFAULT_CONFIG = {
    "minimum_history_days": 31,
    "minimum_score_coverage": 0.50,
    "minimum_exchange_liquidity_usd": 25_000,
    "minimum_dex_liquidity_usd": 25_000,
    "weights": {"momentum_30d": 0.25, "relative_strength_btc_30d": 0.20,
                "relative_strength_universe_30d": 0.15, "relative_volume": 0.15,
                "liquidity": 0.15, "activity_change": 0.10},
}


def _num(x: Any) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        n = float(x)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _bars(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    cleaned = []
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("date"), str):
            continue
        try:
            date.fromisoformat(r["date"])
        except ValueError:
            continue
        close = _num(r.get("close"))
        if close is None or close <= 0:
            continue
        cleaned.append({**r, "close": close})
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in cleaned:
        by_date.setdefault(row["date"], []).append(row)
    # Conflicting same-day bars are ambiguous; exclude that date instead of
    # making source ordering silently select a price.
    return [rows[0] for day, rows in sorted(by_date.items())
            if len({json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) for row in rows}) == 1]


def _return(bars: list[dict[str, Any]], asof: str, days: int) -> dict[str, Any]:
    end = next((r for r in bars if r["date"] == asof), None)
    start_date = (date.fromisoformat(asof).toordinal() - days)
    start_key = date.fromordinal(start_date).isoformat()
    start = next((r for r in bars if r["date"] == start_key), None)
    if not end or not start:
        return {"value": None, "status": "UNKNOWN", "reason": f"close missing at {asof} or {start_key}", "observation_dates": [start_key, asof]}
    return {"value": end["close"] / start["close"] - 1, "status": "KNOWN", "observation_dates": [start_key, asof], "inputs": {start_key: start["close"], asof: end["close"]}}


def _indicators(bars: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for period in (7, 14, 20, 50):
        if len(bars) >= period:
            closes = [r["close"] for r in bars[-period:]]
            out[f"sma_{period}d"] = {"value": statistics.fmean(closes), "timeframe": "1d", "observations": period, "status": "KNOWN"}
        else:
            out[f"sma_{period}d"] = {"value": None, "timeframe": "1d", "observations": len(bars), "status": "UNKNOWN"}
    if len(bars) >= 15:
        changes = [bars[i]["close"] - bars[i-1]["close"] for i in range(len(bars)-14, len(bars))]
        gains = statistics.fmean(max(x, 0) for x in changes)
        losses = statistics.fmean(max(-x, 0) for x in changes)
        rsi = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
        out["rsi_14d"] = {"value": rsi, "timeframe": "1d", "observations": 15, "status": "KNOWN"}
    else:
        out["rsi_14d"] = {"value": None, "timeframe": "1d", "observations": len(bars), "status": "UNKNOWN"}
    if len(bars) >= 15 and all(_num(b.get("high")) is not None and _num(b.get("low")) is not None for b in bars[-14:]):
        trs = []
        for i in range(len(bars)-14, len(bars)):
            b, prev = bars[i], bars[i-1]["close"]
            trs.append(max(float(b["high"])-float(b["low"]), abs(float(b["high"])-prev), abs(float(b["low"])-prev)))
        out["atr_14d"] = {"value": statistics.fmean(trs), "timeframe": "1d", "observations": 14, "status": "KNOWN"}
    else:
        out["atr_14d"] = {"value": None, "timeframe": "1d", "observations": 0, "status": "UNKNOWN"}
    return out


def _liquidity(asset: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    values: dict[str, dict[str, float]] = {"exchange": {}, "dex": {}}
    venue_types = {str(v.get("name", "")): str(v.get("type", "")).lower()
                   for v in asset.get("venues", []) if isinstance(v, dict)}
    for i, obs in enumerate(asset.get("liquidity_observations", [])):
        if not isinstance(obs, dict):
            continue
        venue_name = str(obs.get("venue") or obs.get("name") or "")
        typ = str(obs.get("venue_type", obs.get("type", venue_types.get(venue_name, "")))).lower()
        typ = "dex" if "dex" in typ else "exchange" if any(k in typ for k in ("cex", "exchange")) else "unknown"
        amount = _num(obs.get("usd"))
        venue = venue_name or str(obs.get("provider") or f"observation-{i}")
        if amount is not None and amount >= 0 and typ != "unknown":
            values[typ][venue] = max(amount, values[typ].get(venue, 0))
    result = {}
    for typ in ("exchange", "dex"):
        known = bool(values[typ])
        result[f"{typ}_liquidity_usd"] = {"value": sum(values[typ].values()) if known else None,
            "status": "KNOWN" if known else "UNKNOWN", "venue_count": len(values[typ]), "method": "sum of distinct reported venues; may overlap across providers"}
    return result, (list(values["exchange"].values()) + list(values["dex"].values()))


def _score_parts(metrics: dict[str, Any], config: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    # Component transforms are fixed and bounded to [0,100]. Missing components earn zero.
    values = {}
    transforms = {
        "momentum_30d": lambda x: max(0, min(100, 50 + x * 100)),
        "relative_strength_btc_30d": lambda x: max(0, min(100, 50 + x * 100)),
        "relative_strength_universe_30d": lambda x: max(0, min(100, 50 + x * 100)),
        "relative_volume": lambda x: max(0, min(100, 50 + math.log2(max(x, 1e-12)) * 20)),
        "liquidity": lambda x: max(0, min(100, math.log10(max(x, 1)) * 10)),
        "activity_change": lambda x: max(0, min(100, 50 + x * 100)),
    }
    for name, fn in transforms.items():
        val = metrics.get(name, {}).get("value")
        values[name] = fn(val) if metrics.get(name, {}).get("status") == "KNOWN" and val is not None else None
    weights = config["weights"]
    score = sum(weights[k] * (values[k] if values[k] is not None else 0) for k in weights)
    known_weight = sum(weights[k] for k in weights if values[k] is not None)
    conf = known_weight / sum(weights.values()) if sum(weights.values()) else 0
    coverage = {k: {"value": values[k], "weight": weights[k], "status": "KNOWN" if values[k] is not None else "UNKNOWN"} for k in weights}
    return round(score, 4), round(conf, 4), coverage


def screen(universe: dict[str, Any], history: dict[str, Any], *, benchmark_history: dict[str, Any] | None = None,
           config: dict[str, Any] | None = None, generated_at: str | None = None) -> dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if config:
        for k, v in config.items():
            if k == "weights":
                cfg[k].update(v)
            else:
                cfg[k] = v
    if set(cfg["weights"]) != set(DEFAULT_CONFIG["weights"]) or any(_num(v) is None or v < 0 for v in cfg["weights"].values()) or sum(cfg["weights"].values()) <= 0:
        raise ValueError("weights must be nonnegative known components with positive total")
    total_weight = sum(cfg["weights"].values())
    cfg["weights"] = {k: v / total_weight for k, v in cfg["weights"].items()}
    asof = universe.get("snapshot_date")
    date.fromisoformat(asof)
    assets = universe.get("assets", [])
    histories = {k: _bars(v) for k, v in (history or {}).items()}
    btc = _bars((benchmark_history or {}).get("BTC", []))
    records = []
    for asset in assets:
        aid = asset["asset_id"]
        bars = histories.get(aid, [])
        m: dict[str, Any] = {}
        for d in (1, 7, 30, 90):
            m[f"return_{d}d"] = _return(bars, asof, d)
        m["relative_strength_btc_30d"] = {"value": None, "status": "UNKNOWN", "reason": "asset or BTC 30d return unavailable"}
        ar, br = m["return_30d"]["value"], _return(btc, asof, 30)["value"]
        if ar is not None and br is not None:
            m["relative_strength_btc_30d"] = {"value": ar-br, "status": "KNOWN", "calculation": "asset 30d return minus BTC 30d return", "inputs": {"asset_return": ar, "btc_return": br}}
        m["relative_strength_universe_30d"] = {"value": None, "status": "UNKNOWN", "reason": "fewer than two peer 30d returns"}
        m["relative_volume"] = {"value": None, "status": "UNKNOWN", "reason": "at least 21 daily volume observations required"}
        vols = [_num(x.get("volume_usd")) for x in bars[-21:]]
        if len(vols) == 21 and all(x is not None for x in vols) and statistics.median(vols[:-1]) > 0:
            m["relative_volume"] = {"value": vols[-1]/statistics.median(vols[:-1]), "status": "KNOWN", "calculation": "latest daily USD volume / median prior 20 daily volumes", "observations": 21}
        m["abnormal_turnover"] = {"value": None, "status": "UNKNOWN", "reason": "market cap or 21 daily volume observations unavailable"}
        cap = _num(asset.get("circulating_market_cap_usd"))
        if cap and m["relative_volume"]["value"] is not None:
            m["abnormal_turnover"] = {"value": vols[-1]/cap, "status": "KNOWN", "calculation": "latest daily volume / observed circulating market cap", "inputs": {"volume_usd": vols[-1], "market_cap_usd": cap}}
        m["trading_activity_change"] = {"value": None, "status": "UNKNOWN", "reason": "daily trades or volume windows unavailable"}
        trade_vals = [_num(x.get("trades")) for x in bars[-8:]]
        if len(trade_vals) == 8 and all(x is not None for x in trade_vals) and statistics.fmean(trade_vals[:7]) > 0:
            m["trading_activity_change"] = {"value": trade_vals[-1]/statistics.fmean(trade_vals[:7])-1, "status": "KNOWN", "calculation": "latest daily trades / mean prior seven daily trades - 1", "observations": 8}
        m["volatility_30d"] = {"value": None, "status": "UNKNOWN", "reason": "31 consecutive daily closes required", "timeframe": "1d"}
        closes = [x for x in bars if x["date"] <= asof]
        if len(closes) >= 31 and all((date.fromisoformat(closes[-i]["date"])-date.fromisoformat(closes[-i-1]["date"])).days == 1 for i in range(1,31)):
            daily = [closes[i]["close"]/closes[i-1]["close"]-1 for i in range(-30,0)]
            m["volatility_30d"] = {"value": statistics.stdev(daily)*math.sqrt(365), "status": "KNOWN", "timeframe": "1d annualized", "observations": 30, "calculation": "sample standard deviation of daily close returns × sqrt(365)"}
        window = closes[-90:]
        contiguous = len(window) == 90 and all((date.fromisoformat(window[i]["date"])-date.fromisoformat(window[i-1]["date"])).days == 1 for i in range(1, len(window)))
        peak = max((x["close"] for x in window), default=None)
        m["drawdown_from_90d_peak"] = {"value": (closes[-1]["close"]/peak-1) if contiguous else None, "status": "KNOWN" if contiguous else "UNKNOWN", "timeframe": "1d", "observations": len(window), "reason": None if contiguous else "90 consecutive daily closes required"}
        m["market_cap_fdv_gap"] = {"value": None, "status": "UNKNOWN", "reason": "market cap or FDV unavailable"}
        fdv = _num(asset.get("fully_diluted_valuation_usd"))
        if cap is not None and cap > 0 and fdv is not None:
            m["market_cap_fdv_gap"] = {"value": fdv/cap-1, "status": "KNOWN", "calculation": "FDV / circulating market cap - 1", "inputs": {"market_cap_usd": cap, "fdv_usd": fdv}}
        liq, liq_inputs = _liquidity(asset)
        m.update(liq)
        venue_values = liq_inputs
        m["liquidity_concentration"] = {"value": max(venue_values)/sum(venue_values) if venue_values and sum(venue_values)>0 else None, "status": "KNOWN" if venue_values and sum(venue_values)>0 else "UNKNOWN", "calculation": "largest reported classified venue / sum of classified venue liquidity", "venue_count": len(venue_values)}
        # Score liquidity only with known venue liquidity; snapshot total remains separate.
        combined_liq = sum(liq_inputs) if liq_inputs else _num(asset.get("liquidity_usd"))
        m["momentum_30d"] = m["return_30d"]
        m["activity_change"] = m["trading_activity_change"]
        m["liquidity"] = {"value": combined_liq, "status": "KNOWN" if combined_liq is not None else "UNKNOWN", "observation": "distinct reported exchange/DEX venues or universe snapshot total"}
        score, confidence, components = _score_parts(m, cfg)
        warnings = list(asset.get("flags", []))
        if len(bars) < cfg["minimum_history_days"]: warnings.append("insufficient_history")
        if bars and (asof != bars[-1]["date"]): warnings.append("stale_or_missing_asof_price")
        if m["market_cap_fdv_gap"]["value"] is not None and m["market_cap_fdv_gap"]["value"] > 5: warnings.append("high_fdv_to_market_cap_gap")
        if m["relative_volume"]["value"] is not None and m["relative_volume"]["value"] > 10: warnings.append("volume_outlier")
        if (liq.get("exchange_liquidity_usd", {}).get("value") or 0) < cfg["minimum_exchange_liquidity_usd"] and (liq.get("dex_liquidity_usd", {}).get("value") or 0) < cfg["minimum_dex_liquidity_usd"]: warnings.append("thin_or_unknown_liquidity")
        if m["liquidity_concentration"]["value"] is not None and m["liquidity_concentration"]["value"] >= .80: warnings.append("liquidity_concentrated_in_one_venue")
        quality = {"valid_history_days": len(bars), "required_history_days": cfg["minimum_history_days"], "score_component_coverage": confidence, "minimum_score_coverage": cfg["minimum_score_coverage"], "status": "PASS" if confidence >= cfg["minimum_score_coverage"] else "FAIL"}
        reasons = []
        if not asset.get("included", True): reasons.extend(asset.get("exclusion_reasons", []) or ["universe eligibility false"])
        if bars and bars[-1]["date"] != asof: reasons.append("latest daily close does not match snapshot date")
        if len(bars) < cfg["minimum_history_days"]: reasons.append("minimum daily history requirement not met")
        if quality["status"] != "PASS": reasons.append("minimum score data coverage not met")
        record = {"asset_id": aid, "ticker": asset.get("ticker"), "universe_eligible": asset.get("included", True), "opportunity_score": score, "data_confidence_score": round(confidence*100, 2), "score_components": components, "metrics": m, "indicators": _indicators(bars), "data_quality": quality, "risk_flags": sorted(set(warnings)), "rejection_reasons": sorted(set(reasons)), "evidence": {"universe_snapshot_id": universe.get("snapshot_id"), "snapshot_date": asof, "daily_bars": [{"date": b["date"], "close": b["close"], "volume_usd": b.get("volume_usd"), "trades": b.get("trades"), "open": b.get("open"), "high": b.get("high"), "low": b.get("low")} for b in bars], "asset_observations": {k: asset.get(k) for k in ("circulating_market_cap_usd", "fully_diluted_valuation_usd", "volume_24h_usd", "liquidity_usd", "liquidity_observations", "venues")}}}
        records.append(record)
    peer = [r["metrics"]["return_30d"]["value"] for r in records if r["universe_eligible"] and r["metrics"]["return_30d"]["value"] is not None]
    median_peer = statistics.median(peer) if len(peer) >= 2 else None
    for r in records:
        ret = r["metrics"]["return_30d"]["value"]
        if ret is not None and median_peer is not None:
            val = ret - median_peer
            r["metrics"]["relative_strength_universe_30d"] = {"value": val, "status": "KNOWN", "calculation": "asset 30d return minus universe median 30d return", "inputs": {"asset_return": ret, "universe_median_return": median_peer, "peer_count": len(peer)}}
            r["metrics"]["relative_strength_universe_30d"]["score_note"] = "reported as a metric; score_component coverage recalculated below"
        score, confidence, components = _score_parts(r["metrics"], cfg)
        r["opportunity_score"], r["data_confidence_score"], r["score_components"] = score, round(confidence*100,2), components
        r["data_quality"]["score_component_coverage"] = confidence
        r["data_quality"]["status"] = "PASS" if confidence >= cfg["minimum_score_coverage"] else "FAIL"
        if r["data_quality"]["status"] != "PASS" and "minimum score data coverage not met" not in r["rejection_reasons"]: r["rejection_reasons"].append("minimum score data coverage not met")
        if r["data_quality"]["status"] == "PASS" and not r["rejection_reasons"]: r["rejection_reasons"] = []
    records.sort(key=lambda r: (-r["opportunity_score"], r["asset_id"]))
    return {"schema_version": VERSION, "status": "REPRODUCIBLE_OFFLINE_SCREEN", "snapshot_date": asof,
            "generated_at": generated_at or f"{asof}T00:00:00+00:00", "universe_snapshot_id": universe.get("snapshot_id"),
            "config": cfg, "rubric": {"score_range": [0,100], "missing_component_value": 0, "weights_are_fixed_denominator": True, "transforms": {"returns_and_relative_strength": "clamp(50 + 100*x, 0, 100)", "relative_volume": "clamp(50 + 20*log2(ratio), 0, 100)", "liquidity_usd": "clamp(10*log10(max(USD,1)), 0, 100)"}, "data_confidence": "weighted fraction of known score components × 100", "minimum_coverage": cfg["minimum_score_coverage"], "rank_ties": "asset_id ascending"},
            "ranked_candidates": [r for r in records if not r["rejection_reasons"]], "rejected_candidates": [r for r in records if r["rejection_reasons"]], "candidate_evidence": records}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path); p.add_argument("--output", type=Path); p.add_argument("--config", type=Path)
    a = p.parse_args(argv)
    try:
        payload = json.loads(a.input.read_text(encoding="utf-8"))
        cfg = json.loads(a.config.read_text(encoding="utf-8")) if a.config else None
        result = screen(payload["universe"], payload.get("history", {}), benchmark_history=payload.get("benchmark_history"), config=cfg)
        encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if a.output: a.output.write_text(encoded, encoding="utf-8")
        else: print(encoded, end="")
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
