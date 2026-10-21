---
name: offer-evaluator
description: Use when the user receives a job offer (or expects one) and asks to evaluate it, compare offers or an offer against their current package, adjust for relocation / cost of living, plan a negotiation, or decide. Produces a total-compensation table, a COL-adjusted comparison, a negotiation-lever plan, and a weighted decision matrix for senior director / VP / executive IT roles. Uses only figures the user supplies (offer letter, current comp, COL indices); no hardcoded market or COL data.
license: MIT
metadata:
  domain: career
  adlc_stage: career
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: offers, type: csv, required: true, from: "offer comparison CSV (layout: assets/offer-comparison.csv)"}
      - {name: horizon, type: string, required: false, default: "4"}
      - {name: col, type: string, required: false, from: "user-supplied COL indices, e.g. Columbus OH=100,Austin TX=108; without it no COL adjustment is made"}
      - {name: base_location, type: string, required: false}
      - {name: tax, type: string, required: false, from: "effective tax rates per location"}
    run:
      - {step: compare-json, kind: script, cmd: "python3 -I scripts/compare.py --file {offers} --horizon {horizon} [--col {col}] [--base-location {base_location}] [--tax {tax}] --json", stdout: "{out}/comparison.json"}
      - {step: compare-table, kind: script, cmd: "python3 -I scripts/compare.py --file {offers} --horizon {horizon} [--col {col}] [--base-location {base_location}] [--tax {tax}]", stdout: "{out}/comparison.md"}
    outputs:
      - {path: "{out}/comparison.json", checks: [exists, json, contains:"annualized_total"]}
      - {path: "{out}/comparison.md", checks: [exists, contains:"annualized"]}
    modes:
      new: {case: agent-mode-new, bring: "the offers you hold, with no current package to compare"}
      existing: {case: agent-happy-path, bring: "the offers plus your current package"}
---

# Offer Evaluator

## In a conversation: evaluate the offer now
- **The offer figures are in the request**: evaluate in this reply, in this order: (1) recommendation line first (accept / negotiate X then accept / decline) with the deciding number; (2) total-comp table per option — base, target bonus, sign-on, equity per year (grant ÷ vesting years), relocation, year-1 cash, annual recurring, annualized total over the horizon, COL-adjusted recurring; (3) COL basis — the user's indices quoted with their source and date (e.g., "Columbus 100, Austin 108 — user's calculator, Oct 2026"); (4) negotiation plan with 2–3 levers, each with ask, justification, fallback and order; (5) decision matrix with weights summing to 100 and each option's weight × score arithmetic and total shown — score from the stated facts only; a criterion with no facts is scored `[TO BE BASELINED — owner: user]` (never a made-up default), the arithmetic is shown for every scored criterion, and the totals are labelled "partial — N of M criteria scored" until the user supplies the rest; (6) risks and open items with owners. Components not given are `[TO BE BASELINED — owner: user]`.
- **COL index missing or the user asks you to "figure out" cost of living**: never supply, estimate or recall an index. Still produce the nominal total-comp table from the figures supplied (rows for every component; values not given are `[TO BE BASELINED — owner: user]`), show the COL-adjusted column as `[TO BE BASELINED — owner: user]`, and ask for each location's index with its source and date.
- **Negotiation plan only**: sequence it per `references/negotiation-levers.md`: thank and ask for a call → lead with the biggest lever stated as a number (base, L1, citing the disclosed band and its midpoint) → hold sign-on (L2, citing the forfeited bonus amount) as the bridge → bundle non-cash items → one justified counter → close with written confirmation and a revised letter. Ask the user for their probability of a yes on each lever rather than assuming it, and point to `outreach-and-followup` (negotiation-open) for the message draft.
- **No offer details at all** ("is this offer good?"): ask once, in one list, for the offer components, the current package and the locations; do not estimate a bonus, equity value or market rate.

## Starting points
- **New** — the offers alone (e.g. between roles, no current package): year-1 cash, recurring and annualized totals, COL-adjusted only with indices you supply.
- **Existing** — include your current package as the `Current` row: every offer is also shown as the change against what you have today, recurring and COL-adjusted.

## When to use
- "Is this offer good?", "compare offer A vs B vs my current job", "adjust for moving to Austin", "what should I negotiate?", "help me decide".
- NOT for: writing the negotiation email (`outreach-and-followup` → negotiation open), interview prep, or tracking status (`application-tracker`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Offer components (base, target bonus %, sign-on, equity grant and vesting, benefits, 401k match, PTO, relocation, start date) | yes | offer letter / user |
| Current package, same components | yes for comparison | user |
| Cost-of-living index for each location, with source and date | no — without it the COL-adjusted column is `[TO BE BASELINED — owner: user]` | user supplies (e.g., a COL calculator result); the skill never assumes one |
| Role facts: title, reporting line, team size, budget, remote/travel | no — unknowns marked `[TO BE BASELINED — owner: user]` | JD / interviews |
| User's decision weights (or accept defaults in `references/decision-matrix.md`) | no | user |
| Market comp reference (survey, pay-transparency bands) with source | no | user |

Missing offer components → show them as `[TO BE BASELINED — owner: user]` in the table and ask once at the end; only when no offer details are given at all, ask before drafting. Never estimate a bonus, equity value, or COL index. Mark unknown components `[TO BE BASELINED — owner: user]`.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. Fill `assets/offer-comparison.csv` with one row per option (current job included). Equity: use the user's stated value and vesting; show annualized value over the user's planning horizon only.
3. Run `scripts/compare.py` with `--file offer-comparison.csv --horizon 4 --col "Columbus OH=100,Austin TX=108" --base-location "Columbus OH"` (indices supplied by the user). The script computes year-1 cash, annualized total comp, and COL-adjusted figures per `references/total-comp.md` and `references/col-adjustment.md`.
4. Build the negotiation plan from `references/negotiation-levers.md`: rank levers by expected value × likelihood, pick 2–3, state the ask and the fallback.
5. Score each option in the decision matrix (`references/decision-matrix.md`) using user weights. Show the arithmetic.
6. State the recommendation first, then the table, then risks (likelihood, impact, mitigation, owner).
7. Run the self-check. Reply ≤50 words; the artifact carries the detail.

## Output
Markdown `offer-eval-<company>.md`:
1. Recommendation line (accept / negotiate X then accept / decline) with the deciding number
2. Total-comp table (per option: base, bonus, sign-on, equity/yr, benefits value, total yr-1, annualized, COL-adjusted)
3. Negotiation plan: lever, ask, justification, fallback, order
4. Decision matrix with weights and scores
5. Risks and open items (`[TO BE BASELINED — owner: ___]`)

## Self-check
- [ ] Every figure traces to the offer letter, the user, or a cited source; nothing estimated silently
- [ ] COL indices carry a source and date supplied by the user
- [ ] Equity valued only on user-stated price/value and vesting; horizon stated
- [ ] Decision matrix weights sum to 100; scores shown with arithmetic
- [ ] Recommendation is the first line; risks have owners
- [ ] No author personal data pulled from memory

## References
- `references/total-comp.md` — components, valuation rules
- `references/col-adjustment.md` — index method, what to adjust and what not to
- `references/negotiation-levers.md` — levers, typical ranges to *ask the user about*, sequencing
- `references/decision-matrix.md` — criteria, default weights, scoring scale
- `assets/offer-comparison.csv` — input layout
- `scripts/compare.py` — comparison calculator (stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py career/offer-evaluator --input <name>=<value> … --out <dir>` (see `--explain career/offer-evaluator`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.
