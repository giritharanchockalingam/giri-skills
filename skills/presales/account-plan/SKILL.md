---
name: account-plan
description: Use when the user asks to build or refresh a quarterly or annual account plan, account strategy, or account review for an existing or target client. Produces a one-page-first account plan — account snapshot, relationship and stakeholder map with coverage gaps, white-space map (our services × their business units/platforms), pipeline table, risks to the account, and 90-day plays with owners and dates — with every revenue, pipeline, or stakeholder fact sourced to the user's inputs or marked [TO BE BASELINED — owner: ___]. Do not use for pre-pitch research on a new logo (client-research-brief) or for a single-pursuit battle card (competitive-positioning).
license: MIT
metadata:
  domain: presales
  version: 0.1.0
  author: giri-skills
---

# account-plan

## When to use
- "Build the Q<n> account plan for <client>."
- "Refresh the account strategy — we just lost the renewal / won the assessment."
- "Prepare the quarterly account review for leadership."
- NOT for: new-logo research (`client-research-brief`), one pursuit (`competitive-positioning`, `proposal-writer`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Account facts: current engagements (scope, value, end dates), revenue history, contract vehicles, team on the account | yes | user / CRM export / prior plan |
| Stakeholder list with titles, our relationship owner, last contact | yes (any subset; rest TBD) | user / CRM |
| Client business context: strategy, initiatives, org changes, budget cycle (from `client-research-brief` or user) | no | brief / user |
| Pipeline: opportunities, stage, value, close date, next step | yes or "none" | CRM / user |
| Our service catalog (for white space) | yes | file / user |
| Prior plan (for refresh) | no | file |
| Quarter and planning horizon | yes | user |

If account facts or the service catalog are missing, ask once. Never estimate the client's spend with us or wallet share from memory.

## Procedure
Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md` first.

1. **Snapshot**: fill the account snapshot table (`assets/account-plan-template.md` §1) from inputs only: revenue by period, active engagements with end dates, contract vehicles, NPS/health signals if provided. Each cell sourced (CRM export date, prior plan version, user statement) or marked.
2. **Stakeholder map** per `references/account-planning-method.md` §2: for each stakeholder — role, influence (decision / influencer / gatekeeper / user), disposition toward us (advocate / neutral / skeptic / unknown), our relationship owner, last meaningful contact, next contact plan. Compute coverage gaps: decision-makers with no owner or no contact in 90 days; business units with no relationship. Unknown disposition is `unknown`, never assumed neutral.
3. **White-space map** (§3): matrix of our service lines × the client's business units or platforms. Cells: `current` (sourced engagement), `qualified` (pipeline), `hypothesis` (signal from brief or discovery with the signal cited), `no fit` (reason), `unknown`. Hypotheses carry the confirming action. Count the cells; the plan's growth plays come from `hypothesis` cells with the strongest signals.
4. **Pipeline table**: each opportunity with stage (use the user's stage names), value (from CRM or marked), close date, win probability only if the user's CRM supplies it (no invented probabilities), next step with owner and date, and the blocker if any. Reconcile the sum with the snapshot.
5. **Decision point — account posture.** Per §4: Grow / Defend / Harvest / Enter, from the facts (renewal exposure, relationship coverage, competitive threat, white-space signal strength). State the posture on line 1 and the two or three facts that drove it.
6. **Risks to the account** (§5): renewal risk, stakeholder departure, competitive entry, delivery issues, budget cut, concentration risk; each with likelihood, impact, early signal, mitigation, owner.
7. **90-day plays**: 3–6 plays, each with objective, actions, owner, date, success measure, and which white-space cell or risk it addresses. Plays without an owner are not plays. Include at least one relationship play (coverage gap) and one delivery-quality play if any engagement is active.
8. **Targets** only from the user: if a revenue target exists, show gap-to-target = target − (booked + weighted pipeline, if probabilities are supplied) and the plays that close it. If no target, `[TO BE BASELINED — owner: ___]`.
9. **One-page view first**, detail behind. Refresh mode: diff against the prior plan (what changed, what was achieved, what was dropped and why).
10. Run the self-check.

## Output
- File: `account-plan-<client>-<quarter>.md` per `assets/account-plan-template.md`
- Page 1: posture and bottom line · snapshot · top risks · 90-day plays. Following pages: stakeholder map and gaps · white-space matrix · pipeline · risk register · change log (refresh)

## Self-check
- [ ] Posture stated on line 1 with the driving facts
- [ ] Every revenue, pipeline, and target figure sourced or `[TO BE BASELINED — owner: ___]`
- [ ] No invented win probabilities; weighted pipeline only if the CRM supplies probabilities
- [ ] Stakeholder dispositions sourced; unknowns marked unknown
- [ ] Coverage gaps computed and addressed by at least one play
- [ ] White-space hypotheses cite a signal and a confirming action
- [ ] Every play has owner, date, success measure
- [ ] Risks have likelihood, impact, early signal, mitigation, owner
- [ ] Internal document; no content copied into client-facing material without review

## References
- `references/account-planning-method.md` — snapshot, stakeholder mapping, white-space logic, posture decision, risk patterns, play design, review cadence
- `assets/account-plan-template.md` — plan template (one page first)
