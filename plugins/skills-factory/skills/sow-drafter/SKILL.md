---
name: sow-drafter
description: Use when the user asks to convert an approved proposal into a Statement of Work, draft or redline an SOW, or tighten scope, deliverables, acceptance criteria, assumptions, change control, or RACI for a services engagement. Produces an SOW on template with numbered scope and out-of-scope, deliverables with acceptance criteria, milestones, assumptions and dependencies (each a change-control trigger), governance and RACI, commercial schedule placeholders, and a scope-ambiguity register. Every figure comes from the proposal or estimate or is marked [TO BE BASELINED — owner: ___]. Do not use for proposal narrative (proposal-writer) or effort math (effort-estimator); legal terms are flagged for counsel, not drafted.
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: proposal, type: md, required: true, from: "approved proposal.md from proposal-writer (needs the Scope and deliverables table; assumptions register is carried over)"}
      - {name: existing_sow, type: md, required: false, from: "a SOW draft already in play (client paper or earlier version); reconciled against the approved proposal"}
    run:
      - {step: sow, kind: script, cmd: "python3 -I scripts/sow_from_proposal.py {proposal} --template assets/sow-template.md --out {out}/SOW.md --deliverables {out}/deliverables.csv --assumptions-check {out}/assumptions-check.csv [--existing-sow {existing_sow}] --reconcile {out}/sow-reconciliation.md"}
    outputs:
      - {path: "{out}/SOW.md", checks: [exists, sections:["Scope","Deliverables and acceptance","Assumptions","RACI","Change control"]]}
      - {path: "{out}/deliverables.csv", checks: [exists, csv:[id,deliverable,acceptance,phase,format], csv_rows:acceptance!empty]}
      - {path: "{out}/assumptions-check.csv", checks: [exists, max_lines:1]}
    modes:
      new: {case: agent-happy-path, bring: "the approved proposal"}
      existing: {case: agent-mode-existing, bring: "the approved proposal and the SOW draft already in play"}
---

# sow-drafter

## In a conversation: draft the SOW now
- **The request carries the approved proposal, the estimate and the commercial model** — including when the proposal and estimate are said to be attached but their contents are not in the conversation: draft the SOW **in this reply** on `assets/sow-template.md` from the stated facts. Never reply with only a request for files. In this order:
  1. **Scope** — numbered `S-nn` statements (verb + object + boundary, with appendix references) and mirrored `O-nn` out-of-scope items where ambiguity is likely.
  2. **Deliverables and acceptance** — table with ID, format, objective acceptance criteria, method, review window, approver (client role), milestone; plus a **deemed-acceptance clause**.
  3. **Milestones and payment** tied to accepted deliverables per the stated model (e.g. fixed price per wave → one milestone per wave on acceptance); amounts from the proposal pricing or `[TO BE BASELINED — owner: ___]`.
  4. **Assumptions** — every estimate quantity as an assumption with basis, consequence if false, change-control trigger = Y, and who confirms by when.
  5. **Client dependencies** with due dates and a delay-consequence clause.
  6. **Governance and RACI** with exactly one A per row; **change-control procedure** with a minor-change threshold.
  7. **Legal flags** — topics (IP, liability, warranties, termination, data protection, non-solicit, insurance) referenced to the MSA clause and marked "confirm with counsel", not drafted.
  8. Separately, internal (not shipped): **proposal → SOW traceability table** and **scope-ambiguity register**.
  Mark every value the request does not give `[TO BE BASELINED — owner: ___]` naming its source, and end with the few questions that close those gaps.
- **No proposal, or no commercial model** ("turn this proposal into an SOW"): ask once, in one list, for the commercial model (fixed / T&M / milestone / run-rate) and the estimate file (and the proposal if absent). Say in one line that acceptance-payment linkage depends on the model. Do not draft the commercial section on an assumed model; you may offer to draft scope and deliverables meanwhile.
- **Asked for subjective acceptance or an unsourced price** ("to the client's reasonable satisfaction", "put roughly what we discussed on the call"): say in one line that subjective acceptance invites disputes over sign-off and payment. Rewrite the criteria as objective, testable ones per `references/acceptance-criteria-patterns.md`. Show the total as `[TO BE BASELINED — owner: ___]` with a note that it must come from the estimate/proposal pricing — never print the discussed figure anywhere. Offer a **deemed-acceptance clause** (accepted unless written rejection with reasons within the review window) as the flexibility mechanism instead.

