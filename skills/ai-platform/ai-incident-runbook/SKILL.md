---
name: ai-incident-runbook
description: Use when something has gone wrong with a live AI system and the user needs to respond — "the bot leaked customer data", "we have a prompt injection incident", "the assistant gave harmful answers", "LLM costs spiked overnight", "how severe is this AI incident", "write the runbook and postmortem". Produces runbook.md (Severity, Immediate actions, Containment, Recovery, Communications, Postmortem) and incident.json from an incident facts CSV - severity SEV1-SEV4 with the matrix rows that fired, the bundled per-category playbook (contain, eradicate, recover, verify), a timeline anchored on started_at, a comms checklist with a regulator track only when regulated data is yes or unknown, and a postmortem skeleton. Not legal advice; not for monitoring (llm-observability) or general software incidents without an AI failure mode.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: operate
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: incident, type: csv, required: true, from: "incident facts key,value (layout: assets/incident-template.csv) - category, started_at required; unknowns stay unknown"}
      - {name: matrix, type: csv, required: false, from: "your severity matrix rule_id,conditions,severity,reason; without it the skill's documented default (references/severity-matrix.md) is used and stated"}
    run:
      - {step: runbook, kind: script, cmd: "python3 -I scripts/runbook.py --incident {incident} [--matrix {matrix}] --out-dir {out}"}
    outputs:
      - {path: "{out}/runbook.md", checks: [exists, sections:["Severity","Immediate actions","Containment","Recovery","Communications","Postmortem"], no_unowned_tbd, numbers_trace_to:"{out}/incident.json"]}
      - {path: "{out}/incident.json", checks: [exists, json, contains:"\"fired_rules\"", contains:"\"matrix_source\""]}
    modes:
      new:      {case: agent-happy-path, bring: "the facts of an incident as you know them now"}
      existing: {case: agent-mode-existing, bring: "the incident facts plus your team's own severity matrix"}
---

# AI Incident Runbook

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-incident-runbook --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-incident-runbook`). Report the `run.json` results; do not hand-write the deliverables the script produces (`runbook.md`, `incident.json`). A severity matrix in which no row fires fails the run (exit 1) on purpose.

## Starting points
- **New** — no runbook or severity policy yet: bring the incident facts; the skill classifies with its documented default matrix (and says so) and assembles the runbook.
- **Existing** — bring the incident facts and your team's own severity matrix; every row of your matrix is evaluated, the fired rules are listed, and a matrix with no baseline row fails the run instead of guessing.

## When to use
- A live AI incident: hallucination, data leak, prompt injection, outage, cost spike or harmful output.
- Classifying severity consistently and showing why; producing the comms checklist and the postmortem skeleton.
- NOT for: legal advice on notification duties (route to counsel), detection and SLO alerting (`llm-observability`), pre-launch risk review (`ai-governance-risk`), turning feedback into fixes (`feedback-improvement-loop`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `incident` CSV: `category`, `started_at` | yes | incident commander |
| `users_affected`, `data_exposed`, `regulated_data` (yes/no/unknown) | no — missing = unknown, and unknown escalates | incident commander, privacy |
| `detected_at`, `detected_by`, `system_name`, `summary` | no | alert or report |
| `owner_<role>`: incident_commander, engineering_lead, comms_lead, legal_privacy, security_lead | no — missing = TBD with the accountable role | on-call rota |
| `matrix` CSV (rule_id, conditions, severity, reason) | no | your incident policy; default = the skill's documented matrix |

If `incident` is missing the runner exits 2 and asks once. No time, name or count is invented.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Fill `assets/incident-template.csv` with what is known now; leave unknowns as `unknown`.
3. Run the skill. The script evaluates every matrix row (`references/severity-matrix.md`), takes the most severe, and lists every fired row as reasoning.
4. It loads `assets/playbooks/<category>.md` into Containment (contain, eradicate) and Recovery (recover, verify).
5. It builds the timeline from `started_at` / `detected_at` only; later events are TBD for the Incident commander.
6. Communications: internal always; customer unless `users_affected = 0`; regulator only when `regulated_data` is yes or unknown, with Legal / privacy confirming obligations.
7. Re-run as facts change (unknown → yes/no); severity can go down only with evidence.
8. Run the self-check.

## Output
- `runbook.md`: Severity (fired rules, facts, unknowns), Immediate actions (+ Timeline), Containment, Recovery, Communications (internal, customer, regulator), Postmortem (fields and action items).
- `incident.json`: the same record, machine-readable.

## Self-check
- [ ] Severity shows every fired row and the matrix source (supplied or the skill's default)
- [ ] Unknown data/regulated status escalated, not assumed away
- [ ] Regulator track present only for regulated yes/unknown; no deadlines invented
- [ ] Timeline holds only supplied times; the rest TBD with an owner role
- [ ] Every owner named or `[TO BE BASELINED — owner: <role>]`
- [ ] Postmortem action items include a regression eval case and the missing alert

## References
- `references/severity-matrix.md` — the default matrix, method, comms rule
- `references/severity-matrix.default.csv` — machine copy of the default matrix
- `assets/playbooks/` — per-category playbooks (contain, eradicate, recover, verify)
- `assets/incident-template.csv` — input layout
- `scripts/runbook.py` — the classifier and runbook builder (argparse; stdlib)
