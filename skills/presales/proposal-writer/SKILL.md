---
name: proposal-writer
description: Use when the user asks to write, assemble, structure, or redline a client proposal, RFP response narrative, executive summary, or statement of qualifications — including assembling it from a win-themes.json (themes, proof, so_what) with a discovery pack and estimate memo, wording the outcome claims in a proposal's executive summary, or being asked to "fill in typical numbers so it reads well". Produces an on-template proposal — executive summary, understanding of needs, approach, solution, team, timeline, governance, risks, assumptions, pricing placeholders, why-us — built on win themes and ghosting the competition, with every figure sourced or marked [TO BE BASELINED — owner: ___]. In redline mode it keeps the existing storyline and sharpens it section by section. Do not use for compliance matrices (rfp-compliance-matrix), SOWs (sow-drafter), pricing math (effort-estimator), building the ROI/benefits model itself (value-case-builder) or competitor battle cards (competitive-positioning).
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: win_themes, type: json, required: true, from: "win-themes.json: {client, initiative, themes:[{theme, proof, so_what}]} (layout: evals/fixtures/win-themes.json)"}
      - {name: discovery, type: md, required: false, from: "discovery pack from discovery-interview (pain matrix is quoted into section 2)"}
      - {name: estimate, type: md, required: false, from: "estimate memo from effort-estimator (bottom line is quoted into pricing)"}
      - {name: value_case, type: md, required: false, from: "value-case.md from value-case-builder (bottom line is quoted into objectives)"}
      - {name: existing, type: md, required: false, from: "a proposal draft the team already wrote; redlined against the win themes and inputs (storyline kept), no model step"}
      - {name: draft_only, type: flag, required: false, flag: "--draft-only", from: "true to skip the model sharpen step: the assembled draft becomes proposal-final.md"}
    run:
      - {step: assemble, kind: script, cmd: "python3 -I scripts/assemble.py {win_themes} --library assets/section-library.md [--discovery {discovery}] [--estimate {estimate}] [--value-case {value_case}] --out {out}/proposal.md --placeholders {out}/placeholders.csv --sources {out}/sources.md --final {out}/proposal-final.md {draft_only} [--existing {existing}] --redline {out}/proposal-redline.md"}
      - {step: sharpen, kind: llm, template: assets/proposal-final-template.md, context: ["{out}/proposal.md", "{out}/sources.md", "{out}/placeholders.csv", "references/proposal-method.md"], out: "{out}/proposal-final.md", skip_if_present: [existing, draft_only]}
    outputs:
      - {path: "{out}/proposal.md", checks: [exists, sections:["Executive summary","Understanding of your needs","Scope and deliverables","Risks and assumptions","Pricing","Why"], numbers_trace_to:"{out}/sources.md"]}
      - {path: "{out}/placeholders.csv", checks: [exists, csv:[placeholder,section,owner]]}
      - {path: "{out}/proposal-final.md", checks: [exists, sections:["Executive summary","Scope and deliverables","Pricing","Why"], no_unowned_tbd, numbers_trace_to:"{out}/sources.md"]}
    modes:
      new: {case: agent-mode-new, bring: "win themes, plus discovery pack and estimate memo"}
      existing: {case: agent-mode-existing, bring: "your team's proposal draft plus the win themes and inputs"}
---

# proposal-writer

## In a conversation: write the proposal now
The reply **is the proposal (or its redline)**, never only a command or a request for files. About 1,000 tokens: tables, one-line section bodies, no preamble.

**Never**
- Never state a benefit percentage or outcome number the user "wants because it reads stronger" or calls "typical" (e.g. "reduce run cost by 40%, recovery time by 75%"). Decline in one line: *outcome numbers must come from the value case (value-case-builder) or the client's own baseline*. Show the outcome table with Baseline and Target `[TO BE BASELINED — owner: ___]`, and offer the compliant alternative: **state the outcome as a hypothesis, with baselining as a phase-1 deliverable and the measurement method named**. The numbers appear nowhere else in the reply.
- Never fill a slot "with typical numbers": every unfilled slot is `[TO BE BASELINED — owner: ___]`.
- Never write "understanding of needs" from imagination; never name the incumbent or competitor in client text (ghost them).
- Never keep a figure in a team draft that no input backs (e.g. an unsourced "40% cost cut") — replace it with an owned marker; keep figures an input backs (e.g. a price the estimate memo states).

