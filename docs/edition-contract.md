# Edition packet contract (v1)

> Product responsibility: the active Codex CLI session researches, decides, fact-checks, edits, and authors the newsletter. Python implements the deterministic packet validator, claim checker, assembler, and local Markdown renderer described below. The packet contract does not designate Python as the AI orchestrator or establish that supplied research is current or accurate. See [native Codex architecture](ARCHITECTURE.md).

The control surface accepts a JSON packet created by an authorized research process. It does not fetch market data or verify source contents. All timestamps use ISO 8601; source URLs must be absolute HTTP(S) URLs.

## Required fields

- `edition.date`: publication date (`YYYY-MM-DD`)
- `edition.cutoff_utc`: ISO 8601 cutoff timestamp
- `edition.status`: `draft` or `approved`
- `edition.regime`: short human-written regime description
- `sections`: object keyed by every slug below; each value has non-empty `content` and a list of `source_ids`
- `sources`: array of unique `{id, label, url, accessed_utc}` records
- `pick`: `{status: "NO_PICK"}` or candidate details and review gates
- `editorial_approval`: boolean; required to render with `--release`

The edition has thirteen sections in this exact order:

1. `small-cap-crypto-daily`
2. `market-in-90-seconds`
3. `market-dashboard`
4. `whats-moving`
5. `under-the-radar`
6. `todays-deep-dive`
7. `small-cap-leaderboard`
8. `pick-of-the-day`
9. `risk-desk`
10. `previous-pick-accountability`
11. `watchlist`
12. `bottom-line`
13. `sources-method-and-research-appendix`

## Persisted-artifact production

`python tools/newsletter.py assemble <manifest.json> --output <packet.json>` builds a v1 packet from project-local JSON artifacts. The manifest has the same `edition` and `sources` fields as the packet and an `artifacts` object with paths for `market`, `screening`, `committee`, `watchlist`, `accountability`, `methodology`, and exactly nine `desks` reports. Source records may include `artifact_keys` to bind a source to named manifest artifact keys; source IDs embedded in artifact evidence are also mapped to their corresponding sections. The appendix lists the full source manifest. Paths resolve relative to the manifest and must remain inside the project. Assembly is offline and read-only apart from its explicitly named packet output. A committee `PICK` without packet-level frozen reviewer evidence is represented as NO PICK with the missing evidence disclosed.

Assembly creates a structured evidence draft for the newsletter editor. The read-only `newsletter-editor` agent contract requires an opening summary, honest market/sector context, a supported pick or NO PICK, watchlist rationale and conditions, risk discussion, citations, and explicit evidence gaps. After editorial revision, run `python tools/newsletter.py fact-check <packet.json> --manifest <manifest.json>` before `check` and `render`. Every material number in edited section prose must have an `editorial_claims` record containing `section`, exact `text`, exact `value`, `artifact`, `json_pointer`, and known `source_ids`. The checker resolves the JSON Pointer, compares the exact value, and checks section numerical tokens against persisted evidence. Unsupported or unregistered numerical claims fail. This is a separate stage from packet shape validation.

The assembler retains the v1 packet schema, thirteen slugs, NO PICK behavior, and local Markdown output. No posting or distribution action is available.

For `pick.status: "PICK"`, require `asset`, `ticker`, all eight `gates` set to `PASS`, frozen reviewer inputs, and a structured adversarial challenge report. The eight gate keys are `identity`, `market_data`, `liquidity`, `supply`, `security`, `catalyst`, `token_value_capture`, and `risk`. The review input digest must match the exact identity, thesis, observations, and calculations reviewed. The report must assess all twelve dimensions defined in `tools/adversarial_review.py`; contradictions or unresolved issues prevent PASS. `newsletter.validate(..., reviewer_runtime_event_ids=...)` requires the reviewer execution event ID to come from coordinator-observed runtime events. A report's own `independent` flag, verdict, or event string cannot establish provenance. The file-based `newsletter.py check` command has no Codex runtime event feed, so it fails closed on PICK packets until an observed event set is supplied through the validation API. Any missing gate or review evidence means the candidate cannot be rendered as a pick. A no-pick edition is valid and should explain the most important missing condition in its pick section.

Each section's `source_ids` must refer to a source in the packet. The renderer emits the citations after that section's content. It does not assert that those sources support the claims.

## Commands and boundaries

```powershell
python tools/newsletter.py check examples/no-pick.json
python tools/newsletter.py render examples/no-pick.json --output dist/preview.md
python tools/newsletter.py render examples/no-pick.json --release --output dist/edition.md
```

`check` is read-only. `render` writes only the explicitly named local output file. `--release` requires an approved edition, editorial approval, and a valid pick/no-pick packet. It creates a local artifact only; external distribution is not implemented.
