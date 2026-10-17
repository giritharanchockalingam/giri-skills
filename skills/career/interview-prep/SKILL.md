---
name: interview-prep
description: Use when the user has an interview scheduled (recruiter screen, hiring manager, panel, CIO/CEO, board-style case) for a senior director / VP / executive IT role and asks to prepare, practice, build STAR stories, draft a 90-day plan, or list questions to ask. Produces a competency-mapped story set in STAR+R format, a likely-question bank for the round type, a 90-day plan draft, and questions to ask. TRUTH LOCK - every story traces to the user's story bank or master résumé; no invented examples.
license: MIT
metadata:
  domain: career
  version: 0.1.0
  author: giri-skills
---

# Interview Prep (truth-locked)

## When to use
- "I have a panel interview Thursday", "grill me for the CIO round", "map my stories to this JD", "draft my 90-day plan", "what should I ask them".
- Mock-interview mode: user asks to be questioned and scored.
- NOT for: résumé rewriting (`resume-tailor`), post-interview thank-you notes (`outreach-and-followup`), offer decisions (`offer-evaluator`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Story bank (STAR+R entries with stable IDs) | yes | user file; format in `assets/story-bank.example.md` |
| Master résumé | yes (if story bank is thin) | user file; same format as `resume-tailor` |
| JD text | yes | user paste |
| Round type and interviewers (titles) | yes | user |
| Company context (public: strategy, recent news, tech stack) | no | user or web search, each fact sourced |
| Interview date and format (virtual/onsite, length, case prompt) | no | user |

Missing story bank: ask once; offer to build it from the master résumé by interviewing the user (one question per bullet). Never fill it from memory.

## TRUTH LOCK (hard rule)
1. Every story, number, title and outcome traces to a story-bank ID `[SB-nn]` or résumé line `[MR-Lnn]`.
2. Allowed: reframe a story for a different competency, tighten, pick which details to lead with, add a Reflection sentence the user confirms.
3. Not allowed: invent a story, add a metric, change the user's role in the story, upgrade "contributed" to "led".
4. If the JD needs a competency with no story, say so and offer: (a) interview the user for a true example, or (b) prepare an honest "here is the closest experience and how I would approach it" answer.
5. Output includes a traceability table: competency → story ID → fit (STRONG / ADEQUATE / GAP).

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. Map JD responsibilities to the competencies in `references/competency-map.md`. Rank by JD emphasis.
3. For each competency, select the best story from the story bank. Rewrite it in STAR+R per `references/star-r-format.md` (≤120 words spoken, ~90 seconds). Cite the ID.
4. Pull the question bank for the round type from `references/question-bank.md`. Pair each likely question with a story ID or a GAP note.
5. If the round is hiring manager, CIO/CEO or board-style: draft the 90-day plan from `assets/90-day-plan.md` using only JD facts and sourced company facts. Mark unknowns `[TO BE BASELINED — owner: ___]`.
6. Select 6–8 questions to ask from `references/questions-to-ask.md`, tuned to interviewer title.
7. Mock mode: ask one question at a time, score the answer against the STAR+R rubric (structure, specificity, scale, result, reflection; 1–5 each), give one fix, move on. Do not score stories not in the bank.
8. Run the self-check. Reply ≤50 words outside the artifact.

## Output
Markdown file `prep-<company>-<round>.md`:
1. Competency → story traceability table
2. STAR+R stories (ranked by JD emphasis)
3. Likely questions for this round with story mapping
4. 90-day plan draft (if applicable)
5. Questions to ask (by interviewer)
6. Gaps and how to handle them honestly

## Self-check
- [ ] Every story cites `[SB-nn]` or `[MR-Lnn]`; traceability table complete
- [ ] No metric or role claim beyond the source; Reflection lines confirmed by user or marked `[confirm]`
- [ ] Each story ≤120 words; Result contains a number where the source has one
- [ ] Question bank matches the round type; interviewer titles respected
- [ ] 90-day plan uses only JD and sourced facts; unknowns carry an owner
- [ ] No author personal data pulled from memory

## References
- `references/competency-map.md` — exec IT competencies, behavioral indicators, JD phrases
- `references/star-r-format.md` — STAR+R structure, timing, scoring rubric
- `references/question-bank.md` — questions by round type
- `references/questions-to-ask.md` — questions to ask by interviewer
- `assets/story-bank.example.md` — EXAMPLE story bank (fictional)
- `assets/90-day-plan.md` — plan skeleton
