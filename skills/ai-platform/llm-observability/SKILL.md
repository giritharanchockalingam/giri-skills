---
name: llm-observability
description: Use when an LLM feature is live and the user needs to know how it is behaving — "set up LLM monitoring", "are we meeting our SLOs", "p95 latency and cost per request by feature", "has quality drifted since last week", "what should our trace schema be". Produces dashboard.json and alerts.md (Status, SLO breaches, Drift, By feature) from trace spans (JSONL) and an SLO CSV - request count, error rate, nearest-rank p50/p95/p99 latency, tokens and cost per request (cost only from spans that carry it), eval score mean, drift against a baseline window - plus the recommended trace schema. Not for app logging/Sentry setup (observability-setup), offline evals (llm-eval-harness) or incident handling (ai-incident-runbook).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: operate
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: traces, type: file, required: true, from: "trace spans as JSONL, one span per line (schema: assets/trace-schema.json)"}
      - {name: slo, type: csv, required: true, from: "SLO rows metric,threshold,window[,feature][,comparator] (layout: assets/slo-template.csv); owner-supplied"}
      - {name: baseline_start, type: string, required: false, from: "baseline window start date, e.g. 2026-09-01 (drift needs both baseline dates)"}
      - {name: baseline_end, type: string, required: false, from: "baseline window end date (inclusive)"}
    run:
      - {step: rollup, kind: script, cmd: "python3 -I scripts/observe.py --traces {traces} --slo {slo} --out-dir {out} [--baseline-start {baseline_start}] [--baseline-end {baseline_end}]"}
    outputs:
      - {path: "{out}/dashboard.json", checks: [exists, json, contains:"\"slo_results\"", contains:"nearest-rank"]}
      - {path: "{out}/alerts.md", checks: [exists, sections:["Status","SLO breaches","Drift","By feature"], no_unowned_tbd, numbers_trace_to:"{out}/dashboard.json"]}
      - {path: "{out}/trace-schema.json", checks: [exists, json, contains:"\"required\""]}
    modes:
      existing: {case: agent-happy-path, bring: "trace exports from your running app and your SLO targets"}
---

# LLM Observability (traces → SLOs → alerts)

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/llm-observability --input <name>=<value> … --out <dir>` (see `--explain ai-platform/llm-observability`). Report the `run.json` results; do not hand-write the deliverables the script produces (`dashboard.json`, `alerts.md`, `trace-schema.json`). Any SLO breach fails the run (exit 1) on purpose; the outputs are still written.

## Starting points
- **Existing** — rolls up spans your running application already emitted against the owner's SLOs, with drift against a baseline window.
- Only for existing: there is nothing to measure until an application produces traces; for a new app, emit spans per `assets/trace-schema.json` and set SLOs from `assets/slo-template.csv`, then run this on the first traffic.

## When to use
- A deployed LLM/agent feature needs per-feature latency, error, token, cost and quality roll-ups against SLOs.
- "Has it drifted?" — compare the current window to a baseline window.
- Defining what every span must log (trace schema) before go-live.
- NOT for: application logging, Sentry or health checks (`observability-setup`), building eval sets (`llm-eval-harness`), running an incident (`ai-incident-runbook`), release gates (`ai-release-plan`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `traces` JSONL: trace_id, ts, feature/route, model, latency_ms, input_tokens, output_tokens, status; optional cost_usd, eval_score, user_feedback | yes | tracing export (OpenTelemetry, Langfuse, provider logs) mapped to `assets/trace-schema.json` |
| `slo` CSV: metric, threshold, window, optional feature and comparator | yes | service owner; the skill never sets a threshold |
| `baseline_start`, `baseline_end` | no | owner; without them drift is not computed |

If `traces` or `slo` is missing the runner exits 2 and asks once. Spans missing required fields are rejected and counted, never repaired.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Map the trace export to `assets/trace-schema.json` (the script copies it to the output as the reference schema).
3. Fill `assets/slo-template.csv` with the owner's thresholds and windows.
4. Run the skill. The script splits baseline/current windows, computes the metrics in `references/metrics-method.md` per feature and overall, and evaluates each SLO in its window.
5. Read `alerts.md`: Status first, then breaches, then drift and the feature table.
6. NO DATA rows mean the signal is not instrumented (e.g. no `cost_usd`) — instrument it; do not estimate it.
7. Run the self-check.

## Output
- `dashboard.json`: windows, overall and per-feature metrics, baseline, drift, SLO results, rejected-span reasons.
- `alerts.md`: Status, SLO breaches (every SLO with observed value and status), Drift, By feature.
- `trace-schema.json`: the recommended span schema (JSON Schema).

## Self-check
- [ ] Percentiles are nearest-rank and labelled as such
- [ ] Cost per request only from `cost_usd` on spans, with coverage shown; never from guessed prices
- [ ] Every SLO threshold came from the SLO file; NO DATA is not reported as met
- [ ] Drift states both windows and is relative to the baseline
- [ ] Rejected spans counted with reasons
- [ ] Exit 1 when any SLO is breached

## References
- `references/metrics-method.md` — windows, metric definitions, percentile method, drift, SLO evaluation
- `assets/trace-schema.json` — recommended span schema
- `assets/slo-template.csv` — SLO input layout
- `scripts/observe.py` — the roll-up (argparse; stdlib)
