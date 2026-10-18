---
name: data-readiness-assessment
description: Use when the user asks whether a dataset is ready for an AI or analytics use case — "is our data ready", "profile this sample", "data readiness check", "does this extract meet the data requirements", "how fresh / complete / unique is this data". Produces a column profile (rows, null %, inferred types, distinct counts, duplicate rows and keys, freshness against an as_of date) scored pass/fail/TBD per readiness dimension against owner-supplied thresholds, with a Ready / Ready-with-gaps / Not ready verdict and a gaps-and-owners table; thresholds are never defaulted. Not for PII discovery (pii-data-inventory), fine-tune dataset preparation (finetune-dataset-builder), or data pipeline design.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: data
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: data, type: csv, required: true, from: "sample dataset CSV with a header row (an extract, not the whole lake)"}
      - {name: requirements, type: csv, required: true, from: "owner-set thresholds key,value (layout: assets/readiness-requirements.csv); an absent key is reported TBD, never defaulted"}
      - {name: as_of, type: string, required: false, from: "ISO date (YYYY-MM-DD) freshness is measured from; without it freshness stays TBD"}
    run:
      - {step: assess, kind: script, cmd: "python3 -I scripts/assess.py --data {data} --requirements {requirements} [--as-of {as_of}] --out-dir {out}"}
    outputs:
      - {path: "{out}/readiness.json", checks: [exists, json, contains:"\"verdict\"", contains:"\"column_profile\""]}
      - {path: "{out}/readiness.md", checks: [exists, sections:["Verdict","Dimensions","Column profile","Gaps and owners"], no_unowned_tbd, numbers_trace_to:"{out}/readiness.json"]}
---

# Data Readiness Assessment

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/data-readiness-assessment --input <name>=<value> … --out <dir>` (see `--explain ai-platform/data-readiness-assessment`). Report the `run.json` results; do not hand-write the deliverables the script produces (`readiness.json`, `readiness.md`). A "Not ready" verdict exits 1 on purpose: the run is telling you the data fails an owner threshold.

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
