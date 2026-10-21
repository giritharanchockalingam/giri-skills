---
name: ai-controls-mapping
description: Use when the user needs to show how an AI system's controls line up with the NIST AI Risk Management Framework — "map our evidence to NIST AI RMF", "what's our AI RMF coverage", "which GOVERN/MAP/MEASURE/MANAGE subcategories are gaps", "do we have evidence for our AI Act obligations", "AI controls gap analysis". Produces controls.csv (all 72 AI RMF 1.0 subcategories with status, evidence, owner; unknown ids flagged as errors), coverage.json (per-function counts and coverage = (implemented + 0.5 x partial) / applicable) and controls-report.md, with an optional minimum-coverage gate (exit 1) and an optional check of open EU AI Act obligations against the evidence (skill's own crosswalk). Not for classifying a system under the AI Act (eu-ai-act-classifier) or building a risk register (ai-governance-risk).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: govern
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: evidence, type: csv, required: true, from: "evidence register subcategory_id,status,evidence,owner (ids as in NIST AI 100-1, e.g. GOVERN 1.1; status implemented|partial|planned|not_applicable; layout: assets/evidence-template.csv)"}
      - {name: min_coverage, type: string, required: false, from: "fraction 0-1 set by the AI risk lead; overall evidence-backed coverage (uncited implemented/partial claims get no credit) below it fails the run (exit 1); never defaulted"}
      - {name: obligations, type: csv, required: false, from: "obligations.csv from eu-ai-act-classifier; lists open AI Act obligations and whether their mapped NIST subcategories have evidence"}
    run:
      - {step: map, kind: script, cmd: "python3 -I scripts/map_controls.py --evidence {evidence} [--min-coverage {min_coverage}] [--obligations {obligations}] --out-dir {out}"}
    outputs:
      - {path: "{out}/controls.csv", checks: [exists, csv:[subcategory_id,function,category,status,evidence,owner,gap], csv_rows:owner!empty, "csv_rows:status~^(implemented|partial|planned|not_applicable|missing|error)$", cmd:"python3 -I scripts/map_controls.py --verify {path}"]}
      - {path: "{out}/coverage.json", checks: [exists, json, contains:"\"subcategories_in_catalogue\": 72", cmd:"python3 -I scripts/map_controls.py --verify {path}"]}
      - {path: "{out}/controls-report.md", checks: [exists, sections:["Summary","Coverage by function","Gaps","Evidence register","Method"], no_unowned_tbd, cmd:"python3 -I scripts/map_controls.py --verify {path}"]}
    modes:
      new:      {case: agent-mode-new, bring: "the evidence template, filled in with what you have today"}
      existing: {case: agent-happy-path, bring: "your current evidence register and open AI Act obligations"}
---

# AI Controls Mapping (NIST AI RMF 1.0)

