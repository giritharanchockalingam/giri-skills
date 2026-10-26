---
name: orals-prep
description: Use when the user asks to prepare for a pitch presentation, orals, bid defense, shortlist interview, steering-committee presentation, or executive readout where the team presents and takes questions, or to script what a presenter says in answer to an evaluator question ("for the 'why are you more expensive' question, have the lead say…"). Produces a timed script with speaker assignments, the opening and close, a likely-questions bank with sourced answers, red-team objections with responses, a rehearsal plan, and a scoring rubric for dry runs — with every number in the script traceable to the proposal or sources and every unknown marked [TO BE BASELINED — owner: ___]. Do not use for deck content rework (exec-deck-redline) or for building the battle card against an incumbent or competitor (competitive-positioning); both feed this skill, and spoken orals answers that mention the incumbent belong here.
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: proposal, type: md, required: true, from: "the submitted proposal.md (every number in the script must trace to it)"}
      - {name: speakers, type: string, required: true, from: "comma list of presenters in speaking order"}
      - {name: minutes, type: string, required: false, default: "60"}
      - {name: talk_track, type: md, required: false, from: "the team's existing talk track (`Name: line` per turn); checked for figures not in the proposal, airtime and unlisted speakers"}
    run:
      - {step: script, kind: script, cmd: "python3 -I scripts/orals.py {proposal} --minutes {minutes} --speakers {speakers} --question-bank references/question-bank-and-red-team.md --script {out}/orals-script.md --registry {out}/number-registry.csv --questions {out}/likely-questions.md [--talk-track {talk_track}] --check {out}/talk-track-check.md"}
    outputs:
      - {path: "{out}/orals-script.md", checks: [exists, sections:["Timed script","Airtime check","Number sheet","Handoffs"], numbers_trace_to:"{out}/number-registry.csv"]}
      - {path: "{out}/number-registry.csv", checks: [exists, csv:[number,section,context]]}
      - {path: "{out}/likely-questions.md", checks: [exists]}
    modes:
      new: {case: agent-happy-path, bring: "the submitted proposal and who presents"}
      existing: {case: agent-mode-existing, bring: "the proposal and your team's current talk track"}
---

# orals-prep

