---
name: orals-prep
description: Use when the user asks to prepare for a pitch presentation, orals, bid defense, shortlist interview, steering-committee presentation, or executive readout where the team presents and takes questions. Produces a timed script with speaker assignments, the opening and close, a likely-questions bank with sourced answers, red-team objections with responses, a rehearsal plan, and a scoring rubric for dry runs — with every number in the script traceable to the proposal or sources and every unknown marked [TO BE BASELINED — owner: ___]. Do not use for deck content rework (exec-deck-redline) or for competitive analysis (competitive-positioning); both feed this skill.
license: MIT
metadata:
  domain: presales
  version: 0.1.0
  author: giri-skills
---

# orals-prep

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

If format rules or the team are missing, ask once; a script cannot be timed or assigned without them.

## Procedure
Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md` first.

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
