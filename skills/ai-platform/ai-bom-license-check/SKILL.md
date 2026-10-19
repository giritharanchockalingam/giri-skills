---
name: ai-bom-license-check
description: Use when an AI system is heading to release and the user needs to know what it is built from and whether every licence is allowed — "build our AI bill of materials", "AI-BOM", "check model and dataset licences", "can we ship with Llama / CC BY-NC data", "licence compliance before release", "CycloneDX for our models". Produces aibom.csv, a CycloneDX 1.6-shaped aibom.json (models, datasets, libraries, services) and license-report.md (Summary, Components, Blocked, Needs review, Obligations, Method) - each licence normalised to an SPDX or LicenseRef id from a verified catalog, decided by the organisation's policy, flagged for commercial restriction, copyleft, attribution and use-based restrictions; unknown licences go to Legal counsel, never guessed. Gate: any deny, or commercial use of a non-commercial licence, fails the run. Not legal advice. Not for vulnerability scanning (security-review), PII in data (pii-data-inventory) or model choice (model-selection).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: govern
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: bom, type: csv, required: true, from: "component,type (model|dataset|library|service),version,license,source_url,use (internal|commercial|redistribution)"}
      - {name: policy, type: csv, required: false, from: "licence policy license,decision (allow|review|deny),notes (layout: assets/license-policy.example.csv); without it every decision is TBD for Legal counsel"}
      - {name: system, type: string, required: false, from: "name of the AI system the BOM describes"}
    run:
      - {step: check, kind: script, cmd: "python3 -I scripts/aibom.py --bom {bom} [--policy {policy}] [--system {system}] --out-dir {out}"}
    outputs:
      - {path: "{out}/aibom.csv", checks: [exists, csv:[component,type,version,license_raw,spdx_id,decision,reason,flags], csv_rows:spdx_id!empty, "csv_rows:type~^(model|dataset|library|service)$", no_unowned_tbd]}
      - {path: "{out}/aibom.json", checks: [exists, json, contains:"\"bomFormat\": \"CycloneDX\"", contains:"\"specVersion\": \"1.6\"", cmd:"python3 -I scripts/aibom.py --verify {path}"]}
      - {path: "{out}/license-report.md", checks: [exists, sections:["Summary","Components","Blocked","Needs review","Obligations","Method"], no_unowned_tbd, cmd:"python3 -I scripts/aibom.py --verify {path}"]}
---

# AI-BOM Licence Check

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-bom-license-check --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-bom-license-check`). Report the `run.json` results; do not hand-write the deliverables the script produces (`aibom.csv`, `aibom.json`, `license-report.md`). **Gate:** any denied component fails the run (exit 1) on purpose; all three outputs are still written. Not legal advice.

## When to use
- ADLC govern stage: before an AI release, or when a model, dataset, library or API is added or upgraded.
- "Can we ship this?" — every component's licence against the organisation's licence policy, with the use it will be put to.
- Producing an AI bill of materials in a CycloneDX-shaped JSON for a release record.
- NOT for: vulnerability or dependency CVE scanning (`security-review`), finding personal data (`pii-data-inventory`), choosing a model (`model-selection`), a legal opinion on a licence (route to Legal counsel).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `bom` — `component,type,version,license,source_url,use` | yes | engineering lead; model cards, dataset cards, package metadata | run stops (exit 2), asks once |
| `policy` — `license,decision,notes` | no | Legal counsel (start from `assets/license-policy.example.csv`) | every decision is `[TO BE BASELINED — owner: Legal counsel]` |
| `system` — AI system name | no | product owner | report title TBD (owner: Engineering lead); JSON omits `metadata` |

`type`: model | dataset | library | service. `use`: internal | commercial | redistribution. Other values stop the run (exit 2). Blank version or licence → TBD (owner: Engineering lead); a blank licence counts as unknown.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. List every model, dataset, library and hosted service the AI system depends on, with the licence string exactly as published and the intended use.
3. Run the skill. `scripts/aibom.py` normalises each licence through `assets/license-catalog.csv` (`references/method.md`); unknown strings stay `unknown` and go to review.
4. Decisions come only from the policy. Commercial or redistribution use of a non-commercial licence is denied; Llama's conditional commercial terms turn an allow into a review.
5. Any deny fails the gate (exit 1). Resolve each Blocked row (replace, relicense, or change use), then re-run.
6. Send Needs review rows to Legal counsel; ship the Obligations (notices, attribution, flow-down terms) with the release.
7. Run the self-check.

## Output
- `aibom.csv` — `component, type, version, license_raw, spdx_id, decision, reason, flags, use`.
- `aibom.json` — CycloneDX-shaped subset (specVersion 1.6): `components` typed `machine-learning-model` / `data` / `library`, `services`, `licenses` (SPDX `id` or `expression`; `name` for unknown), `externalReferences`, decision/flags in `properties`.
- `license-report.md` — **Summary** (gate), **Components**, **Blocked**, **Needs review**, **Obligations**, **Method**.

## Self-check
- [ ] Every `spdx_id` is from the catalog or `unknown`; no licence guessed
- [ ] Every decision came from the policy, a documented use rule, or is TBD for Legal counsel
- [ ] Commercial/redistribution use of a non-commercial licence is denied and the run exits 1
- [ ] `aibom.json` passes `--verify`; it is described as a CycloneDX-shaped subset, not a validated SBOM
- [ ] Obligations listed for every shipped component; limits and "not legal advice" stated

## References
- `references/sources.md` — SPDX list 3.29.0, publisher licence pages, CycloneDX 1.6 schema, with dates checked
- `references/method.md` — normalisation, expressions, decision and use rules, gate
- `assets/license-catalog.csv` — SPDX/LicenseRef catalog with flags, obligations and source URL per row
- `assets/license-policy.example.csv` — example policy for Legal counsel to replace
- `scripts/aibom.py` — checker, CycloneDX writer and `--verify` (argparse; stdlib)
