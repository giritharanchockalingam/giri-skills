---
name: model-selection
description: Use when the user must choose an LLM/SLM for a use case from a shortlist — "which model should we use", "compare these models for X", "API vs self-hosted model", "rank the candidates on our evals and cost", "does the winner change if we weight cost higher". Produces a ranking.json and a decision.md (Recommendation, Eliminated, Scores, Sensitivity, Sources) from a candidates CSV of user-supplied model facts (prices, latency, context, eval scores with source and as-of date), a criteria CSV (weights, direction, hard constraints such as self-host or data residency) and an optional workload for monthly cost; ships a stdlib scoring script with a ±20% weight-sensitivity check. Never supplies model facts itself. Not for running the evals that produce the scores (llm-eval-harness), GPU capacity sizing (infra-gpu-sizing) or agent pattern choice (agent-architecture).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: architecture
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: candidates, type: csv, required: true, from: "candidate models with user-supplied facts and scores, row-level source + as_of (layout: assets/candidates-template.csv); the skill never supplies model facts"}
      - {name: criteria, type: csv, required: true, from: "criterion, weight, direction higher|lower, optional hard_min/hard_max/hard_in (layout: assets/criteria-template.csv)"}
      - {name: workload, type: csv, required: false, from: "tokens_in_per_request, tokens_out_per_request, requests_per_month as key,value (layout: assets/workload-template.csv); enables monthly_cost_usd"}
      - {name: incumbent, type: string, required: false, from: "the model in production today, exactly as named in the candidates CSV; adds the switch-or-stay view"}
    run:
      - {step: rank, kind: script, cmd: "python3 -I scripts/select_model.py --candidates {candidates} --criteria {criteria} [--workload {workload}] [--incumbent {incumbent}] --out-dir {out}"}
    outputs:
      - {path: "{out}/ranking.json", checks: [exists, json, contains:"winner_changes", cmd:"python3 -I scripts/select_model.py --verify {path}"]}
      - {path: "{out}/decision.md", checks: [exists, sections:["Recommendation","Eliminated","Scores","Sensitivity","Sources"], no_unowned_tbd, numbers_trace_to:"{out}/ranking.json"]}
    modes:
      new:      {case: agent-happy-path, bring: "candidate models with your eval results, weights and volumes"}
      existing: {case: agent-mode-existing, bring: "the same inputs plus the model you run in production today"}
---

# Model Selection