## In a conversation: map the controls now
The reply **is the controls mapping**: first line `Coverage: <overall, or [TO BE BASELINED — owner: AI risk lead]> against NIST AI RMF 1.0 (72 subcategories) — self-assessment, not an audit`. It corresponds to `python3 -I scripts/map_controls.py --evidence <file> [--min-coverage <x>] [--obligations <file>] --out-dir <out>`, which writes `controls.csv`, `coverage.json` and `controls-report.md`; name that command (with the case's flags) and those files.

**Never**
- Never assign an owner the user names for unowned gaps ("put the product manager on them"): every gap with a blank owner shows `[TO BE BASELINED — owner: AI risk lead]`; say how many gaps lack an owner.
- Never print an asserted figure ("call it 80%") as coverage, never estimate statuses, never lower a gate to pass.
- Never invent a gate: no `min_coverage` given → `Gate: no minimum coverage given`.
- Never count a blank or absent row as implemented: it is `missing`.

**Procedure — compute row by row from the supplied file, never estimate**
1. Catalogue (72): GOVERN 1.1-1.7, 2.1-2.3, 3.1-3.2, 4.1-4.3, 5.1-5.2, 6.1-6.2 (19) · MAP 1.1-1.6, 2.1-2.3, 3.1-3.5, 4.1-4.2, 5.1-5.2 (18) · MEASURE 1.1-1.3, 2.1-2.13, 3.1-3.3, 4.1-4.3 (22) · MANAGE 1.1-1.4, 2.1-2.4, 3.1-3.2, 4.1-4.3 (13). Function = the word before the number.
2. Read each data row (skip `#` lines). Status blank **and** evidence blank → unfilled template row = `missing`. Status not in implemented|partial|planned|not_applicable, or a duplicate id → **stops (exit 2)**. An id not in the catalogue → `ERROR` row, excluded from coverage, run **stops (exit 1)** after writing outputs.
3. Per function, count implemented, partial, planned, not_applicable from the rows; missing = function total − rows counted. applicable = total − not_applicable.
4. coverage = (implemented + 0.5 × partial) ÷ applicable, 3 decimals. Same for ALL (72).
5. Evidence-backed coverage (gate basis): an implemented/partial row with blank `evidence` gets no credit (counted as missing). Flag those ids ("implemented/partial with no evidence cited: …") and not_applicable rows with blank evidence.
6. Gate (only with min_coverage): evidence-backed ALL coverage ≥ min → PASS (equality passes); below → FAIL, run **stops (exit 1)** with full outputs written. Say "stops (exit 1)" explicitly.
7. Gaps = partial, planned, missing. Owner blank → `[TO BE BASELINED — owner: AI risk lead]`. Count gaps without a named owner.
8. Obligations (only if given): skip status done/not_applicable. Look up `assets/aiact-nist-crosswalk.csv` (trailing `*` = prefix match, e.g. TR-50-* → MEASURE 2.8). supported = every mapped subcategory implemented or not_applicable (≥1 implemented); partial = any implemented/partial; none = only planned/missing; no row → `no crosswalk entry`. Label it "the skill's own crosswalk, not an official NIST or EU mapping".

**Reply layout**
1. Working table first: `function | total | implemented | partial | planned | not_applicable | missing | applicable | coverage | evidence-backed`, rows GOVERN, MAP, MEASURE, MANAGE, ALL, with the formula `(implemented + 0.5 × partial) ÷ applicable` stated above it. Then the gate verdict.
2. Gaps — `subcategory_id | function | status | owner` for every gap (or grouped by function with ids listed when long); count without owner.
3. Flags, AI Act obligations (if given), outputs written.
4. Limits — voluntary framework, self-assessed statuses; self-assessment, not compliance, certification or an audit.

**No register rows in the conversation** (a spreadsheet is mentioned but not attached, or "call it 80%"): still give the layout — the function table with formula and every cell `[TO BE BASELINED — owner: AI risk lead]`, gaps "all subcategories without a row are missing; owner [TO BE BASELINED — owner: AI risk lead]", the self-assessment line — and ask once for the evidence register as `subcategory_id,status,evidence,owner` (ids as in NIST AI 100-1, e.g. `GOVERN 1.1`; template `assets/evidence-template.csv`). Without evidence the run stops (exit 2). Do not estimate coverage.

## Starting points
- **New** — starting a controls programme: fill `assets/evidence-template.csv` with what exists today; blank rows count as missing and the report gives the baseline coverage and the full gap list.
- **Existing** — bring the evidence register you maintain (and `obligations.csv` from `eu-ai-act-classifier`); the skill re-scores coverage, withholds credit from uncited claims, tracks the open obligations and applies your minimum-coverage gate.

## When to use
- ADLC govern stage: before a release review, an audit or a customer assurance questionnaire that asks for NIST AI RMF alignment.
- "Where are our gaps across GOVERN, MAP, MEASURE and MANAGE, and who owns them?"
- After `eu-ai-act-classifier`: pass its `obligations.csv` to see which open AI Act obligations lack supporting evidence.
- NOT for: AI Act tiering (`eu-ai-act-classifier`), risk registers and likelihood/impact scoring (`ai-governance-risk`), evaluating the AI system itself (`llm-eval-harness`, `red-team-suite`), certification or audit opinions.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `evidence` — `subcategory_id,status,evidence,owner` | yes | AI risk lead with control owners (copy `assets/evidence-template.csv`) | run stops (exit 2), asks once |
| owner blank on a row | — | control owner | `[TO BE BASELINED — owner: AI risk lead]` |
| subcategory absent from `evidence` | — | — | counted as `missing` (a gap) |
| `min_coverage` — fraction 0-1 | no | AI risk lead | no gate; coverage reported only |
| `obligations` — classifier `obligations.csv` | no | `eu-ai-act-classifier` run | AI Act section omitted |

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Copy `assets/evidence-template.csv` (all 72 ids). Owners fill status, evidence (document id or link) and owner. Mark `not_applicable` only with a justification in `evidence`.
3. Run the agent. `scripts/map_controls.py` joins the evidence to `assets/nist-ai-rmf-1.0.csv` and computes coverage per `references/crosswalk-method.md`.
4. With `obligations`, it looks up each open obligation in `assets/aiact-nist-crosswalk.csv` (the skill's own mapping) and reports supported, partial or none.
5. Exit 1 means coverage is below `min_coverage` or there are unknown ids. Fix the evidence; do not lower the threshold to pass.
6. Run the self-check.

## Output
- `controls.csv` — `subcategory_id, function, category, status, evidence, owner, gap, note`: 72 rows in catalogue order, plus `ERROR` rows for unknown ids.
- `coverage.json` — per-function and overall counts (implemented, partial, planned, not_applicable, missing, applicable) and coverage; gate; gaps; flags; input errors; AI Act obligation support.
- `controls-report.md` — **Summary**, **Coverage by function**, **Gaps** (with the AI Act sub-section when given), **Evidence register**, **Method**.

## Self-check
- [ ] All 72 subcategories present; counts per function are 19/18/22/13
- [ ] Coverage recomputes from controls.csv (`--verify` passes)
- [ ] Every gap has an owner or the AI risk lead TBD marker
- [ ] Claims without evidence and unjustified not_applicable rows are flagged
- [ ] The crosswalk is labelled the skill's own mapping wherever it is shown
- [ ] Limits stated: voluntary framework, self-assessed statuses, not compliance or an audit

## References
- `references/sources.md` — NIST AI 100-1, Playbook, crosswalk list; URLs and check date
- `references/crosswalk-method.md` — coverage formula, gap rules, crosswalk rules and limits
- `assets/nist-ai-rmf-1.0.csv` — 72 subcategories with function, category and paraphrase
- `assets/evidence-template.csv` — input template
- `assets/aiact-nist-crosswalk.csv` — AI Act obligation → subcategory mapping (skill's own)
- `scripts/map_controls.py` — mapper and `--verify` (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-controls-mapping --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-controls-mapping`). Report the `run.json` results; do not hand-write the deliverables the script produces (`controls.csv`, `coverage.json`, `controls-report.md`). With `min_coverage`, the skill is a gate: evidence-backed coverage (claims with no evidence cited get no credit) below the minimum fails the run (exit 1) and the outputs are still written. Unknown subcategory ids also fail the run until they are fixed.
