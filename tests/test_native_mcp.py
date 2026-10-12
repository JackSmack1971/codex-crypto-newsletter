import unittest
import sys
import copy
import json
import queue
import time
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import native_mcp


def lifecycle(*, server="dexpaprika", tool="getTokenMultiPrices", result=None,
              status="completed", call_id="call-1", arguments=None, turn_status="completed"):
    args = arguments if arguments is not None else {"network": "ethereum", "tokens": ["0xabc"]}
    result = result if result is not None else {"structuredContent": {"price": 1.25, "token_id": "0xabc", "chain": "ethereum"}, "content": []}
    started = {"type": "mcpToolCall", "id": call_id, "server": server, "tool": tool, "arguments": args, "status": "inProgress"}
    completed = {**started, "status": status, "readOnlyHint": True, "result": result}
    return [
        {"method": "thread/started", "params": {"thread": {"id": "thread-1"}}},
        {"method": "turn/started", "params": {"threadId": "thread-1", "turn": {"id": "turn-1"}}},
        {"method": "item/started", "params": {"threadId": "thread-1", "turnId": "turn-1", "item": started}},
        {"method": "item/completed", "params": {"threadId": "thread-1", "turnId": "turn-1", "item": completed}},
        {"method": "turn/completed", "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": turn_status, "items": [copy.deepcopy(completed)]}}},
    ]


class NativeMcpTests(unittest.TestCase):
    def test_authorized_native_lifecycle_and_normalized_observation(self):
        result = native_mcp.validate_protocol_events(lifecycle(), request_id="req-1", provider="dexpaprika",
            tool="getTokenMultiPrices", expected_arguments={"network": "ethereum", "tokens": ["0xabc"]})
        self.assertEqual("VERIFIED", result["status"])
        self.assertEqual("thread-1", result["thread_id"])
        self.assertTrue(result["turn_success"])
        self.assertEqual("call-1", result["records"][0]["call_id"])
        self.assertEqual(1.25, result["observations"][0]["price"])
        self.assertEqual("dexpaprika-dex-data", result["observations"][0]["provider"])

    def test_missing_or_incomplete_lifecycle_evidence_is_unverified(self):
        events = lifecycle()
        result = native_mcp.validate_protocol_events([events[0], events[1], events[3], events[4]], request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])
        events = lifecycle(call_id=None)
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])

    def test_missing_thread_or_turn_correlation_is_unverified(self):
        events = lifecycle()
        del events[2]["params"]["turnId"]
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])

    def test_unauthorized_provider_or_tool_is_blocked(self):
        for provider, tool in (("coinpaprika", "search"), ("dexpaprika", "trade")):
            result = native_mcp.validate_protocol_events(lifecycle(), request_id="req", provider=provider, tool=tool)
            self.assertEqual("BLOCKED", result["status"])

    def test_unexpected_server_or_tool_identity_is_unverified(self):
        result = native_mcp.validate_protocol_events(lifecycle(server="other"), request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])

    def test_tool_without_read_only_annotation_is_unverified(self):
        events = lifecycle()
        events[2]["params"]["item"]["readOnlyHint"] = False
        events[3]["params"]["item"]["readOnlyHint"] = False
        events[4]["params"]["turn"]["items"][0]["readOnlyHint"] = False
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])
        result = native_mcp.validate_protocol_events(lifecycle(tool="getStats"), request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])

    def test_completed_tool_and_failed_enclosing_turn_are_separate_states(self):
        for turn_status in ("interrupted", "failed"):
            events = lifecycle(turn_status=turn_status)
            result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
            self.assertEqual("VERIFIED", result["status"])
            self.assertFalse(result["turn_success"])
            self.assertTrue(result["observations"])
        events = lifecycle(status="failed")
        events[3]["params"]["item"]["error"] = {"message": "provider failed; api_key=secret"}
        events[4]["params"]["turn"]["items"][0]["error"] = {"message": "provider failed; api_key=secret"}
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("FAILED", result["status"])
        self.assertNotIn("secret", str(result))
        self.assertTrue(result["events"])
        self.assertTrue(native_mcp.verify_event_hashes(result["events"]))
        result = native_mcp.execute(provider="dexpaprika", tool="getTokenMultiPrices", arguments={}, authorized=False)
        self.assertEqual("BLOCKED", result["status"])

    def test_malformed_provider_output_is_not_accepted(self):
        events = lifecycle(result={"content": [{"text": "not json"}]})
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])

    def test_response_without_resolvable_asset_identity_is_not_accepted(self):
        events = lifecycle(result={"structuredContent": {"price": 12.0}, "content": []})
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])
        self.assertEqual("provider_response_has_no_resolvable_asset_identity", result["reason"])

    def test_model_generated_summary_is_not_a_provider_result(self):
        events = [
            {"method": "thread/started", "params": {"thread": {"id": "thread-1"}}},
            {"method": "turn/started", "params": {"threadId": "thread-1", "turn": {"id": "turn-1"}}},
            {"method": "item/completed", "params": {"threadId": "thread-1", "turnId": "turn-1",
                "item": {"type": "agentMessage", "id": "message-1", "text": '{"price": 42}'}}},
            {"method": "turn/completed", "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed", "items": []}}},
        ]
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])
        self.assertFalse(result["observations"])

    def test_tool_arguments_must_correlate_with_authorized_request(self):
        result = native_mcp.validate_protocol_events(lifecycle(), request_id="req", provider="dexpaprika", tool="getTokenMultiPrices",
            expected_arguments={"network": "base", "tokens": ["0xabc"]})
        self.assertEqual("UNVERIFIED", result["status"])
        self.assertEqual("tool_arguments_do_not_match_request", result["reason"])

    def test_completed_item_without_started_item_is_rejected(self):
        events = lifecycle()
        events.pop(2)
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])
        self.assertEqual("completed_call_without_started_event", result["reason"])

    def test_credentials_are_redacted_from_provider_output(self):
        events = lifecycle(result={"structuredContent": {"price": 2, "token_id": "0xabc", "api_key": "secret", "note": "Bearer abcdef"}, "content": []})
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("VERIFIED", result["status"])
        self.assertNotIn("api_key", result["records"][0]["result"])
        self.assertNotIn("abcdef", str(result))
        self.assertIn("sha256", result["events"][0])
        self.assertIn("threadId", next(event for event in result["events"] if event["method"] == "item/started")["params"])
        self.assertTrue(native_mcp.verify_event_hashes(result["events"]))
        tampered = [dict(result["events"][0], method="changed"), *result["events"][1:]]
        self.assertFalse(native_mcp.verify_event_hashes(tampered))
        self.assertFalse(native_mcp.verify_event_hashes(result["events"][1:]))
        self.assertFalse(native_mcp.verify_event_hashes(list(reversed(result["events"]))))

    def test_unpaired_duplicate_conflicting_and_unrelated_events_are_rejected(self):
        events = lifecycle()
        events[2]["params"]["threadId"] = "other-thread"
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])

    def test_turn_completion_must_bind_to_the_active_thread_and_turn(self):
        events = lifecycle()
        events[-1]["params"]["threadId"] = "other-thread"
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("missing_or_mismatched_turn_thread", result["reason"])

    def test_any_thread_or_turn_scoped_notification_must_belong_to_execution(self):
        events = lifecycle()
        events.insert(2, {"method": "some/futureNotification", "params": {"threadId": "foreign"}})
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("unrelated_thread_event", result["reason"])
        events = lifecycle()
        events.insert(2, {"method": "some/futureNotification", "params": {"threadId": "thread-1", "turnId": "foreign"}})
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("unrelated_turn_event", result["reason"])
        events = lifecycle()
        events[-1]["params"]["turn"]["id"] = "other-turn"
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("missing_or_mismatched_turn_thread", result["reason"])

    def test_sensitive_arguments_are_denied_before_prompt_construction(self):
        result = native_mcp.execute(provider="dexpaprika", tool="getTokenMultiPrices",
            arguments={"api_key": "private"}, authorized=True)
        self.assertEqual("BLOCKED", result["status"])


