# Durable control-plane goal record

**Goal / observable outcome:** Build and verify a local-first, project-level Codex control surface for Small-Cap Crypto Daily research-to-newsletter work, with manifest-backed recommendations, safe execution boundaries, and an offline end-to-end acceptance path.

**Status:** offline acceptance complete; live research operation remains unconfigured and unverified.  
**Owner / resumption note:** Main implementation owner. Evidence and implementation plan are in `.codex/PROGRESS.md` and `.codex/IMPLEMENTATION_PLAN.md`.  
**Constraints / authorization:** Windows PowerShell target. No paid model launch, external publication, trade execution, global install, or remote mutation without separate explicit authorization. Keep subprocesses argument-array based, workspace paths bounded, reports credential-safe.

## Acceptance criteria and evidence

1. P0 doctor: implemented and tested offline; `doctor` probes version/config/workspace/instructions/skills without starting a model or exposing credentials.
2. P1 routing: implemented and tested against real installed manifests plus four checked-in fixtures; reasons, rejections, override validation, duplicate/missing abstention, and denominator-backed metrics are present.
3. P2 orchestration: implemented and tested offline; check-only is default, workspace/mode/profile validated, subprocess uses argv arrays with timeout and exit propagation.
4. End-to-end: synthetic nested workspace passes doctor/policy/discovery/routing/mock launch/artifact readback and newsletter render.
5. Packet behavior: no-pick packet check passes; renderer outputs a local 13-section edition.

## Explicit limits

CoinGecko and DexPaprika are enabled as project-level MCP read sources; CoinPaprika MCP is disabled until its tool schema is verified and allowlisted. The fixed CoinPaprika REST and DexScreener routes remain available under exact-host read policy. No live market/news data tool has been called. Paid operations and external publication remain disabled, and the project has not produced a current-market newsletter. The project does not enforce a per-run source-call quota; shared provider quotas apply. The Codex skill resolver is a recommendation and does not establish live Codex trigger accuracy. No paid or live model session was started. Git metadata is absent, so Git status/diff checks are unavailable. No separate reviewer was available under the active no-subagent instruction.

## Final evidence

See `.codex/IMPLEMENTATION_PLAN.md` for exact commands and results. The offline acceptance artifact is `.codex/results/offline-acceptance.json` with a companion local Markdown draft.
