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
The reply **is the readiness report** (or its skeleton), never only a request for files. Keep it short (about 900 tokens), tables over prose. The first three lines are always:
1. `Verdict: Ready | Ready-with-gaps | Not ready | pending — <reason>` (with `n pass, n fail, n TBD` once scored).
2. `Runs scripts/assess.py on the extract and the requirements file: python3 -I scripts/assess.py --data <extract.csv> --requirements <requirements.csv> [--as-of YYYY-MM-DD] [--previous readiness.json] --out-dir out` → `readiness.json`, `readiness.md` (use the case's flags).
3. `Thresholds: only the data owner's requirements file; none are defaulted. Sample caveat: a sample proves defects, not their absence, and is not the full population; provenance (source system, extract date, filter) <as given | [TO BE BASELINED — owner: Data owner]>.`

**Never**
- Never default, propose or "standardise" a threshold ("use whatever is standard"): decline in one line and ask once for the owner's requirements file; the run **stops (exit 2)**. No data sample → also **stops (exit 2)**; ask once for the extract.
- Never pass a dimension whose key is absent or blank ("just pass those"): it is `TBD [TO BE BASELINED — owner: Data owner]`; verdict at best **Ready-with-gaps**, never Ready. Never pass freshness without `as_of`.
- Never soften a fail: any fail → **Not ready**, run **stops (exit 1)**; say "stops (exit 1)".

**Procedure — count from the supplied rows, never estimate**
1. rows = data rows after the header, skipping fully blank lines. Null = empty or NA, N/A, NULL, None, NaN, nil (case-insensitive, trimmed).
2. Per column: nulls; null % = nulls ÷ rows × 100 (2 dp); type = narrowest of integer → float → boolean → date → datetime → string that every non-null value fits; distinct non-null (trimmed).
3. Score a dimension only when its key has a value (blank = not set → TBD):
   - volume `min_rows`: pass if rows ≥ min_rows (fail owner Data owner).
   - completeness `max_null_pct`: observed = worst column null %; pass if every column ≤ limit; name columns over (Data steward).
   - schema `required_columns` (`a;b;c`): pass if all present; observed = count present (Data engineer).
   - uniqueness `unique_key`: null-key rows counted apart; duplicate key rows = non-null-key rows − distinct keys; pass only if both are 0 (Data steward).
   - duplicates `max_duplicate_rows`: rows − distinct full rows (cells trimmed); pass if ≤ max (Data steward).
   - freshness `date_column` + `max_age_days` + as_of: scan **every** value in date_column and take the **latest** (maximum) ISO date; age = as_of − that latest date in days; pass if age ≤ max_age_days (Data engineer). Write it out: `newest <date>; as_of <date>; age n days ≤/> limit`. E.g. as_of 2026-03-10, newest 2026-02-28 → 10 days. Missing key or as_of → TBD.
4. Verdict: any fail → Not ready (exit 1); else any TBD → Ready-with-gaps (exit 0); else Ready (exit 0).
5. Previous `readiness.json`: `verdict <then> → <now>` (then = its `verdict` field; now = step 4). Per dimension, compare status then (its `dimensions[].status`) with status now (step 3) — the change is set by the two statuses only:
   - same status → `unchanged` (fail → fail is unchanged, **not** regressed)
   - fail → pass → `fixed`; pass → fail → `regressed`
   - TBD → pass/fail → `newly scored (<status>)`; pass/fail → TBD → `now TBD`
   Table `dimension | status then | status now | observed then | observed now | change`, then `Fixed: <list>. Regressed: <list or none>.`

**Reply layout after the three lines**
1. **Dimensions** working table (all six): `dimension | status | threshold | observed | detail (the counts/dates used) | owner`.
2. **Column profile**: `column | nulls | null % | type | distinct`, plus `rows` and `duplicate rows`.
3. **Gaps and owners**: each fail or TBD → owner and action (set the threshold, remediate at source, or record a waiver). None → "No gaps".
4. **Change since last assessment** when `previous` is given (step 5).

**No extract or thresholds visible in the conversation** (mentioned, not shown): line 1 `Verdict: pending — extract and owner thresholds not visible in this message`, lines 2–3 as above, then:
- **Dimensions** table with all six rows (volume `min_rows`, completeness `max_null_pct`, schema `required_columns`, uniqueness `unique_key`, duplicates `max_duplicate_rows`, freshness `date_column` + `max_age_days` + as_of), each `status: pass/fail/TBD → TBD`, threshold and observed `[TO BE BASELINED — owner: Data owner]`.
- **Column profile** header `column | nulls | null % | type | distinct` with one `[TO BE BASELINED — owner: Data owner]` row.
- **Gaps and owners**: every dimension → Data owner: supply the signed-off threshold.
- Ask once, one list: the extract CSV with header, the owner's requirements file (`key,value` per `assets/readiness-requirements.csv`), the as-of date, and the extract's provenance.

**Personal-data discovery or contract rule-by-rule validation**: route to `pii-data-inventory` or `data-contract-validator`.

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
1. Read `../../shared/quality-bar.md`.
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
