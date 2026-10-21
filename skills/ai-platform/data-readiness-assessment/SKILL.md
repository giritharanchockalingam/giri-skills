---
name: data-readiness-assessment
description: Use when the user asks whether a dataset is ready for an AI or analytics use case — "is our data ready", "profile this sample", "data readiness check", "does this extract meet the data requirements", "how fresh / complete / unique is this data", "assess this sample (or older extract) against the owner's requirements", "re-assess after the data fix". Produces a column profile (rows, null %, inferred types, distinct counts, duplicate rows and keys, freshness against an as_of date) scored pass/fail/TBD per readiness dimension against owner-supplied thresholds, with a Ready / Ready-with-gaps / Not ready verdict and a gaps-and-owners table; thresholds are never defaulted. Not for PII discovery (pii-data-inventory), fine-tune dataset preparation (finetune-dataset-builder), data pipeline design, or rule-by-rule validation against a data contract (data-contract-validator).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: data
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-happy-path, bring: "a sample extract and the data owner's signed-off requirements"}
      existing: {case: agent-mode-existing, bring: "a fixed extract plus your last readiness result"}
    inputs:
      - {name: data, type: csv, required: true, from: "sample dataset CSV with a header row (an extract, not the whole lake)"}
      - {name: requirements, type: csv, required: true, from: "owner-set thresholds key,value (layout: assets/readiness-requirements.csv); an absent key is reported TBD, never defaulted"}
      - {name: as_of, type: string, required: false, from: "ISO date (YYYY-MM-DD) freshness is measured from; without it freshness stays TBD"}
      - {name: previous, type: json, required: false, from: "readiness.json from an earlier assessment (e.g. before a data fix); adds per-dimension change"}
    run:
      - {step: assess, kind: script, cmd: "python3 -I scripts/assess.py --data {data} --requirements {requirements} [--as-of {as_of}] [--previous {previous}] --out-dir {out}"}
    outputs:
      - {path: "{out}/readiness.json", checks: [exists, json, contains:"\"verdict\"", contains:"\"column_profile\""]}
      - {path: "{out}/readiness.md", checks: [exists, sections:["Verdict","Dimensions","Column profile","Gaps and owners"], no_unowned_tbd, numbers_trace_to:"{out}/readiness.json"]}
---

# Data Readiness Assessment

## In a conversation: assess readiness now
The reply **is the readiness report** (or its skeleton): line 1 is `Verdict: Ready | Ready-with-gaps | Not ready | pending — <reason>`, never only a request for files. Thresholds come only from the data owner's requirements; none are defaulted.
- **The request carries the sample and the owner's thresholds** (or describes them): write the report **in this reply** in the script's order — **Verdict** (any fail → Not ready; else any TBD → Ready-with-gaps; else Ready) with the sample's provenance (source system, extract date, filter; unknown = `[TO BE BASELINED — owner: Data owner]`) and the caveat that a sample is not the full population; **Dimensions** table `dimension | status | threshold | observed | owner` for the six dimensions in `references/readiness-dimensions.md` — volume (`min_rows`), completeness (`max_null_pct`), schema (`required_columns`), uniqueness (`unique_key`), duplicates (`max_duplicate_rows`), freshness (`date_column` + `max_age_days` + as_of); **Column profile** (rows, null %, inferred type, distinct per column); **Gaps and owners** (fail owners per that file: Data owner, Data steward, Data engineer). Name the run that produces the files: `python3 -I scripts/assess.py --data … --requirements … [--as-of …] [--previous …] --out-dir …`.
- **Files said to be attached, or an extract and signed-off thresholds mentioned but not shown** (e.g. "a 20-row orders extract and the thresholds our data owner signed off — ready for the pilot?"): lay out all four sections now, every observed value and threshold `[TO BE BASELINED — owner: Data owner]`, state that `scripts/assess.py` scores each dimension pass/fail/TBD only against the owner's thresholds, then ask once, in one list, for the extract CSV, the requirements file (`key,value` per `assets/readiness-requirements.csv`) and the as-of date.
- **"Use whatever thresholds are standard" / no requirements**: decline in one line (readiness is judged against the accountable owner's thresholds, not this skill's); ask once for the requirements file; propose no numbers.
- **Owner has not set some thresholds ("just pass those")**: those dimensions are `TBD [TO BE BASELINED — owner: Data owner]`, never pass; the verdict is **Ready-with-gaps**, never Ready. Freshness without as_of is TBD.
- **A dimension fails**: report **Not ready** (exit 1) with each failing dimension and its owner; do not soften it.
- **Re-assess after a fix**: add **Change since last assessment** — verdict then → now, and per dimension status then/now, observed then/now, `fixed` / `regressed` / unchanged, and a `Regressed:` line.
- **Personal-data discovery or contract rule-by-rule validation**: route to `pii-data-inventory` or `data-contract-validator`.

