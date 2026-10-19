---
name: feedback-improvement-loop
description: Use when the user has user feedback or eval failures for a live AI feature and wants to know what to fix first — "what are users complaining about", "turn this feedback into a backlog", "triage thumbs-down comments", "which issues should we fix next", "add regression tests from feedback". Produces backlog.csv (ranked by frequency × severity, with hypothesis, fix type prompt/retrieval/guardrail/model/data/UX and owner role), new-eval-cases.json (id, prompt, expected — this repo's eval-case shape) and improvement-report.md (Top issues, Backlog, New eval cases, Regression gate) from a feedback CSV and optional eval failures, grouped deterministically by a bundled taxonomy. Not for building the eval harness (llm-eval-harness), live SLO monitoring (llm-observability) or survey research synthesis.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: improve
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      existing: {case: agent-happy-path, bring: "user feedback and failed eval cases from production"}
    inputs:
      - {name: feedback, type: csv, required: true, from: "feedback rows id,ts,rating,comment,tags,trace_id,feature (layout: assets/feedback-template.csv); rating 1-5 or up/down"}
      - {name: min_rows, type: string, required: true, from: "minimum valid feedback rows before ranking is trusted (owner-chosen whole number)"}
      - {name: eval_failures, type: csv, required: false, from: "failed eval cases case_id,feature,failure_reason (layout: assets/eval-failures-template.csv)"}
    run:
      - {step: loop, kind: script, cmd: "python3 -I scripts/improve.py --feedback {feedback} [--eval-failures {eval_failures}] --min-rows {min_rows} --out-dir {out}"}
    outputs:
      - {path: "{out}/backlog.csv", checks: [exists, csv:[rank,bucket,feature,score,hypothesis,fix_type,owner], csv_rows:fix_type~^(prompt|retrieval|guardrail|model|data|UX)$, csv_rows:owner!empty]}
      - {path: "{out}/new-eval-cases.json", checks: [exists, json, contains:"\"expected\""]}
      - {path: "{out}/improvement-report.md", checks: [exists, sections:["Top issues","Backlog","New eval cases","Regression gate"], no_unowned_tbd, numbers_trace_to:"{out}/backlog.csv"]}
---

# Feedback Improvement Loop

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/feedback-improvement-loop --input <name>=<value> … --out <dir>` (see `--explain ai-platform/feedback-improvement-loop`). Report the `run.json` results; do not hand-write the deliverables the script produces (`backlog.csv`, `new-eval-cases.json`, `improvement-report.md`). Fewer valid feedback rows than `min_rows` fails the run (exit 1) on purpose; outputs are still written and marked INSUFFICIENT DATA.

## Starting points
- **Existing:** ratings and comments from people using the system, plus failed eval cases; they become a ranked, owned backlog and a regression case per failure.
- Only for existing: the loop runs on feedback, which only a system people already use can produce.

## When to use
- Thumbs-down or star-rated feedback (and failed eval cases) needs to become a ranked, owned backlog.
- Every reported failure should become a regression eval case before the fix ships.
- NOT for: designing the eval harness or judges (`llm-eval-harness`), SLO monitoring (`llm-observability`), incident response (`ai-incident-runbook`), qualitative interview synthesis.

## Inputs required
| Input | Required | Source |
|---|---|---|
| `feedback` CSV: id, ts, rating (1-5 or up/down), comment, feature; optional tags, trace_id | yes | in-product feedback export |
| `min_rows` — minimum valid rows before ranking is trusted | yes | product / eval owner |
| `eval_failures` CSV: case_id, feature, failure_reason | no | latest llm-eval-harness run |

If `feedback` or `min_rows` is missing the runner exits 2 and asks once. Rows with unusable ratings are rejected and counted, not guessed.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Export feedback into `assets/feedback-template.csv` layout; include trace_id wherever the product records it.
3. Optionally adapt `assets/taxonomy.json` keywords to the product (keep bucket ids).
4. Run the skill. The script follows `references/method.md`: severity from rating, bucket by tag then keyword, rank (bucket, feature) groups by frequency × severity, link eval failures.
5. Review the top issues and confirm or edit each hypothesis and fix type with the owner role named.
6. Merge `new-eval-cases.json` into the feature's eval set; cases without a trace stay TBD until the original input is recovered.
7. Apply the regression gate: new cases pass and the suite pass rate does not drop — feed it to `ai-release-plan` as an offline_eval gate.
8. Run the self-check.

## Output
- `backlog.csv`: rank, bucket, feature, counts, mean severity, score, eval failures, hypothesis, fix type, owner, evidence ids.
- `new-eval-cases.json`: `{"cases": [{id, prompt, expected, provenance}]}`.
- `improvement-report.md`: Top issues, Backlog, New eval cases, Regression gate.

## Self-check
- [ ] Every backlog row traces to feedback ids and/or eval case ids
- [ ] Fix type is one of prompt, retrieval, guardrail, model, data, UX
- [ ] No eval prompt reconstructed from a complaint; untraced inputs are TBD with Eval lead
- [ ] Positive feedback is not in the backlog; rejected rows are counted
- [ ] Exit 1 when the sample is below `min_rows`

## References
- `references/method.md` — severity mapping, grouping, ranking, eval-case shape, minimum sample
- `assets/taxonomy.json` — issue buckets, keywords, fix types, owner roles, expected behaviours
- `assets/feedback-template.csv`, `assets/eval-failures-template.csv` — input layouts
- `scripts/improve.py` — the loop (argparse; stdlib)
