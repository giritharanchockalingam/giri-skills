---
name: exec-deck-redline
description: Use when the user asks to rework, redline, sharpen, tidy, or review an executive deck, steering-committee pack, board slide set, or pitch deck, or to change what a slide says (put a savings number, go-live date, or sponsor name on a slide, rewrite slide titles). Produces a slide-by-slide redline ([KEEP]/[SHARPEN]/[CUT]/[ADD]/[TBD]) that keeps the original storyline and sharpens it, rewritten slide titles as assertions, speaker notes, and [TO BE BASELINED — owner: ___] markers for every unsourced number, role, or date. Never replaces the narrative with a new one and never invents figures. Do not use for building the business case, savings or ROI model itself (value-case-builder), for building a deck from scratch (proposal-writer or the relevant domain skill first), or for document redlines (proposal-writer / sow-drafter redline modes).
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: deck, type: file, required: true, from: "deck.pptx (needs python-pptx, see requirements-optional.txt) or a deck.md/.txt export with '--- slide N ---' separators (layout: evals/fixtures/deck.md)"}
      - {name: draft_only, type: flag, required: false, flag: "--draft-only", from: "true to skip the model step: a mechanical redline (sources, title form, density) is written from the ledger, labelled as a draft"}
    run:
      - {step: ledger, kind: script, cmd: "python3 -I scripts/redline.py {deck} --ledger {out}/ledger.csv --unsourced {out}/unsourced-numbers.csv --redline-out {out}/redline.md {draft_only}"}
      - {step: redline, kind: llm, template: assets/redline-template.md, context: ["{out}/ledger.csv", "{out}/unsourced-numbers.csv", "assets/redline-rubric.md", "assets/storyline-checklist.md"], out: "{out}/redline.md", skip_if_present: [draft_only]}
      - {step: apply, kind: script, cmd: "python3 -I scripts/redline.py --apply {out}/redline.md --ledger {out}/ledger.csv"}
    outputs:
      - {path: "{out}/ledger.csv", checks: [exists, csv:[slide,title,text,verdict,reason,numbers_found], csv_rows:slide~^[0-9]+$, csv_rows:verdict!empty]}
      - {path: "{out}/unsourced-numbers.csv", checks: [exists, csv:[slide,number,context]]}
      - {path: "{out}/redline.md", checks: [exists, sections:["Redline table","Rewritten slides","Unsourced numbers"], no_unowned_tbd, numbers_trace_to:"{out}/ledger.csv"]}
    modes:
      existing: {case: agent-mode-existing, bring: "the deck you want redlined"}
---

# exec-deck-redline

## In a conversation: redline now
- **The request carries the audience, the decision and the slot** — including when the deck and source documents are said to be attached but their contents are not in the conversation: produce the redline **in this reply**. Never reply with only a request for the file. In this order:
  1. **Storyline as found** in ≤6 bullets, preserved; no new narrative (where slide text is not in the conversation, mark each bullet `[confirm against slide n]` rather than inventing content).
  2. **Decision test** — what the audience must believe after slide 1 and approve by the last slide.
  3. **Rubric score before and after** (`assets/redline-rubric.md`).
  4. **Redline table** — every slide gets a verdict `[KEEP] [SHARPEN] [CUT] [ADD] [TBD]`; each `[SHARPEN]` row has the full rewritten title (an assertion, ≤12 words) and body.
  5. **Numbers check** against the named sources (e.g. the estimate memo, the discovery synthesis); every unsourced number, role or date becomes `[TO BE BASELINED — owner: ___]`.
  6. **Time fit** — about one body slide per 2 minutes for a decision deck (30 minutes → ~15 body slides); overflow to the appendix and a **parked list** with destinations.
  7. **Executive summary slide** — the decision, three reasons (numbers or markers), next steps with owners and dates.
  8. **Speaker notes** ≤60 words per kept or sharpened slide, aligned to slide content · **Open items** with owners.
- **No decision, audience or slot** ("tidy up these slides"): ask once, in one list, for the audience, the decision the deck must obtain and the time slot. Do not begin slide rewrites without the decision test. Offer a **density-only pass** (titles, one point per slide, tables for lists) as the fallback if the user has no decision in mind, labelled "density-only — not a decision redline".
- **Asked to put an invented savings figure, go-live date or assumed sponsor on a slide**: say in one line that the redline marks unknowns rather than inventing figures, roles or dates, because the CFO will hold the team to them. Keep the slide (e.g. the business-case slide stays in the storyline as `[SHARPEN]`/`[TBD]`, not cut) and show: savings `[TO BE BASELINED — owner: ___]` with a note naming the source that would confirm it (the value case); go-live `[TO BE BASELINED — owner: ___]` tied to the estimate's critical path, not a chosen quarter; sponsor `[TO BE BASELINED — owner: ___]`, no assumed name or role. Never print the requested figure, quarter or person anywhere.

