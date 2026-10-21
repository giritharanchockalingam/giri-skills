---
name: infra-gpu-sizing
description: Use when the user asks to size GPU or inference infrastructure, compare self-hosting an LLM against renting GPUs or using an API, or estimate monthly cost for a given user load — "how many GPUs do we need", "self-host vs rent", "cost of serving model X to N users". Produces a workload model (users, requests/day, tokens in/out, latency SLO), throughput math from user-supplied tokens/s per GPU, GPU count, monthly cost for self-host vs rental vs API from user-supplied unit prices, a TCO factor table, and a recommendation; ships a calculator script. Not for training-cluster sizing or vendor selection.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: deploy
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: inputs, type: csv, required: true, from: "workload + price inputs key,value (layout: assets/gpu-sizing-inputs.csv); no throughput or price is ever assumed"}
      - {name: overrides, type: args, required: false, from: "extra --set key=value pairs, e.g. \"--set peak_factor=3\""}
    run:
      - {step: size-json, kind: script, cmd: "python3 -I scripts/size.py --inputs {inputs} {overrides} --json", stdout: "{out}/sizing.json"}
      - {step: size-table, kind: script, cmd: "python3 -I scripts/size.py --inputs {inputs} {overrides}", stdout: "{out}/sizing.txt"}
    outputs:
      - {path: "{out}/sizing.json", checks: [exists, json]}
      - {path: "{out}/sizing.txt", checks: [exists, contains:"gpus_required"]}
    modes:
      new:      {case: agent-happy-path, bring: "your planned users, request volumes, benchmarks and prices"}
      existing: {case: agent-mode-existing, bring: "your production volumes and the GPU fleet running today"}
---

# Infra & GPU Sizing (inference)

## In a conversation: size it now
- **The request carries the workload, a throughput benchmark and prices** (even as symbols like "$X/GPU-hr"): write the sizing **in this reply**, in this order. (1) Inputs table: each value with its source and date; a price given only as a symbol stays that symbol, and anything not given is `[TO BE BASELINED — owner: ___]`. (2) Workload table (`references/workload-model.md`): R_day = U × r; R_avg = R_day ÷ (H × 3600); R_peak = R_avg × p; prefill P_peak = R_peak × T_in and decode D_peak = R_peak × T_out tokens/s; concurrency N_conc = R_peak × (T_out ÷ s_user) by Little's law. Active hours H and peak factor p are stated as assumptions when not given. (3) Capacity (`references/throughput-math.md`): G_d = ceil(D_peak ÷ (d_gpu × u)), G_p from measured prefill tokens/s (or `[TO BE BASELINED]` if not benchmarked), G = max(G_d, G_p), plus spare; utilization target u (0.6 in the inputs template) and the spare are labelled assumptions. Latency check: per-stream decode ≈ d_gpu ÷ batch at the measured batch size vs the tokens/s SLO; TTFT needs a prefill measurement. (4) Monthly cost table — rental ($/GPU-hr × G_tot × hours provisioned, 730 = always on), self-host (capex ÷ amortization months × G_tot + hosting + ops FTE share + software), API (tokens/month ÷ 1M × $/1M in and out) — and breakeven hours = self-host monthly per GPU ÷ $/GPU-hr (`references/tco-factors.md`). (5) Sensitivity: ±50% volume, price ±20%, quantization. (6) Recommendation with revisit triggers: volume crosses a stated level, model change, price change, residency rule change. Then give the calculator run on `assets/gpu-sizing-inputs.csv`.
- **Small pilot or low volume, rent vs API**: answer short and in tables. API cost scales with tokens and is zero when idle; rental and self-host are paid while provisioned (idle cost). Recommend the API for the pilot unless residency or data rules forbid it, and state the revisit trigger as a volume: the monthly tokens at which API cost equals the rental cost of the smallest fleet with spare (rental monthly ÷ blended $/1M tokens), using the user's prices or that formula if prices are not given.
- **Required facts missing** ("how many GPUs for 500 users?"): ask once, in one list, for users and peak factor, requests per user per day, tokens in/out per request, latency SLO (TTFT and tokens/s per stream), model, precision and context length, measured decode and prefill tokens/s per GPU at a stated batch size, and dated unit prices; offer `assets/gpu-sizing-inputs.csv` to fill. Do not quote any GPU throughput as fact.
- **Asked to assume a "typical" throughput or price**: decline in one line (throughput depends on model, precision, serving stack and batch; an invented figure makes the GPU count fiction). Name the missing keys (`decode_tokens_per_s_per_gpu`, `prefill_tokens_per_s_per_gpu`, or the price key), show them as `[TO BE BASELINED — owner: ML platform lead]` without printing any number beside them, and offer the path: a benchmark on the serving stack you will run, or a cited vendor document.
- **A fleet already runs**: size the measured production workload as above, compare with the GPUs running today, give the verdict (over-provisioned, right-sized or under-provisioned) and the delta; price the delta as delta GPUs × the user's $/GPU-hr × hours per month only when that rate is given.

