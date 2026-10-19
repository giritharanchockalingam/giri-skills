---
name: ai-finops-chargeback
description: Use when the user asks what AI usage actually costs and who should pay for it — "show AI spend by team", "build the LLM showback", "chargeback for our AI features", "cost per request by feature", "are teams on track against their AI budgets", "why did AI spend spike". Produces showback.csv (spend, requests, cost per 1k requests, share and month-over-month change at total, month, team, feature and model levels), anomalies.csv (team-days above mean + 3 sd of the trailing 14 days), budget.csv (actual, run-rate forecast, variance, status) and finops-report.md from metered usage and a dated price sheet. Usage without a price is listed as TBD for the FinOps lead, never estimated; --strict exits 1 when a forecast is over budget. Not for forecasting a planned workload before launch (use llm-cost-model), GPU or self-hosting capacity (use infra-gpu-sizing) or reconciling provider invoices.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: operate
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: usage, type: csv, required: true, from: "metered usage per day: date, team, feature, model, requests, input_tokens (incl. cached), output_tokens[, cached_input_tokens] (layout: assets/usage-template.csv); from the AI gateway or provider usage export"}
      - {name: prices, type: csv, required: true, from: "dated price sheet per 1M tokens: model, input_per_1m, output_per_1m[, cached_input_per_1m], effective_from (layout: assets/prices-template.csv); from the FinOps lead; never hardcoded"}
      - {name: budgets, type: csv, required: false, from: "team, month YYYY-MM, budget_usd (layout: assets/budgets-template.csv); absent = every budget TBD for the FinOps lead"}
      - {name: as_of, type: string, required: false, from: "as-of date YYYY-MM-DD for run-rate forecasts (default: latest usage date, never today)"}
      - {name: strict, type: flag, required: false, flag: "--strict", from: "true to fail the run (exit 1) when any team forecast is over budget"}
    run:
      - {step: showback, kind: script, cmd: "python3 -I scripts/chargeback.py --usage {usage} --prices {prices} [--budgets {budgets}] [--as-of {as_of}] {strict} --out-dir {out}"}
    outputs:
      - {path: "{out}/showback.csv", checks: [exists, csv:[month,team,feature,model,requests,cost_usd,cost_per_1k_requests,share], "csv_rows:cost_usd~^(\\d+\\.\\d{2}|\\[TO BE BASELINED — owner: FinOps lead\\])$", cmd:"python3 -I scripts/chargeback.py --verify {path} --usage {usage} --prices {prices} --budgets '{budgets}' --as-of '{as_of}' {strict}"]}
      - {path: "{out}/anomalies.csv", checks: [exists, csv:[date,team,cost_usd,trailing_mean_usd,trailing_sd_usd,threshold_usd,prior_days], cmd:"python3 -I scripts/chargeback.py --verify {path} --usage {usage} --prices {prices} --budgets '{budgets}' --as-of '{as_of}' {strict}"]}
      - {path: "{out}/budget.csv", checks: [exists, csv:[team,month,budget,actual,forecast,variance,status], "csv_rows:status~^(OVER BUDGET|WITHIN BUDGET|NO BUDGET|NOT STARTED)$", cmd:"python3 -I scripts/chargeback.py --verify {path} --usage {usage} --prices {prices} --budgets '{budgets}' --as-of '{as_of}' {strict}"]}
      - {path: "{out}/finops-report.md", checks: [exists, sections:["Summary","Spend by team","Unit economics","Anomalies","Budgets","Unpriced usage","Method"], no_unowned_tbd, numbers_trace_to:["{out}/showback.csv","{out}/anomalies.csv","{out}/budget.csv"], cmd:"python3 -I scripts/chargeback.py --verify {path} --usage {usage} --prices {prices} --budgets '{budgets}' --as-of '{as_of}' {strict}"]}
---

