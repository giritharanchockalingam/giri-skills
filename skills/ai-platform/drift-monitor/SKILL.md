---
name: drift-monitor
description: Use when the user asks whether an AI system's inputs, outputs or scores have shifted — "has our data drifted", "compare this week's traffic to the launch baseline", "PSI and KS for these features", "did the model's confidence distribution move", "drift check before retraining", "compare last week's features to the baseline using our agreed thresholds", "gate this week's window on drift". Produces drift.csv, drift-report.md (Summary, Features, Alerts, Method & limits) and drift.json from a baseline CSV and a current CSV - per feature PSI, two-sample Kolmogorov-Smirnov D and p-value (numeric), chi-square p-value (categorical), missing-value rate change and an ok/warn/alert/insufficient-data status. Default PSI thresholds are the cited 0.1/0.25 rule of thumb, labelled a convention. Exit 1 on any alert. Not for live dashboards and latency/cost SLOs (llm-observability, ai-slo-definition), offline quality evals (llm-eval-harness) or fairness across groups (bias-fairness-check).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: operate
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      existing: {case: agent-happy-path, bring: "a baseline window and a recent window from production"}
    inputs:
      - {name: baseline, type: csv, required: true, from: "reference window CSV with a header row (e.g. launch-week inputs, outputs or scores)"}
      - {name: current, type: csv, required: true, from: "window to test, CSV with the same columns as the baseline"}
      - {name: features, type: string, required: false, from: "comma list of columns to compare; default every column in both windows"}
      - {name: thresholds, type: csv, required: false, from: "metric,warn,alert for psi, p_value, null_rate_delta (layout: assets/thresholds-template.csv); default psi 0.1/0.25 and p_value alert 0.01, marked to be baselined"}
      - {name: types, type: string, required: false, from: "type overrides, e.g. 'store_id=categorical,score=numeric'"}
    run:
      - {step: drift, kind: script, cmd: "python3 -I scripts/drift.py --baseline {baseline} --current {current} [--features {features}] [--thresholds {thresholds}] [--types {types}] --out-dir {out}"}
    outputs:
      - {path: "{out}/drift.csv", checks: [exists, csv:[feature,type,n_baseline,n_current,psi,ks_d,p_value,null_rate_baseline,null_rate_current,status], "csv_rows:status~^(ok|warn|alert|insufficient-data)$", "csv_rows:null_rate_current~^[01]\\.\\d{3}$", cmd:"python3 -I scripts/drift.py --verify {path}"]}
      - {path: "{out}/drift-report.md", checks: [exists, sections:["Summary","Features","Alerts","Method & limits"], no_unowned_tbd, cmd:"python3 -I scripts/drift.py --verify {path}"]}
      - {path: "{out}/drift.json", checks: [exists, json, contains:"\"verdict\""]}
---

# Drift Monitor

## In a conversation: check the drift now
The reply **is the drift report** (or its skeleton): line 1 is `Verdict: no feature in alert | ALERT — <features> | pending — <reason>`, never only a request for files. Drift is a reason to investigate, not proof that quality fell — say so and recommend a quality check (`llm-eval-harness`) on the current window before retraining.
- **The request carries the two windows (or their numbers)**: write the report **in this reply** in the script's order — **Summary** (verdict, counts by status, thresholds used and whether they were agreed); **Features** table `feature, type, n_baseline, n_current, psi, ks_d, p_value, null_rate_baseline, null_rate_current, status` (numeric: PSI + two-sample KS D and p-value; categorical: PSI + chi-square p-value; status per `references/method.md`: insufficient-data when either window has < 30 non-missing values, else alert / warn / ok); **Alerts** (reason, unseen categories, owner); **Method & limits** (univariate; p-values shrink as samples grow). Name the run that produces the files: `python3 -I scripts/drift.py --baseline … --current … [--thresholds …] [--features …] --out-dir …`.
- **Files said to be attached, or windows named but not shown** (e.g. "launch-week extract and last week's extract — has the request mix drifted?"): lay out all four sections now, one Features row per known feature (or `<feature>`) with values `[TO BE BASELINED — owner: ML engineer]`, state that `scripts/drift.py` reports PSI, KS or chi-square p-value and missing-rate change per feature, then ask once, in one list, for the baseline CSV, the current CSV (same columns) and the agreed thresholds file, and ask who owns agreed thresholds (ML engineering lead).
- **No agreed thresholds / "use whatever is standard"**: use the cited defaults — PSI warn 0.1 / alert 0.25, p-value alert 0.01 — and say they are a rule-of-thumb convention (source in `references/sources.md`), not a law; write `Agreed thresholds for this system: [TO BE BASELINED — owner: ML engineering lead]` and `Missing-rate change threshold: [TO BE BASELINED — owner: Data owner]` (reported, not gated).
- **Small window** (e.g. 20 requests since release): every feature is `insufficient-data`, never alert; exit 0; say how many more values are needed (30 per window).
- **Gate this week's window**: any feature in alert → `ALERT — drift beyond the alert threshold`, run exits 1 with full outputs; list new categories unseen in the baseline; name an owner per alerted feature and check upstream changes.
- **Latency, availability, error or cost targets ("are we meeting p95?")**: line 1 routes it to `ai-slo-definition` or `llm-observability`; this skill compares distributions only.

