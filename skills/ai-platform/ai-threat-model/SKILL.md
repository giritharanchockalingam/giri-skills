---
name: ai-threat-model
description: Use when an LLM app, RAG system or agent needs a security threat model before build or release — "threat model our agent", "STRIDE this architecture", "map our chatbot to the OWASP LLM Top 10", "what are the open high threats", "security architecture review for the AI assistant", "no control register yet — what is open?". Produces threats.csv (stable threat ids, STRIDE-per-element plus OWASP Top 10 for LLM Applications 2025 items per component, likelihood × impact severity, mitigation ids, residual status and owner), dfd.md (mermaid DFD with trust zones and boundary-crossing flows) and threat-report.md (Summary, Data flow, Threats by severity, Open high threats, Method & limits) from a components CSV, a flows CSV and an optional controls register; an optional max_open_high gate fails the run. Open threats with no owner name the Security architect. Not for adversarial testing of a running app (red-team-suite), runtime guardrail rules (guardrails-config) or regulatory risk tiering (ai-governance-risk).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: architecture
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-no-controls-not-invented, bring: "the components and data flows of a design on paper"}
      existing: {case: agent-happy-path, bring: "your system's design plus its current control register"}
    inputs:
      - {name: components, type: csv, required: true, from: "DFD elements id,name,kind,trust_zone,handles_pii,write_actions,internet_facing (layout: assets/components-template.csv; kind user|app|llm|retriever|vector_store|tool|data_store|external_api|agent)"}
      - {name: flows, type: csv, required: true, from: "data flows from,to,data,crosses_trust_boundary (layout: assets/flows-template.csv)"}
      - {name: controls, type: csv, required: false, from: "control register threat_id,mitigation_id,status,evidence,owner (layout: assets/controls-template.csv; status in_place|planned); without it every threat is open and owned by the Security architect"}
      - {name: max_open_high, type: string, required: false, from: "integer gate: the run fails (exit 1) when open high threats exceed it; absent = no gate"}
    run:
      - {step: threat-model, kind: script, cmd: "python3 -I scripts/threat_model.py --components {components} --flows {flows} [--controls {controls}] [--max-open-high {max_open_high}] --out-dir {out}"}
    outputs:
      - {path: "{out}/threats.csv", checks: [exists, "csv:[threat_id,element,category,threat,severity,mitigation,status,owner]", "csv_rows:severity~^(high|medium|low)$", "csv_rows:status~^(open|planned|mitigated)$", csv_rows:owner!empty, cmd:"python3 -I scripts/threat_model.py --verify {path}"]}
      - {path: "{out}/dfd.md", checks: [exists, mermaid_parses, contains:"subgraph", contains:"Trust zone:"]}
      - {path: "{out}/threat-report.md", checks: [exists, sections:["Summary","Data flow","Threats by severity","Open high threats","Method & limits"], no_unowned_tbd, contains:"OWASP LLM Top 10 (2025)"]}
---

# AI Threat Model (STRIDE + OWASP LLM Top 10 2025)

## In a conversation: write the threat model now
- **The request names the architecture** (components such as web app, orchestrator, hosted LLM, vector store, refund API), even when the CSVs are not in the conversation: build the threat model **in this reply**, in this order. Never reply with only a request for the CSVs.
  1. **Components table** in the `assets/components-template.csv` columns: `id, name, kind, trust_zone, handles_pii, write_actions, internet_facing` (kinds: user, external_api, app, llm, retriever, tool, agent, vector_store, data_store). **Flows table**: `from, to, data, crosses_trust_boundary`. Attributes the user did not state are `[TO BE BASELINED — owner: Solution architect]`; ask the user to confirm the two tables in one list.
  2. The command that produces the files: `python3 -I scripts/threat_model.py` via the runner (see "How to run" below), giving `threats.csv`, `dfd.md`, `threat-report.md`.
  3. **Threats by severity** (high first), one row each: `threat_id` (stable: `<component>:<category>` or `<from>><to>:<category>`) | element | category (STRIDE letter or OWASP 2025 id LLM01–LLM10) | threat | likelihood | impact | severity | mitigation ids | status | owner. Apply `references/method.md`: STRIDE per element (external entity S, R; process S, T, R, I, D, E; data store T, I, D; flow T, I, D); OWASP rules (LLM01 on llm/agent reachable from an untrusted origin; LLM02 where PII is handled; LLM05 on anything receiving model output; LLM06 where write_actions = yes; LLM07, LLM09, LLM10 on the llm; LLM08 on vector store and retriever). Likelihood = 1 + exposed + boundary; impact = 1 + PII + write (cap 3; D and LLM10 fixed at 2); severity high ≥ 6, medium 3–4, low ≤ 2.
  4. **Mitigation ids** only from `assets/mitigations.csv`: S M01; T M02, M07; R M03; I M04; D M05 (stores also M08); E M06, M07; LLM01 M20–M23; LLM02 M24, M25; LLM03 M26, M27; LLM04 M28, M27; LLM05 M29, M30; LLM06 M31–M33; LLM07 M34, M35; LLM08 M36, M28; LLM09 M37, M38; LLM10 M39, M40.
  5. **Open high threats** with owner: status comes only from a control register; with none, every threat is `open` and owned by `[TO BE BASELINED — owner: Security architect]`.
  6. **Data flow**: a mermaid flowchart, one subgraph per trust zone, boundary-crossing flows labelled.
  7. **Method & limits**: rule-based enumeration of the declared design; misses business-logic abuse and attack chains; not a penetration test or a security sign-off.
