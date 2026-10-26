---
name: discovery-interview
description: Use when the user asks to prepare for, run, or synthesize a client discovery call, scoping workshop, or stakeholder interview in a presales context. Produces a vertical-specific question bank (EdTech, Retail, Manufacturing, Travel), a pain/impact/urgency matrix, a hypothesis register, and a gaps list that feeds proposal-writer and effort-estimator. Do not use for client background research (client-research-brief) or for internal product research synthesis.
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: vertical, type: string, required: true, from: "one of edtech, retail, manufacturing, travel"}
      - {name: personas, type: string, required: true, from: "comma list of attendee personas, e.g. 'CIO,VP Digital'"}
      - {name: minutes, type: string, required: false, default: "45"}
      - {name: notes, type: md, required: false, from: "raw call notes / transcript (synthesize mode); without it only the prep pack is produced"}
      - {name: client, type: string, required: false, default: "<Client>"}
    run:
      - {step: pack, kind: script, cmd: "python3 -I scripts/build_pack.py --vertical {vertical} --personas {personas} --minutes {minutes} --banks references/question-banks --client {client} --out {out}/discovery-pack.md --five-closes {out}/five-closes.md --pain-matrix {out}/pain-matrix.csv"}
      - {step: synthesize, kind: script, cmd: "python3 -I scripts/synthesize.py {notes} --pain-matrix {out}/pain-matrix.csv --five-closes {out}/five-closes.md --client {client}", skip_if_missing: [notes]}
    outputs:
      - {path: "{out}/discovery-pack.md", checks: [exists, sections:["Time budget","Question plan","Five closes"]]}
      - {path: "{out}/five-closes.md", checks: [exists, sections:["Five closes"]]}
      - {path: "{out}/pain-matrix.csv", checks: [exists, csv:[pain,impact,urgency,evidence,owner]]}
    modes:
      new: {case: agent-mode-new, bring: "the client's industry and who will be on the call"}
      existing: {case: agent-happy-path, bring: "your raw notes or transcript from the call"}
---

# discovery-interview

## In a conversation: produce the pack now
- **The request names the vertical and the call** (who attends, how long, the trigger): write the prep pack **in this reply** — do not ask for files first. 3–5 hypotheses in a table (each with what would confirm or kill it and the questions that test it); 12–18 questions from the vertical's question bank ordered situation → pain → impact → urgency → decision → constraints, each tagged with persona and hypothesis ID; the five closes (decision owner, budget state, timeline driver, incumbents, success measure); a time budget that leaves about 20% to the client's questions. No question opens with a technology or vendor comparison.
- **The request gives call notes**: synthesize them now. Line 1 is the qualification call. Pains scored with verbatim evidence; impact without a stated figure scores 2 or lower and shows `[TO BE BASELINED — owner: ___]`; a gaps list names who at the client likely holds each missing fact and our owner; forcing events are named without inventing dates.
- **The request lacks the vertical or the mode (prep vs synthesize)**: ask once for mode, vertical and opportunity context, and stop — no question list before the vertical; never invent attendees, triggers or pains.
- **Asked to fill numbers, budgets or decision owners "from what clients usually do"**: say in one line that it was not in the notes and must be baselined; mark it `[TO BE BASELINED — owner: ___]`.

## Starting points
- **New** — before the call: a timed question plan for the attendees' personas from the vertical's question bank, with the five closes all open and an empty pain matrix.
- **Existing** — after the call: your notes or transcript are synthesised into the pain matrix and the five closes; anything the notes do not say stays an owned TBD.

