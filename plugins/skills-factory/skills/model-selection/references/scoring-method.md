# Scoring Method — model selection

A transparent multi-criteria decision method (weighted sum over min-max normalised criteria, with
non-compensatory hard constraints). Every input is user-supplied; the method adds no facts.

## 1. Hard constraints (non-compensatory)
A hard constraint is a must-have that no score can buy back: data residency, self-hosting,
a latency SLO ceiling, a minimum context window, an accuracy floor.

| Column | Meaning | Elimination rule |
|---|---|---|
| `hard_min` | numeric floor | value < hard_min |
| `hard_max` | numeric ceiling | value > hard_max |
| `hard_in` | allowed text values, `;`-separated | value not in the set (case-insensitive) |

A blank value on a constrained criterion eliminates the candidate: the constraint cannot be
verified, and an unverified must-have is treated as unmet. Every elimination lists its reasons.

## 2. Normalisation (survivors only)
For each criterion with weight > 0, over the surviving candidates that have a value:

```
higher is better   n = (x − min) / (max − min)
lower is better    n = (max − x) / (max − min)
all equal          n = 1.0           (the criterion does not discriminate)
missing value      n = 0             (penalised and listed under Gaps with an owner)
```

Normalising over survivors (not all candidates) keeps eliminated outliers from compressing the scale.
Min-max is relative: adding or removing a candidate can change every normalised value. Re-run, do not hand-edit.

## 3. Weighted score and rank
```
w_k'   = w_k / Σ w            (weights normalised to sum to 1)
score  = Σ_k w_k' × n_k        (0 … 1)
rank   = score descending, ties broken by model name (deterministic)
```
`contribution` in ranking.json is `w_k' × n_k`, so the per-criterion contributions sum to the score.

## 4. Sensitivity
Each weight is multiplied by 0.8 and by 1.2 in turn (others unchanged, then all renormalised), and the
ranking is recomputed with the same normalised values. The verdict is:

- **stable** — the winner is the same in all 2 × k runs;
- **sensitive** — at least one run produces a different winner (named as a challenger). The decision then
  depends on a weighting judgement and goes back to the decision owner with that trade-off made explicit.

## 5. Monthly cost (optional)
```
monthly_cost_usd = requests_per_month × (tokens_in × price_in_per_1m + tokens_out × price_out_per_1m) / 1e6
```
For self-hosted candidates, supply an effective $/1M tokens (for example from `infra-gpu-sizing`) as the
price columns, with its source; otherwise the cost is a gap.

## Limits
- Weighted sums assume criteria are roughly independent; two criteria measuring the same thing double-count it.
- Scores are only as good as the evals behind them: same dataset, same prompts, same date for every candidate.