**Which reply**
1. **No problem statement / evidence** (e.g. "draft a proposal for a retail client, make it compelling"): ask once, one list — problem statement with evidence (discovery synthesis, RFP or notes), scope/solution outline, estimate output (or confirmation to use pricing placeholders). Write no needs section. Close with: "Once these arrive I start from the win-theme worksheet (`assets/win-theme-worksheet.md`)."
2. **Win-themes file missing** when assembling ("Write the proposal." with only a discovery pack): ask once for **`win-themes.json`** (`{client, initiative, themes:[{theme, proof, so_what}]}`); `scripts/assemble.py` stops (exit 1) without it.
3. **Write** (inputs described or attached), in this order:
   a. **Win-theme worksheet first** (internal): `| # | Client hot button ("quoted" from their evidence, or [quote — discovery §, owner: ___]) | Discriminator | 4 tests: relevance · uniqueness · provability · consequence | Proof (cleared) | Ghost line |`. A theme without proof is cut.
   b. **Executive summary (≤1 page)**: first sentence = the outcome in the client's KPI terms; 3–5 bullets each tied to a theme; what it takes — duration, team and onshore/offshore split copied exactly from the estimate; price `[TO BE BASELINED — owner: ___]` unless a price is supplied.
   c. **Sections in `assets/section-library.md` order** (Understanding of your needs · Objectives and success measures · Approach and methodology · Proposed solution · Scope and deliverables · Timeline · Team and governance · Risks and assumptions · Pricing · Why us · Compliance appendix), each heading an assertion, one "so what" line; lists of 3+ items as tables.
   d. **Ghost** the incumbent (e.g. a vendor's services arm) by the capability it lacks, never by name.
   e. **Risks** `| Risk | Likelihood | Impact | Mitigation | Owner |`; **Assumptions** `| Assumption | Consequence if false (change-control trigger) |`.
   f. **Submission checklist — internal, do not ship** (page limit, forms, file naming).
4. **Assemble from files** (win-themes.json ± discovery pack ± estimate memo): name the command and outputs, then show the result:
   `python3 -I scripts/assemble.py win-themes.json --library assets/section-library.md [--discovery …] [--estimate …] --out proposal.md --placeholders placeholders.csv --sources sources.md --final proposal-final.md [--draft-only] [--existing draft.md --redline proposal-redline.md]`.
   - Win themes threaded into the executive summary as T1..Tn and the why-us table; estimate "Bottom line" quoted into Pricing; pain matrix into section 2.
   - **Every `<slot>` not filled by an input is registered** in `placeholders.csv` (placeholder, section, owner) as `[TO BE BASELINED — owner: Bid manager]`; say so. A thin theme (no proof, no estimate) → its proof, so-what and every number stay markers, listed in placeholders.csv; no numbers invented.
   - `draft_only` / "no model step": **`proposal-final.md` is the assembled draft, labelled "draft — sharpen step not run"; every number traces to `sources.md`.**
5. **Redline an existing draft** (keep our storyline): table `| Section | [KEEP]/[SHARPEN]/[ADD]/[TBD] | Note |` — present sections kept (e.g. team), missing library sections [ADD]ed, the executive summary [SHARPEN]ed for each win theme it lacks (name them), every figure in no input [TBD] and replaced by `[TO BE BASELINED — owner: Bid manager]` in proposal-final.md, figures an input backs kept and say which input (e.g. "USD 1,472,000 kept — estimate memo"). Then the sharpened executive summary.

## Starting points
- **New** — win themes (and the discovery pack, estimate memo, value case when you have them) are assembled into a proposal on the section library; the model step sharpens it, or with `draft_only` the assembled draft is final. Every number traces to an input.
- **Existing** — add `existing` (your team's draft): it is redlined against the library and the win themes — sections kept, missing ones added from the inputs, the executive summary sharpened where a theme is missing — and every figure no input backs is replaced by an owned marker in `proposal-final.md` and listed in `proposal-redline.md`.

## When to use
- "Write the proposal for <client> based on the discovery synthesis and estimate."
- "Draft the executive summary and approach sections for the <RFP> response."
- "Redline this proposal draft — keep the story, make it sharper."
- NOT for: requirement inventory (`rfp-compliance-matrix`), contract terms (`sow-drafter`), effort numbers (`effort-estimator`), deck rework (`exec-deck-redline`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Mode: `write` or `redline` | yes | user |
| Problem statement with evidence (discovery synthesis, RFP, or user notes) | yes | file |
| Scope and solution outline (architecture doc or user description) | yes | file / user |
| Estimate output (effort, team, duration) or "pricing placeholders" | yes | file / user |
| Client format constraints (page limit, mandated sections, forms) | no | RFP / user |
| Competitive context (incumbent, likely bidders) | no | user / competitive-positioning |
| Existing draft (redline mode) | yes in redline | file |
| Reference projects we are cleared to name | no | user |

If the problem statement or scope is missing, ask once. Do not write an "understanding of needs" from imagination.

## Procedure
Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md` first. The redline convention in quality-bar.md governs redline mode.

### Mode A — write
1. **Build the win-theme worksheet** (`assets/win-theme-worksheet.md`) before any prose. For each of 3–4 themes: client hot button (quoted from their evidence) → our discriminator → proof (named, cleared) → ghost (what the alternative cannot do, stated without naming them). A theme without proof is cut. See `references/win-themes-and-ghosting.md`.
2. **Decision point — proposal shape.** Choose per `references/proposal-method.md` §1: Assessment (short, fixed-fee, decision-oriented), Delivery (phased, milestone-priced), Managed service (SLA-led, run-rate priced), or Hybrid. The shape sets section emphasis and the pricing structure placeholder.
3. **Write the executive summary last, but outline it first**: ≤1 page, four moves — their situation in their numbers, the outcome we commit to, how (three to five bullets, each tied to a win theme), what it takes (duration, team shape, price placeholder). No company history, no "we are pleased to submit".
4. **Draft sections from `assets/section-library.md`** in the client's mandated order if one exists; otherwise the library order. Each section opens with its "so what" sentence. Pull evidence verbatim from the discovery synthesis; cite RFP clause IDs where the client gave them. Compliance-driven responses: every mandatory requirement is answered where the compliance matrix points, using the "requirement → response → evidence" micro-structure.
5. **Numbers discipline.** Effort, duration, team, and price come only from the estimate file. Benefits come only from `value-case-builder` output or client statements. Anything else is `[TO BE BASELINED — owner: ___]`. Never round a placeholder into a number to "make it read better".
6. **Risks and assumptions**: use the registers in `references/proposal-method.md` §4. Every risk has likelihood, impact, mitigation, owner. Every assumption states what changes if it fails (it becomes a change-control trigger in the SOW).
7. **Team section**: roles, responsibilities, allocation, onshore/offshore split from the estimate. Named individuals only if the user supplies them. No biographies of the author or of people not confirmed for the engagement.
8. **Why-us and proof**: only cleared references, with the client's permission status noted internally. Ghost competitors via the win themes, never by naming them in the document.
9. **Compliance and format pass**: page limits, fonts, forms, signature pages, file naming from the RFP. Build the submission checklist.

### Mode B — redline
1. Read the whole draft once. Write the storyline as it stands in five bullets. If it holds, keep it; the job is to sharpen.
2. Redline every section with `[KEEP] [SHARPEN] [CUT] [ADD] [TBD]` and a reason. `[SHARPEN]` includes the rewritten text. Headings become assertions. Remove banned words. Convert prose lists of 3+ items to tables.
3. Check every number against its source; unsourced numbers become `[TBD — owner]` with a note on where the source should come from.
4. Deliver the redline table and the clean rewritten version.

### Both modes
10. Run the self-check. Strip anything that references other clients without clearance, internal rates, or the author's own history.

## Output
| Mode | File | Format |
|---|---|---|
| write | `proposal-<client>-<initiative>-v0.1.md` | Sections per `assets/section-library.md`; win-theme worksheet in an internal appendix (not shipped); submission checklist |
| redline | `proposal-<client>-redline-<yyyy-mm-dd>.md` | Redline table (section · verdict · reason · rewritten text) followed by the clean v+1 draft |

## Self-check
- [ ] Executive summary ≤1 page; first sentence states the outcome in the client's terms
- [ ] Every win theme has quoted hot button, discriminator, proof, ghost
- [ ] Every number traceable to estimate, value case, or client evidence; else `[TO BE BASELINED — owner: ___]`
- [ ] Mandatory RFP requirements each answered where the compliance matrix points
- [ ] Risks: likelihood, impact, mitigation, owner. Assumptions: consequence if false
- [ ] No banned words; headings are assertions; 3+ items are tables
- [ ] No other-client specifics without clearance; no author résumé content
- [ ] Format constraints met; submission checklist complete

## References
- `references/proposal-method.md` — proposal shapes, section intent, evidence rules, risk/assumption registers, review gates
- `references/win-themes-and-ghosting.md` — theme construction, discriminator tests, ghosting rules, proof standards
- `assets/section-library.md` — section-by-section templates with "so what" openers
- `assets/win-theme-worksheet.md` — worksheet

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/proposal-writer --input <name>=<value> … --out <dir>` (see `--explain presales/proposal-writer`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`proposal.md`, `placeholders.csv`, `sources.md`, `proposal-final.md`, `proposal-redline.md`).
