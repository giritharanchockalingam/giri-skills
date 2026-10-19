---
name: ai-slo-definition
description: Use when the user needs service-level objectives for an AI feature — "define SLOs for our assistant", "what should our latency and availability targets be", "are we inside our error budget", "set up burn-rate alerts", "quality and cost per request as SLOs". Produces slos.csv, slo-spec.md (Summary, SLIs and objectives, Error budgets, Alerting policy, Method) and slo.json from a request log - availability, latency under threshold, quality pass rate and cost under threshold as SLIs, nearest-rank p50/p95/p99, error budget, budget consumed and multiwindow burn rates per the Google SRE workbook (14.4x / 6x / 1x for 30 days). Without targets it proposes objectives from observed data, each marked to be baselined by the Product owner. Exit 1 when an agreed SLO is breached. Not for live dashboards or trace schemas (llm-observability), distribution drift (drift-monitor) or monthly API cost forecasts (llm-cost-model).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: requirements
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: log, type: csv, required: true, from: "request log timestamp (ISO-8601), latency_ms, status ok|error, optional quality_pass 0/1, optional cost_usd (layout: assets/log-template.csv)"}
      - {name: targets, type: csv, required: false, from: "agreed targets sli,objective,threshold,window_days (layout: assets/targets-template.csv); without it every objective is a proposal for the Product owner"}
      - {name: system, type: string, required: false, from: "name of the AI feature for the report title"}
    run:
      - {step: slo, kind: script, cmd: "python3 -I scripts/slo.py --log {log} [--targets {targets}] [--system {system}] --out-dir {out}"}
    outputs:
      - {path: "{out}/slos.csv", checks: [exists, csv:[sli,objective,threshold,observed,budget_consumed,burn_rate,status], "csv_rows:status~^(met|at-risk|breached|proposed)$", "csv_rows:observed~^[01]\\.\\d{5}$", cmd:"python3 -I scripts/slo.py --verify {path}"]}
      - {path: "{out}/slo-spec.md", checks: [exists, sections:["Summary","SLIs and objectives","Error budgets","Alerting policy","Method"], no_unowned_tbd, cmd:"python3 -I scripts/slo.py --verify {path}"]}
      - {path: "{out}/slo.json", checks: [exists, json, contains:"\"verdict\""]}
    modes:
      new:      {case: agent-mode-new, bring: "a few days of request logs from your pilot"}
      existing: {case: agent-happy-path, bring: "the request log from production and your agreed targets"}
---

# AI SLO Definition

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-slo-definition --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-slo-definition`). Report the `run.json` results; do not hand-write the deliverables the script produces (`slos.csv`, `slo-spec.md`, `slo.json`). An agreed SLO with budget consumed above 1 fails the run (exit 1) on purpose, with every output still written. Both tabular outputs pass `--verify`, which recomputes budgets, alerts and statuses from the counts in `slo.json`.

## Starting points
- **New** — no SLOs yet: bring a pilot request log; every objective is proposed from the observed data and marked for the Product owner to agree.
- **Existing** — bring the production request log and the targets already agreed; the skill measures each SLI against them, computes budget burn and flags breaches.

## When to use
- ADLC requirements stage: turn "it should be fast and reliable" into measurable SLIs, objectives and error budgets before build sign-off.
- Drafting first objectives from a pilot or shadow log: the skill proposes them from observed data for the Product owner to accept or change.
- Checking a release or a week of traffic against agreed targets, and wiring the burn-rate alert policy.
- NOT for: dashboards, trace schemas and live monitoring (`llm-observability`); input or score drift (`drift-monitor`); monthly API spend forecasts (`llm-cost-model`); judging answer quality itself (`llm-eval-harness` produces the `quality_pass` labels).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `log` — request log CSV | yes | platform / API gateway logs (copy `assets/log-template.csv`) | run stops (exit 2), asks once |
| `targets` — `sli,objective,threshold,window_days` | no | Product owner + SRE lead (copy `assets/targets-template.csv`) | objectives proposed from the data, each `[TO BE BASELINED — owner: Product owner]`; never presented as agreed |
| `system` — feature name | no | Product owner | title reads "AI feature" |

An SLI with an agreed target but no eligible rows in the log exits 2. Without `quality_pass` or `cost_usd` values, those SLIs are listed as not measured with a named owner.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Confirm the log covers normal traffic (ideally several days; the 6 h and 3 d alert windows need that much history).
3. Run without `targets` first if none are agreed; take the proposals to the Product owner and SRE lead.
4. Run with the agreed `targets`. `scripts/slo.py` applies `references/method.md`.
5. Read Summary, then Error budgets (consumed > 1 is breached), then Alerting policy (which alerts fire now).
6. On exit 1: open an incident or a reliability work item for each breached SLI; do not lower the objective to pass the gate without the Product owner.
7. Run the self-check.

## Output
- `slos.csv` — `sli, objective, threshold, observed, budget_consumed, burn_rate, status, note` (burn_rate = last 1 h; status met | at-risk | breached | proposed).
- `slo-spec.md` — **Summary**, **SLIs and objectives**, **Error budgets**, **Alerting policy** (burn per window, thresholds, fires), **Method**.
- `slo.json` — exact counts and fractions per SLI and window, verdict.

## Self-check
- [ ] Every observed value comes from the log; percentiles are nearest-rank
- [ ] Every proposed objective carries `[TO BE BASELINED — owner: Product owner]`; none is called agreed
- [ ] Burn-rate thresholds and windows match `references/sources.md` (SRE workbook, checked 2026-10-18)
- [ ] A breached agreed SLO exits 1 with full outputs
- [ ] Limits stated: sample log, short logs cannot show long windows, quality depends on labelling

## References
- `references/method.md` — SLI definitions, budget and burn formulas, proposal rules, hand-checked worked example
- `references/sources.md` — Google SRE workbook burn-rate policy with URL and date checked
- `assets/targets-template.csv`, `assets/log-template.csv` — input layouts
- `scripts/slo.py` — calculator and `--verify` (argparse; stdlib; exit 0 / 1 breached / 2 input)
