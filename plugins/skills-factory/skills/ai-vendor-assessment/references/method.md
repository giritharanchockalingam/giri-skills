# Method — ai-vendor-assessment

## Scoring
- Normalised weight w_c = raw weight_c ÷ Σ raw weights (weights need not sum to 1 or 100; the report states the raw sum).
- Weighted score (option) = Σ_c w_c × score(option, c), scores on 1–5. Reported to 3 dp; comparisons use full precision.
- Rank: descending score; equal scores share a rank; ties listed by option name.
- Incomplete option: any criterion without a score. It gets no weighted score, no rank and is excluded from the recommendation; `missing_criteria` names the gaps with `[TO BE BASELINED — owner: Procurement lead]`. Scores are never imputed.

## Sensitivity
- For each criterion c and each factor f ∈ {0.8, 1.2}: raw weight_c × f, others unchanged, renormalise, rescore complete options.
- `top_changed = yes` when the first option differs from the baseline first option, or when first place is tied.
- Rank stability % = runs with `top_changed = no` ÷ (2 × number of criteria) × 100.

Worked example (fictional fixture): weights 40/25/20/15; Fabrikam 5,3,4,4 → 0.40×5 + 0.25×3 + 0.20×4 + 0.15×4 = 4.150. With answer_quality ×0.8 the raw weights are 32/25/20/15 (sum 92): Fabrikam 375/92 = 4.076, Tailspin 353/92 = 3.837, margin 0.239, top unchanged.

## Third-party AI risk
- Each question in `assets/third-party-ai-risk-questions.csv` has an `answer_type` (yes_no, yes_no_progress, number) and a `red_flag_rule`: `eq:<value>`, `gt:<n>` or `lt:<n>`.
- `unknown` (or blank, or no row) = unanswered: listed with `[TO BE BASELINED — owner: Third-party risk manager]`, not a red flag. `n/a` = not applicable (e.g. an in-house build).
- Numeric thresholds (retention > 30 days, change notice < 30 days, incident notice > 72 hours) are template defaults, not regulatory values; set them to your policy via the `questions` input.

## Recommendation
Clear winner = baseline top complete option that (1) is not tied, (2) has no red flags, (3) stays first in every sensitivity run. Otherwise "no clear winner" with reasons; the report also names the highest-scoring option without red flags. Exit 0 either way, unless `--require-clear-winner` (then exit 1 when there is no clear winner). Without a risk file the recommendation is conditional on a third-party risk review.

## Limits
Scores are only as good as their sources. A ±20% one-at-a-time perturbation does not test joint weight changes. Certificates and reports (SOC 2, ISO/IEC 27001, ISO/IEC 42001) must be inspected; this skill records answers, it does not verify them. Not a legal or contract review.
