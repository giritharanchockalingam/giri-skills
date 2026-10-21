---
name: dpia
description: Use when an AI system processes personal data and the user needs a Data Protection Impact Assessment under GDPR Art. 35 — "do we need a DPIA", "write the DPIA for our assistant", "screen this use case against the EDPB criteria", "is prior consultation needed", "turn the PII inventory into DPIA risks". Produces dpia.md (Screening, Description of processing, Necessity and proportionality, Risks to rights and freedoms, Measures, Residual risk and consultation, Sign-off), dpia-risks.csv and screening.json from a processing description, the pii-data-inventory output and an optional risk list - nine WP248 criteria screening, Art. 35(3) cases, 3x3 risk scores, Art. 36 prior-consultation flag, and a gate that fails when a high residual risk has no measure. Blank facts become TBDs owned by the Data protection officer. Not legal advice. Not for finding the PII (pii-data-inventory), EU AI Act or enterprise AI risk registers (ai-governance-risk) or bias testing (bias-fairness-check).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: govern
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-mode-new, bring: "a description of the processing and its personal data"}
      existing: {case: agent-happy-path, bring: "your processing description plus the risk register you keep"}
    inputs:
      - {name: processing, type: csv, required: true, from: "processing description key,value,source,notes (layout: assets/processing-template.csv) - controller, purpose, lawful_basis, data_subjects, retention, transfers, and yes|no screening keys"}
      - {name: pii_inventory, type: csv, required: false, from: "pii-inventory.csv from ai-platform/pii-data-inventory; PII columns with TBD handling become risks"}
      - {name: risks, type: csv, required: false, from: "risk,likelihood (1-3),severity (1-3),measure,owner,residual (low|medium|high) (layout: assets/risks-template.csv)"}
    run:
      - {step: dpia, kind: script, cmd: "python3 -I scripts/dpia.py --processing {processing} [--pii-inventory {pii_inventory}] [--risks {risks}] --out-dir {out}"}
    outputs:
      - {path: "{out}/dpia.md", checks: [exists, sections:["Screening","Description of processing","Necessity and proportionality","Risks to rights and freedoms","Measures","Residual risk and consultation","Sign-off"], no_unowned_tbd, cmd:"python3 -I scripts/dpia.py --verify {path}"]}
      - {path: "{out}/dpia-risks.csv", checks: [exists, csv:[risk,source,likelihood,severity,score,level,measure,owner,residual], csv_rows:risk!empty, "csv_rows:level~^(low|medium|high|unscored)$", no_unowned_tbd]}
      - {path: "{out}/screening.json", checks: [exists, json, contains:"\"required\":", contains:"\"criteria_met\":", cmd:"python3 -I scripts/dpia.py --verify {path}"]}
---

# DPIA (GDPR Art. 35) for an AI system

## In a conversation: screen and draft the DPIA now
The reply **is the screening and DPIA draft**, never only a request for the template. Not legal advice — say so in the reply. Only the facts the user states count as answered; nothing is assumed.
- **The request describes the processing** (e.g. "ranks customers for payment plans, runs on an LLM") but the processing description, PII inventory or risk list are not in the conversation: write, **in this reply**, in the order of `dpia.md`:
  1. **Screening** — line 1: `DPIA required: yes / no / yes (precautionary)` with the basis. Table of the nine WP248 criteria — C1 evaluation or scoring, C2 automated decision-making with legal or similar effect, C3 systematic monitoring, C4 sensitive or highly personal data, C5 large scale, C6 matching or combining datasets, C7 vulnerable data subjects, C8 innovative use or new technology, C9 prevents a right, service or contract — each `met / not met / not answered` with the stated fact behind it (ranking customers → C1; an LLM → C8 if the user calls it new technology; otherwise `not answered`). Then the Art. 35(3) cases: (a) scoring plus automated decisions with legal or similar effect, (b) large-scale special-category or criminal data, (c) large-scale monitoring of a publicly accessible area. Rule: required when an Art. 35(3) case applies, when two or more criteria are met, or precautionarily when met plus unanswered criteria reach two.
  2. **Description of processing** (Art. 35(7)(a)), **Necessity and proportionality** (7(b)) — controller, purpose, data subjects, data categories, lawful basis, retention, transfers, minimisation, transparency, data-subject rights (incl. Art. 22 safeguards): stated facts filled, every blank `[TO BE BASELINED — owner: Data protection officer]`.
  3. **Risks to rights and freedoms** (7(c)) — table `risk | source | likelihood (1–3) | severity (1–3) | score | level | measure | owner | residual`; score = likelihood × severity (1–2 low, 3–4 medium, 6–9 high). Only risks the user states are scored; otherwise one placeholder "not yet identified", owner Data protection officer. PII columns with undecided handling become unscored DPO-owned risks.
  4. **Measures** (7(d)), **Residual risk and consultation** — any high residual flags Art. 36 prior consultation; a high residual with no measure blocks sign-off (gate).
  5. **Sign-off** — measures approved by, residual risk accepted by, DPO advice and whether accepted: TBD for the Data protection officer.
  6. **Next step** — the controller fills `assets/processing-template.csv` (yes/no screening keys), runs `pii-data-inventory` on a sample, and runs `python3 scripts/run_skill.py ai-platform/dpia --input processing=<processing.csv> [--input pii_inventory=<pii-inventory.csv>] [--input risks=<risks.csv>] --out <dir>`.
