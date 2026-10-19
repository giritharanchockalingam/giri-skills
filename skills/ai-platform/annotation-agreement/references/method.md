# Method — annotation-agreement

All statistics are computed by `scripts/agreement.py` with the Python standard library. Sources: `sources.md`.

## Data model
Ratings `(item, annotator, label)`; blank labels are "not rated". An item is **pairable** when it has 2+ ratings. Items with one rating are excluded from every statistic and listed. With no pairable item the run exits 1 and reports no score.

## Percent agreement
Per item with m ratings and n_k ratings of label k: P_i = Σ_k n_k(n_k − 1) / (m(m − 1)) — the share of agreeing annotator pairs. Percent agreement = mean P_i. Not chance-corrected.

## Cohen's kappa (per annotator pair)
On items both annotators rated: p_o = share of identical labels; p_e = Σ_k p_A(k) p_B(k); κ = (p_o − p_e)/(1 − p_e). Undefined (n/a) when p_e = 1.
Worked check (Wikipedia, Cohen 1960 example): 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no → p_o 0.70, p_e 0.50, κ 0.40.

## Fleiss' kappa
Only when every pairable item has the same number of ratings m. p_j = share of all ratings in label j; P̄ = mean P_i; P̄_e = Σ p_j²; κ = (P̄ − P̄_e)/(1 − P̄_e). Otherwise n/a with the reason.
Worked check (Wikipedia example: 10 subjects, 14 raters, 5 categories): P̄ 0.378, P̄_e 0.213, κ 0.210.

## Krippendorff's alpha (nominal)
Coincidence matrix over pairable items: o_ck = Σ_u (number of ordered pairs of ratings (c, k) in u) / (m_u − 1); n_c = Σ_k o_ck; n = Σ_c n_c.
alpha = 1 − (n − 1) · Σ_{c≠k} o_ck / Σ_{c≠k} n_c n_k. Undefined (n/a) when only one label is used.
Worked checks (Krippendorff 2011): 4 observers × 12 units with missing values → 0.743; Meg/Owen binary 2 × 10 → 0.095.

## Per-label agreement
agreement(k) = o_kk / n_k: of the pairable ratings with label k, the share whose paired rating on the same item is also k. For two annotators this equals the specific agreement 2a/(2a + b + c) (yes: 2·20/(40 + 15) = 0.727 in the Cohen example). `n` in `label-agreement.csv` is the number of pairable ratings with that label.

## Confusion pairs
For each pairable item and each pair of annotators who rated it with different labels, count the unordered label pair. Sorted by count, then label.

## Disputed items and guideline gaps
- Disputed: pairable items with P_i < 1, lowest first; `majority` is the plurality label or `tie`.
- Low-agreement label: agreement(k) below the overall percent agreement (both are shares of agreeing pairs, so the comparison is like for like; no fixed threshold is assumed).
- Guideline gap: a low-agreement label whose name does not appear in the guidelines (case-insensitive word match; `_` and `-` also matched as spaces). Without guidelines: `[TO BE BASELINED — owner: Annotation lead]`.

## Interpretation bands (conventions, not tests)
| Kappa (Landis & Koch 1977) | Band |
|---|---|
| < 0 | poor |
| 0.00–0.20 | slight |
| 0.21–0.40 | fair |
| 0.41–0.60 | moderate |
| 0.61–0.80 | substantial |
| 0.81–1.00 | almost perfect |

Alpha (Krippendorff): ≥ 0.800 commonly relied on; 0.667–0.800 tentative conclusions only; < 0.667 discard. The `min_agreement` gate is the data owner's choice; the skill never sets one.

## Limits
Nominal labels only (no ordinal / interval distance); point estimates without bootstrap CIs; agreement measures consistency, not correctness; multi-label items must be split into one binary label per item first.
