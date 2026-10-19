# Method — ab-test-analysis

All statistics are computed by `scripts/ab_test.py` with the Python standard library (`math`, `statistics.NormalDist`). Sources: `sources.md`.

## Sample ratio mismatch (SRM)
- Observed: assigned units per variant (aggregated: `users` of the primary metric; unit-level: distinct `unit_id`).
- Expected: total × expected share (`expected_split`; default equal shares, labelled as a default).
- Statistic: Pearson chi-square Σ (O − E)² / E, df = variants − 1; p = Q(df/2, χ²/2), the regularised upper incomplete gamma.
- Flag: p < `srm_alpha` (default 0.001). This threshold is a practitioner convention; Microsoft's ExP uses 0.0005. A strict threshold is used because SRM checks run on every experiment and false alarms are costly.
- Worked check (tests): 10,000 vs 10,600 at 50/50 → χ² = 2 × 300² / 10,300 = 17.4757, p = erfc(√(χ²/2)) = 0.000029 → SRM.

## Binary metric — two-proportion z-test
- p_c = conversions_c / n_c, p_t likewise; diff = p_t − p_c; relative lift = diff / p_c.
- Pooled p = (x_c + x_t) / (n_c + n_t); SE_pooled = √(p(1 − p)(1/n_c + 1/n_t)); z = diff / SE_pooled; two-sided p = erfc(|z| / √2).
- Wald CI: diff ± z_{1−α/2} · √(p_c(1 − p_c)/n_c + p_t(1 − p_t)/n_t) (unpooled).
- Worked check (fixture): 2,000/5,000 vs 2,150/5,000 → diff 0.030000, SE_pooled 0.0098544, z 3.0443, p 0.002332; CI [0.010695, 0.049305].

## Continuous metric — Welch's t-test
- mean = sum / n; variance = (sumsq − sum²/n) / (n − 1).
- SE = √(s_c²/n_c + s_t²/n_t); t = diff / SE; df = SE⁴ / [(s_c²/n_c)²/(n_c − 1) + (s_t²/n_t)²/(n_t − 1)] (Welch–Satterthwaite).
- p = 2(1 − F_t(|t|; df)), F_t(t) = 1 − ½ I_{df/(df+t²)}(df/2, ½) for t ≥ 0; I is the regularised incomplete beta (continued fraction, modified Lentz).
- CI: diff ± t_{1−α/2, df} · SE; the quantile is found by bisection on F_t.
- Verified in tests against closed forms (df = 1: ½ + atan(t)/π; df = 2: ½ + t / (2√(2 + t²))) and table quantiles (t_{0.975,10} = 2.228, t_{0.975,20} = 2.086, t_{0.995,5} = 4.032).

## Multiple treatments — Holm
Within each metric, p-values for the k treatments are sorted ascending; adjusted p_(i) = max_{j ≤ i} min(1, (k − j + 1) p_(j)). Significance uses the adjusted p. One treatment → no adjustment.

## Power and sample size (primary metric)
- Smallest detectable effect at the observed n: (z_{1−α/2} + z_{power}) · SE_unpooled.
- With an MDE δ (absolute, or relative to the control mean when given with `%`):
  - binary: variances p_c(1 − p_c) and (p_c + δ)(1 − p_c − δ); continuous: the observed variances.
  - achieved power = Φ(|δ|/SE_δ − z_{1−α/2}) + Φ(−|δ|/SE_δ − z_{1−α/2}).
  - n per arm = ⌈(z_{1−α/2} + z_{power})² (v_c + v_t) / δ²⌉ (equal allocation, unadjusted alpha).
- Worked check (fixture): p_c 0.40, δ 0.02 → n per arm = ⌈7.8489 × 0.4836 / 0.0004⌉ = 9,490; achieved power at 5,000 per arm 0.5294.
- No MDE → `[TO BE BASELINED — owner: Experiment owner]`; no value is assumed.

## Decision rule (per treatment)
| Primary metric (Holm-adjusted) | Guardrails | Decision |
|---|---|---|
| significantly worse | any | don't ship |
| significantly better | any guardrail significantly worse | don't ship |
| significantly better | a guardrail moved significantly with no declared direction, or a declared guardrail is missing | inconclusive (TBD Experiment owner) |
| significantly better | none significantly worse | ship |
| not significant | any | inconclusive |

Overall: SRM → untrustworthy (exit 1). Otherwise ship the shipping treatment with the largest improvement; don't ship when every treatment is don't ship; else inconclusive.

## Limits
Fixed-horizon frequentist analysis (no peeking correction, no sequential testing); independent units (no clustering or repeated measures; ratio metrics need the delta method, not provided); normal approximation for binary metrics (poor for very small counts); novelty, seasonality and interference are not detected.
