"""Opt-in Codex App Server MCP execution with evidence-backed acceptance."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import tomllib
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import research_sources
from controlplane import ControlPlaneError, authorize_source, load_source_policy

RECORD_SCHEMA_VERSION = 1
MAX_TURN_SECONDS = 90
MAX_OUTPUT_CHARS = 100_000
MAX_RESULT_BYTES = research_sources.MAX_RESPONSE_BYTES
APPROVED = {
    "coingecko": {"provider": "coingecko-market-data", "tools": {"execute"}},
    "dexpaprika": {"provider": "dexpaprika-dex-data", "tools": {
        "getNetworks", "getNetworkDexes", "getNetworkPools", "getDexPools", "getNetworkPoolsFilter",
        "getPoolDetails", "getPoolOHLCV", "getTokenDetails", "getTokenPools", "getTopTokens",
        "filterNetworkTokens", "getTokenMultiPrices", "search", "getStats"}},
}
SECRET_KEY = re.compile(r"authorization|api.?key|secret|password|bearer|access.?token|refresh.?token|private.?key|seed.?phrase|email|phone", re.I)
_APP_SERVER_EOF = object()


def _redact(value):
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items() if not SECRET_KEY.search(str(k))}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)(api[_-]?key|access[_-]?token|secret|password)(\s*[:=]\s*)[^\s,;]+", r"\1\2[REDACTED]", value)
        return value[:MAX_OUTPUT_CHARS]
    return value


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _event_item(event):
    params = event.get("params", {}) if isinstance(event, dict) else {}
    item = params.get("item") if isinstance(params, dict) else None
    return item if isinstance(item, dict) and item.get("type") == "mcpToolCall" else None


def verify_event_hashes(event_records):
    """Verify the redacted event snapshots persisted in an execution record."""
    if not isinstance(event_records, list):
        return False
    previous = None
    for record in event_records:
        if not isinstance(record, dict) or not isinstance(record.get("sha256"), str):
            return False
        if record.get("previous_sha256") != previous:
            return False
        body = {key: value for key, value in record.items() if key != "sha256"}
        if _digest(body) != record["sha256"]:
            return False
        previous = record["sha256"]
    return True


def _redact_with_markers(value, path="$", dropped=None):
    dropped = dropped if dropped is not None else []
    if isinstance(value, dict):
        output = {}
        for key, child in value.items():
            if SECRET_KEY.search(str(key)):
                dropped.append(f"{path}.{key}")
            else:
                output[key] = _redact_with_markers(child, f"{path}.{key}", dropped)
        return output
    if isinstance(value, list):
        return [_redact_with_markers(child, f"{path}[{index}]", dropped) for index, child in enumerate(value)]
    return _redact(value)


def _capture_native_events(events):
    records = []
    for event in events:
        if not isinstance(event, dict):
            continue
        method = event.get("method")
        params = event.get("params", {})
        if method in ("item/started", "item/completed") and _event_item(event):
            dropped = []
            safe_params = _redact_with_markers(params, dropped=dropped)
            records.append({"method": method, "params": safe_params, "redaction": {"dropped_fields": dropped}})
        elif method == "turn/started" and isinstance(params, dict):
            turn = params.get("turn", {})
            records.append({"method": method, "params": {"threadId": params.get("threadId"),
                "turn": {"id": turn.get("id")} if isinstance(turn, dict) else {}}})
        elif method == "turn/completed" and isinstance(params, dict):
            turn = params.get("turn", {})
            records.append({"method": method, "params": {"threadId": params.get("threadId"),
                "turn": {"id": turn.get("id"), "status": turn.get("status")} if isinstance(turn, dict) else {}}})
        elif isinstance(method, str):
            dropped = []
            safe_params = _redact_with_markers(params, dropped=dropped)
            records.append({"method": method, "params": safe_params, "redaction": {"dropped_fields": dropped}})
        elif event.get("_malformed"):
            records.append({"method": "app-server/malformed", "params": {"message": "invalid_json"},
                            "redaction": {"dropped_fields": []}})
    previous = None
    for record in records:
        record["previous_sha256"] = previous
        record["sha256"] = _digest(record)
        previous = record["sha256"]
    if len(json.dumps(records, ensure_ascii=False).encode("utf-8")) > 1_100_000:
        return [], "event_capture_exceeds_size_limit"
    return records, None


def validate_protocol_events(events, *, request_id, provider, tool, expected_arguments=None, thread_id=None, turn_id=None):
    """Validate actual App Server lifecycle evidence; malformed/absent evidence fails closed."""
    event_records, capture_error = _capture_native_events(events)
    approved = APPROVED.get(provider)
    if not approved or tool not in approved["tools"]:
        return {"status": "BLOCKED", "reason": "unauthorized_provider_or_tool", "observations": [], "events": event_records}
    if capture_error:
        return {"status": "UNVERIFIED", "reason": capture_error, "observations": [], "events": event_records}
    started, completed, turn_status = {}, {}, None
    expected_thread_id = thread_id
    thread_started_id = None
    turn_thread_id = None
    active_turn_id = None
    completed_turn_id = None
    for event in events:
        if not isinstance(event, dict):
            continue
        method = event.get("method")
        params = event.get("params") if isinstance(event.get("params"), dict) else {}
        if method == "thread/started":
            thread = params.get("thread")
            if isinstance(thread, dict):
                observed = thread.get("id")
                if thread_started_id is not None and observed != thread_started_id:
                    return {"status": "UNVERIFIED", "reason": "conflicting_thread_context", "observations": [], "events": event_records}
                thread_started_id = observed
        if method == "turn/started":
            turn = params.get("turn")
            if isinstance(turn, dict):
                observed_turn_thread_id, observed_turn_id = params.get("threadId"), turn.get("id")
                if ((turn_thread_id is not None and observed_turn_thread_id != turn_thread_id) or
                        (active_turn_id is not None and observed_turn_id != active_turn_id)):
                    return {"status": "UNVERIFIED", "reason": "conflicting_turn_context", "observations": [], "events": event_records}
                turn_thread_id, active_turn_id = observed_turn_thread_id, observed_turn_id
        if method in ("item/started", "item/completed"):
            item = _event_item(event)
            if not item:
                continue
            target = started if method == "item/started" else completed
            call_id = item.get("id")
            if not call_id:
                return {"status": "UNVERIFIED", "reason": "missing_call_item_id", "observations": [], "events": event_records}
            if call_id in target:
                return {"status": "UNVERIFIED", "reason": "duplicate_call_lifecycle_event", "observations": [], "events": event_records}
            if method == "item/completed" and call_id not in started:
                return {"status": "UNVERIFIED", "reason": "completed_call_without_started_event", "observations": [], "events": event_records}
            target[call_id] = item
        if method == "turn/completed":
            turn = params.get("turn")
            if isinstance(turn, dict):
                if expected_thread_id and params.get("threadId") != expected_thread_id:
                    return {"status": "UNVERIFIED", "reason": "thread_start_response_mismatch", "observations": [], "events": event_records}
                if (params.get("threadId") != turn_thread_id or params.get("threadId") != thread_started_id or
                        turn.get("id") != active_turn_id):
                    return {"status": "UNVERIFIED", "reason": "missing_or_mismatched_turn_thread", "observations": [], "events": event_records}
                turn_status = turn.get("status")
                completed_turn_id = turn.get("id")
                for item in turn.get("items", []):
                    if isinstance(item, dict) and item.get("type") == "mcpToolCall":
                        call_id = item.get("id")
                        if call_id not in completed and call_id not in started:
                            return {"status": "UNVERIFIED", "reason": "completed_call_without_started_event", "observations": [], "events": event_records}
                        if call_id in completed and completed[call_id] != item:
                            return {"status": "UNVERIFIED", "reason": "conflicting_terminal_call_record", "observations": [], "events": event_records}
    if not thread_started_id or not turn_thread_id or not active_turn_id:
        return {"status": "UNVERIFIED", "reason": "missing_thread_or_turn_context", "observations": [], "events": event_records}
    if expected_thread_id and thread_started_id != expected_thread_id:
        return {"status": "UNVERIFIED", "reason": "thread_start_response_mismatch", "observations": [], "events": event_records}
    if expected_thread_id and turn_thread_id != expected_thread_id:
        return {"status": "UNVERIFIED", "reason": "turn_thread_response_mismatch", "observations": [], "events": event_records}
    if turn_id and active_turn_id != turn_id:
        return {"status": "UNVERIFIED", "reason": "turn_start_response_mismatch", "observations": [], "events": event_records}
    if completed_turn_id and completed_turn_id != active_turn_id:
        return {"status": "UNVERIFIED", "reason": "completed_turn_id_mismatch", "observations": [], "events": event_records}
    for event in events:
        if not isinstance(event, dict):
            continue
        params = event.get("params")
        if not isinstance(params, dict):
            continue
        if params.get("threadId") is not None and params.get("threadId") != thread_started_id:
            return {"status": "UNVERIFIED", "reason": "unrelated_thread_event", "observations": [], "events": event_records}
        if params.get("turnId") is not None and params.get("turnId") != active_turn_id:
            return {"status": "UNVERIFIED", "reason": "unrelated_turn_event", "observations": [], "events": event_records}
    if set(completed) - set(started):
        return {"status": "UNVERIFIED", "reason": "completed_call_without_started_event", "observations": [], "events": event_records}
    records = []
    for call_id, item in completed.items():
        first = started.get(call_id)
        # A final turn item alone can be authoritative but requires a matching started lifecycle event
        # for native invocation proof, avoiding stale/history-only items.
        if not call_id or not first:
            continue
        started_params = next((e.get("params", {}) for e in events if e.get("method") == "item/started" and _event_item(e) and _event_item(e).get("id") == call_id), {})
        completed_params = next((e.get("params", {}) for e in events if e.get("method") == "item/completed" and _event_item(e) and _event_item(e).get("id") == call_id), {})
        if (not started_params.get("threadId") or not started_params.get("turnId") or
                started_params.get("threadId") != completed_params.get("threadId") or
                started_params.get("turnId") != completed_params.get("turnId") or
                (thread_started_id and started_params.get("threadId") != thread_started_id) or
                (turn_thread_id and started_params.get("threadId") != turn_thread_id) or
                (active_turn_id and started_params.get("turnId") != active_turn_id) or
                (turn_id and started_params.get("turnId") != turn_id)):
            return {"status": "UNVERIFIED", "reason": "missing_or_mismatched_thread_turn_correlation", "observations": [], "events": event_records}
        if item.get("server") != provider or item.get("tool") != tool:
            return {"status": "UNVERIFIED", "reason": "unexpected_server_or_tool_identity", "observations": [], "events": event_records}
        if first.get("server") != provider or first.get("tool") != tool or first.get("status") != "inProgress":
            return {"status": "UNVERIFIED", "reason": "unexpected_started_identity", "observations": [], "events": event_records}
        if item.get("readOnlyHint") is not True:
            return {"status": "UNVERIFIED", "reason": "tool_not_verified_read_only", "observations": [], "events": event_records}
        if expected_arguments is not None and (item.get("arguments") != expected_arguments or first.get("arguments") != expected_arguments):
            return {"status": "UNVERIFIED", "reason": "tool_arguments_do_not_match_request", "observations": [], "events": event_records}
        status = item.get("status")
        if status != "completed" or item.get("error"):
            records.append({"call_id": call_id, "status": "FAILED", "error": _redact(item.get("error"))})
            continue
        result = item.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("content"), list):
            return {"status": "UNVERIFIED", "reason": "malformed_tool_result", "observations": [], "events": event_records}
        payload = result.get("structuredContent")
        if payload is None:
            for content in result["content"]:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    try:
                        payload = json.loads(content["text"])
                        break
                    except json.JSONDecodeError:
                        continue
        if not isinstance(payload, (dict, list)):
            return {"status": "UNVERIFIED", "reason": "malformed_provider_response", "observations": [], "events": event_records}
        raw = payload
        try:
            if len(json.dumps(raw, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_RESULT_BYTES:
                return {"status": "UNVERIFIED", "reason": "provider_response_exceeds_size_limit", "observations": [], "events": event_records}
        except (TypeError, ValueError):
            return {"status": "UNVERIFIED", "reason": "malformed_provider_response", "observations": [], "events": event_records}
        safe = _redact(raw)
        normalized = research_sources.normalize_observation(approved["provider"], safe)
        if not normalized or not any(any(row.get(key) is not None for key in ("price", "market_cap", "volume", "liquidity", "exchange", "chain", "contract_address", "token_id")) for row in normalized):
            return {"status": "UNVERIFIED", "reason": "provider_response_has_no_normalizable_observations", "observations": [], "events": event_records}
        try:
            for row in normalized:
                research_sources._canonical_identity(row)
        except ValueError:
            return {"status": "UNVERIFIED", "reason": "provider_response_has_no_resolvable_asset_identity", "observations": [], "events": event_records}
        records.append({"call_id": call_id, "status": "SUCCESS", "result": safe, "normalized": normalized,
                        "content_sha256": _digest(raw), "normalized_sha256": _digest(normalized)})
    successful = [r for r in records if r["status"] == "SUCCESS"]
    failed = [r for r in records if r["status"] == "FAILED"]
    if not records:
        status, reason = "UNVERIFIED", "missing_tool_call_lifecycle_evidence"
    elif failed:
        status, reason = "FAILED", "tool_call_failed"
    elif len(successful) != 1:
        status, reason = "UNVERIFIED", "expected_exactly_one_authorized_tool_call"
    else:
        status, reason = "VERIFIED", None
    return {"status": status, "reason": reason, "request_id": request_id, "thread_id": thread_started_id,
            "turn_id": active_turn_id, "turn_status": turn_status, "turn_success": turn_status == "completed",
            "provider": provider, "tool": tool, "records": records,
            "observations": successful[0]["normalized"] if status == "VERIFIED" else [],
            "events": event_records}


class _AppServer:
    def __init__(self, command, cwd, timeout):
        self.process = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        self.events = queue.Queue()
        self.timeout = timeout
        self.deadline = time.monotonic() + timeout
        threading.Thread(target=self._read, daemon=True).start()
        self.counter = 0

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.events.put(json.loads(line))
                except json.JSONDecodeError:
                    self.events.put({"_malformed": True})
        finally:
            self.events.put(_APP_SERVER_EOF)

    def send(self, obj):
        self.process.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def rpc(self, method, params, events):
        self.counter += 1
        request_id = self.counter
        self.send({"id": request_id, "method": method, "params": params})
        deadline = min(self.deadline, time.monotonic() + self.timeout)
        while time.monotonic() < deadline:
            event = self.events.get(timeout=max(.01, deadline - time.monotonic()))
            if event is _APP_SERVER_EOF:
                raise RuntimeError("app_server_exited")
            if not isinstance(event, dict):
                events.append({"_malformed": True})
                raise RuntimeError("malformed_app_server_message")
            if "method" not in event and event.get("id") == request_id and ("result" in event or "error" in event):
                if "error" in event:
                    raise RuntimeError("app_server_rpc_failed")
                return event.get("result"), events
            events.append(event)
        raise TimeoutError("app_server_timeout")

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()


def execute(*, provider, tool, arguments, authorized=False, cwd=None, timeout=MAX_TURN_SECONDS, codex="codex"):
    """Run one explicitly authorized model-backed MCP turn through Codex App Server."""
    request_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    approved = APPROVED.get(provider)
    if authorized is not True:
        return {"status": "BLOCKED", "reason": "explicit_model_and_network_authorization_required", "request_id": request_id, "observations": []}
    if not approved or tool not in approved["tools"] or not isinstance(arguments, dict):
        return {"status": "BLOCKED", "reason": "unauthorized_provider_or_tool", "request_id": request_id, "observations": []}
    try:
        if any(SECRET_KEY.search(str(key)) for key in arguments):
            return {"status": "BLOCKED", "reason": "sensitive_argument_key_denied", "request_id": request_id, "observations": []}
        if len(json.dumps(arguments, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 8_000:
            return {"status": "BLOCKED", "reason": "arguments_exceed_size_limit", "request_id": request_id, "observations": []}
    except (TypeError, ValueError):
        return {"status": "BLOCKED", "reason": "malformed_arguments", "request_id": request_id, "observations": []}
    if not 1 <= timeout <= MAX_TURN_SECONDS:
        return {"status": "BLOCKED", "reason": "timeout_out_of_bounds", "request_id": request_id, "observations": []}
    cwd = Path(cwd or Path.cwd()).resolve()
    try:
        policy = load_source_policy(cwd / ".codex" / "source-policy.json")
    except (ControlPlaneError, OSError):
        return {"status": "BLOCKED", "reason": "source_policy_unavailable_or_invalid", "request_id": request_id, "observations": []}
    source = APPROVED[provider]["provider"]
    host = {"coingecko": "mcp.api.coingecko.com", "dexpaprika": "mcp.dexpaprika.com"}[provider]
    decision = authorize_source(policy, source, "read", f"https://{host}/", 0)
    if decision["status"] != "ALLOW":
        return {"status": "BLOCKED", "reason": "source_policy_denied", "request_id": request_id, "observations": []}
    config_path = cwd / ".codex" / "config.toml"
    try:
        project_config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"status": "BLOCKED", "reason": "project_mcp_config_unavailable_or_invalid", "request_id": request_id, "observations": []}
    server_config = project_config.get("mcp_servers", {}).get(provider, {})
    expected_urls = {"coingecko": "https://mcp.api.coingecko.com/mcp",
                     "dexpaprika": "https://mcp.dexpaprika.com/streamable-http"}
    configured_url = server_config.get("url")
    parsed_url = urlparse(configured_url) if isinstance(configured_url, str) else None
    if (server_config.get("enabled") is not True or tool not in server_config.get("enabled_tools", []) or
            configured_url != expected_urls[provider] or not parsed_url or parsed_url.scheme != "https"):
        return {"status": "BLOCKED", "reason": "project_mcp_allowlist_denied", "request_id": request_id, "observations": []}
    events = []
    server = None
    thread_id = None
    expected_turn_id = None
    turn = {}
    outcome = None

    def runtime_result(reason, status="UNVERIFIED"):
        captured, _ = _capture_native_events(events)
        result = {"status": status, "reason": reason, "request_id": request_id, "execution_id": execution_id,
                  "thread_id": thread_id, "turn_id": expected_turn_id,
                  "turn_status": turn.get("status"), "turn_success": turn.get("status") == "completed",
                  "provider": provider, "tool": tool, "records": [], "observations": [], "events": captured}
        record = {"schema_version": RECORD_SCHEMA_VERSION, "request_id": request_id, "execution_id": execution_id,
                  "recorded_at": datetime.now(timezone.utc).isoformat(), "codex_version": _codex_version(codex),
                  "status": status, "reason": reason, "provider": provider, "tool": tool,
                  "thread_id": thread_id, "turn_id": expected_turn_id, "turn_status": turn.get("status"),
                  "turn_success": turn.get("status") == "completed", "calls": [],
                  "event_sha256": _digest(captured), "native_events": captured}
        record["calls_sha256"] = _digest([])
        result["execution_record"] = record
        return result
    try:
        server = _AppServer([codex, "app-server", "--listen", "stdio://"], cwd, timeout)
        _, events = server.rpc("initialize", {"clientInfo": {"name": "cp003b-research-adapter", "title": "CP-003B Research Adapter", "version": "1"}}, events)
        server.send({"method": "initialized"})
        result, events = server.rpc("thread/start", {"cwd": str(cwd), "approvalPolicy": "on-request", "sandbox": "read-only"}, events)
        thread_obj = result.get("thread") if isinstance(result, dict) else None
        thread_id = thread_obj.get("id") if isinstance(thread_obj, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise ValueError("missing_thread_id")
        prompt = ("Use exactly one MCP tool call to answer the read-only research request. "
                  "Do not call other tools. Return provider data as tool output. "
                  f"Requested server={provider}, tool={tool}, arguments={json.dumps(arguments, separators=(',', ':'))}")
        turn_result, events = server.rpc("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]}, events)
        turn_obj = turn_result.get("turn") if isinstance(turn_result, dict) else None
        expected_turn_id = turn_obj.get("id") if isinstance(turn_obj, dict) else None
        if not isinstance(expected_turn_id, str) or not expected_turn_id:
            raise ValueError("missing_turn_id")
        # A completion notification can arrive before the turn/start RPC response.
        early_completion = next((e for e in reversed(events) if isinstance(e, dict) and e.get("method") == "turn/completed"), None)
        if early_completion:
            early_params = early_completion.get("params") if isinstance(early_completion.get("params"), dict) else {}
            turn = early_params.get("turn", {})
            if not isinstance(turn, dict):
                turn = {}
            validated = validate_protocol_events(events, request_id=request_id, provider=provider, tool=tool,
                expected_arguments=arguments, thread_id=thread_id, turn_id=expected_turn_id)
            validated["execution_id"] = execution_id
            validated["execution_record"] = {"schema_version": RECORD_SCHEMA_VERSION, "request_id": request_id, "execution_id": execution_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(), "codex_version": _codex_version(codex),
                "status": validated["status"], "provider": provider, "tool": tool,
                "thread_id": validated.get("thread_id"), "turn_id": validated.get("turn_id"),
                "turn_status": validated.get("turn_status"), "turn_success": validated.get("turn_success", False),
                "calls": _redact(validated.get("records", [])), "event_sha256": _digest(_redact(validated["events"])),
                "native_events": validated["events"]}
            validated["execution_record"]["calls_sha256"] = _digest(validated.get("records", []))
            outcome = validated
            return outcome
        deadline = server.deadline
        while time.monotonic() < deadline:
            event = server.events.get(timeout=max(.01, deadline-time.monotonic()))
            if event is _APP_SERVER_EOF:
                raise RuntimeError("app_server_exited")
            events.append(event)
            if event.get("method") == "turn/completed":
                params = event.get("params") if isinstance(event.get("params"), dict) else {}
                turn = params.get("turn", {})
                if not isinstance(turn, dict):
                    turn = {}
                validated = validate_protocol_events(events, request_id=request_id, provider=provider, tool=tool,
                                                     expected_arguments=arguments, thread_id=thread_id,
                                                     turn_id=expected_turn_id)
                validated["thread_id"] = thread_id
                validated["execution_id"] = execution_id
                validated["execution_record"] = {"schema_version": RECORD_SCHEMA_VERSION,
                    "request_id": request_id, "execution_id": execution_id, "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "codex_version": _codex_version(codex), "status": validated["status"],
                    "provider": provider, "tool": tool, "turn_status": turn.get("status"),
                    "turn_success": validated.get("turn_success", False), "calls": _redact(validated.get("records", [])),
                    "event_sha256": _digest(_redact(validated["events"])), "native_events": validated["events"]}
                validated["execution_record"]["calls_sha256"] = _digest(validated.get("records", []))
                outcome = validated
                return outcome
        outcome = runtime_result("turn_timeout")
        return outcome
    except (OSError, RuntimeError, ValueError, TimeoutError, queue.Empty) as exc:
        outcome = runtime_result("turn_timeout" if isinstance(exc, queue.Empty) else type(exc).__name__)
        return outcome
    finally:
        if server:
            try:
                server.close()
            except Exception:
                if outcome is not None:
                    outcome["cleanup_error"] = "app_server_cleanup_failed"
                    record = outcome.get("execution_record")
                    if isinstance(record, dict):
                        record["cleanup_error"] = outcome["cleanup_error"]
                        record["cleanup_error_sha256"] = _digest(outcome["cleanup_error"])
                    if outcome.get("status") == "VERIFIED":
                        outcome["status"] = "UNVERIFIED"
                        outcome["reason"] = "app_server_cleanup_failed"
                        if isinstance(record, dict):
                            record["status"] = "UNVERIFIED"
                            record["reason"] = "app_server_cleanup_failed"


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=sorted(APPROVED))
    parser.add_argument("--tool", required=True)
    parser.add_argument("--arguments", required=True, help="JSON object containing tool arguments")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-model-and-network", action="store_true")
    args = parser.parse_args(argv)
    try:
        arguments = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    result = execute(provider=args.provider, tool=args.tool, arguments=arguments,
                     authorized=args.authorize_model_and_network)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + f".{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(_redact(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, args.output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps({"status": result["status"], "reason": result.get("reason"), "request_id": result["request_id"]}))
    return 0 if result["status"] == "VERIFIED" else 2


def _codex_version(binary):
    try:
        completed = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5, check=False)
        value = completed.stdout.strip()
        return value if completed.returncode == 0 and value and len(value) < 100 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
