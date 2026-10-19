# Sources — annotation-agreement

Checked 2026-10-18 with WebSearch / WebFetch. Worked examples below are reproduced exactly by `tests/test_aiplatform_agreement.py`.

| Topic | Source | What it supports | URL |
|---|---|---|---|
| Krippendorff's alpha, coincidence matrix, worked examples | Krippendorff, K. (2011). "Computing Krippendorff's Alpha-Reliability." Annenberg School for Communication, University of Pennsylvania | Nominal alpha; 4 observers × 12 units with missing data → 0.743; two-observer binary example (Meg, Owen) → 0.095 | https://www.asc.upenn.edu/sites/default/files/2021-03/Computing%20Krippendorff%27s%20Alpha-Reliability.pdf |
| Alpha thresholds 0.800 / 0.667 | Wikipedia "Krippendorff's alpha", citing Krippendorff (2004) *Content Analysis*, pp. 241–243 | ≥ 0.800 relied on; 0.667–0.800 tentative conclusions only; below discarded | https://en.wikipedia.org/wiki/Krippendorff%27s_alpha |
| Fleiss' kappa and worked example | Fleiss, J. L. (1971). "Measuring nominal scale agreement among many raters." *Psychological Bulletin* 76(5): 378–382. doi:10.1037/h0031619; worked example table on Wikipedia | 10 subjects × 14 raters × 5 categories → κ 0.210 | https://en.wikipedia.org/wiki/Fleiss%27_kappa |
| Landis & Koch bands | Landis, J. R., Koch, G. G. (1977). "The measurement of observer agreement for categorical data." *Biometrics* 33(1): 159–174. doi:10.2307/2529310 (table as given on the Fleiss' kappa page) | Kappa interpretation bands; the page notes they are not universally accepted | https://en.wikipedia.org/wiki/Fleiss%27_kappa |
| Cohen's kappa and worked example | Cohen, J. (1960). "A coefficient of agreement for nominal scales." *Educational and Psychological Measurement* 20(1): 37–46. doi:10.1177/001316446002000104 | 50 proposals, 20/5/10/15 → κ 0.40 | https://en.wikipedia.org/wiki/Cohen%27s_kappa |

Not cited: Uebersax's page on specific agreement could not be fetched on the check date, so per-label agreement is defined from Krippendorff's coincidence matrix (o_kk / n_k) and its two-rater equivalence to 2a/(2a + b + c) is shown in the tests rather than cited.
