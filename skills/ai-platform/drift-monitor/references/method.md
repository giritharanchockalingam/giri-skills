# Drift method (what `scripts/drift.py` computes)

## Feature typing
- A feature is **numeric** when at least 95% of its non-missing values (both windows together) parse as finite numbers; otherwise **categorical**.
- Override with `types`, e.g. `store_id=categorical` for numeric-looking IDs.
- Missing values: blank, `NA`, `N/A`, `NaN`, `null`, `None` (case-insensitive). They are excluded from every distribution and reported as `null_rate_baseline` / `null_rate_current` (missing rows ÷ all rows).
- In a numeric feature, values that do not parse are excluded and counted in `drift.json` (`unparsed_baseline`, `unparsed_current`).

## Population Stability Index (PSI)
`PSI = Σ (c_i − b_i) · ln(c_i / b_i)`, where `b_i`, `c_i` are the baseline and current proportions in bin `i`.
- Numeric bins: cut points are the baseline's nearest-rank 10th…90th percentiles (`value at rank ceil(q·n/10)`), bins `(−∞, e1], (e1, e2], …, (e9, ∞)`. Tied cut points merge, so a feature with few distinct values has fewer than 10 bins (`bins` in `drift.json`).
- Categorical bins: one per category in either window. A category unseen in the baseline keeps its own bin and is listed in the Alerts section.
- Empty bin: its proportion is replaced by **ε = 0.0001** so `ln` stays finite. This is a convention; an unseen category with a large current share therefore produces a large PSI by design (it is new behaviour).

## Two-sample Kolmogorov–Smirnov (numeric)
- `D = max_x |F_base(x) − F_cur(x)|` over the pooled sorted values (ties handled by stepping both ECDFs together).
- p-value is the asymptotic Kolmogorov tail `Q_KS(λ) = 2 Σ_{k≥1} (−1)^{k−1} e^{−2k²λ²}` with `λ = √(nm/(n+m)) · D`; for `λ < 1` the equivalent series `1 − √(2π)/λ Σ e^{−(2k−1)²π²/(8λ²)}` is used (it converges fast there).
- Checked: `Q_KS(1.3581) ≈ 0.0500`, `Q_KS(1.6276) ≈ 0.0100` (the classic 5% and 1% critical values). Small samples make the asymptotic p-value approximate.

## Chi-square test of homogeneity (categorical)
- 2 × K table (baseline vs current counts per category); `E = row total × column total ÷ n`; `χ² = Σ (O − E)² / E`; `df = K − 1`.
- p-value `= Q(df/2, χ²/2)`, the regularised upper incomplete gamma (series below `a+1`, Lentz continued fraction above). Checked: χ²=3.841, df 1 → 0.0500; χ²=5.991, df 2 → 0.0500; χ²=11.345, df 3 → 0.0100.
- No Yates continuity correction. Expected counts below 5 make the p-value unreliable; read PSI instead.

## Status rule (per feature)
1. `insufficient-data` when either window has fewer than **30** non-missing values. Never alert.
2. `alert` when PSI ≥ psi.alert, or p < p_value.alert, or |Δ missing rate| ≥ null_rate_delta.alert.
3. `warn` on the same tests against the warn levels.
4. otherwise `ok`.
Defaults: psi warn 0.1 / alert 0.25; p_value alert 0.01; null_rate_delta none (reported, not gated, owner Data owner). Any alert makes the run exit 1 (gate) with full outputs.

## Worked example (hand-checked; used in the tests)
Baseline A 50, B 50; current A 30, B 70.
- PSI = (0.3 − 0.5)·ln(0.6) + (0.7 − 0.5)·ln(1.4) = 0.102165 + 0.067294 = **0.1695** → warn.
- χ²: E = 40/60 per row; (10²/40)·2 + (10²/60)·2 = **8.3333**, df 1, p = erfc(√(8.3333/2)) = **0.0039** → alert.
- Status **alert**.

## Limits
- Univariate: each feature is tested alone; correlated or joint drift is not detected. No multiple-comparison correction.
- p-values fall with sample size; on large windows tiny shifts become "significant". Use PSI and D for magnitude.
- Drift is a reason to investigate, not proof the model got worse. Pair with a quality check (`llm-eval-harness`) on the current window.
