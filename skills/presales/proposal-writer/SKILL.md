---
name: proposal-writer
description: Use when the user asks to write, structure, or redline a client proposal, RFP response narrative, or statement of qualifications. Produces an on-template proposal — executive summary, understanding of needs, approach and methodology, solution, team, timeline, governance, risks, assumptions, pricing placeholders, and why-us — built on win themes and ghosting the competition, with every figure sourced or marked [TO BE BASELINED — owner: ___]. In redline mode it keeps the existing storyline and sharpens it slide/section by section. Do not use for compliance matrices (rfp-compliance-matrix), SOWs (sow-drafter), or pricing math (effort-estimator).
license: MIT
metadata:
  domain: presales
  version: 0.1.0
  author: giri-skills
---

# proposal-writer

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
