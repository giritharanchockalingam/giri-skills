---
name: interview-prep
description: Use when the user has an interview scheduled (recruiter screen, hiring manager, panel, CIO/CEO, board-style case) for a senior director / VP / executive IT role and asks to prepare, practice, build STAR stories, draft a 90-day plan, or list questions to ask. Produces a competency-mapped story set in STAR+R format, a likely-question bank for the round type, a 90-day plan draft, and questions to ask. TRUTH LOCK - every story traces to the user's story bank or master résumé; no invented examples.
license: MIT
metadata:
  domain: career
  adlc_stage: career
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: jd, type: file, required: true, from: "job description text file"}
      - {name: stories, type: md, required: true, from: "story bank with SB-nn ids and competency tags (layout: assets/story-bank.example.md)"}
      - {name: round, type: string, required: false, default: "hiring-manager", from: "recruiter | hiring-manager | panel | executive | case"}
      - {name: previous_round, type: md, required: false, from: "your debrief notes from the earlier round (story ids told, questions asked); adds what is spent and what to lead with"}
    run:
      - {step: prep, kind: script, cmd: "python3 -I scripts/prep.py --jd {jd} --stories {stories} --round {round} --competencies references/competency-map.md --questions references/question-bank.md --ask references/questions-to-ask.md --plan-template assets/90-day-plan.md --out-dir {out} [--previous-round {previous_round}]"}
    outputs:
      - {path: "{out}/competency-map.csv", checks: [exists, csv:[competency,status,name,in_jd,jd_evidence,story_ids], csv_rows:status~^(mapped|GAP)$]}
      - {path: "{out}/prep-pack.md", checks: [exists, sections:["Competency","Stories by competency","Likely questions","Gaps"]]}
      - {path: "{out}/questions-to-ask.md", checks: [exists, sections:["Questions to ask"]]}
      - {path: "{out}/90-day-plan.md", checks: [exists, sections:["Mandate","Days 1","Days 31","Days 61","Focus areas from the JD"], no_unowned_tbd]}
    modes:
      new: {case: agent-happy-path, bring: "the job description and your story bank"}
      existing: {case: agent-mode-existing, bring: "the job description, story bank and your last-round notes"}
---

# Interview Prep (truth-locked)

## In a conversation: prepare the candidate now
- **The request names the round, the interviewers and the JD / story bank** (even if the files are "attached" and their contents are not in the conversation): build the prep pack in this reply, in this order: (1) traceability table — JD competency (C1–C10 from `references/competency-map.md`, ranked by JD emphasis) → story ID → fit STRONG / ADEQUATE / GAP; (2) STAR+R stories, each ≤120 words and citing `[SB-nn]` or `[MR-Lnn]`; (3) likely questions for this round type, each mapped to a story ID or GAP; (4) for hiring-manager, CIO/CEO or executive rounds, a 90-day plan on the Days 1–30 / 31–60 / 61–90 skeleton with an owner per item, built only from JD facts, unknowns `[TO BE BASELINED — owner: ___]`; (5) questions to ask, grouped by interviewer title (e.g., business VP, peer directors, principal architect; CIO-specific questions for a CIO round); (6) gaps and how to handle each honestly. Where story content is not visible, keep the user's SB ids and mark the content `[TO BE BASELINED — owner: user, source SB-nn]`; never invent it. Never reply with only a request for files. Chat reply ≤50 words outside the pack.
- **Asked to make up a story** ("make up a SOX remediation story"): decline in one line, naming the **TRUTH LOCK** rule — every story must trace to the story bank or résumé, and an invented story fails the first follow-up question. Show the competency (SOX/audit → C7 Risk, security and compliance) as **GAP** in the traceability table, then offer (a) to interview the user for a true adjacent example, or (b) an honest "closest experience and how I would approach it" answer outline.
- **No story bank and no master résumé**: ask once for the story bank (or the résumé, to build one by interviewing the user). Do not fill stories from memory and do not run a mock round on invented stories.

## Starting points
- **New** — the JD's competencies are mapped to your story bank (gaps stay gaps — nothing is invented), with the round's likely questions, questions to ask and a 90-day plan skeleton.
- **Existing** — add your debrief from the last round: stories you already told are marked, competencies where every story is spent and JD competencies not shown yet are listed, and the questions already asked are kept for consistent follow-ups.

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

Story bank named but its contents not visible: build the pack anyway with the SB ids and `[TO BE BASELINED]` story content. No story bank and no résumé: ask once; offer to build it from the master résumé by interviewing the user (one question per bullet). Never fill it from memory.

## TRUTH LOCK (hard rule)
1. Every story, number, title and outcome traces to a story-bank ID `[SB-nn]` or résumé line `[MR-Lnn]`.
2. Allowed: reframe a story for a different competency, tighten, pick which details to lead with, add a Reflection sentence the user confirms.
3. Not allowed: invent a story, add a metric, change the user's role in the story, upgrade "contributed" to "led".
4. If the JD needs a competency with no story, say so and offer: (a) interview the user for a true example, or (b) prepare an honest "here is the closest experience and how I would approach it" answer.
5. Output includes a traceability table: competency → story ID → fit (STRONG / ADEQUATE / GAP).

## Procedure
1. Read `../../shared/quality-bar.md` and `../../shared/writing-style.md`.
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
- `scripts/prep.py` — JD competencies → story map (GAP when no story), prep pack by round type, questions to ask, 90-day plan skeleton (stdlib, offline)
- `references/competency-map.md` — exec IT competencies, behavioral indicators, JD phrases
- `references/star-r-format.md` — STAR+R structure, timing, scoring rubric
- `references/question-bank.md` — questions by round type
- `references/questions-to-ask.md` — questions to ask by interviewer
- `assets/story-bank.example.md` — EXAMPLE story bank (fictional)
- `assets/90-day-plan.md` — plan skeleton

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py career/interview-prep --input <name>=<value> … --out <dir>` (see `--explain career/interview-prep`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.
