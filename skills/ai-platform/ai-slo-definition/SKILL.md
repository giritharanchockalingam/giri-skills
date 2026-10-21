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

## In a conversation: draft the SLO spec now
The reply **is the SLO spec draft**, never only a request for the log. No log rows are in the conversation, so no observed value is printed; every number the log would give is a marker.
- **The request names the feature and says logs exist** ("a week of pilot logs", "here are two days of logs") but no rows are in the conversation: write the spec **in this reply**, in this order:
  1. **Summary** — line 1: `Status: proposed — no objective is agreed until the Product owner signs it.` Then how the objectives are set: `scripts/slo.py` is run on the pilot log **without targets** (`python3 scripts/run_skill.py ai-platform/ai-slo-definition --input log=<pilot-log.csv> --input system="<feature>" --out <dir>`), and each objective is proposed from the observed data.
  2. **SLIs and objectives** — table `sli | good ÷ eligible | proposal rule | objective | threshold | status` for the four SLIs: availability (`status = ok` ÷ every request); latency (ok requests with `latency_ms <= threshold`; failed requests count against availability only); quality (`quality_pass = 1` ÷ labelled rows); cost (`cost_usd <= threshold` ÷ rows with a cost). Proposal rules from `references/method.md`: availability and quality take the highest ladder level not above the observed SLI (availability `0.9 / 0.95 / 0.99 / 0.995 / 0.999 / 0.9995 / 0.9999`; quality `0.8 / 0.85 / 0.9 / 0.95 / 0.98 / 0.99`); latency threshold = observed nearest-rank p95 of ok requests rounded up to the next 100 ms at objective 0.95; cost threshold = observed p95 cost rounded up to the next 0.001 USD at objective 0.95. Every objective cell reads `[TO BE BASELINED — owner: Product owner]` and every status `proposed`; none is called agreed. Without `quality_pass` or `cost_usd` in the log, that SLI is "not measured" with its owner.
  3. **Error budgets** — error budget = 1 − objective; budget consumed = (1 − SLI) ÷ (1 − objective); above 1 is breached. Proposals are never gated; only agreed targets are.
  4. **Alerting policy** — Google SRE workbook multiwindow burn-rate alerts at a 30-day window: fast-burn page 14.4x over 1 h with a 5 m short window (2% of budget); slow-burn page 6x over 6 h / 30 m (5%); ticket 1x over 3 d / 6 h (10%). An alert fires when both windows burn at or above the threshold. The SLO window is `[TO BE BASELINED — owner: SRE lead]` until agreed; a pilot shorter than 3 days cannot show the ticket window.
  5. **Method & limits** — nearest-rank percentiles, the log must cover normal traffic, quality depends on labelling; then the next step: take the proposals to the Product owner and SRE lead, then re-run with the agreed `targets` file (`sli,objective,threshold,window_days`).
- **Agreed targets and a measurement are asked for** ("measure against our targets", "errors spiked — check the SLOs and alerts"): give the same sections with the stated targets as objectives, the observed / consumed / burn columns as `[TO BE BASELINED — owner: SRE lead]` until the log is run, and state the gate: consumed above 1 on an agreed SLO is breached and the run exits 1 with every output written; a firing alert on an unbreached SLO is at-risk.
- **No feature and no log mentioned at all**: ask once, in one list, for the request log (`timestamp, latency_ms, status`, optional `quality_pass`, `cost_usd`), any agreed targets, and the feature name. Do not invent latency, availability or cost figures.
- **Asked to "just set sensible SLOs" or to lower an objective so a breach passes**: decline in one line — objectives come from observed data and the Product owner's agreement, not from typical industry numbers, and a breached objective is not lowered to pass the gate without the Product owner. Never print a suggested target number; show `[TO BE BASELINED — owner: Product owner]` and the proposal rules above.
- **Distribution drift** ("have our confidence scores shifted since launch?"): that is `drift-monitor`; this skill measures SLIs against objectives.

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

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ai-slo-definition --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ai-slo-definition`). Report the `run.json` results; do not hand-write the deliverables the script produces (`slos.csv`, `slo-spec.md`, `slo.json`). An agreed SLO with budget consumed above 1 fails the run (exit 1) on purpose, with every output still written. Both tabular outputs pass `--verify`, which recomputes budgets, alerts and statuses from the counts in `slo.json`.
