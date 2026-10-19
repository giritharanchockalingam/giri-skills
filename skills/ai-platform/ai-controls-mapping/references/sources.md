# Sources — AI controls mapping

All checked **2026-10-18** with WebSearch/WebFetch. NIST publications are US-government works in the public domain. `assets/nist-ai-rmf-1.0.csv` holds short paraphrases, not the full text.

| # | Source | URL | What it confirmed |
|---|---|---|---|
| S1 | NIST AI 100-1, *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*, Jan 2023 — Tables 1-4 | https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf | GOVERN: 6 categories, 19 subcategories (1.1-1.7, 2.1-2.3, 3.1-3.2, 4.1-4.3, 5.1-5.2, 6.1-6.2). MAP: 5 categories, 18 (1.1-1.6, 2.1-2.3, 3.1-3.5, 4.1-4.2, 5.1-5.2). MEASURE: 4 categories, 22 (1.1-1.3, 2.1-2.13, 3.1-3.3, 4.1-4.3). MANAGE: 4 categories, 13 (1.1-1.4, 2.1-2.4, 3.1-3.2, 4.1-4.3). **Total 19 categories, 72 subcategories.** |
| S2 | NIST AI RMF Playbook (page updated 18 Jun 2026) | https://airc.nist.gov/airmf-resources/playbook/ | Suggested actions are aligned to each subcategory of the four functions. The Playbook will be updated after the AI RMF is revised. |
| S3 | NIST, AI Risk Management Framework page | https://www.nist.gov/itl/ai-risk-management-framework | The current version is AI RMF 1.0 (26 Jan 2023). It "is being revised as part of the White House AI Action Plan"; no draft revision was published at check date. AI 600-1 (GenAI profile) released 26 Jul 2024. |
| S4 | NIST AIRC, Crosswalk documents | https://airc.nist.gov/airmf-resources/crosswalks/ | 12 crosswalks listed (ISO/IEC 23894, 42001, 42005, OECD, Singapore, Japan, Korea and others). The only EU-related one is NIST's "OECD/EU/EO13960" (26 Jan 2023), which maps AI RMF trustworthiness characteristics to the **proposed** AI Act. None maps subcategories to the final Regulation (EU) 2024/1689. |
| S5 | NIST crosswalk AI RMF 1.0 ↔ OECD / EO 13960 / proposed EU AI Act | https://www.nist.gov/system/files/documents/2023/01/26/crosswalk_AI_RMF_1_0_OECD_EO_AIA_BoR.pdf | Characteristic-level mapping, used as context only. |

## Why the crosswalk is the skill's own
No authoritative mapping from the final AI Act's obligations to AI RMF subcategories existed on the check date (S4). `assets/aiact-nist-crosswalk.csv` is therefore **the skill's own mapping**, and it is labelled that way in the asset, the report and here. See `crosswalk-method.md`.