- **Components given, flows missing**: still show the components table and the threats the components alone imply, and ask once for the flows CSV; do not guess flows.
- **No control register, or asked to "assume the usual controls are in place"**: decline in one line (a control counts only with a register row and evidence); no threat is marked mitigated or planned; every threat is open, owner `[TO BE BASELINED — owner: Security architect]`; offer `assets/controls-template.csv` for control owners to fill, then re-run.
- **Release gate** ("fail if more than N high threats remain open"): report open high vs the limit — more than N fails (exit 1), equal passes; all outputs are still written.
- **Live jailbreak or prompt-leak testing of a running app**: route to `red-team-suite`; offer this skill for the design-level threat model.

## Starting points
- **New:** components and flows of a design not yet built give every threat, all open and owned by the Security architect until controls exist.
- **Existing:** add the control register you already keep (`controls`); each in-place or planned control closes or downgrades its threats, and only the residual open threats count toward the gate.

## When to use
- ADLC architecture stage: the component and data-flow design of an LLM app, RAG pipeline or agent is drafted and needs a security review before build.
- Before a release review: re-run with the current control register to show residual (open) threats and gate on open highs.
- After a design change (new tool, new data store, new vendor model): re-run; threat ids are stable, so the control register carries over.
- NOT for: attacking a running app (`red-team-suite`), writing runtime input/output filters (`guardrails-config`), EU AI Act or NIST risk tiering (`ai-governance-risk`), or a penetration test or security sign-off.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `components` — id, name, kind, trust_zone, handles_pii, write_actions, internet_facing | yes | solution architect (copy `assets/components-template.csv`) | run stops (exit 2), asks once |
| `flows` — from, to, data, crosses_trust_boundary | yes | solution architect (copy `assets/flows-template.csv`) | run stops (exit 2), asks once |
| `controls` — threat_id or mitigation_id, status, evidence, owner | no | security architect / control owners (copy `assets/controls-template.csv`) | every threat is `open`; owner `[TO BE BASELINED — owner: Security architect]` |
| `max_open_high` — integer | no | CISO / release owner | no gate; report says "no gate set" |

Component ids are letters, digits and `_`. A flow whose ends sit in different trust zones is treated as crossing a boundary even if marked `no` (listed in `dfd.md`).

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Build the components and flows CSVs from the architecture diagram; one row per component and per directed flow.
3. Run the agent. `scripts/threat_model.py` applies STRIDE per element and the OWASP LLM 2025 rules in `references/method.md`, scores likelihood × impact, and attaches mitigation ids from `assets/mitigations.csv`.
4. First run without controls: hand `threats.csv` to control owners; they record `in_place` / `planned` rows by `threat_id` or `mitigation_id` with evidence and owner.
5. Re-run with the controls file and, for a release gate, `max_open_high`.
6. Review the open high threats with the Security architect; add threats the rules cannot see (business-logic abuse, attack chains) by hand to the risk register.
7. Run the self-check.

## Output
- `threats.csv` — `threat_id, element, element_type, category, threat, likelihood, impact, severity, mitigation, status, owner, evidence`; sorted by severity then id. `threat_id` = `<component>:<category>` or `<from>><to>:<category>`.
- `dfd.md` — mermaid flowchart: one subgraph per trust zone, boundary-crossing flows labelled and dashed red.
- `threat-report.md` — **Summary**, **Data flow**, **Threats by severity**, **Open high threats**, **Method & limits** (with the mitigation catalogue used).

## Self-check
- [ ] Every component and flow from the architecture is in the inputs (unlisted elements are not analysed)
- [ ] Every threat has a severity from the documented rule and at least one mitigation id
- [ ] Status comes only from the control register; no control is assumed
- [ ] Every owner is a named role or `[TO BE BASELINED — owner: Security architect]`
- [ ] Limits stated: rule-based enumeration, not a penetration test or sign-off

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-threat-model --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-threat-model`). Report the `run.json` results; do not hand-write the deliverables the script produces (`threats.csv`, `dfd.md`, `threat-report.md`). With `max_open_high` set, the run is a gate: more open high threats than the limit fails the run (exit 1) and all outputs are still written.

## References
- `references/method.md` — element mapping, OWASP rules, likelihood/impact/severity, status rules, limits
- `references/sources.md` — OWASP 2025 list and STRIDE-per-element sources with dates checked
- `assets/owasp-llm-top10-2025.csv` — LLM01–LLM10 ids, names, paraphrase, applicability, mitigation ids
- `assets/mitigations.csv` — mitigation catalogue (id, mitigation, maps_to, applies_to)
- `scripts/threat_model.py` — generator and `--verify` mode (argparse; stdlib)