## Starting points
- **New:** a sample extract and the owner's requirements give a verdict per dimension before you commit to a use case.
- **Existing:** add the `readiness.json` from the last assessment (`previous`), e.g. before a data fix; the report adds the verdict and each dimension's status and observed value then vs now, naming what was fixed and what regressed.

## When to use
- Gate check at the ADLC data stage: before committing to a use case, a RAG corpus, a fine-tune or a model build.
- "Profile this extract and tell me if it meets the requirements the data owner signed off."
- Re-check after a data fix: re-run with the same requirements file and compare verdicts.
- NOT for: PII discovery or handling policy (`pii-data-inventory`), building train/val/test splits (`finetune-dataset-builder`), designing pipelines or data contracts, full-population data quality monitoring.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `data` — sample dataset CSV with header | yes | data owner / engineer extract | run stops (exit 2), asks once |
| `requirements` — `key,value` thresholds | yes | data owner sign-off (copy `assets/readiness-requirements.csv`) | run stops (exit 2), asks once |
| `as_of` — ISO date for freshness | no | the assessment date the owner agrees | freshness reported TBD |

Requirement keys: `min_rows`, `max_null_pct`, `required_columns` (`a;b;c`), `unique_key` (`a[;b]`), `max_duplicate_rows`, `date_column` + `max_age_days`. A blank or absent key leaves its dimension `[TO BE BASELINED — owner: Data owner]`. Unknown keys are listed in Notes and ignored.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Confirm the sample is representative (source system, extract date, filter) and that the requirements came from the accountable data owner, not from this skill.
3. Run the agent. `scripts/assess.py` profiles every column (null %, inferred type, distinct), counts fully duplicated rows, and scores six dimensions — volume, completeness, schema, uniqueness, duplicates, freshness — using `references/readiness-dimensions.md`.
4. Read the verdict: any fail → **Not ready** (exit 1); else any TBD → **Ready-with-gaps**; else **Ready**.
5. For each gap, hand the owner named in "Gaps and owners" the action: set the missing threshold, remediate at source, or record a waiver. Re-run after changes.
6. Run the self-check.

## Output
- `readiness.json` — source files, requirements as parsed, verdict, per-dimension status/threshold/observed/detail/owner, column profile, notes.
- `readiness.md` — sections **Verdict**, **Dimensions**, **Column profile**, **Gaps and owners** (+ Notes when keys were ignored). Every number traces to `readiness.json`.

## Self-check
- [ ] Every threshold came from the requirements file; none were assumed
- [ ] Every TBD names an accountable owner (`Data owner`)
- [ ] The sample's provenance (system, date, filter) is stated next to the verdict when reported
- [ ] Not ready is reported as Not ready, with the failing dimensions and owners, not softened
- [ ] Freshness is TBD, not passed, when `as_of` was not supplied

## References
- `references/readiness-dimensions.md` — dimension definitions, formulas, null and type rules
- `references/method-notes.md` — sampling caveats and how this maps to public data-quality frameworks
- `assets/readiness-requirements.csv` — requirements template for the data owner
- `scripts/assess.py` — profiler and scorer (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/data-readiness-assessment --input <name>=<value> … --out <dir>` (see `--explain ai-platform/data-readiness-assessment`). Report the `run.json` results; do not hand-write the deliverables the script produces (`readiness.json`, `readiness.md`). A "Not ready" verdict exits 1 on purpose: the run is telling you the data fails an owner threshold.
