"""Durable, evidence-gated rolling seven-day crypto watchlist."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATES = {"DISCOVERED", "RESEARCHING", "WATCHING", "TRIGGERED", "PROMOTED", "INVALIDATED", "EXPIRED", "ARCHIVED"}
TERMINAL = {"INVALIDATED", "EXPIRED", "ARCHIVED"}
TRANSITIONS = {
    "DISCOVERED": {"RESEARCHING", "INVALIDATED", "EXPIRED", "ARCHIVED"},
    "RESEARCHING": {"WATCHING", "INVALIDATED", "EXPIRED", "ARCHIVED"},
    "WATCHING": {"TRIGGERED", "INVALIDATED", "EXPIRED", "ARCHIVED"},
    "TRIGGERED": {"WATCHING", "PROMOTED", "INVALIDATED", "EXPIRED", "ARCHIVED"},
    "PROMOTED": {"WATCHING", "INVALIDATED", "EXPIRED", "ARCHIVED"},
    "INVALIDATED": {"ARCHIVED"}, "EXPIRED": {"ARCHIVED"}, "ARCHIVED": set(),
}


def _stamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO-8601 with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601 with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Watchlist:
    """SQLite watchlist. Asset identities are tombstoned permanently by unique key."""
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
          candidate_id INTEGER PRIMARY KEY, identity_key TEXT NOT NULL UNIQUE,
          identity TEXT NOT NULL, discovered_on TEXT NOT NULL, expires_on TEXT NOT NULL,
          expiration_conditions TEXT NOT NULL,
          thesis TEXT NOT NULL, catalyst TEXT NOT NULL, market_cap_tier TEXT NOT NULL,
          liquidity_classification TEXT NOT NULL, entry_trigger TEXT NOT NULL,
          invalidation_trigger TEXT NOT NULL, confidence REAL NOT NULL,
          risk_assessment TEXT NOT NULL, next_review_date TEXT NOT NULL,
          state TEXT NOT NULL, material_changes TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS observations (
          observation_id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES candidates(candidate_id),
          observed_at TEXT NOT NULL, payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transitions (
          transition_id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES candidates(candidate_id),
          from_state TEXT, to_state TEXT NOT NULL, transitioned_at TEXT NOT NULL,
          evidence TEXT NOT NULL, reason TEXT NOT NULL
        );
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def identity_key(identity: Any) -> str:
        if not isinstance(identity, dict) or not all(isinstance(identity.get(k), str) and identity[k].strip()
                                                        for k in ("chain", "asset_id")):
            raise ValueError("identity requires stable chain and asset_id")
        return f"{identity['chain'].strip().lower()}:{identity['asset_id'].strip().lower()}"

    def _transition(self, row: sqlite3.Row, to_state: str, at: str, evidence: Any, reason: str) -> None:
        if to_state not in STATES or to_state not in TRANSITIONS[row["state"]]:
            raise ValueError(f"invalid state transition {row['state']} -> {to_state}")
        if not isinstance(evidence, list) or not evidence or any(not isinstance(item, dict) or not item.get("observed_at") for item in evidence):
            raise ValueError("every transition requires evidence with observed_at timestamps")
        for item in evidence:
            _stamp(item["observed_at"])
        self.db.execute("UPDATE candidates SET state=?, updated_at=? WHERE candidate_id=?", (to_state, at, row["candidate_id"]))
        self.db.execute("INSERT INTO transitions(candidate_id,from_state,to_state,transitioned_at,evidence,reason) VALUES(?,?,?,?,?,?)",
                        (row["candidate_id"], row["state"], to_state, at, _json(evidence), reason))

    def add(self, candidate: dict[str, Any], as_of: str) -> int:
        at = _stamp(as_of)
        ident = candidate.get("identity")
        key = self.identity_key(ident)
        required = ("thesis", "catalyst", "market_cap_tier", "liquidity_classification", "entry_trigger",
                    "invalidation_trigger", "confidence", "risk_assessment", "next_review_date")
        if any(candidate.get(k) in (None, "") for k in required):
            raise ValueError("candidate is missing required durable fields")
        if not isinstance(candidate["confidence"], (float, int)) or isinstance(candidate["confidence"], bool) or not 0 <= candidate["confidence"] <= 1:
            raise ValueError("confidence must be between 0 and 1")
        review = date.fromisoformat(candidate["next_review_date"])
        if review < at.date():
            raise ValueError("next_review_date cannot precede discovery")
        discovery_evidence = candidate.get("discovery_evidence", [])
        if not isinstance(discovery_evidence, list) or not discovery_evidence:
            raise ValueError("discovery requires timestamped evidence")
        for item in discovery_evidence:
            if not isinstance(item, dict):
                raise ValueError("discovery evidence must be objects")
            _stamp(item.get("observed_at"))
        expiry = at.date() + timedelta(days=6)
        expiration = candidate.get("expiration_conditions", "Expires after the seventh calendar day from discovery unless invalidated or archived sooner.")
        if not isinstance(expiration, str) or not expiration.strip():
            raise ValueError("expiration_conditions must be a non-empty explanation")
        cur = self.db.execute("""INSERT INTO candidates(identity_key,identity,discovered_on,expires_on,expiration_conditions,thesis,catalyst,
          market_cap_tier,liquidity_classification,entry_trigger,invalidation_trigger,confidence,risk_assessment,
          next_review_date,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, _json(ident), at.date().isoformat(), expiry.isoformat(), expiration, candidate["thesis"], _json(candidate["catalyst"]),
             candidate["market_cap_tier"], candidate["liquidity_classification"], _json(candidate["entry_trigger"]),
             _json(candidate["invalidation_trigger"]), candidate["confidence"], _json(candidate["risk_assessment"]),
             review.isoformat(), "DISCOVERED", at.isoformat(), at.isoformat()))
        cid = cur.lastrowid
        self.db.execute("INSERT INTO transitions(candidate_id,from_state,to_state,transitioned_at,evidence,reason) VALUES(?,?,?,?,?,?)",
                        (cid, None, "DISCOVERED", at.isoformat(), _json(discovery_evidence), "independently screened discovery"))
        self.db.commit()
        return cid

    def daily_run(self, packet: dict[str, Any]) -> dict[str, Any]:
        at = _stamp(packet.get("as_of"))
        stamp = at.isoformat()
        if not isinstance(packet.get("refreshes", []), list) or not isinstance(packet.get("screened_candidates", []), list):
            raise ValueError("refreshes and screened_candidates must be arrays")
        with self.db:
            # Refresh existing records first. Original thesis is immutable; material changes append annotations.
            for refresh in packet.get("refreshes", []):
                key = self.identity_key(refresh.get("identity"))
                row = self.db.execute("SELECT * FROM candidates WHERE identity_key=?", (key,)).fetchone()
                if row is None or row["state"] in TERMINAL:
                    continue
                observed = refresh.get("observations", [])
                if not isinstance(observed, list):
                    raise ValueError("observations must be an array")
                for obs in observed:
                    if not isinstance(obs, dict) or "observed_at" not in obs:
                        raise ValueError("supporting observations require observed_at")
                    _stamp(obs["observed_at"])
                    self.db.execute("INSERT INTO observations(candidate_id,observed_at,payload) VALUES(?,?,?)",
                                    (row["candidate_id"], _stamp(obs["observed_at"]).isoformat(), _json(obs)))
                changes = json.loads(row["material_changes"])
                if refresh.get("material_thesis_change"):
                    evidence = refresh.get("change_evidence", [])
                    if not evidence:
                        raise ValueError("material thesis changes require evidence")
                    for item in evidence: _stamp(item.get("observed_at"))
                    changes.append({"recorded_at": stamp, "change": refresh["material_thesis_change"], "evidence": evidence})
                confidence = refresh.get("confidence", row["confidence"])
                if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                    raise ValueError("refreshed confidence must be between 0 and 1")
                review_date = refresh.get("next_review_date", max(at.date().isoformat(), row["next_review_date"]))
                if date.fromisoformat(review_date) < at.date():
                    raise ValueError("refreshed next_review_date cannot precede the run date")
                updates = {"confidence": confidence,
                           "risk_assessment": _json(refresh.get("risk_assessment", json.loads(row["risk_assessment"]))),
                           "next_review_date": review_date,
                           "material_changes": _json(changes), "updated_at": stamp}
                self.db.execute("""UPDATE candidates SET confidence=:confidence,risk_assessment=:risk_assessment,
                  next_review_date=:next_review_date,material_changes=:material_changes,updated_at=:updated_at WHERE candidate_id=:id""",
                  {**updates, "id": row["candidate_id"]})
                row = self.db.execute("SELECT * FROM candidates WHERE candidate_id=?", (row["candidate_id"],)).fetchone()
                if refresh.get("invalidated"):
                    self._transition(row, "INVALIDATED", stamp, refresh.get("transition_evidence", []), "invalidation condition met")
                elif at.date() > date.fromisoformat(row["expires_on"]):
                    self._transition(row, "EXPIRED", stamp, refresh.get("transition_evidence", observed), "seven-day window elapsed")
                elif refresh.get("eligible_for_committee") and row["state"] == "TRIGGERED":
                    self._transition(row, "PROMOTED", stamp, refresh.get("transition_evidence", observed), "eligible for committee review")
                elif refresh.get("triggered") and row["state"] == "WATCHING":
                    self._transition(row, "TRIGGERED", stamp, refresh.get("transition_evidence", observed), "entry/confirmation trigger met")
                elif refresh.get("advance_to"):
                    self._transition(row, refresh["advance_to"], stamp, refresh.get("transition_evidence", observed), refresh.get("reason", "evidence-backed review"))
            # Expire unattended records with timestamped system evidence.
            rows = self.db.execute("SELECT * FROM candidates WHERE state NOT IN ('INVALIDATED','EXPIRED','ARCHIVED') AND expires_on < ?", (at.date().isoformat(),)).fetchall()
            for row in rows:
                self._transition(row, "EXPIRED", stamp, [{"source_id": "watchlist-clock", "observed_at": stamp, "value": row["expires_on"]}], "seven-day window elapsed")
            # Screened new additions are created last; uniqueness preserves expired/retired tombstones.
            for candidate in packet.get("screened_candidates", []):
                key = self.identity_key(candidate.get("identity"))
                if self.db.execute("SELECT 1 FROM candidates WHERE identity_key=?", (key,)).fetchone():
                    continue
                self.add(candidate, stamp)
        return self.ranked(at.date().isoformat())

    def ranked(self, as_of: str) -> dict[str, Any]:
        rows = self.db.execute("SELECT * FROM candidates ORDER BY confidence DESC,identity_key ASC").fetchall()
        live = [r for r in rows if r["state"] not in TERMINAL and r["discovered_on"] <= as_of <= r["expires_on"]]
        result = []
        for r in live:
            observations = self.db.execute("SELECT payload FROM observations WHERE candidate_id=? ORDER BY observed_at", (r["candidate_id"],)).fetchall()
            result.append({"identity": json.loads(r["identity"]), "state": r["state"], "discovered_on": r["discovered_on"],
                "expires_on": r["expires_on"], "expiration_conditions": r["expiration_conditions"],
                "thesis": r["thesis"], "catalyst": json.loads(r["catalyst"]),
                "market_cap_tier": r["market_cap_tier"], "liquidity_classification": r["liquidity_classification"],
                "entry_trigger": json.loads(r["entry_trigger"]), "invalidation_trigger": json.loads(r["invalidation_trigger"]),
                "observations": [json.loads(o["payload"]) for o in observations], "confidence": r["confidence"],
                "risk_assessment": json.loads(r["risk_assessment"]), "next_review_date": r["next_review_date"],
                "material_changes": json.loads(r["material_changes"]),
                "monitor_next": f"Review {r['next_review_date']}; check catalyst, entry trigger, invalidation trigger, and fresh liquidity evidence."})
        return {"as_of": as_of, "window_days": 7, "ranked_watchlist": result}

    def history(self, identity: dict[str, Any]) -> list[dict[str, Any]]:
        key = self.identity_key(identity)
        return [dict(r) | {"evidence": json.loads(r["evidence"])} for r in self.db.execute(
            "SELECT from_state,to_state,transitioned_at,evidence,reason FROM transitions WHERE candidate_id=(SELECT candidate_id FROM candidates WHERE identity_key=?) ORDER BY transition_id", (key,))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("packet", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        store = Watchlist(args.database)
        result = store.daily_run(json.loads(args.packet.read_text(encoding="utf-8"))) if args.packet else store.ranked(date.today().isoformat())
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output: args.output.write_text(rendered, encoding="utf-8")
        else: print(rendered, end="")
        store.close()
        return 0
    except (OSError, sqlite3.Error, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