## In a conversation: prepare the team now
- **The request carries the format and the team** (duration, presentation vs Q&A split, evaluators, presenters) — including when the proposal, deck, compliance matrix or battle card are said to be attached but their contents are not in the conversation: write the orals pack **in this reply** from the stated facts. Never reply with only a request for files. In this order:
  1. **Evaluation map** — each stated criterion (or, if criteria are unknown, the proposal's structure) → slide(s) → speaker.
  2. **Timed script** fitting the presentation slot — segments with start/end minute, speaker, slide, point, proof (number with source or `[TO BE BASELINED — owner: ___]`), transition; **opening ≤90 s and close ≤60 s written verbatim**; scripted handoffs; **airtime check** (every speaker ≥1 segment, none >40%).
  3. **Likely-questions bank** (table) — one question per compliance partial (e.g. each security partial), per `[TBD]`, per estimate assumption, plus the battle card's objections and the standard evaluator set; each answer ≤75 words with the answerer, evidence pointer and "do not say" line.
  4. **The hard three** (typically price, the known gaps, incumbent continuity) with honest answers that state the gap and the mitigation.
  5. **Red-team protocol** and **rehearsal plan** — three dry runs (content and timing, Q&A only, full with red team), each with a date or `[TO BE BASELINED — owner: ___]` and the rubric (`assets/orals-rubric.md`).
  6. **Number sheet** — every figure the team may say, with its proposal page · **Logistics and risks** · **Open items** with owners.
  No competitor is named in any answer.
- **No format or team** ("help us get ready for the pitch"): ask once, in one list, for the format (duration, presentation/Q&A split, attendees, evaluation criteria), the presenting team and the proposal and deck. Do not produce a timed script without the duration and the team. If the proposal is available, offer to generate the question bank from it as a parallel first step.
- **Asked to script new numbers, uncleared client claims or a competitor attack** ("say we are 30% faster", "our last clients saw 40% savings", "name the incumbent's failed upgrade"): say in one line that new numbers and competitor naming in orals create credibility and compliance risk. Rewrite the answer around the proposal's basis of estimate, P80 contingency and a like-for-like comparison; use cleared references only, in their cleared form, or omit them; replace the competitor mention with a ghost line in consequence language (the risk the client should weigh, and how we remove it). Never print the requested percentages in the answer, unless the user shows they are in the proposal with a source.

## Starting points
- **New** — from the submitted proposal: a timed script skeleton with speakers, an airtime check, a number sheet every presenter keeps in front of them, and likely evaluator questions.
- **Existing** — add your team's current talk track: every figure it says that the proposal does not contain is flagged, each speaker's spoken length is compared with their slot, and people with lines but no slot are listed (`talk-track-check.md`).

## When to use
- "We are shortlisted; orals are Thursday — prepare us."
- "Run a red-team on our pitch."
- "Build the Q&A bank for the steering-committee readout."
- NOT for: fixing the slides (`exec-deck-redline`), building the battle card (`competitive-positioning`), writing the proposal (`proposal-writer`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| The proposal or readout document (final) | yes | file |
| The deck to be presented (final or near-final) | yes | file |
| Format rules: duration, presentation vs Q&A split, attendees (names/roles if known), evaluation criteria, allowed presenters | yes | RFP / client / user |
| Our presenting team (names, roles on the engagement) | yes | user |
| Battle card (if a competitive pursuit) | no | competitive-positioning output |
| Compliance matrix and clarification answers (RFP pursuits) | no | rfp-compliance-matrix output |

If format rules or the team are missing, ask once; a script cannot be timed or assigned without them. Missing files (proposal, deck, compliance matrix, battle card) or unknown evaluation criteria do not stop the pack when the format and team are stated: the gaps are marked `[TO BE BASELINED — owner: ___]`.

## Procedure
Read `../../shared/quality-bar.md` and `../../shared/writing-style.md` first.

1. **Decode the evaluation**: from the format rules, list what is scored and by whom. If the evaluation criteria are unknown, mark `[TO BE BASELINED — owner: ___]` and assume the proposal's structure is the scoring frame. Map each scored criterion to the slide(s) and speaker that will prove it (`references/orals-method.md` §1).
2. **Build the timed script** on `assets/script-template.md`: segments with start/end minute, speaker, slide, the point (one sentence), the proof (number with source), the transition line. Reserve ≥35% of total time for Q&A unless the format fixes it. Opening ≤90 seconds: their situation, the outcome, what they will hear. Close ≤60 seconds: the ask and the next step.
3. **Assign speakers by credibility**, not seniority: the person who will do the work speaks to the approach; the engagement lead to governance and commitments; the executive sponsor opens and closes. Every speaker has ≥1 segment and ≤40% of airtime. Note handoffs explicitly.
4. **Generate the likely-questions bank** (`references/question-bank-and-red-team.md` §1): from the proposal's weak spots (every `P`/`N` in the compliance matrix, every `[TBD]`, every assumption), from the evaluation criteria, from the battle card's objections, and from the standard evaluator set. For each: question, who answers, the answer (≤75 words, number + source, no new claims), the evidence slide/page, and the "do not say" line.
5. **Decision point — the hard three.** Identify the three questions the team most fears (price, a gap, a credibility challenge). Write the answers with the engagement lead; rehearse these first and most. If an honest answer exposes a real gap, the answer states the gap and the mitigation; it does not spin.
6. **Red-team** (§2): assign one person to play the skeptical evaluator and one the incumbent-friendly evaluator; run the objections in the bank plus three unscripted; score with `assets/orals-rubric.md`; log every answer that exceeded 90 seconds, invented a number, or contradicted the proposal.
7. **Rehearsal plan**: dry run 1 (content and timing), dry run 2 (Q&A only), dry run 3 (full, with red team), each with a date and the rubric scores. Fix list after each.
8. **Logistics and risk**: room/virtual setup, backups (PDF of deck, offline), who speaks if someone drops, name pronunciation for attendees, prohibited content (other clients' names without clearance, pricing details if sealed).
9. Run the self-check.

## Output
- File: `orals-prep-<client>-<yyyy-mm-dd>.md`
- Sections: Evaluation map (criterion → slide → speaker) · Timed script · Speaker assignments and handoffs · Likely questions bank (table) · The hard three · Red-team log · Rehearsal plan · Logistics and risks · Open items
- Companion: `assets/orals-rubric.md` scored per dry run

## Self-check
- [ ] Every scored criterion mapped to a slide and a speaker
- [ ] Script timed to the format; Q&A ≥35% unless fixed by the client
- [ ] Every number in the script and answers traces to the proposal/sources; none new
- [ ] Hard three identified with honest answers that state gaps and mitigations
- [ ] Each answer ≤75 words with a named answerer and evidence pointer
- [ ] No competitor named in any answer; no uncleared client references
- [ ] Rehearsal plan has dates and rubric scores recorded
- [ ] Logistics and backups listed

## References
- `references/orals-method.md` — evaluation decoding, script structure, speaker assignment, answer discipline, delivery rules
- `references/question-bank-and-red-team.md` — standard evaluator questions by theme, question-generation sources, red-team protocol
- `assets/script-template.md` — timed script layout
- `assets/orals-rubric.md` — dry-run scoring rubric

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/orals-prep --input <name>=<value> … --out <dir>` (see `--explain presales/orals-prep`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.