## Starting points
- **Existing:** a baseline window and a recent window from the running system; each feature's PSI, KS or chi-square result is judged against your thresholds.
- Only for existing: drift compares live data against a baseline, so there is nothing to measure before a system runs.

## When to use
- ADLC operate stage: a scheduled check of this week's inputs, outputs or model scores against a launch or last-known-good baseline.
- Before retraining or re-indexing: confirm which features moved and by how much.
- After an upstream change (new channel, schema change, pipeline fix): check missing-value rates and new categories.
- NOT for: live latency, error and cost SLOs (`llm-observability`, `ai-slo-definition`); judging answer quality (`llm-eval-harness`); group fairness (`bias-fairness-check`); text or embedding drift without a numeric or categorical feature to compare.

## Inputs
| Input | Required | Source | If missing |
|---|---|---|---|
| `baseline` — CSV with header | yes | ML engineer: reference window extract | run stops (exit 2), asks once |
| `current` — CSV, same columns | yes | ML engineer: window under test | run stops (exit 2), asks once |
| `features` — comma list | no | ML engineer | every column present in both windows |
| `thresholds` — `metric,warn,alert` | no | ML engineering lead (copy `assets/thresholds-template.csv`) | defaults psi 0.1/0.25, p_value alert 0.01; report states agreed thresholds are `[TO BE BASELINED — owner: ML engineering lead]` |
| `types` — `col=numeric\|categorical` | no | ML engineer | auto: numeric when ≥ 95% of values parse as numbers |

Lines starting with `#` are comments. A feature named in `features` that is not in both windows exits 2.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Confirm both windows describe the same system and population (same columns, same units, comparable time spans).
3. Agree thresholds with the ML engineering lead, or run on defaults and record that they are conventions.
4. Run the agent. `scripts/drift.py` applies the method in `references/method.md` per feature.
5. Read Summary, then Alerts (largest PSI first in practice), then Features for the full table.
6. On exit 1: name an owner per alerted feature, check upstream changes, then run a quality check on the current window before retraining.
7. Run the self-check.

## Output
- `drift.csv` — `feature, type, n_baseline, n_current, psi, ks_d, p_value, null_rate_baseline, null_rate_current, status`.
- `drift-report.md` — **Summary** (verdict, counts, thresholds used), **Features** (table), **Alerts** (reasons, unseen categories, owner), **Method & limits**.
- `drift.json` — every metric unrounded, bins, chi-square statistic and df, thresholds, verdict.

## Self-check
- [ ] Every number came from the two input windows; no threshold presented as agreed unless a thresholds file was supplied
- [ ] PSI cut-offs described as a convention with the source in `references/sources.md`
- [ ] Windows under 30 non-missing values show insufficient-data, not alert
- [ ] Any alert exits 1 and names an owner
- [ ] Limits stated: univariate, p-values shrink with sample size, drift is not proof of lower quality

## References
- `references/method.md` — PSI binning and epsilon, KS and chi-square formulas, status rule, hand-checked worked example, limits
- `references/sources.md` — source of the PSI rule of thumb (checked 2026-10-18)
- `assets/thresholds-template.csv` — thresholds layout for the ML engineering lead
- `scripts/drift.py` — calculator and `--verify` (argparse; stdlib; exit 0 / 1 alert / 2 input)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/drift-monitor --input <name>=<value> … --out <dir>` (see `--explain ai-platform/drift-monitor`). Report the `run.json` results; do not hand-write the deliverables the script produces (`drift.csv`, `drift-report.md`, `drift.json`). Any feature in alert fails the run (exit 1) on purpose, with every output still written. Both tabular outputs pass `--verify`, which re-derives each status from `drift.json`.