class AppServerAdapterTests(unittest.TestCase):
    class StubServer:
        def __init__(self, command, cwd, timeout, *, scenario="success"):
            self.events = queue.Queue()
            self.deadline = time.monotonic() + 1
            self.scenario = scenario
            self.calls = []
            self.counter = 0

        def rpc(self, method, params, events):
            self.calls.append((method, params))
            if self.scenario == "init_failure" and method == "initialize":
                raise RuntimeError("rpc failed with api_key=hidden")
            if method == "thread/start":
                if self.scenario == "malformed_thread":
                    return {"thread": {"id": ""}}, events
                return {"thread": {"id": "thread-2" if self.scenario == "mismatched_thread" else "thread-1"}}, events
            if method == "turn/start":
                if self.scenario == "malformed_early_completion":
                    events.append({"method": "turn/completed", "params": []})
                    return {"turn": {"id": "turn-1"}}, events
                if self.scenario.startswith("malformed_after_turn_"):
                    malformed = {"array": [], "string": "invalid", "number": 42, "null": None}[self.scenario.rsplit("_", 1)[-1]]
                    self.events.put(malformed)
                    return {"turn": {"id": "turn-1"}}, events
                if self.scenario not in ("timeout", "timeout_cleanup_failure"):
                    for event in lifecycle():
                        self.events.put(event)
                if self.scenario == "missing_turn_response_id":
                    return {"turn": {}}, events
                return {"turn": {"id": "turn-2" if self.scenario == "mismatched_turn" else "turn-1"}}, events
            return {}, events

        def send(self, obj):
            self.calls.append((obj.get("method"), obj))

        def close(self):
            if self.scenario in ("cleanup_failure", "timeout_cleanup_failure"):
                raise OSError("cleanup failed api_key=cleanup-secret")

    def run_execute(self, scenario):
        server = self.StubServer(None, None, None, scenario=scenario)
        with mock.patch.object(native_mcp, "_AppServer", return_value=server), \
             mock.patch.object(native_mcp, "_codex_version", return_value="codex-cli 0.162.1"):
            result = native_mcp.execute(provider="dexpaprika", tool="getTokenMultiPrices",
                arguments={"network": "ethereum", "tokens": ["0xabc"]}, authorized=True,
                cwd=Path(__file__).resolve().parents[1], timeout=1)
        return result, server

    def test_mocked_app_server_rpc_lifecycle_and_record(self):
        result, server = self.run_execute("success")
        self.assertEqual("VERIFIED", result["status"])
        self.assertEqual(["initialize", "initialized", "thread/start", "turn/start"], [c[0] for c in server.calls])
        record = result["execution_record"]
        self.assertEqual(1, record["schema_version"])
        self.assertEqual(result["execution_id"], record["execution_id"])
        self.assertTrue(native_mcp.verify_event_hashes(record["native_events"]))

    def test_rpc_established_thread_and_turn_ids_must_match_notifications(self):
        for scenario, expected_reason in (("mismatched_thread", "thread_start_response_mismatch"),
                                          ("mismatched_turn", "turn_start_response_mismatch")):
            result, _ = self.run_execute(scenario)
            self.assertEqual("UNVERIFIED", result["status"])
            self.assertEqual(expected_reason, result["reason"])
            self.assertFalse(result["observations"])

    def test_malformed_early_completion_retains_structured_failure_record(self):
        result, _ = self.run_execute("malformed_early_completion")
        self.assertEqual("UNVERIFIED", result["status"])
        self.assertIn("execution_record", result)
        self.assertTrue(native_mcp.verify_event_hashes(result["events"]))

    def test_malformed_post_turn_notifications_retain_structured_failure_records(self):
        for value_type in ("array", "string", "number", "null"):
            result, _ = self.run_execute(f"malformed_after_turn_{value_type}")
            self.assertEqual("UNVERIFIED", result["status"])
            self.assertEqual("RuntimeError", result["reason"])
            self.assertIn("execution_record", result)
            self.assertTrue(native_mcp.verify_event_hashes(result["events"]))
            self.assertEqual("app-server/malformed", result["events"][0]["method"])

    def test_mocked_rpc_failure_and_timeout_retain_versioned_evidence(self):
        for scenario in ("init_failure", "timeout", "malformed_thread", "missing_turn_response_id", "cleanup_failure", "timeout_cleanup_failure"):
            result, _ = self.run_execute(scenario)
            self.assertEqual("UNVERIFIED", result["status"])
            self.assertIn("execution_record", result)
            self.assertEqual(result["execution_id"], result["execution_record"]["execution_id"])
            self.assertTrue(native_mcp.verify_event_hashes(result["events"]))
        result, _ = self.run_execute("cleanup_failure")
        self.assertEqual("app_server_cleanup_failed", result["reason"])
        self.assertEqual("app_server_cleanup_failed", result["execution_record"]["cleanup_error"])
        result, _ = self.run_execute("timeout_cleanup_failure")
        self.assertEqual("turn_timeout", result["reason"])
        self.assertEqual("app_server_cleanup_failed", result["execution_record"]["cleanup_error"])
        self.assertNotIn("cleanup-secret", str(result))
        self.assertFalse(result["observations"])
        self.assertTrue(native_mcp.verify_event_hashes(result["events"]))

    def test_json_rpc_transport_correlates_responses_and_rejects_malformed_objects(self):
        class Stdin:
            def write(self, value):
                self.value = value
            def flush(self):
                pass

        class Process:
            def __init__(self, lines):
                self.stdin = Stdin()
                self.stdout = iter(lines)
            def terminate(self): pass
            def wait(self, timeout=None): return 0
            def kill(self): pass

        notification = json.dumps({"method": "turn/started", "params": {"threadId": "thread-1"}})
        response = json.dumps({"id": 1, "result": {"ok": True}})
        events = []
        with mock.patch.object(native_mcp.subprocess, "Popen", return_value=Process([notification, response])):
            server = native_mcp._AppServer(["codex"], Path.cwd(), 1)
            result, events = server.rpc("initialize", {}, events)
            server.close()
        self.assertEqual({"ok": True}, result)
        self.assertEqual("turn/started", events[0]["method"])

        for malformed in ("[]", '"scalar"', "17", "null"):
            with mock.patch.object(native_mcp.subprocess, "Popen", return_value=Process([malformed])):
                server = native_mcp._AppServer(["codex"], Path.cwd(), 1)
                malformed_events = []
                with self.assertRaisesRegex(RuntimeError, "malformed_app_server_message"):
                    server.rpc("initialize", {}, malformed_events)
                self.assertEqual([{"_malformed": True}], malformed_events)
                self.assertTrue(native_mcp.verify_event_hashes(native_mcp._capture_native_events(malformed_events)[0]))
                server.close()
        events = lifecycle()
        events.insert(4, events[3])
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])
        events = lifecycle()
        events[4]["params"]["turn"]["items"][0]["status"] = "failed"
        result = native_mcp.validate_protocol_events(events, request_id="req", provider="dexpaprika", tool="getTokenMultiPrices")
        self.assertEqual("UNVERIFIED", result["status"])


if __name__ == "__main__":
    unittest.main()
