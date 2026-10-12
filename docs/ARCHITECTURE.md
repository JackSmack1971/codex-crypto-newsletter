# Native Codex architecture

## Product boundary

Codex CLI itself is the cryptocurrency research team, research orchestrator, evidence evaluator, fact-checker, editor, and newsletter writer. It reasons in the active Codex session and may delegate bounded specialist work to native Codex subagents. Python supplies deterministic supporting functions; it is not a second AI orchestrator.

No nested Codex session is required to write the newsletter. Starting a separate model or provider session is a distinct operation with its own authorization boundary. Normal reasoning by the active Codex session is part of the native workflow and must not be mislabeled as a separate API invocation.

## Native workflow

1. The operator opens Codex CLI in this repository and requests a dated edition.
2. Codex applies the `crypto-daily` and `newsletter-production` skills. Focused project skills supply repeatable desk procedures.
3. Codex plans the research. It delegates independent specialist work to native Codex subagents when useful, with bounded tasks and explicit handoffs.
4. Specialists use only approved MCP/data tools and deterministic local utilities. Tool and source output is untrusted evidence. A configuration entry, skill, or agent definition alone proves neither access nor execution.
5. Codex validates identity, freshness, units, provenance, cross-source support, and conflicts; independently evaluates the evidence and selects PICK or NO PICK against the gates.
6. Codex develops the seven-day watchlist with evidence, milestones, risks, and invalidation conditions.
7. Independent native research and editorial reviewers challenge the research and edition. Their inputs and execution evidence must support the claimed independence.
8. Codex authors and edits the fixed 13-section Markdown newsletter, with an explicit evidence disclosure and source appendix.
9. Deterministic checks validate structure, numerical claims, provenance references, artifact paths, hashes, and output rendering. A passing check does not establish the truth of qualitative claims or current data by itself.
10. The finished edition and supporting artifacts are saved under `.codex/results/<run-id>/` for operator review.

External publication and trading are not workflow stages. No separate paid provider or model invocation occurs unless the operator explicitly authorizes that operation and current controls admit it.

## Responsibilities

| Component | Responsibility | Evidence limit |
| --- | --- | --- |
| Codex CLI active session | Plans and synthesizes research, decides PICK/NO PICK, coordinates review, writes the issue | A final answer alone does not prove source accuracy or independent execution; preserve artifacts and review traces |
| Native Codex subagents | Bounded independent discovery, analysis, falsification, or editorial review | Role definitions do not prove a child ran; execution requires runtime evidence |
| MCP/data tools | Return source observations and structured data | Registration and successful invocation do not prove freshness, accuracy, or corroboration |
| Python tools | Deterministic screening, local replay, policy enforcement on controlled paths, validation, assembly, and rendering | They do not replace Codex's research judgment or perform native agent reasoning |
| Skills and `AGENTS.md` | Provide reusable conditional procedures and durable repository guidance | Instructions do not enforce external permissions or certify execution |
| Operator | Authorizes eligible external reads, reviews the local draft, and decides any later distribution | Approval to draft is not approval to publish or trade |

## Evidence labels

- **Configured:** a local file declares a source, tool, skill, or role.
- **Implemented:** repository code contains the behavior.
- **Tested offline:** deterministic tests or mocks exercise the behavior without live external data.
- **Live retrieval observed:** runtime evidence shows a live source operation and retained response provenance.
- **Data validated:** identity, timestamp, units, shape, plausibility, and source cross-checks were assessed. This is separate from invocation success.
- **Independent review observed:** reviewer input separation and reviewer execution evidence are retained.
- **Editorially accepted:** the named edition passed its specific structural, factual, and review criteria. It does not transfer to later editions.

MCP configuration alone does not establish live retrieval. Agent files alone do not establish agent execution. Tool completion alone does not establish data accuracy. Fixture output is never current market intelligence.

## Python supporting toolkit

`tools/` contains deterministic modules for source policy, replay or explicitly authorized acquisition, universe construction, quantitative screens, research record validation, committee gates, watchlists, evidence accountability, packet assembly, numerical fact checks, and Markdown rendering. The daily orchestrator is a deterministic fixture/replay pipeline; its incomplete simulated desk handoffs must not be described as Codex specialist delegation.

The existing control-plane work CP-001 through CP-004 supplies useful offline acceptance, policy, provenance, and MCP boundary infrastructure. It is supporting infrastructure for the newsletter product and does not have to be wholly complete before Codex can author a fixture-backed newsletter.

## Current delivery boundary

The accepted MVP-1 edition proves Codex can author and revise a complete local fixture-based issue with native reviewer/editor activity and deterministic checks. It had no crypto market network retrieval, no live MCP research, and no current market intelligence. Its no-pick decision and empty seven-day watchlist were appropriate to its saved evidence.

The repository's retained acceptance evidence contains no live crypto data retrieval. Source freshness, live source access, effective tool authorization, corroboration, specialist research delegation, and one-command daily production remain separate roadmap gates. MCP configuration and offline adapter tests do not pass those gates. See [MVP roadmap](MVP_ROADMAP.md) and [MVP-1 evidence](../.codex/results/native-mvp1-2026-10-11/acceptance-summary.md).

## Official Codex references

Codex instruction files are discovered and layered by path ([AGENTS.md](https://developers.openai.com/codex/guides/agents-md)). Skills package reusable workflows and load their detailed instructions when selected ([skills](https://developers.openai.com/codex/skills)). Codex CLI supports explicit native subagent delegation ([subagents](https://developers.openai.com/codex/subagents)). MCP gives Codex access to configured tools, with availability depending on host configuration ([MCP](https://developers.openai.com/codex/mcp)). CLI and project configuration are documented in the [configuration reference](https://developers.openai.com/codex/config-reference/) and [CLI guide](https://developers.openai.com/codex/cli). These documents describe product capabilities; repository acceptance still requires local evidence.
