# Sources — ab-test-analysis

Checked 2026-10-18 with WebSearch / WebFetch. IDs and short paraphrases only.

| Topic | Source | What it supports | URL |
|---|---|---|---|
| SRM definition and test | Fabijan, A. et al. (2019). "Diagnosing Sample Ratio Mismatch in Online Controlled Experiments." Proc. KDD '19, pp. 2156–2164 | SRM as a trust check; chi-square test of observed vs configured split | https://www.microsoft.com/en-us/research/articles/diagnosing-sample-ratio-mismatch-in-a-b-testing/ |
| SRM threshold | Microsoft Research ExP article (same URL) | Microsoft's platform flags SRM at p < 0.0005 to limit false alarms | https://www.microsoft.com/en-us/research/articles/diagnosing-sample-ratio-mismatch-in-a-b-testing/ |
| SRM threshold convention | MetricGate SRM test documentation | Practitioners use a strict threshold, commonly 0.001 or smaller (no primary source cited there — hence "convention") | https://metricgate.com/docs/sample-ratio-mismatch-test/ |
| SRM in the trust-guardrail chapter | Kohavi, R., Tang, D., Xu, Y. (2020). *Trustworthy Online Controlled Experiments*, Cambridge University Press, ch. 21 "Sample Ratio Mismatch and Other Trust-Related Guardrail Metrics" | SRM invalidates results; check before reading metrics | https://www.cambridge.org/core/books/trustworthy-online-controlled-experiments/sample-ratio-mismatch-and-other-trustrelated-guardrail-metrics/8DBB0F59AC7729D7BC6B94690DB9CCD5 |
| SRM worked example | Wikipedia, "Sample ratio mismatch" | Pearson chi-square goodness-of-fit used for SRM | https://en.wikipedia.org/wiki/Sample_ratio_mismatch |
| Welch's t-test | Welch, B. L. (1947). "The generalization of 'Student's' problem when several different population variances are involved." *Biometrika* 34(1–2): 28–35. doi:10.1093/biomet/34.1-2.28 | Unequal-variance t-test and df | https://en.wikipedia.org/wiki/Welch%27s_t-test |
| Holm correction | Holm, S. (1979). "A simple sequentially rejective multiple test procedure." *Scandinavian Journal of Statistics* 6(2): 65–70 | Step-down adjusted p-values | https://en.wikipedia.org/wiki/Holm%E2%80%93Bonferroni_method |
| Student-t CDF / incomplete beta | Standard identity F_t(t) = 1 − ½ I_{ν/(ν+t²)}(ν/2, ½); continued fraction evaluated with the modified Lentz method | Implementation; verified in tests against exact closed forms for ν = 1, 2 and published t-table quantiles | (closed forms are exact; no external figure relied on) |

The chosen default `srm_alpha` = 0.001 follows the brief and the practitioner convention above; set `srm_alpha,0.0005` in the config to match Microsoft ExP.
