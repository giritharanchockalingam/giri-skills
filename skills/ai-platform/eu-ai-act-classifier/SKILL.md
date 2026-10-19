---
name: eu-ai-act-classifier
description: Use when the user needs to know where one AI system sits under the EU AI Act and what follows — "is this high-risk under the AI Act", "classify our chatbot under the EU AI Act", "which AI Act obligations apply to us and from when", "are we a prohibited practice", "AI Act tier for this use case". Produces classification.json (prohibited | high-risk | limited-transparency | minimal, or undetermined with the open questions), obligations.csv (obligation, article, application date, role, owner, status, in force as of a given date) and ai-act-report.md from a yes/no questionnaire, with dates per Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744; a prohibited practice fails the gate (exit 1). Not legal advice. Not for enterprise risk registers (ai-governance-risk) or NIST AI RMF control coverage (ai-controls-mapping).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: govern
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: system, type: csv, required: true, from: "system questionnaire key,value,source,notes (layout: assets/system-questionnaire.csv) - role, intended purpose, yes/no for every Art. 5 practice, Annex I, Annex III area, Art. 6(3) condition, Art. 50 trigger and GPAI flag; blank = open question"}
      - {name: evidence, type: csv, required: false, from: "obligation_id,status,evidence,owner (status done|in_progress|not_started|not_applicable; ids from assets/obligations-catalogue.csv); without it every obligation is open"}
      - {name: as_of, type: string, required: false, from: "YYYY-MM-DD date to mark obligations already in force; never defaulted to today"}
    run:
      - {step: classify, kind: script, cmd: "python3 -I scripts/classify.py --system {system} [--evidence {evidence}] [--as-of {as_of}] --out-dir {out}"}
    outputs:
      - {path: "{out}/classification.json", checks: [exists, json, contains:"\"not_legal_advice\": true", contains:"\"unanswered_keys\"", cmd:"python3 -I scripts/classify.py --verify {path}"]}
      - {path: "{out}/obligations.csv", checks: [exists, csv:[obligation_id,article,obligation,applies_from,applies_to_role,owner,status], no_unowned_tbd, cmd:"python3 -I scripts/classify.py --verify {path}"]}
      - {path: "{out}/ai-act-report.md", checks: [exists, sections:["Summary","Classification","Obligations","Open questions","Limits"], no_unowned_tbd, contains:"Not legal advice", cmd:"python3 -I scripts/classify.py --verify {path}"]}
---

# EU AI Act Classifier

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/eu-ai-act-classifier --input <name>=<value> … --out <dir>` (see `--explain ai-platform/eu-ai-act-classifier`). Report the `run.json` results; do not hand-write the deliverables the script produces (`classification.json`, `obligations.csv`, `ai-act-report.md`). This skill is a gate: a prohibited practice fails the run with exit 1, and the outputs are still written so the finding is visible. The result is not legal advice.

## When to use
- ADLC govern stage: before an AI system is built, bought or placed on the EU market, and again whenever its purpose changes.
- "Is this high-risk?", "which AI Act articles apply to us as deployer?", "what is already in force today?"
- Track AI Act obligations: re-run with an evidence CSV and `as_of` to see what is done, open and in force.
- NOT for: legal opinions (route to counsel), enterprise AI risk registers (`ai-governance-risk`), mapping evidence to NIST AI RMF (`ai-controls-mapping`), non-EU regimes.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `system` — questionnaire CSV `key,value,source,notes` | yes | product owner + AI compliance lead (copy `assets/system-questionnaire.csv`) | run stops (exit 2), asks once |
| blank answers inside `system` | — | same | listed under Open questions as `[TO BE BASELINED — owner: AI compliance lead]`; tier `undetermined` if any could change it |
| `evidence` — `obligation_id,status,evidence,owner` | no | obligation owners | every obligation `open`, owner = `accountable_owner` or TBD |
| `as_of` — YYYY-MM-DD | no | the reviewer | `in_force` = "not assessed"; the run date is never used |

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Copy `assets/system-questionnaire.csv`. Have the product owner answer each key with yes or no. Leave a key blank rather than guess, and record the source of each answer.
3. Run the agent. `scripts/classify.py` applies `references/classification-method.md`: Art. 5 first, then Annex I and Annex III with the Art. 6(3) derogation and profiling rule, then the Art. 50 triggers.
4. Obligations come from `assets/obligations-catalogue.csv`, filtered by role. Their dates are verified in `references/sources.md` (Reg. 2026/1744 moved the high-risk dates to 2 Dec 2027 and 2 Aug 2028).
5. Prohibited means exit 1: stop the work and escalate to counsel. Undetermined means exit 0 with open questions: resolve them and re-run.
6. Run the self-check.

## Output
- `classification.json` — `tier`, `provisional_tier`, `basis_articles`, `high_risk_routes`, `art_6_3_derogation_applied`, `gpai`, `transparency_triggers`, `unanswered_keys`, `tier_open_keys`, counts, `legal_basis`, `dates_verified_on`, `gate`, `not_legal_advice`.
- `obligations.csv` — `obligation_id, article, obligation, applies_from, applies_to_role, owner, status, in_force, evidence, date_basis`.
- `ai-act-report.md` — **Summary**, **Classification**, **Obligations**, **Open questions**, **Limits**.

## Self-check
- [ ] Every answer came from the questionnaire; blanks are open questions with an owner, never assumed "no"
- [ ] `undetermined` whenever a blank could change the tier; `provisional_tier` shown
- [ ] Every date traces to `references/sources.md`; the skill's own readings are labelled as such in `date_basis`
- [ ] `in_force` only when `as_of` was given
- [ ] Prohibited → exit 1 and outputs written
- [ ] "Not legal advice" stated in the report; Limits name the amendment and the check date

## References
- `references/sources.md` — primary and secondary sources with URLs and check date; dates table; status of the law
- `references/classification-method.md` — decision rules, undetermined logic, obligation filtering
- `assets/system-questionnaire.csv` — input template (every key)
- `assets/obligations-catalogue.csv` — obligations, triggers, roles, dates (paraphrased)
- `scripts/classify.py` — classifier and `--verify` (argparse; stdlib)