## Starting points
- **New** — the approved proposal becomes a SOW on the template: scope in and out, deliverables with acceptance criteria, milestones, team, every assumption carried, the change-control clause verbatim.
- **Existing** — add `existing_sow` (the client's paper or an earlier version): it is reconciled against the proposal — deliverables missing or added, subjective acceptance criteria, assumptions not carried, clauses absent — in `sow-reconciliation.md`, next to the SOW drafted from the proposal.

## When to use
- "Turn the approved proposal into an SOW."
- "Redline this SOW — the scope is too loose."
- "Write acceptance criteria for these deliverables."
- NOT for: proposal narrative (`proposal-writer`), estimate (`effort-estimator`), MSA/legal clauses (flag for counsel).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Approved proposal (final version) | yes | file |
| Estimate output: phases, effort, team, milestones | yes | file |
| Commercial model decided: fixed / T&M / milestone / run-rate | yes | user |
| Governing agreement (MSA) reference and any mandated SOW template | no | user / file |
| Client-side named roles for RACI | no | user |
| Existing SOW draft (redline mode) | yes in redline | file |

If the proposal or commercial model is missing, ask once. A missing estimate figure, MSA reference or client role name does not stop the draft: it is marked `[TO BE BASELINED — owner: ___]`. An SOW without a decided commercial model cannot define acceptance and payment linkage.

## Procedure
Read `../../shared/quality-bar.md` and `../../shared/writing-style.md` first. Redline convention applies in redline mode.

1. **Extract the scope baseline** from the proposal: objectives, phases, deliverables, team, timeline, assumptions, risks. Build a traceability table: proposal section → SOW clause. Anything in the proposal that is not scope, deliverable, assumption, or commercial term (marketing language, win themes) is dropped from the SOW.
2. **Write scope as numbered statements** per `references/sow-method.md` §2: each in-scope item is a verb + object + boundary ("Migrate the 42 interfaces listed in Appendix A from platform X to platform Y, including unit and integration test"). Mirror every in-scope item with an explicit out-of-scope statement where ambiguity is likely. Run the scope-ambiguity scan (§3) and register each ambiguity with its resolution.
3. **Define deliverables with acceptance criteria** using `references/acceptance-criteria-patterns.md`. Each deliverable: ID, description, format, acceptance criteria (objective, testable), acceptance method (review / test / demonstration), review window (days), deemed-acceptance rule, approver (client role).
4. **Decision point — commercial linkage.** Per `references/sow-method.md` §5: fixed-price → milestones tied to accepted deliverables; T&M → monthly invoicing against approved timesheets with a not-to-exceed; milestone → payment on acceptance with a percentage schedule; run-rate → service levels with credits. Amounts come from the estimate/proposal pricing or are `[TO BE BASELINED — owner: ___]`. Never place a number without a source.
5. **Convert every assumption into a change-control trigger**: assumption → basis → what happens if false (effort, schedule, price) → who confirms by when. Client dependencies get a due date and a consequence clause ("delay of client dependency D3 by more than 5 business days shifts dependent milestones day for day").
6. **Governance and RACI**: forums, cadence, decision rights, escalation path, and a RACI across the deliverables with one A per row. Client roles named if supplied, else role titles with `[TO BE BASELINED — owner: ___]`.
7. **Change-control procedure**: request → impact assessment (effort, schedule, price, risk) → approval authority and threshold → documentation. Include a minor-change threshold to avoid paperwork for trivial items.
8. **Legal flags**: list every clause that counsel must confirm against the MSA (IP, liability, warranties, termination, data protection, non-solicit, insurance). Do not draft these; reference the MSA or mark for counsel.
9. **Redline mode**: read the draft fully; score each clause against the ambiguity scan and acceptance patterns; produce `[KEEP] [SHARPEN] [CUT] [ADD] [TBD]` with rewritten text; deliver the clean version.
10. Run the self-check.

## Output
- File: `sow-<client>-<initiative>-v0.1.md` (or `-redline-<date>.md` in redline mode)
- Template: `assets/sow-template.md`
- Companion: `assets/assumptions-checklist.md` completed as Appendix C
- Internal (not shipped): proposal→SOW traceability table; scope-ambiguity register; legal-flags list

## Self-check
- [ ] Every in-scope item is numbered, bounded, and has a matching out-of-scope statement where ambiguity exists
- [ ] Every deliverable has objective acceptance criteria, method, review window, approver, deemed-acceptance rule
- [ ] Every assumption states consequence if false and is a change-control trigger
- [ ] Client dependencies have due dates and delay consequences
- [ ] Payment schedule links to accepted deliverables/milestones; all amounts sourced or `[TO BE BASELINED — owner: ___]`
- [ ] RACI has exactly one A per deliverable
- [ ] Legal clauses referenced to MSA or flagged for counsel; none drafted here
- [ ] No proposal marketing language, no other-client references, no author history

## References
- `references/sow-method.md` — scope statements, ambiguity scan, commercial linkage, change control, governance
- `references/acceptance-criteria-patterns.md` — patterns by deliverable type with examples
- `assets/sow-template.md` — SOW template
- `assets/assumptions-checklist.md` — assumptions and dependencies checklist by engagement type

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/sow-drafter --input <name>=<value> … --out <dir>` (see `--explain presales/sow-drafter`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.
