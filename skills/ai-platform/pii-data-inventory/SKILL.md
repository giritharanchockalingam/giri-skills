---
name: pii-data-inventory
description: Use when the user asks what personal data a dataset holds before it is used for AI — "scan this file for PII", "build a PII inventory", "which columns are sensitive", "what must we mask before this goes to the model", "check the extract against our privacy policy". Produces a per-column PII inventory (email, phone, US SSN pattern, Luhn-valid payment card, IPv4/IPv6, date of birth, column-name hints) with match rate, match count and the handling the owner's policy assigns (mask, tokenize, drop, allow) — or a TBD naming the Privacy officer when the policy is silent; raw values are never written, only masked examples. Not for legal determinations, data-quality scoring (data-readiness-assessment) or building training sets (finetune-dataset-builder).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: data
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: data, type: csv, required: true, from: "sample CSV with a header row (an extract; values are read, never echoed)"}
      - {name: policy, type: csv, required: false, from: "privacy policy pii_type,handling (layout: assets/pii-policy.csv; handling mask|tokenize|drop|allow); without it every PII column is TBD for the Privacy officer"}
      - {name: strict, type: flag, required: false, flag: "--strict", from: "true to fail the run (exit 1) when any PII column has no policy handling"}
      - {name: previous, type: csv, required: false, from: "pii-inventory.csv from the last scan of the same table; adds per-column change (new, removed, pii-added, pii-removed, handling-changed)"}
    run:
      - {step: scan, kind: script, cmd: "python3 -I scripts/scan_pii.py --data {data} [--policy {policy}] [--previous {previous}] {strict} --out-dir {out}"}
    outputs:
      - {path: "{out}/pii-inventory.csv", checks: [exists, csv:[column,pii_types,match_rate,rows_scanned,handling], csv_rows:handling!empty, "csv_rows:match_rate~^[01]\\.\\d{3}$", cmd:"python3 -I scripts/scan_pii.py --leak-check {path} --data {data}"]}
      - {path: "{out}/pii-report.md", checks: [exists, sections:["Summary","Column inventory","Handling gaps","Method"], no_unowned_tbd, cmd:"python3 -I scripts/scan_pii.py --leak-check {path} --data {data}"]}
    modes:
      new:      {case: agent-happy-path, bring: "a sample of a table never inventoried, plus your privacy policy"}
      existing: {case: agent-mode-existing, bring: "a fresh sample, your policy and last quarter's inventory"}
---

# PII Data Inventory

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/pii-data-inventory --input <name>=<value> … --out <dir>` (see `--explain ai-platform/pii-data-inventory`). Report the `run.json` results; do not hand-write the deliverables the script produces (`pii-inventory.csv`, `pii-report.md`). Both outputs pass a leak check: the script re-scans the source and fails if any raw matched value appears in them.

## Starting points
- **New** — first inventory of a table: scan a sample, map each PII column to your policy's handling.
- **Existing** — also pass the last inventory as `previous`: each column is classed new, removed, pii-added, pii-removed, handling-changed or unchanged (`change_vs_previous`), and PII that was not there before is called out for the Privacy officer ("Changes since last inventory").

## When to use
- ADLC data stage: before a sample is copied into a notebook, a vector store, a prompt or a fine-tune set.
- "Which columns in this extract are personal data, and what does our policy say to do with each?"
- Policy gap finding: run with the current policy to list PII types the policy does not yet cover.
- NOT for: legal or regulatory determinations (route to counsel / DPO), quality scoring (`data-readiness-assessment`), de-identifying the data itself (this skill inventories; it does not transform), unstructured documents or images.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `data` — sample CSV with header | yes | data owner extract | run stops (exit 2), asks once |
| `policy` — `pii_type,handling` | no | Privacy officer / DPO (copy `assets/pii-policy.csv`) | every PII column's handling is `[TO BE BASELINED — owner: Privacy officer]` |
| `strict` — true/false | no | use-case owner | false: gaps reported, run exits 0 |

Policy `pii_type` values: `email, phone, ssn, payment_card, ipv4, ipv6, dob, name, address`. `handling`: `mask | tokenize | drop | allow`. A blank handling counts as not decided.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Confirm the sample may be read by this process (it is processed locally; nothing leaves the run directory).
3. Run the agent. `scripts/scan_pii.py` scans every cell with the detectors in `references/detectors.md` and applies column-name hints.
4. Per column, the handling is the strictest of its types' policy handlings (drop > tokenize > mask > allow); any type the policy omits makes the column TBD for the Privacy officer.
5. With `strict=true`, any TBD column fails the run (exit 1) — use this as the gate before data moves to a lower-trust environment.
6. Review hint-only columns (name, address) by eye and confirm or dismiss them; free-text columns need human review regardless of match rate.
7. Run the self-check.

## Output
- `pii-inventory.csv` — `column, pii_types, match_rate, rows_scanned, handling, matches, basis` (one row per column; `none` / `n/a` for non-PII columns).
- `pii-report.md` — **Summary**, **Column inventory** (with masked examples), **Handling gaps** (owner: Privacy officer), **Method** (detectors and limits).

## Self-check
- [ ] No raw value appears in any output (both outputs pass `--leak-check`)
- [ ] Every handling came from the supplied policy; gaps name the Privacy officer
- [ ] Hint-only columns are flagged for human confirmation, not asserted as PII
- [ ] Columns the policy allows in clear are listed for a lawful-basis check
- [ ] Limits stated: sample-based, pattern-based, not a legal determination

## References
- `references/detectors.md` — detector rules, masking formats, false-positive notes
- `references/handling-policy.md` — what mask / tokenize / drop / allow mean and how the strictest wins
- `assets/pii-policy.csv` — policy template for the Privacy officer
- `scripts/scan_pii.py` — scanner, masker and leak check (argparse; stdlib)