- **No processing described at all**: ask once for the processing description (template keys) and, if available, the PII inventory and risk list.
- **Asked to fill the rest "with sensible defaults"**: decline in one line — unanswered criteria stay unanswered and owned by the DPO, because a guessed "no" could wrongly skip a required DPIA; apply the precautionary rule and keep the placeholder risk.
- **Asked to sign off with a high risk unmitigated** ("go live Monday"): decline sign-off in one line — residual equals the inherent level without a measure, so the DPIA cannot be signed off and Art. 36 prior consultation is flagged; offer the path: record a measure and owner, re-score, DPO advice.

## Starting points
- **New:** a processing description (and, if you have it, the PII inventory) gives the screening and a first risk list; risks from undecided PII handling are owned by the DPO and stay unscored.
- **Existing:** add the risk register you already keep (`risks`); its likelihood, severity, measures, owners and residual levels are scored and drive the Art. 36 consultation call.

## When to use
- ADLC govern stage: before an AI system that processes personal data goes live, or when its purpose, data or model changes.
- "Do we need a DPIA?" — screening against the nine WP248 criteria and the Art. 35(3) cases.
- Turning a `pii-data-inventory` result into DPIA risks: undecided handling becomes a risk owned by the DPO.
- Deciding whether Art. 36 prior consultation of the supervisory authority is needed.
- NOT for: finding PII in data (`pii-data-inventory`), EU AI Act classification or the enterprise AI risk register (`ai-governance-risk`), fairness testing (`bias-fairness-check`), legal opinions (route to counsel / DPO).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `processing` — kv-csv `key,value,source,notes` | yes | controller / product owner, reviewed by DPO (copy `assets/processing-template.csv`) | run stops (exit 2), asks once |
| `pii_inventory` — `pii-inventory.csv` | no | `ai-platform/pii-data-inventory` run on a sample | description says no inventory: TBD (owner: Data protection officer); criterion 4 relies on facts only |
| `risks` — `risk,likelihood,severity,measure,owner,residual` | no | risk workshop with DPO, security, product (copy `assets/risks-template.csv`) | one placeholder risk "not yet identified", owner Data protection officer |

Screening keys take `yes|no`; blank means not answered. Any other value stops the run (exit 2). Likelihood and severity take 1–3; residual takes low|medium|high.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Run `pii-data-inventory` on a sample first if the data has not been inventoried.
3. Fill `processing-template.csv` with the controller; leave unknowns blank (they become TBDs, never guesses).
4. Run the skill. `scripts/dpia.py` screens against WP248 C1–C9 and Art. 35(3) (`references/risk-method.md`); a DPIA is required at two or more criteria, or precautionarily when unanswered criteria could reach two.
5. It scores each risk `likelihood × severity` (1–2 low, 3–4 medium, 6–9 high) and adds a risk for every PII column whose handling is blank or TBD.
6. Residual risk: stated by the owner; with no measure it equals the inherent level (a stated residual below the inherent level with no measure is not credible: it is overridden to the inherent level and reported). Any high residual flags Art. 36 prior consultation; a high residual without a measure is the gate (exit 1).
7. Hand `dpia.md` to the DPO for advice (Art. 35(2)) and record it in the Sign-off rows; re-run after changes.
8. Run the self-check.

## Output
- `dpia.md` — **Screening**, **Description of processing** (Art. 35(7)(a)), **Necessity and proportionality** (7(b)), **Risks to rights and freedoms** (7(c)), **Measures** (7(d)), **Residual risk and consultation** (Art. 36 flag, gate), **Sign-off**.
- `dpia-risks.csv` — `risk, source, likelihood, severity, score, level, measure, owner, residual`.
- `screening.json` — criteria with met/basis, `criteria_met`, `art35_3_cases`, `required` (bool), `basis`, `prior_consultation_required`, `signoff_status`, `gate_blockers`.

## Self-check
- [ ] Every blank fact is `[TO BE BASELINED — owner: Data protection officer]`; nothing inferred beyond the documented rules
- [ ] Screening cites the key behind each criterion; `required` matches the rule
- [ ] Every TBD-handling PII column appears as a risk
- [ ] Scores are likelihood × severity; levels follow the bands (`--verify` passes)
- [ ] Art. 36 flagged when any residual is high; exit 1 when a high residual has no measure
- [ ] "Not legal advice" stated; sources in `references/sources.md`

## References
- `references/sources.md` — GDPR Art. 35/36 (EUR-Lex), WP248 rev.01 and EDPB endorsement, with dates checked
- `references/risk-method.md` — criteria mapping, required rule, scoring, gate
- `assets/processing-template.csv`, `assets/risks-template.csv` — input layouts
- `scripts/dpia.py` — screener, DPIA writer and `--verify` (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/dpia --input <name>=<value> … --out <dir>` (see `--explain ai-platform/dpia`). Report the `run.json` results; do not hand-write the deliverables the script produces (`dpia.md`, `dpia-risks.csv`, `screening.json`). **Gate:** a high residual risk with no measure fails the run (exit 1) on purpose — the DPIA is still written and states it cannot be signed off. Not legal advice.
