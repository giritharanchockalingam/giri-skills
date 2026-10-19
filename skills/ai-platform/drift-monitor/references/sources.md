# Sources (checked 2026-10-18)

| Item | Source | What it supports |
|---|---|---|
| PSI cut-offs 0.1 / 0.25 | J. du Pisanie, J. S. Allison, C. J. Budde, I. J. H. Visagie, "A Critical Review of Existing and New Population Stability Testing Procedures in Credit Risk Scoring", arXiv:2303.01227 (2023) — https://arxiv.org/abs/2303.01227 | Attributes the 0.1 / 0.25 interpretation of PSI to E. M. Lewis, *An Introduction to Credit Scoring* (1994); notes rules of thumb are hard to justify statistically and ignore sample size and the number of bins. |
| PSI in scorecard practice | `scorecard` R package, `perf_psi` documentation — https://search.r-project.org/CRAN/refmans/scorecard/html/perf_psi.html | PSI as the standard population-stability measure in credit scorecards. |

**Convention, not law.** The 0.1 / 0.25 PSI thresholds are an industry rule of thumb. They carry no confidence level and do not adjust for sample size or bin count. Teams should agree their own thresholds (`assets/thresholds-template.csv`); until then the report marks them `[TO BE BASELINED — owner: ML engineering lead]`.

The KS and chi-square formulas are standard textbook statistics; the implementation was cross-checked against SciPy (`kstwobign.sf`, `chi2_contingency(correction=False)`) on the eval fixtures during development. SciPy is not a runtime dependency.
