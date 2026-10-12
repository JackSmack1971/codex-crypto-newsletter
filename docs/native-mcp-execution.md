# Native Codex MCP execution adapter

The research adapter's `live-mcp` mode uses the installed Codex App Server protocol. It is a model-backed path and requires `--authorize-model-and-network`; no MCP invocation happens in replay mode or through MCP registration/discovery alone. The supported project server/tool allowlists and `.codex/source-policy.json` are both checked before starting Codex.

## Evidence contract (Codex CLI 0.162.1)

The generated schema bundle from `codex app-server generate-json-schema --out <dir>` was inspected for installed CLI `0.162.1` (2026-10-11). `v2/ItemStartedNotification.json` and `v2/ItemCompletedNotification.json` include `threadId`, `turnId`, and `item`. Their item union's `McpToolCallThreadItem` requires `id`, `server`, `tool`, `arguments`, `status`, and `type`; `result`, `error`, `readOnlyHint`, and duration are optional. The status enum is `inProgress`, `completed`, or `failed`. `v2/TurnCompletedNotification.json` supplies the enclosing `threadId` and `turn` (including its final status and items). The documentation describes `item/started` and `item/completed` as the authoritative item lifecycle and the final `item/completed` item as authoritative state.

| Evidence | Schema source | Treatment |
| --- | --- | --- |
| Item `id`, `server`, `tool`, `arguments`, `status`, `result`, `error` | `McpToolCallThreadItem` in the item union | Directly observed in `item/started` / `item/completed`; item ID pairs the lifecycle, server/tool and arguments must match the approved request, only terminal `completed` with no error can pass. |
| `threadId`, `turnId` | `ItemStartedNotification` and `ItemCompletedNotification` | Directly observed and required to match both lifecycle notifications and the active thread/turn context. |
| Thread/turn context and turn status | `ThreadStartedNotification`, `TurnStartedNotification`, `TurnCompletedNotification` | Bound from the App Server protocol notifications and the `thread/start` / `turn/start` results; tool completion and overall turn completion are stored separately. |
| Request and execution correlation UUIDs | No corresponding MCP item field | Generated locally and stored with native item/thread/turn identifiers; they are not claimed to be App Server event fields. |
| Data accuracy, freshness, independent corroboration | Not established by these schemas | Unavailable from protocol lifecycle evidence. Provider timestamps and source claims remain separately labeled; validation proves shape and identity only. |

The event item is distinguished from `agentMessage`: model-generated text is not a provider payload. The schema does not itself certify the accuracy of `result` content.

The adapter accepts a tool result only when it sees one matching start and completion with the same item ID, expected server and tool, exact requested arguments, verified read-only annotation, matching nonempty thread and turn identifiers, and a successful structured or JSON tool result. A turn item's terminal copy must agree with the lifecycle completion. Missing, duplicate, conflicting, unrelated, or unexpected evidence is `UNVERIFIED`; a failed tool call is `FAILED`. A tool call can be `VERIFIED` while `turn_success` is false; acquisition then reports `PARTIAL` and records both states. An interrupted or failed turn without a completed tool call contributes no observation.

The only provider payload accepted is `mcpToolCall.result.structuredContent`, or JSON parsed from that completed MCP result's text content. A model assistant message or summary is never parsed as provider data. `readOnlyHint` and the project tool allowlist are execution-scope signals, not proof that the source data is accurate, fresh, or independently corroborated.

## Records and normalization

Before normalization, the versioned execution record retains redacted `item/started`, `item/completed`, `turn/started`, and `turn/completed` evidence for successful and unsuccessful validation outcomes. Event records form a SHA-256 linked chain after redaction; dropped sensitive fields are listed by path. This proves integrity of sanitized snapshots only, not equivalence to original unredacted events. The record also contains a digest of the event list, call records and payload digests, Codex version, provider/tool identity, request and execution UUIDs, thread/turn IDs, tool-call status, and enclosing turn status. `native_mcp.verify_event_hashes` checks the chain. CLI output is replaced atomically, including failure outcomes. Payload digests are calculated over the original provider payload and do not retain the payload itself in clear form.

Validated output then enters the existing CP-003A observation and provenance envelope. The source is labeled `LIVE_RETRIEVED` only after a runtime MCP tool completion and output validation. Provider accuracy, freshness beyond provider timestamps, shared quotas, and independent corroboration remain outside this protocol evidence.

## Opt-in commands

Separate protocol smoke test:

```powershell
python tools/native_mcp.py --provider dexpaprika --tool getTokenMultiPrices --arguments '{"network":"ethereum","tokens":["0x..."]}' --authorize-model-and-network --output .codex/results/native-mcp-smoke.json
```

Orchestrated acquisition:

```powershell
python tools/daily_orchestrator.py --date YYYY-MM-DD --mode live-mcp --mcp-provider dexpaprika --mcp-tool getTokenMultiPrices --mcp-arguments '{"network":"ethereum","tokens":["0x..."]}' --authorize-model-and-network --output .codex/results/native-mcp-run
```

These commands start a Codex model session and make a network-backed MCP request. They were not run during offline acceptance. Only one allowlisted server/tool call is accepted per turn; execution is bounded to 90 seconds, Codex's MCP per-tool timeout remains configured at 30 seconds, and the App Server thread uses the `read-only` sandbox. `CP-003B.1` protocol compatibility/offline tests and `CP-003B.2` live runtime acceptance are separate states.

## Official references

- [Codex App Server](https://developers.openai.com/codex/app-server/)
- [Codex MCP configuration](https://developers.openai.com/codex/mcp/)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference/)
- [Codex CLI](https://developers.openai.com/codex/cli/)
- [Codex source](https://github.com/openai/codex)
