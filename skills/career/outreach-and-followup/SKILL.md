---
name: outreach-and-followup
description: Use when the user needs to write or time a job-search message - referral ask, recruiter reply, post-interview thank-you, status check, decline, or negotiation opener - by LinkedIn or email, for senior director / VP / executive IT roles. Produces 2-3 goal-labelled variants per message, a subject line, and the follow-up cadence (what to send, when, and when to stop). Facts come only from the user's inputs; no invented names, dates or claims.
license: MIT
metadata:
  domain: career
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: type, type: string, required: true, from: "referral-ask | recruiter-reply | thank-you | status-check | decline | negotiation-open"}
      - {name: context, type: json, required: true, from: "context.json: {recipient, company, role, last_touch_date, specifics:[...]} (layout: evals/fixtures/context-thank-you.json)"}
    run:
      - {step: fill, kind: script, cmd: "python3 -I scripts/fill.py --type {type} --context {context} --templates assets/message-templates.md --cadence-ref references/cadence.md --message {out}/message.md --cadence {out}/cadence.csv"}
      - {step: polish, kind: llm, template: assets/message-final-template.md, context: ["{out}/message.md", "{out}/cadence.csv", "references/message-types.md"], out: "{out}/message-final.md"}
    outputs:
      - {path: "{out}/message.md", checks: [exists, sections:["Variant A","Unfilled placeholders","Cadence"]]}
      - {path: "{out}/cadence.csv", checks: [exists, csv:[touch,date,channel,template,basis,stop_rule], csv_rows:touch!empty]}
      - {path: "{out}/message-final.md", checks: [exists, sections:["Message","Facts used","Cadence"], no_unowned_tbd]}
---

# Outreach and Follow-up

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py career/outreach-and-followup --input <name>=<value> … --out <dir>` (see `--explain career/outreach-and-followup`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## When to use
- "Write a note to X asking for a referral", "reply to this recruiter", "thank-you after my panel", "it's been 10 days, nudge them", "decline this politely", "open the comp conversation".
- "When should I follow up?" → cadence table.
- NOT for: résumé content (`resume-tailor`), interview answers (`interview-prep`), offer math (`offer-evaluator`), logging the touch (`application-tracker`, but remind the user to log it).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Message type (one of six) | yes | user |
| Recipient: name, title, relationship, channel (LinkedIn / email / text) | yes | user |
| Role and company | yes | user |
| Context: last contact date, what was said, interview details, deadline | yes for follow-ups | user or tracker row |
| Facts to cite (1–2 outcomes from master résumé / story bank, with IDs) | no | user file |
| Goal of this message (one sentence) | yes | user; ask once if missing |

No recipient name or context → ask once. Never guess names, dates, titles, or what was discussed.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. Identify message type and load its rules from `references/message-types.md` (goal, length, tone, must-include, must-avoid).
3. Draft 2–3 variants that differ in **strategy**, not tone (e.g., "Direct ask" vs "Soft ask via advice"; "Hold firm" vs "Open the door"). Label each with the goal it serves and the trade-off.
4. Pull structure from `assets/message-templates.md`; fill only from supplied facts. Any `<placeholder>` left unfilled is listed for the user.
5. Add a subject line for email. Keep LinkedIn connection notes ≤300 characters; InMail ≤150 words; email ≤180 words; thank-you ≤120 words.
6. Attach the cadence row from `references/cadence.md`: next touch date, channel, stop rule.
7. Run the self-check. Reply ≤50 words outside the artifact; drafts are the artifact.

## Output
```
Type: <message type> | Channel: <x> | Goal: <one line>

### Variant A — <strategy label>  (prioritizes …; trades off …)
Subject: …
<body>

### Variant B — <strategy label>
…

Cadence: next touch <date / +N business days> via <channel>; stop after <n> touches or on <event>.
Log: add a row to tracker.csv (stage, touch date, next action).
Unfilled placeholders: <list or "none">
```

## Self-check
- [ ] No name, date, title, or interview detail that the user did not supply
- [ ] Any résumé fact cited carries its `[MR-…]` / `[SB-…]` ID
- [ ] Variants differ in strategy, each labelled with what it prioritizes and trades off
- [ ] Length limits respected; one ask per message; no banned words; no flattery
- [ ] Cadence row present with a stop rule
- [ ] No author personal data pulled from memory

## References
- `scripts/fill.py` — fills the type's variants from context.json only (unfilled slots become owned markers) and dates the cadence in business days (stdlib, offline)
- `assets/message-final-template.md` — the llm step polishes into this; every fact and id from message.md is kept
- `references/message-types.md` — rules per type
- `references/cadence.md` — timing, channels, stop rules, escalation ladder
- `assets/message-templates.md` — skeletons with placeholders
