---
name: data-contract-validator
description: Use when a dataset must be checked against its data contract before an AI system uses it for training, RAG ingestion or evaluation — "validate this extract against the contract", "does this data meet the contract", "gate the feed before ingestion", "check types, nulls, uniqueness and allowed values", "is this data fresh enough". Produces violations.csv (every violation with rule, severity, failing rows and rate, at most 3 truncated examples and the owner), profile.csv (inferred type, null rate, distinct, min/max per column) and contract-report.md with a PASS / PASS WITH WARNINGS / FAIL verdict; any error-severity violation exits 1. Contract as CSV, or an ODCS v3 YAML subset. Not for finding personal data (use pii-data-inventory), scoring overall data readiness (use data-readiness-assessment) or building training sets (use finetune-dataset-builder).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: data
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-mode-new, bring: "a first extract of a new feed, no contract yet"}
      existing: {case: agent-happy-path, bring: "your agreed data contract and the latest extract"}
    inputs:
      - {name: contract, type: file, required: false, from: "data contract CSV (layout: assets/contract-template.csv) or ODCS v3 YAML subset (references/odcs-subset.md); from the data owner. Without it a DRAFT contract is inferred from the data to {out}/contract-draft.csv (warn severity, no owners) and the extract is checked against it"}
      - {name: data, type: csv, required: true, from: "dataset extract CSV with a header row (values are read; at most 3 truncated examples per violation are written)"}
      - {name: freshness_column, type: string, required: false, from: "date or datetime column whose newest value must be recent; without as_of and max_age_days freshness is TBD for the Data owner"}
      - {name: as_of, type: string, required: false, from: "as-of date YYYY-MM-DD for the freshness check (never defaults to today)"}
      - {name: max_age_days, type: string, required: false, from: "maximum age in days of the newest record (data owner's freshness SLA)"}
    run:
      - {step: validate, kind: script, cmd: "python3 -I scripts/validate_contract.py [--contract {contract}] --draft-contract {out}/contract-draft.csv --data {data} [--freshness-column {freshness_column}] [--as-of {as_of}] [--max-age-days {max_age_days}] --out-dir {out}"}
    outputs:
      - {path: "{out}/violations.csv", checks: [exists, csv:[column,rule,severity,failing_rows,failing_rate,examples,owner], cmd:"python3 -I scripts/validate_contract.py --verify {path} --contract '{contract}' --draft-contract {out}/contract-draft.csv --data {data} --freshness-column '{freshness_column}' --as-of '{as_of}' --max-age-days '{max_age_days}'"]}
      - {path: "{out}/profile.csv", checks: [exists, csv:[column,inferred_type,null_rate,distinct,min,max], "csv_rows:null_rate~^[01]\\.\\d{3}$", cmd:"python3 -I scripts/validate_contract.py --verify {path} --contract '{contract}' --draft-contract {out}/contract-draft.csv --data {data} --freshness-column '{freshness_column}' --as-of '{as_of}' --max-age-days '{max_age_days}'"]}
      - {path: "{out}/contract-report.md", checks: [exists, sections:["Summary","Verdict","Violations","Profile","Method"], no_unowned_tbd, cmd:"python3 -I scripts/validate_contract.py --verify {path} --contract '{contract}' --draft-contract {out}/contract-draft.csv --data {data} --freshness-column '{freshness_column}' --as-of '{as_of}' --max-age-days '{max_age_days}'"]}
---

