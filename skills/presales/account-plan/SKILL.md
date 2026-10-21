---
name: account-plan
description: Use when the user asks to build or refresh a quarterly or annual account plan, account strategy, or account review for an existing or target client. Produces a one-page-first account plan — account snapshot, relationship and stakeholder map with coverage gaps, white-space map (our services × their business units/platforms), pipeline table, risks to the account, and 90-day plays with owners and dates — with every revenue, pipeline, or stakeholder fact sourced to the user's inputs or marked [TO BE BASELINED — owner: ___]. Do not use for pre-pitch research on a new logo (client-research-brief) or for a single-pursuit battle card (competitive-positioning).
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: stakeholders, type: csv, required: true, from: "stakeholders.csv: name, role, stance -2..2, influence 1-5, last_contact, departure_risk (layout: evals/fixtures/stakeholders.csv)"}
      - {name: pipeline, type: csv, required: true, from: "pipeline.csv: opportunity, stage, value, close_date, owner, next_step (CRM export; layout: evals/fixtures/pipeline.csv)"}
      - {name: services, type: csv, required: true, from: "services.csv: service, status_at_account in active|proposed|none (layout: evals/fixtures/services.csv)"}
      - {name: client, type: string, required: false, default: "<Client>"}
      - {name: as_of, type: string, required: false, from: "yyyy-mm-dd; enables stale-contact (90 days) detection"}
      - {name: previous_plays, type: csv, required: false, from: "last quarter's plays.csv (optional status column: done | open | dropped) for the refresh"}
      - {name: previous_pipeline, type: csv, required: false, from: "last quarter's pipeline.csv, for the pipeline delta"}
    run:
      - {step: plan, kind: script, cmd: "python3 -I scripts/account_plan.py {stakeholders} {pipeline} {services} --out {out}/account-plan.md --plays {out}/plays.csv --client {client} [--as-of {as_of}] [--previous-plays {previous_plays}] [--previous-pipeline {previous_pipeline}]"}
    outputs:
      - {path: "{out}/account-plan.md", checks: [exists, sections:["Stakeholder map","White-space matrix","Pipeline","90-day plays"]]}
      - {path: "{out}/plays.csv", checks: [exists, csv:[play_id,play,addresses,owner,date,success_measure], csv_rows:owner!empty]}
    modes:
      new: {case: agent-happy-path, bring: "stakeholder list, CRM pipeline export and service coverage"}
      existing: {case: agent-mode-existing, bring: "this quarter's exports plus last quarter's plays and pipeline"}
---

# account-plan

## In a conversation: write the plan now
- **The request carries account facts** (engagements, end dates, pipeline, stakeholders, events such as a sponsor leaving), or says the CRM export, stakeholder list, catalog or prior plan are attached but their contents are not in the conversation: write the full account plan **in this reply** from the stated facts. Never reply with only a request for files. In this order, page 1 standing alone:
  1. **Posture on line 1** (Grow / Defend / Harvest / Enter) with the two or three facts that drove it (e.g. sponsor departure, nearest engagement end date).
  2. **Snapshot** — revenue, active engagements with end dates, contract vehicles; each cell sourced ("CRM export, <date>") or `[TO BE BASELINED — owner: ___]`. Weighted pipeline only when the CRM supplies probabilities, and say so.
  3. **Top risks** and **90-day plays** (3–6), each with owner, date and success measure: at least one coverage play (e.g. the successor to a departing sponsor) and one renewal/defense play for the nearest engagement end.
  4. Detail: **stakeholder map** (role, influence, disposition — unknown stays `unknown` —, our owner, last contact) with departures flagged as exposure and **coverage gaps** computed; **white-space matrix** (our services × their units) using `current / qualified / hypothesis / no fit / unknown`, each hypothesis citing its signal and confirming action; **pipeline table**; **risk register**; **change log vs the prior plan** on a refresh (achieved, carried, dropped and why).
  Mark every value the request does not give `[TO BE BASELINED — owner: ___]` naming the source it will come from, and end with the few questions that close those gaps.
- **No account facts at all** ("write an account plan for X"): ask once, in one list, for account facts (engagements, revenue, stakeholders, pipeline), our service catalog and the quarter. Do not estimate current spend, wallet share or stakeholder dispositions. Offer the **Enter** posture template with every cell marked `[TO BE BASELINED — owner: ___]` if the account is a target with no history.
- **Asked to invent win probabilities or a target** ("assign 60% / 30%", "put the target at what we usually aim for"): say in one line that probabilities and targets are not invented, because leadership will treat them as forecast. Show the **unweighted** pipeline only; offer to add probabilities if the user records them in the CRM as their own sales judgment, labelled as such. Show the target as `[TO BE BASELINED — owner: ___]` until the user confirms the official target and its source, and report gap-to-target as a marker until target and weighting are confirmed. Never print the requested percentages or target figure as plan values.

## Starting points
- **New** — stakeholders, pipeline and service coverage become a 90-day plan: stakeholder map, white space, pipeline, risks and plays with owned TBDs.
- **Existing** — add last quarter's plays and pipeline: the refresh says which plays were done, carried over (with last quarter's owner to confirm), dropped or closed by events, which plays are new, and how each opportunity moved since the last plan.

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

If the request carries no account facts at all, ask once. Individual facts missing from a request that has some (catalog, revenue, a stakeholder's last contact) do not stop the draft: they are marked `[TO BE BASELINED — owner: ___]`. Never estimate the client's spend with us or wallet share from memory.

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

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/account-plan --input <name>=<value> … --out <dir>` (see `--explain presales/account-plan`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.
