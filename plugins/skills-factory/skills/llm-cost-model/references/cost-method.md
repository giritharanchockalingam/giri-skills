# Cost method — API token economics

## Formulas (per feature, per month)
| Quantity | Formula |
|---|---|
| Input tokens | requests × average input tokens |
| Cached input tokens | input tokens × cached_input_share (blank share = 0) |
| Output tokens | requests × average output tokens |
| Input cost | (input − cached) ÷ 1M × price_in_per_1m |
| Cached input cost | cached ÷ 1M × cached_in_per_1m (full input price when no cached price is supplied) |
| Output cost | output ÷ 1M × price_out_per_1m |
| Caching saving | cost with every input token at full price − modelled cost |
| Cost per request | feature cost ÷ requests |

What-if: for each feature, the same workload priced on every model listed in `eligible_models` that has a price row; the cheapest wins only if it is cheaper than the current model. Budget: utilisation = total ÷ budget; headroom = budget − total; alert amount = budget × level (default levels 50, 80, 100 %).

## Worked example (the eval fixture — fictional prices, hand-checked)
Prices per 1M tokens: fict-large in 3.00 / out 15.00 / cached 0.30; fict-small in 0.25 / out 1.25 / cached 0.025.

| Feature | Workload | Cost on assigned model |
|---|---|---|
| support-chat (fict-large) | 100,000 req × 1,000 in (50 % cached) × 200 out | 50M × 3 + 50M × 0.30 + 20M × 15 = 150 + 15 + 300 = **465.00** (no caching 600.00; saving 135.00; 0.00465 / request) |
| doc-summary (fict-large) | 20,000 req × 4,000 in × 500 out | 80M × 3 + 10M × 15 = 240 + 150 = **390.00** (0.0195 / request) |

Total 855.00 for 120,000 requests (0.007125 / request). What-if support-chat on fict-small: 50M × 0.25 + 50M × 0.025 + 20M × 1.25 = 12.50 + 1.25 + 25.00 = 38.75 (saving 426.25). Budget 1,000: utilisation 85.5 %, headroom 145.00, 50 % and 80 % alerts reached. Budget 800: over budget, exit 1.

## Cost levers (in order of usual effort)
1. Prompt caching for stable prefixes (system prompt, tool schemas, shared context) — raise `cached_input_share` only to what the cache hit rate in logs supports.
2. Trim tokens: shorter system prompts, fewer retrieved chunks, output length caps.
3. Route by difficulty: move a feature (or its easy share) to a cheaper model that passed the eval bar — mark it in `eligible_models`.
4. Batch or asynchronous processing where the vendor prices it lower — model it as a separate price row with its own source.
5. Volume caps and rate limits per tenant or user.

## Boundaries
- `infra-gpu-sizing` sizes GPUs and compares self-hosting, rental and API; this skill prices hosted API tokens only.
- Eligibility is a quality decision (`llm-eval-harness`); this skill never assumes two models are interchangeable.
- Prices change often: every row carries source and as-of; re-run on a price change. Standards for cost governance (e.g. the FinOps Foundation's FinOps Framework) inform the alert levels; the levels themselves are the user's choice.