# Data Contract Validator

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/data-contract-validator --input <name>=<value> … --out <dir>` (see `--explain ai-platform/data-contract-validator`). Report the `run.json` results; do not hand-write the deliverables the script produces (`violations.csv`, `profile.csv`, `contract-report.md`). This is a gate: any error-severity violation exits 1 with complete outputs. Each output is re-verified against the data and contract with the script's `--verify` mode.

## Starting points
- **New:** with only a first extract, the run drafts `contract-draft.csv` from it (types, required, keys, code lists, null limits, observed ranges in `notes`, all at warn severity with no owner invented) and checks the extract against the draft; the report marks the contract DRAFT until the Data owner signs it off.
- **Existing:** your agreed contract (CSV or ODCS YAML) and the latest extract give every breach with its owner and the error-severity gate.

## When to use
- ADLC data stage: before an extract is loaded into a vector store, a fine-tune set or an evaluation set.
- A recurring feed into an AI system needs a pass/fail gate on schema, types, nulls, keys, ranges, code lists and freshness.
- A data owner has a contract (CSV, or an ODCS v3 YAML file) and wants every breach listed with its owner.
- NOT for: finding personal data (`pii-data-inventory`), overall readiness scoring (`data-readiness-assessment`), building or cleaning training data (`finetune-dataset-builder`), cross-table or drift checks, fixing the data (this skill reports; it never edits the source).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `contract` — CSV `column, type, required, unique, min, max, allowed, regex, max_null_rate, severity, owner` or ODCS v3 YAML | no | data owner (copy `assets/contract-template.csv`) | a DRAFT contract is inferred from the extract to `contract-draft.csv` (warn severity, owners TBD) and the report says the pass is by construction |
| `data` — extract CSV with header | yes | data engineering | run stops (exit 2), asks once |
| `freshness_column` | no | data owner | freshness not requested |
| `as_of` — YYYY-MM-DD | no | run owner (the load date) | freshness reads `not checked … [TO BE BASELINED — owner: Data owner]`; never today's date |
| `max_age_days` | no | data owner's freshness SLA | as for `as_of` |

Contract types: `string, integer, number, boolean, date, datetime, email, enum`. `min`/`max` are numbers, dates or (for text types) character lengths. `allowed` is pipe-separated. Blank `severity` = error; blank `owner` = `[TO BE BASELINED — owner: Data owner]`. YAML: the subset in `references/odcs-subset.md` is parsed with the repo's YAML subset parser; anything outside it is listed as not evaluated, never silently passed.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Get the contract from the data owner; if none exists, start from `assets/contract-template.csv` and have the owner sign off each row (severity and owner especially).
3. If the extract may hold personal data, run `pii-data-inventory` first; examples here are truncated but still real values.
4. Run the agent. `scripts/validate_contract.py` checks every rule in `references/rules.md` and profiles every column.
5. Read the Verdict. FAIL (exit 1): send each error row to its owner; fix at source and re-run — never edit the outputs.
6. Review warnings and `extra_column` rows with the Data owner: add the column to the contract or drop it from the feed.
7. Run the self-check.

## Output
- `violations.csv` — `column, rule, severity, failing_rows, failing_rate, examples, owner, expectation`; errors first.
- `profile.csv` — `column, inferred_type, null_rate, distinct, min, max` (min/max for numeric and date-like columns only).
- `contract-report.md` — **Summary**, **Verdict**, **Violations**, **Profile**, **Method**.

## Self-check
- [ ] Every violation names an owner or `[TO BE BASELINED — owner: Data owner]`
- [ ] No more than 3 examples per violation, each ≤ 40 characters; no text values in the profile
- [ ] Freshness used the supplied as-of date, or is marked TBD — never today's date
- [ ] YAML terms outside the subset are listed as not evaluated
- [ ] Each output passes `--verify`; an error-severity violation exits 1
- [ ] Limits stated: one extract, not a statistical guarantee

## References
- `references/rules.md` — rules, denominators, type parsing, sensitivity handling, limits
- `references/odcs-subset.md` — ODCS v3 YAML mapping and what is not evaluated
- `references/sources.md` — ODCS sources checked 2026-10-18
- `assets/contract-template.csv` — contract layout for the data owner
- `scripts/validate_contract.py` — validator and `--verify` (argparse; stdlib; exit 0 / 1 gate / 2 input)