## Starting points
- **New** — size a fleet for a planned workload from your benchmarks and price quotes.
- **Existing** — add `current_gpus` (and optionally `current_cost_usd_per_month`) to the inputs with volumes measured in production: the run compares today's fleet with the sized need and returns `current_fleet` (delta, over-/right-/under-provisioned, priced delta and saving).

## When to use
- Sizing inference capacity for a self-hosted or rented LLM/SLM; deciding self-host vs rental vs API; budgeting a pilot or rollout.
- NOT for: training/fine-tuning cluster sizing, picking a model (use evals), network/storage design.

## Inputs required
| Input | Required | Source |
|---|---|---|
| Concurrent or daily active users and peak factor | yes | user |
| Requests per user per day; tokens in/out per request (averages) | yes | user / logs; if absent ask, then state assumptions |
| Latency SLO: time-to-first-token and tokens/s per stream, or end-to-end p95 | yes | user |
| Model(s) and precision (e.g., 8B at fp16/int8), context length | yes | user |
| Measured or vendor-stated throughput: tokens/s per GPU for that model + serving stack | yes | user benchmark or vendor doc; **not** invented by the skill |
| Unit prices: $/GPU-hr rental, self-host capex and power/hosting, API $/1M tokens | yes | user; dated |
| Availability target, residency, data constraints | no | user |

If throughput per GPU or unit prices are missing, ask once; otherwise run with explicitly labeled placeholder inputs and mark results illustrative.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. **Build the workload model** with `references/workload-model.md`: requests/day → peak requests/s → tokens/s required (prefill and decode separated).
3. **Compute capacity** with `references/throughput-math.md`: GPUs = ceil(peak tokens/s ÷ effective tokens/s per GPU ÷ utilization target) with headroom for redundancy. Latency check: decode tokens/s per stream vs SLO at the resulting concurrency.
4. **Run the calculator**: fill `assets/gpu-sizing-inputs.csv`, then `python3 -I scripts/size.py --inputs assets/gpu-sizing-inputs.csv`. Compare scenarios (low/expected/peak) and options (self-host / rental / API).
5. **Apply TCO factors** with `references/tco-factors.md`: utilization, ops staffing, upgrade cycle, egress, support, idle time, scaling elasticity.
6. **Recommend**: option, GPU count, monthly cost range, breakeven utilization between rental and self-host, and the triggers to revisit.
7. Run the self-check.

## Output
- `gpu-sizing-<name>.md`: inputs table (with sources/dates), capacity math, cost comparison table, sensitivity, recommendation, assumptions, risks.
- Calculator output (table or JSON) embedded.

## Self-check
- [ ] Every throughput figure cites a benchmark or vendor doc, or is labeled illustrative
- [ ] Every price is a dated user input; nothing hardcoded
- [ ] Prefill and decode handled separately; latency SLO checked, not only throughput
- [ ] Peak factor, utilization target, and redundancy stated as assumptions
- [ ] Breakeven between options shown as a function of utilization
- [ ] TCO includes people and idle cost, not only hardware
- [ ] Recommendation names revisit triggers (volume, model change, price change)

## References
- `references/workload-model.md` — from users to tokens/s
- `references/throughput-math.md` — capacity and latency formulas (figures illustrative)
- `references/tco-factors.md` — self-host vs rental vs API factors
- `scripts/size.py` — calculator (argparse; stdlib)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/infra-gpu-sizing --input <name>=<value> … --out <dir>` (see `--explain ai-platform/infra-gpu-sizing`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.
