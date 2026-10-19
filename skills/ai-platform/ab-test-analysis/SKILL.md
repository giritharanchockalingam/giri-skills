---
name: ab-test-analysis
description: Use when the user has results from an online experiment comparing AI variants (prompt, model, retrieval or agent change) and asks whether to ship — "analyse this A/B test", "did prompt v3 win", "is the lift significant", "check the split for sample ratio mismatch", "how many users do we need for this MDE". Produces ab-results.csv, ab-report.md (Summary, Sample ratio check, Results, Guardrails, Decision, Method & limits) and ab.json from aggregated or unit-level results - SRM chi-square, two-proportion z-test or Welch's t-test, CIs, relative lift, Holm adjustment across treatments, achieved power and sample size for the declared MDE, and a ship / don't ship / inconclusive decision with guardrails. Missing MDE or guardrails are TBD for the Experiment owner, never assumed. Exit 1 when SRM is detected. Not for offline eval sets (llm-eval-harness), designing the rollout (ai-release-plan) or live monitoring (llm-observability).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: improve
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: results, type: csv, required: true, from: "experiment results, aggregated variant,users,conversions[,metric_sum,metric_sumsq][,metric] or unit-level variant,unit_id,converted[,value][,guardrail columns] (layouts: assets/results-*-template.csv)"}
      - {name: config, type: csv, required: false, from: "kv-csv key,value (layout: assets/ab-config.csv) - control, alpha, power, expected_split, mde, metric_type, primary_metric, direction, guardrails, srm_alpha; absent keys use labelled defaults, absent MDE is TBD for the Experiment owner"}
    run:
      - {step: analyse, kind: script, cmd: "python3 -I scripts/ab_test.py --results {results} [--config {config}] --out-dir {out}"}
    outputs:
      - {path: "{out}/ab-results.csv", checks: [exists, csv:[metric,role,variant,n,rate_or_mean,diff,ci_low,ci_high,rel_lift,p_value,p_adj,significant], "csv_rows:significant~^(yes|no|control)$", "csv_rows:p_value~^(n/a|[01]\\.\\d{6})$", cmd:"python3 -I scripts/ab_test.py --verify {path} --results {results}"]}
      - {path: "{out}/ab-report.md", checks: [exists, sections:["Summary","Sample ratio check","Results","Guardrails","Decision","Method & limits"], no_unowned_tbd, cmd:"python3 -I scripts/ab_test.py --verify {path} --results {results}"]}
      - {path: "{out}/ab.json", checks: [exists, json, contains:"\"srm_detected\"", cmd:"python3 -I scripts/ab_test.py --verify {path} --results {results}"]}
    modes:
      existing: {case: agent-happy-path, bring: "the results export from an experiment that already ran"}
---

# A/B Test Analysis (AI variants)

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/ab-test-analysis --input <name>=<value> … --out <dir>` (see `--explain ai-platform/ab-test-analysis`). Report the `run.json` results; do not hand-write the deliverables the script produces (`ab-results.csv`, `ab-report.md`, `ab.json`). A sample ratio mismatch fails the run (exit 1) on purpose: every output is still written, and the decision reads "untrustworthy". Each output passes `--verify`, which re-derives it from the results and the config recorded in `ab.json`.

## Starting points
- **Existing** — you bring the per-variant results of an experiment that has run (plus its pre-registered config); the skill checks the split, tests every metric and returns ship / don't ship / inconclusive.
- Only for existing: an A/B analysis always reads results from an experiment that already ran; pre-launch sizing without results belongs in the experiment design, not here.

## When to use
- ADLC improve stage: a prompt, model, retrieval or agent change ran as an online experiment and the team needs ship / don't ship / inconclusive with the statistics behind it.
- Trust check before reading lifts: is the traffic split what the config promised (SRM)?
- Planning a re-run: achieved power for the declared MDE and the n per arm it needs.
- NOT for: offline eval sets or LLM-as-judge scoring (`llm-eval-harness`), staged rollout gates (`ai-release-plan`), production drift and alerting (`llm-observability`), sequential or Bayesian designs (this is fixed-horizon frequentist).

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `results` — aggregated or unit-level CSV | yes | experimentation platform export or warehouse query | run stops (exit 2), asks once |
| `config` — kv-csv (`assets/ab-config.csv`) | no | Experiment owner (pre-registration) | defaults used and labelled: control = variant named `control` else first variant, alpha 0.05, power 0.8, equal split, srm_alpha 0.001, direction higher_better; MDE and guardrails `[TO BE BASELINED — owner: Experiment owner]` |

Aggregated: one row per variant (and per `metric` when several). Binary metrics use `conversions/users`; continuous metrics use `metric_sum` and `metric_sumsq` (sum of squares). Unit-level: one row per randomised unit; `converted` is 0/1, `value` is continuous, guardrail columns are named in `guardrails`. Guardrails take a direction, e.g. `escalated:lower_better;csat:higher_better`. `mde` is absolute (`0.02`) or relative to control (`5%`).

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Confirm the config was fixed before the experiment ran (alpha, MDE, primary metric, guardrails). Post-hoc changes invalidate the p-values; record them in the report notes.
3. Run the agent. `scripts/ab_test.py` checks SRM, then tests each declared metric per treatment against control, applies Holm across treatments, computes power, and applies the decision rule.
4. If SRM is detected (exit 1), stop: send the split table to the platform owner and do not quote any lift.
5. Read the Guardrails section: a guardrail with no declared direction blocks a ship on any significant move.
6. Inconclusive with low achieved power → quote the n per arm needed for the MDE; do not call it "no effect".
7. Run the self-check.

## Output
- `ab-results.csv` — `metric, role, variant, n, rate_or_mean, diff, ci_low, ci_high, rel_lift, p_value, p_adj, significant` (control rows read `n/a` / `control`).
- `ab-report.md` — **Summary** (decision first, settings with their basis), **Sample ratio check**, **Results** (primary metric and power), **Guardrails**, **Decision** (per treatment and overall, with the rule), **Method & limits**.
- `ab.json` — config as given, effective settings and provenance, every statistic, decisions.

## Self-check
- [ ] SRM checked first; an SRM run is reported as untrustworthy, not as a result
- [ ] Every default is labelled; MDE and guardrails come from the Experiment owner or read TBD with that owner
- [ ] Holm-adjusted p-values drive significance when there is more than one treatment
- [ ] Guardrail breaches block a ship; undeclared guardrail directions are flagged
- [ ] Inconclusive results state power / required n instead of "no difference"
- [ ] Limits stated: fixed-horizon, independent units, statistical not product sign-off

## References
- `references/method.md` — formulas, decision rule, worked numbers used in the tests
- `references/sources.md` — SRM (Fabijan et al., Kohavi et al.), Welch, Holm, incomplete beta; verified URLs and dates
- `assets/ab-config.csv`, `assets/results-aggregated-template.csv`, `assets/results-unit-template.csv` — input layouts
- `scripts/ab_test.py` — analysis and `--verify` (argparse; stdlib)
