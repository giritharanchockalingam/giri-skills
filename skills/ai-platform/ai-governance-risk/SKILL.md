---
name: ai-governance-risk
description: Use when the user asks for an AI compliance or risk review — "assess the risks of this AI use case", "build our AI risk register", "write a model card", "map us to NIST AI RMF / EU AI Act", "what controls do we need before launch". Produces a risk register (bias, privacy, hallucination, IP, security, misuse) with likelihood, impact, controls, and owners; a controls checklist; a model card; and a summary-level mapping to NIST AI RMF functions and EU AI Act risk tiers. Not legal advice; not for strategy (ai-strategy-coe) or agent design (agent-architecture).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: govern
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: canvas, type: md, required: true, from: "filled use-case canvas (ai-use-case-canvas assets/use-case-canvas.md layout; fixture: evals/fixtures/use-case-canvas.md)"}
      - {name: controls, type: md, required: false, default: "references/controls-catalog.md", from: "controls catalog with the | ID | Control | Addresses | table"}
      - {name: name, type: string, required: false, from: "system name for the model card (default: canvas title)"}
    run:
      - {step: register, kind: script, cmd: "python3 -I scripts/risk_register.py {canvas} --out-dir {out} --controls {controls} [--name {name}] --template assets/model-card.md"}
    outputs:
      - {path: "{out}/risk-register.csv", checks: [exists, csv:[risk_id,category,description,likelihood,impact,rating,control_id,control,owner], csv_rows:control!empty, csv_rows:rating!empty]}
      - {path: "{out}/model-card.md", checks: [exists, sections:["Intended use","Out-of-scope uses","Data","Limitations","Controls in place","Monitoring"], no_unowned_tbd, contains:"legal review required"]}
---

# AI Governance & Risk Review

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-governance-risk --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-governance-risk`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`risk-register.csv`, `model-card.md`). Scores the canvas cannot support stay `[TO BE BASELINED — owner: ___]`; a High risk with no mapped control fails the run (exit 1) on purpose.

## When to use
- Pre-launch risk review of an AI use case; building or refreshing the AI risk register; model documentation; regulatory mapping at summary level.
- NOT for: legal opinions (state this; route to counsel), strategy/CoE (`ai-strategy-coe`), eval mechanics (`llm-eval-harness`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Use-case description: purpose, users, decisions influenced, autonomy level | yes | user / design doc |
| Data: categories (PII, special categories, minors, financial, health, education records), sources, jurisdictions | yes | user |
| Model(s): provider/open-weights, version, fine-tuned?, hosting location | yes | user |
| Deployment context: internal / employee-facing / customer-facing / regulated decision | yes | user |
| Existing controls and policies | no | user |
| Applicable regulations the org already tracks | no | user; otherwise summary mapping only |

If the use case, data categories, or deployment context are missing, ask once.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. **Classify the use case.** Determine the internal risk tier (low / medium / high) using `references/risk-taxonomy.md` §Tiering, and the summary EU AI Act tier using `references/regulatory-mapping.md`. State both with the criteria met.
3. **Identify risks.** Walk the taxonomy (bias, privacy, hallucination, IP, security, misuse, operational, transparency). For each applicable risk: scenario, likelihood (1–5), impact (1–5), inherent score, in `assets/risk-register.csv`.
4. **Select controls** from `references/controls-catalog.md` per risk; record control owner, status (in place / planned / gap), evidence, and residual score. Gaps become next steps with owner and date.
5. **Write the model card** from `assets/model-card.md`: intended use, out-of-scope use, data, evaluation results (from `llm-eval-harness` where available), limitations, monitoring, contacts.
6. **Map to frameworks** at summary level with `references/regulatory-mapping.md`: NIST AI RMF Govern/Map/Measure/Manage coverage table; EU AI Act tier and headline obligations; note other regimes the org names. Add the line: "Summary mapping for planning; legal review required for obligations."
7. **Decide.** Launch recommendation: go / go with conditions / no-go, with the conditions listed as owner + date.
8. Run the self-check.

## Output
- `ai-risk-review-<use-case>.md`: tiering, risk register table, controls, model card, framework mapping, decision, next steps.
- `risk-register.csv` filled.

## Self-check
- [ ] Both internal tier and EU AI Act summary tier stated with criteria
- [ ] Every risk has likelihood, impact, control, owner, residual score
- [ ] Zero gaps without an owner and date
- [ ] Model card has out-of-scope uses and limitations, not only intended use
- [ ] Framework mapping is labeled summary-level; legal review line present
- [ ] No fabricated regulatory citations; cite article/section only when provided by a source
- [ ] Decision line is first

## References
- `references/risk-taxonomy.md` — risk categories, scenarios, tiering
- `references/controls-catalog.md` — controls by risk with evidence expectations
- `references/regulatory-mapping.md` — NIST AI RMF functions, EU AI Act tiers (summary)
- `scripts/risk_register.py` — canvas + controls catalog → `risk-register.csv` + `model-card.md`; exit 1 if a High risk has no control
