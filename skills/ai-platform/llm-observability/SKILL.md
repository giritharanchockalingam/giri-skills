---
name: llm-observability
description: Use when an LLM feature is live and the user needs to know how it is behaving from its traces — "monitor our LLM traces", "set up LLM monitoring", "are we meeting our SLOs", "check the last 24h p95 for a feature", "p95 latency and cost per request by feature", "has quality drifted since last week", "what should our trace schema be". Produces dashboard.json and alerts.md (Status, SLO breaches, Drift, By feature) from trace spans (JSONL) and the owner's SLO CSV - request count, error rate, nearest-rank p50/p95/p99 latency, tokens and cost per request (only from spans that carry cost_usd, never estimated from token prices), eval score mean, drift against a baseline window - plus the recommended trace schema. Never picks SLO thresholds. Not for app logging/Sentry setup (observability-setup), offline evals (llm-eval-harness), incident handling (ai-incident-runbook), SLO design from a request log (ai-slo-definition) or team spend showback (ai-finops-chargeback).
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

## In a conversation: set up the roll-up now
The reply gives the monitoring setup and the exact inputs it needs; numbers appear only from real spans.
- **The feature is live but traces and SLOs are not in the conversation** ("are we meeting SLOs, has latency drifted", or files said to be attached): in this reply give
  1. **What to send**: the trace export as JSONL and the SLO thresholds from the service owner. Never propose thresholds as the SLO; show the SLO CSV skeleton (`metric,threshold,window,feature,comparator`, rows for error_rate, latency_p95_ms, eval_score_mean, cost_per_request_usd, drift_*_pct) with each threshold `[TO BE BASELINED — owner: service owner]`.
  2. **Trace fields** per `assets/trace-schema.json`: required `trace_id, ts, feature, model, latency_ms, input_tokens, output_tokens, status`; optional `cost_usd, eval_score, user_feedback`. Spans missing required fields are rejected and counted, never repaired. Cost per request is reported only from spans that carry `cost_usd`, with coverage; without it the cost SLO reads NO DATA.
  3. **Drift**: against a baseline window once both dates are given (convert "first week of September" to `baseline_start`/`baseline_end` and confirm the year); drift = (current − baseline) ÷ baseline × 100 for tokens per request, p95 latency and eval score mean.
  4. **The run**: `python3 -I scripts/observe.py --traces spans.jsonl --slo slo.csv --out-dir <dir> [--baseline-start …] [--baseline-end …]` → `dashboard.json`, `alerts.md` (Status, SLO breaches, Drift, By feature), `trace-schema.json`; percentiles nearest-rank; any BREACH exits 1. Do not print metric values that were not computed.
- **Asked to pick sensible SLOs**: decline in one line (a threshold is the service owner's commitment, not this skill's); show the skeleton with markers and ask for the values.
- **Asked to estimate cost from token prices** (cost not logged): decline in one line; the cost SLO for that feature is NO DATA, reported and never counted as met; the fix is to instrument `cost_usd` on spans. Still report the other SLOs, e.g. a p95 above its threshold in its window is a BREACH and exits 1.
- **Nothing about the app**: ask once for the feature names, the trace source (OpenTelemetry, Langfuse, provider logs) and the SLO owner.

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

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/llm-observability --input <name>=<value> … --out <dir>` (see `--explain ai-platform/llm-observability`). Report the `run.json` results; do not hand-write the deliverables the script produces (`dashboard.json`, `alerts.md`, `trace-schema.json`). Any SLO breach fails the run (exit 1) on purpose; the outputs are still written.
