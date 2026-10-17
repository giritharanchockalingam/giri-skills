---
name: infra-gpu-sizing
description: Use when the user asks to size GPU or inference infrastructure, compare self-hosting an LLM against renting GPUs or using an API, or estimate monthly cost for a given user load — "how many GPUs do we need", "self-host vs rent", "cost of serving model X to N users". Produces a workload model (users, requests/day, tokens in/out, latency SLO), throughput math from user-supplied tokens/s per GPU, GPU count, monthly cost for self-host vs rental vs API from user-supplied unit prices, a TCO factor table, and a recommendation; ships a calculator script. Not for training-cluster sizing or vendor selection.
license: MIT
metadata:
  domain: ai-platform
  version: 0.1.0
  author: giri-skills
---

# Infra & GPU Sizing (inference)

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