# AI FinOps Chargeback (showback)

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-finops-chargeback --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-finops-chargeback`). Report the `run.json` results; do not hand-write the deliverables the script produces (`showback.csv`, `anomalies.csv`, `budget.csv`, `finops-report.md`). Every dollar figure in the report traces to the CSVs, and each output is re-verified against the inputs with `--verify`. With `strict=true` the run is a gate: a team forecast over budget exits 1, with complete outputs.

## When to use
- ADLC operate stage: monthly showback of AI spend to the teams and features that consume it, before Finance decides on chargeback.
- Unit economics: cost per 1k requests by feature and model, to target optimisation work.
- Budget tracking mid-month: run-rate forecast and variance per team, with a strict gate for alerts.
- Spend spike triage: which team-days broke the trailing-14-day pattern and which feature drove them.
- NOT for: pricing a planned workload before launch (`llm-cost-model`), GPU or self-hosting sizing (`infra-gpu-sizing`), provider invoice reconciliation or posting journal entries (Finance owns chargeback posting).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `usage` — date, team, feature, model, requests, input_tokens, output_tokens[, cached_input_tokens] | yes | AI gateway / provider usage export, tagged by team and feature | run stops (exit 2), asks once |
| `prices` — model, input_per_1m, output_per_1m[, cached_input_per_1m], effective_from | yes | FinOps lead, from contract or vendor price page, dated | run stops (exit 2), asks once; never estimated |
| `budgets` — team, month, budget_usd | no | FinOps lead / budget owners | every budget reads `[TO BE BASELINED — owner: FinOps lead]`, status NO BUDGET |
| `as_of` — YYYY-MM-DD | no | run owner | latest usage date |
| `strict` — true/false | no | FinOps lead | false: over-budget reported, run exits 0 |

A usage row whose model has no price row, or no price in effect on its date, gets no cost: it is listed under Unpriced usage with `[TO BE BASELINED — owner: FinOps lead]` and excluded from every total.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Export usage per day with team and feature tags; copy the layouts in `assets/`. Confirm `input_tokens` includes cached tokens.
3. Get the dated price sheet from the FinOps lead (one row per price change). Never fill a price from memory.
4. Run the agent. `scripts/chargeback.py` applies `references/method.md`.
5. Read Summary, then Budgets (OVER BUDGET rows first), Anomalies (send each to the team's engineering lead), Unpriced usage (FinOps lead adds price rows and re-runs).
6. Publish showback (team and team_feature rows). Chargeback posting is Finance's call once unpriced usage is priced and figures reconcile to the invoice.
7. Run the self-check.

## Output
- `showback.csv` — `level, month, team, feature, model, requests, cost_usd, cost_per_1k_requests, share, mom_change_pct, input_tokens, output_tokens`; levels total, month, month_team, team, team_feature, model, detail.
- `anomalies.csv` — `date, team, cost_usd, trailing_mean_usd, trailing_sd_usd, threshold_usd, excess_usd, prior_days, top_feature`.
- `budget.csv` — `team, month, budget, actual, forecast, variance, status, basis, days_elapsed, days_in_month, unpriced_requests`.
- `finops-report.md` — **Summary**, **Spend by team**, **Unit economics**, **Anomalies**, **Budgets**, **Unpriced usage**, **Method**.

## Self-check
- [ ] Every price came from the supplied sheet; unpriced usage is TBD for the FinOps lead, never estimated
- [ ] Totals reconcile to the cent across levels (total = months = teams)
- [ ] Every $ figure in the report appears in a CSV (`numbers_trace_to` passes)
- [ ] The as-of month is flagged as partial; forecasts use the stated as-of date, never today
- [ ] Anomaly rule and forecast method are stated in Method; they are this skill's method, not a standard
- [ ] Fixture or fictional prices are never presented as real vendor prices

## References
- `references/method.md` — formulas, levels, worked example (the eval fixture, hand-checked), how showback feeds chargeback
- `references/sources.md` — FinOps Foundation showback / chargeback definitions, checked 2026-10-18
- `assets/usage-template.csv`, `assets/prices-template.csv`, `assets/budgets-template.csv` — input layouts
- `scripts/chargeback.py` — calculator and `--verify` (argparse; stdlib; exit 0 / 1 strict over budget / 2 input)
