---
name: llm-cost-model
description: Use when the user asks what an LLM API workload will cost per month or how to cut it — "what will these features cost on model X", "cost per request", "does prompt caching pay off", "what if we move feature Y to a cheaper model", "are we within the AI budget". Produces cost-model.json and cost-model.md from a workload CSV, a dated price sheet and a feature-to-model assignment - monthly cost by feature and by model, totals, cost per request, the prompt-caching saving, a what-if swap to the cheapest model the user marked eligible, and budget headroom with 50/80/100% alerts. No price is built in. Exit 1 when the total exceeds the supplied budget. Not for GPU or self-hosting capacity (infra-gpu-sizing), model quality selection (llm-eval-harness) or a full business case (value-case-builder).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: deploy
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: workload, type: csv, required: true, from: "per-feature monthly requests and average tokens in/out, optional cached_input_share (layout: assets/workload-template.csv)"}
      - {name: prices, type: csv, required: true, from: "user price sheet per 1M tokens with source and as_of (layout: assets/prices-template.csv); never hardcoded"}
      - {name: assignment, type: csv, required: true, from: "feature -> model, optional ';'-separated eligible_models for the what-if (layout: assets/assignment-template.csv)"}
      - {name: budget_usd_month, type: string, required: false, from: "monthly budget in the price-sheet currency (absent = to be baselined)"}
    run:
      - {step: cost-model, kind: script, cmd: "python3 -I scripts/cost_model.py --workload {workload} --prices {prices} --assignment {assignment} [--budget {budget_usd_month}] --out {out}"}
    outputs:
      - {path: "{out}/cost-model.json", checks: [exists, json, contains:"monthly_total"]}
      - {path: "{out}/cost-model.md", checks: [exists, sections:["Monthly total","By feature","What-if","Budget","Sources"], no_unowned_tbd, numbers_trace_to:"{out}/cost-model.json"]}
---

# LLM Cost Model (API token economics)

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/llm-cost-model --input <name>=<value> … --out <dir>` (see `--explain ai-platform/llm-cost-model`). Report the `run.json` results; do not hand-write the deliverables the script produces (`cost-model.json`, `cost-model.md`). A total above the supplied budget fails the run (exit 1) on purpose; with no budget, the Budget section reads `[TO BE BASELINED — owner: FinOps lead]`.

## When to use
- Pricing a set of LLM-backed features on hosted APIs before launch, or re-forecasting after a price or volume change.
- Testing a cost lever: prompt caching share, moving a feature to a cheaper eligible model, trimming tokens per request.
- Budget guardrails: headroom and the 50/80/100% alert amounts to wire into billing alerts.
- NOT for: GPU counts, self-host vs rent (`infra-gpu-sizing`); choosing a model on quality (`llm-eval-harness` decides eligibility, this skill prices it); benefits and ROI (`value-case-builder`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `workload` CSV: `feature, requests_per_month, input_tokens, output_tokens[, cached_input_share]` | yes | product plan or usage logs; tokens are averages per request including system prompt and retrieved context |
| `prices` CSV: `model, price_in_per_1m, price_out_per_1m[, cached_in_per_1m], source, as_of` | yes | vendor price page or contract, dated; never recalled from memory |
| `assignment` CSV: `feature, model[, eligible_models]` | yes | engineering; eligible = passed the quality bar for that feature |
| `budget_usd_month` | no | FinOps lead / budget owner |

Missing a required file: the runner exits 2 and asks once. An assigned model without a price row, or a feature without an assignment, also exits 2 — the skill never fills a price.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Build the workload per feature with `references/cost-method.md` (requests, average tokens, cache share). Copy the three `assets/*-template.csv` layouts.
3. Collect prices with source and date for every assigned and eligible model.
4. Run the agent (above) or the script: `python3 -I scripts/cost_model.py --workload w.csv --prices p.csv --assignment a.csv --budget 5000 --out <dir>`.
5. Read Monthly total, then By feature (largest line first), What-if (savings only for models marked eligible), Budget (alert amounts to configure).
6. If over budget (exit 1): apply levers in `references/cost-method.md` (cache, swap, trim tokens, cap volume) and re-run; never edit the outputs by hand.
7. Run the self-check.

## Output
- `cost-model.json`: monthly_total, requests, cost per request, caching saving, per-feature and per-model costs, what-if rows, budget block (utilisation, headroom, alerts), prices with source/as_of, notes.
- `cost-model.md`: sections Monthly total, By feature, What-if, Budget, Sources. Every number traces to `cost-model.json`.

## Self-check
- [ ] Every price has a source and as-of date; any gap reads `[TO BE BASELINED — owner: FinOps lead]`
- [ ] What-if uses only models the user marked eligible; quality caveat kept
- [ ] Caching saving shown, and cached tokens without a cached price are charged at full input price (noted)
- [ ] Budget alerts at the stated levels; over budget exits 1
- [ ] No fixture or fictional price presented as a real vendor price

## References
- `references/cost-method.md` — formulas, worked example (the eval fixture, hand-checked), cost levers, how this differs from infra-gpu-sizing
- `scripts/cost_model.py` — calculator (argparse; stdlib; exit 0 / 1 over budget / 2 input)
- `assets/workload-template.csv`, `assets/prices-template.csv`, `assets/assignment-template.csv` — input layouts