## When to use
- "Prep me for the discovery call with <client> on <topic>."
- "Here are my notes from the workshop — synthesize them."
- "What should I ask a <vertical> CIO about <platform/initiative>?"
- NOT for: company background before a pitch (`client-research-brief`), RFP question lists (`rfp-compliance-matrix`), or pitch rehearsal (`orals-prep`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Client name, vertical (EdTech / Retail / Manufacturing / Travel / other) | yes | user |
| Opportunity context: initiative, platform(s), trigger event | yes | user / brief |
| Attendee list with titles (or "unknown") | no | user |
| Mode: `prep` (before call) or `synthesize` (after call) | yes | user |
| Raw notes / transcript (synthesize mode only) | yes in synthesize | file |
| Time available for the call (minutes) | no — default 45 | user |

If a required input is missing, ask once. Do not invent the vertical, attendees, or the client's pain.

## Procedure
Read `../../shared/quality-bar.md` and `../../shared/writing-style.md` first. Both apply to every output here.

### Mode A — prep
1. Classify the opportunity: vertical, buyer persona (CIO / CDO / VP Apps / COO / Head of Supply Chain / Provost / CFO), and initiative type (modernization, migration, AI, integration, cost-out, compliance). If the vertical is outside the four banks, use `references/question-banks/retail.md` as the structural base and say so.
2. Write 3–5 **hypotheses** before writing questions (`references/hypothesis-and-synthesis.md` §1). Each hypothesis states a suspected pain, who owns it, and what evidence would confirm or kill it. Questions exist to test hypotheses, not to fill time.
3. Load the vertical bank from `references/question-banks/<vertical>.md`. Select 12–18 questions using the time budget rule: ~3 minutes per open question, reserve 20% for their questions. Tag each selected question with the hypothesis it tests (H1…H5) and the persona it is aimed at.
4. Order questions using the funnel in `references/discovery-method.md` §2: situation → pain → impact → urgency → decision process → constraints. Never open with a technology question.
5. Add the five **non-negotiable closes** from `references/discovery-method.md` §4 (decision owner, budget state, timeline driver, incumbents, success measure). These are asked on every call.
6. Produce the prep pack (see Output). Include an "If they say X, go to Y" branch table for the 3 most likely pivots.

### Mode B — synthesize
1. Read the notes once end-to-end before extracting anything. Note what was *not* said (no numbers, no owner named, no timeline).
2. Extract every pain statement verbatim into the pain/impact/urgency matrix using the scoring rubric in `references/discovery-method.md` §3. A pain with no stated impact scores Impact = `[TO BE BASELINED — owner: ___]`, never a guessed number.
3. Update the hypothesis register: confirmed / killed / untested, with the quote that decides it.
4. Build the **gaps list**: every fact the proposal or estimate will need that the call did not produce (volumes, counts, contract dates, team size, budget range). Assign an owner on our side to chase each gap and the client-side person who likely holds it.
5. Decision point — qualify: apply the qualification gate in `references/discovery-method.md` §5. Output one of `PURSUE / PURSUE-WITH-CONDITIONS / PARK` with the two or three facts that drove it. Do not soften a PARK.
6. Draft the follow-up note (≤120 words, client-facing): what we heard, what we will bring next, the two or three things we need from them, by when.

### Both modes
7. Run the self-check. Strip anything that looks like a figure you did not hear or read.

## Output
| Mode | File | Format |
|---|---|---|
| prep | `discovery-prep-<client>-<yyyy-mm-dd>.md` | Sections: Hypotheses (table) · Question plan (table: #, question, persona, hypothesis, time) · Branches · Closes · Pre-reads to send |
| synthesize | `discovery-synthesis-<client>-<yyyy-mm-dd>.md` | Sections: Bottom line (qualification call) · Pain/Impact/Urgency matrix · Hypothesis register · Gaps list (table with owners) · Follow-up note · Parked items |

Template: `assets/discovery-pack-template.md`.

## Self-check
- [ ] Every question maps to a hypothesis; no orphan questions
- [ ] No number in the synthesis that is not a verbatim quote or marked `[TO BE BASELINED — owner: ___]`
- [ ] Five closes present (prep) or answered/gapped (synthesize)
- [ ] Qualification call stated on line 1 of the synthesis
- [ ] Gaps list has an owner for every row
- [ ] Follow-up note contains no internal commentary and no other-client references
- [ ] Tables for questions, matrix, hypotheses, gaps

## References
- `references/discovery-method.md` — funnel, scoring rubric, closes, qualification gate
- `references/hypothesis-and-synthesis.md` — hypothesis writing, listening-for-absence, synthesis patterns
- `references/question-banks/edtech.md`, `references/question-banks/retail.md`, `references/question-banks/manufacturing.md`, `references/question-banks/travel.md` — vertical banks
- `assets/discovery-pack-template.md` — output template

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/discovery-interview --input <name>=<value> … --out <dir>` (see `--explain presales/discovery-interview`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