## In a conversation: rank the models now
- **The request carries model facts** (candidates with prices, latency, context, the team's eval scores, plus weights and constraints — or says they are attached but their contents are not in the conversation): give the decision **in this reply**, in the `decision.md` order: **Recommendation** (winner, runner-up, robustness verdict), **Criteria** (weight, direction, hard constraints), **Eliminated** (each candidate with the hard constraint it fails), **Scores** (min-max normalised per criterion over survivors, weighted sum, rank, monthly cost when a workload is given), **Sensitivity** (each weight ±20%: does the winner change), **Sources** (source and as-of per row), **Gaps**. Use only stated facts; every missing value is `[TO BE BASELINED — owner: ___]` naming who holds it (eval owner, vendor price sheet, product owner for volumes). State that the run is `python3 -I scripts/select_model.py --candidates … --criteria … [--workload …] --out-dir <dir>` and that `--verify` recomputes the ranking. Never reply with only a request for files.
- **No candidate facts** ("which LLM should we use for X?"): ask once, in one list, for (1) the shortlist with the team's own eval scores, prices in/out per 1M tokens, p95 latency and context — each with `source` and `as_of` — using `assets/candidates-template.csv`; (2) criteria with weights, direction and hard constraints (self-host, data residency, latency SLO, minimum accuracy) using `assets/criteria-template.csv`; (3) optional workload via `assets/workload-template.csv`. Say plainly that you will not quote any model price, benchmark score or capability from memory.
- **No candidate meets the hard constraints**: list every candidate eliminated with its reasons and say no candidate meets them (the run exits 1); do not recommend one anyway — offer the constraint to revisit and its owner.
- **Cost criterion without a workload**: do not assume volumes; monthly cost is `[TO BE BASELINED — owner: product owner]` and the run stops with an input error until the workload is given.
- **An incumbent is named**: add "Incumbent" — whether it still passes the hard constraints, its rank, switch or stay, score gap, monthly-cost delta, and the criteria where the incumbent is better.

## Starting points
- **New** — rank candidate models on your criteria, hard constraints and workload.
- **Existing** — also name the model in production as `incumbent` (include it in the candidates CSV): decision.md adds "Incumbent" — whether it still passes the hard constraints, its rank, switch or stay, the score gap, the monthly-cost delta and where the winner is better or worse.

## When to use
- Picking a model for one use case from a shortlist of API and/or self-hosted candidates.
- Re-running the choice when prices, eval scores or constraints change (dated inputs make the decision repeatable).
- Testing whether the choice is robust to how the team weights accuracy vs cost vs latency.
- NOT for: producing the eval scores (`llm-eval-harness`), GPU sizing and self-host TCO (`infra-gpu-sizing`; feed its $/1M figure in as the self-host price), agent pattern design (`agent-architecture`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `candidates` CSV: model, provider, hosting (api\|self-host), context_tokens, price_in_per_1m, price_out_per_1m, p95_latency_ms, one column per eval/benchmark score, `source`, `as_of` | yes | user's own eval runs, vendor price pages, internal TCO; dated |
| `criteria` CSV: criterion, weight, direction, hard_min / hard_max / hard_in | yes | decision owner (solution architect + product) |
| `workload` CSV: tokens in/out per request, requests per month | no | logs or product plan; required only when a criterion is `monthly_cost_usd` |

If a candidate fact is missing, ask once; the script never fills it. A blank on a weighted criterion scores 0 and is listed under Gaps with an owner; a blank on a hard-constrained criterion eliminates the candidate (cannot verify).

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. **Collect facts, not opinions**: fill `assets/candidates-template.csv` from the team's own eval runs (see `llm-eval-harness`) and dated price sheets. Every row carries `source` and `as_of`.
3. **Set criteria** in `assets/criteria-template.csv` per `references/criteria-design.md`: must-haves become hard constraints (weight 0 + `hard_min`/`hard_max`/`hard_in`); trade-offs get weights and a direction.
4. **Run** `python3 -I scripts/select_model.py --candidates … --criteria … [--workload …] --out-dir <dir>`. The script applies hard constraints (with reasons), min-max normalises each weighted criterion over the survivors, computes the weighted score, ranks, and scales each weight by ±20% to test whether the winner changes (`references/scoring-method.md`).
5. **Decision point — robustness.** If Sensitivity shows a challenger, the decision depends on a weight: put the exact trade-off to the decision owner rather than reporting a single winner.
6. **Verify**: `python3 -I scripts/select_model.py --verify <dir>/ranking.json` recomputes scores and ranks.
7. Run the self-check.

## Output
- `ranking.json`: criteria with normalised weights, eliminated candidates and reasons, ranked survivors with raw / normalised / contribution per criterion, monthly cost, sensitivity runs, recommendation, gaps, sources.
- `decision.md`: Recommendation, Criteria, Eliminated, Scores, Sensitivity, Sources, Gaps. Every number traces to `ranking.json`.

## Self-check
- [ ] Every model fact came from the candidates file with a source and as-of date; none was supplied by the skill
- [ ] Hard constraints are stated as constraints, not disguised as heavy weights
- [ ] Each eliminated candidate has its reason(s)
- [ ] Sensitivity verdict reported; a non-robust winner is escalated, not hidden
- [ ] Gaps carry `[TO BE BASELINED — owner: <role>]`
- [ ] `--verify` passes on `ranking.json`

## References
- `references/scoring-method.md` — constraint gating, min-max normalisation, weighted sum, sensitivity
- `references/criteria-design.md` — choosing criteria, weights and hard constraints; provenance rules
- `assets/candidates-template.csv`, `assets/criteria-template.csv`, `assets/workload-template.csv` — input layouts
- `scripts/select_model.py` — scorer and verifier (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/model-selection --input <name>=<value> … --out <dir>` (see `--explain ai-platform/model-selection`). Report the `run.json` results; do not hand-write the deliverables the script produces (`ranking.json`, `decision.md`). When no candidate survives the hard constraints the run exits 1 on purpose and `decision.md` says so.
