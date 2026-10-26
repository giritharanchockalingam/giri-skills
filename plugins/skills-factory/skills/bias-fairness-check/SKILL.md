---
name: bias-fairness-check
description: Use when the user asks whether a classifier or AI decision system treats groups fairly — "run a bias check on these predictions", "disparate impact / four-fifths rule", "equal opportunity or equalised odds gap", "fairness gate before launch", "per-group accuracy by gender/region/age band". Produces fairness.json and fairness-report.md from a labelled predictions CSV - per-group n, base rate, selection rate, accuracy, TPR, FPR, precision; demographic parity difference, disparate impact ratio, equal opportunity and equalised odds differences; small-group flags; a verdict against user-supplied thresholds (none built in; missing ones are to be baselined, never a pass). Exit 1 on any breach. Not for LLM output quality (llm-eval-harness), the risk register or model card (ai-governance-risk), or a legal compliance opinion.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: evaluate
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-happy-path, bring: "labelled predictions from a model before launch, plus thresholds"}
      existing: {case: agent-mode-existing, bring: "this period's decisions plus your last fairness check"}
    inputs:
      - {name: predictions, type: csv, required: true, from: "labelled predictions, one row per decision (layout: assets/predictions-template.csv) with the sensitive-attribute column, label, prediction, optional score"}
      - {name: thresholds, type: csv, required: false, from: "metric,threshold set by the Responsible AI lead (layout: assets/thresholds-template.csv); absent or blank = to be baselined, never a pass"}
      - {name: sensitive_attr, type: string, required: false, default: "group", from: "name of the sensitive-attribute column"}
      - {name: reference_group, type: string, required: false, from: "reference group for the disparate impact ratio (default: highest selection rate, stated in the report)"}
      - {name: min_sample, type: string, required: false, from: "minimum n per group; smaller groups are flagged (absent = to be baselined)"}
      - {name: previous, type: json, required: false, from: "fairness.json from the last check of the same system and attribute; adds metric, selection-rate and breach changes"}
    run:
      - {step: fairness, kind: script, cmd: "python3 -I scripts/fairness.py --predictions {predictions} [--thresholds {thresholds}] --sensitive-attr {sensitive_attr} [--reference-group {reference_group}] [--min-sample {min_sample}] [--previous {previous}] --out {out}"}
    outputs:
      - {path: "{out}/fairness.json", checks: [exists, json, contains:"disparate_impact_ratio"]}
      - {path: "{out}/fairness-report.md", checks: [exists, sections:["Verdict","Metrics","Per-group","Small groups","Limits"], no_unowned_tbd, numbers_trace_to:"{out}/fairness.json"]}
---

# Bias & Fairness Check

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/bias-fairness-check --input <name>=<value> … --out <dir>` (see `--explain ai-platform/bias-fairness-check`). Report the `run.json` results; do not hand-write the deliverables the script produces (`fairness.json`, `fairness-report.md`). A metric that breaches a supplied threshold fails the run (exit 1) on purpose; a metric with no threshold is `[TO BE BASELINED — owner: Responsible AI lead]` and the verdict is INCOMPLETE, never PASS.

## Starting points
- **New:** labelled predictions from a validation set and the thresholds your Responsible AI lead set give the pre-launch gate.
- **Existing:** add the `fairness.json` from the last check (`previous`); the report adds each metric and group selection rate then vs now, and which breaches are new or resolved.

## When to use
- Pre-launch or periodic fairness gate on a binary classifier or a yes/no AI decision (approve/deny, flag/not flag, shortlist/reject).
- Answering "is there disparate impact", "is the error rate the same across groups", "which groups are too small to judge".
- NOT for: LLM answer quality or groundedness (`llm-eval-harness`); the risk register, controls and model card (`ai-governance-risk` — attach this report as evidence); legal advice on anti-discrimination law (route to counsel); multi-class or regression outputs (binarise first and say how).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `predictions` CSV: sensitive-attribute column (default `group`), `label`, `prediction` (0/1, true/false, yes/no), optional `score` | yes | model owner's labelled evaluation sample; fixture rows must be labelled fictional |
| `thresholds` CSV: `metric,threshold` for `demographic_parity_difference`, `disparate_impact_ratio`, `equal_opportunity_difference`, `equalized_odds_difference` | no | Responsible AI lead; policy decision, never invented by the skill |
| `sensitive_attr` | no (default `group`) | user |
| `reference_group` | no | user / policy (often the historically advantaged group) |
| `min_sample` | no | Responsible AI lead / statistician |

If `predictions` is missing the runner exits 2 and asks once. Thresholds are never assumed: the four-fifths rule applies only when the user sets `disparate_impact_ratio` to 0.8.

## Procedure
1. Read `../../shared/quality-bar.md`.
2. Confirm the decision, the positive outcome (what `prediction = 1` means), the sensitive attribute and the evaluation sample's provenance. Copy `assets/predictions-template.csv` and `assets/thresholds-template.csv`.
3. Run the agent (above) or the script directly: `python3 -I scripts/fairness.py --predictions p.csv --thresholds t.csv --reference-group A --min-sample 30 --out <dir>`.
4. Read the verdict: FAIL (a breach, exit 1), INCOMPLETE (a threshold to be baselined or a metric undefined), PASS (every metric within its supplied threshold).
5. Interpret with `references/fairness-metrics.md`: which metric governs for this decision, why base rates differ, whether small groups drive the gap.
6. Hand the report to `ai-governance-risk` as bias-risk evidence; record mitigations (re-threshold per group only with legal sign-off, rebalance data, add human review).
7. Run the self-check.

## Output
- `fairness.json`: verdict, breaches, metrics (value, rule, threshold, status, owner when unbaselined), per-group stats, reference group and basis, small groups, notes.
- `fairness-report.md`: sections Verdict, Metrics, Per-group, Small groups, Limits. Every number traces to `fairness.json`.

## Self-check
- [ ] Every threshold came from the user; missing ones read `[TO BE BASELINED — owner: Responsible AI lead]`, never "pass"
- [ ] Reference group and its basis stated
- [ ] Small groups flagged and kept in the metrics (not silently dropped)
- [ ] Undefined rates (no positives / no negatives in a group) named, not shown as 0
- [ ] Limits section kept: no confidence intervals, metric conflict, label bias, no legal conclusion
- [ ] No fixture or fictional data presented as a real model's results

## References
- `references/fairness-metrics.md` — definitions, worked example (the eval fixture, hand-checked), choosing a metric, standards by name
- `scripts/fairness.py` — calculator (argparse; stdlib; exit 0 / 1 breach / 2 input)
- `assets/predictions-template.csv`, `assets/thresholds-template.csv` — input layouts