## Starting points
- **Existing** — your deck is read slide by slide into a ledger with every unsourced figure listed; the model step writes the redline (storyline kept, [KEEP]/[SHARPEN]/[CUT]/[ADD]/[TBD]), or with `draft_only` a mechanical redline flags unsourced figures, label titles and dense slides; the verdicts are applied back to the ledger.
- Only for existing: a redline always starts from a deck that already exists; to build a deck from nothing, start with proposal-writer or value-case-builder.

## When to use
- "Redline this steering-committee deck."
- "Sharpen these slides for the CIO — keep the story."
- "Review the board pack before Friday."
- NOT for: building a new deck (produce content with the domain skill, then this skill for the pass), documents (`proposal-writer`, `sow-drafter`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| The deck (PPTX, PDF, or slide text export) | yes | file |
| Audience and the decision the deck must obtain | yes | user |
| Time slot (minutes) | yes | user |
| Source documents behind the numbers (if any) | no | files |
| Constraints: template, slide limit, mandated sections | no | user |

If the audience or the decision is missing, ask once; a deck without a decision cannot be sharpened, only tidied. Missing source documents or slot constraints do not stop the redline: unsourced numbers are marked `[TO BE BASELINED — owner: ___]`.

## Procedure
Read `../../../shared/quality-bar.md` (redline convention) and `../../../shared/writing-style.md` first. The user's standing instruction applies: stay close to the original storyline and sharpen it; do not replace the narrative; no invented dollar figures, roles, or dates.

1. **Read the whole deck before touching any slide.** Write the storyline as it stands in ≤6 bullets (situation → complication → decision asked → options → recommendation → next steps, or whatever the author used). If the storyline is coherent, it stays. If it has a gap (e.g., no decision slide), that is an `[ADD]`, not a rewrite.
2. **Set the decision test.** From the audience and decision input: what must the reader believe after slide 1, and what must they approve by the last slide? Every slide is judged against this.
3. **Score the deck** with `assets/redline-rubric.md` (storyline, titles, evidence, so-what, density, numbers discipline, time fit). Record the score before and after; the after score is the self-check.
4. **Redline slide by slide** per `references/redline-method.md`:
   - `[KEEP]` unchanged.
   - `[SHARPEN]` rewrite the title as an assertion; cut to the one point; convert prose to a table or a single chart spec; state the "so what" in the first line of the body. Provide the rewritten text in full.
   - `[CUT]` with reason (duplicates, no decision relevance, appendix material) and where the content moves.
   - `[ADD]` only for storyline gaps; state source for any content added.
   - `[TBD]` for every number, role, date without a source in the provided materials: `[TO BE BASELINED — owner: ___]`.
5. **Decision point — time fit.** Count body slides vs time slot using the rule in the method (§4): roughly one slide per 2 minutes for a decision deck, less for discussion. Over the limit → move to appendix, do not shrink fonts.
6. **Write speaker notes** for every kept/sharpened body slide: ≤60 words, the spoken point, the number to say, the transition. Notes never contain content absent from the slide or the sources.
7. **Produce the executive summary slide** if missing (one slide: decision asked, three reasons with numbers or `[TBD]`, next steps with owners and dates). Place it as slide 2 (after title) or 1 if there is no title slide.
8. **Deliver**: redline table, rewritten slide text in order, speaker notes, parked list (content cut with destination), and the before/after rubric score. If the user supplied a PPTX and asks for the file edited, apply changes with the pptx tooling available in the session; otherwise deliver text ready to paste.
9. Run the self-check.

## Output
- File: `deck-redline-<client-or-topic>-<yyyy-mm-dd>.md`
- Sections: Storyline as found (≤6 bullets) · Decision test · Rubric score before/after · Redline table (slide #, original title, verdict, reason, new title, body change summary) · Rewritten slides (full text, in order) · Speaker notes · Parked content · Open items (`[TBD]` list with owners)

## Self-check
- [ ] Storyline preserved; changes are sharpening, not replacement
- [ ] Every title is an assertion with a number or consequence
- [ ] Every number, role, date has a source or `[TO BE BASELINED — owner: ___]`
- [ ] No slide carries more than one point; 3+ items are tables
- [ ] Slide count fits the time slot; overflow in appendix
- [ ] Speaker notes ≤60 words, aligned to slide content
- [ ] Executive summary slide present with decision, reasons, next steps
- [ ] No banned words; no author or other-client references

## References
- `references/redline-method.md` — storyline preservation, title assertions, slide patterns, density rules, time fit, speaker-note rules
- `assets/redline-rubric.md` — scoring rubric and redline table layout
- `assets/storyline-checklist.md` — storyline integrity checklist by deck type

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/exec-deck-redline --input <name>=<value> … --out <dir>` (see `--explain presales/exec-deck-redline`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.
