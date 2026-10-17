---
name: offer-evaluator
description: Use when the user receives a job offer (or expects one) and asks to evaluate it, compare offers or an offer against their current package, adjust for relocation / cost of living, plan a negotiation, or decide. Produces a total-compensation table, a COL-adjusted comparison, a negotiation-lever plan, and a weighted decision matrix for senior director / VP / executive IT roles. Uses only figures the user supplies (offer letter, current comp, COL indices); no hardcoded market or COL data.
license: MIT
metadata:
  domain: career
  version: 0.1.0
  author: giri-skills
---

# Offer Evaluator

## When to use
- "Is this offer good?", "compare offer A vs B vs my current job", "adjust for moving to Austin", "what should I negotiate?", "help me decide".
- NOT for: writing the negotiation email (`outreach-and-followup` → negotiation open), interview prep, or tracking status (`application-tracker`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Offer components (base, target bonus %, sign-on, equity grant and vesting, benefits, 401k match, PTO, relocation, start date) | yes | offer letter / user |
| Current package, same components | yes for comparison | user |
| Cost-of-living index for each location, with source and date | yes if locations differ | user supplies (e.g., a COL calculator result); the skill never assumes one |
| Role facts: title, reporting line, team size, budget, remote/travel | yes | JD / interviews |
| User's decision weights (or accept defaults in `references/decision-matrix.md`) | no | user |
| Market comp reference (survey, pay-transparency bands) with source | no | user |

Missing offer numbers → ask once. Never estimate a bonus, equity value, or COL index. Mark unknown components `[TO BE BASELINED — owner: user]`.

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
