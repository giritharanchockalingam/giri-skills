# Sources — EU AI Act classifier

All checked **2026-10-18** with WebSearch/WebFetch. The obligations catalogue (`assets/obligations-catalogue.csv`) paraphrases the law; it is not the legal text.

| # | Source | URL | What it confirmed |
|---|---|---|---|
| S1 | Regulation (EU) 2024/1689 (AI Act), Official Journal, EUR-Lex | https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng | Base act, dated 13 Jun 2024. EUR-Lex metadata lists 2 Aug 2026 as a date of application. The page body could not be fetched (proxy blocked direct download; WebFetch returned metadata only). |
| S2 | Regulation (EU) 2026/1744 (AI Omnibus), Official Journal L, EUR-Lex | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202601744 | Dated 8 Jul 2026, published 24 Jul 2026. Recital 40: Chapter III Sections 1-3 apply from 2 Dec 2027 (Annex III) and 2 Aug 2028 (Annex I). Recital 38: a four-month Art. 50(2) transition. Art. 1(5): Art. 4 AI literacy reworded to "take measures to support". Art. 1(7): new Art. 5(1)(ba) non-consensual intimate content and (bb) CSAM prohibitions. Recital 46: entry into force on the third day after publication. Only the first 100,000 of about 150,000 characters were readable, so the operative Art. 113 text was confirmed through S3-S5. |
| S3 | European Commission, "AI Act" policy page (last update 3 Aug 2026) | https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai | Prohibitions and AI literacy from 2 Feb 2025; new prohibition 9 from Dec 2026; GPAI from 2 Aug 2025; transparency Aug 2026; high-risk Annex III 2 Dec 2027; Annex I 2 Aug 2028. Omnibus proposed 19 Nov 2025, political agreement 7 May 2026, in force 27 Jul 2026. |
| S4 | Consolidated Art. 113 (artificialintelligenceact.eu, secondary) | https://artificialintelligenceact.eu/article/113/ | Art. 113 as amended: applies from 2 Aug 2026. (a) Chapters I-II from 2 Feb 2025, with certain Art. 5 points from 2 Dec 2026. (b) Chapter III Section 4, Chapters V, VII and XII and Art. 78 from 2 Aug 2025, except Art. 101. (c) Chapter III Sections 1-3 from 2 Dec 2027 (Annex III) and 2 Aug 2028 (Annex I). (d) Arts. 102-110 from 27 Jul 2026. |
| S5 | Consolidated Art. 111 (artificialintelligenceact.eu, secondary) | https://artificialintelligenceact.eu/article/111/ | Art. 111(3): GPAI models placed on the market before 2 Aug 2025 comply by 2 Aug 2027. Art. 111(2) (amended): pre-existing high-risk systems are caught only on significant design change; public-authority use by 2 Aug 2030. |
| S6 | Consolidated Art. 6 (artificialintelligenceact.eu, secondary) | https://artificialintelligenceact.eu/article/6/ | Art. 6(3) conditions (a)-(d). An Annex III system that profiles natural persons is always high-risk. Art. 6(4): document the assessment and register under Art. 49(2). |
| S7 | White & Case, "EU AI Omnibus enters into force, amending the AI Act" | https://www.whitecase.com/insight-alert/eu-ai-omnibus-enters-force-amending-ai-act | Reg. 2026/1744 signed 8 Jul 2026, OJ 24 Jul 2026, in force 27 Jul 2026. Art. 50(2) systems placed on the market before 2 Aug 2026 comply by 2 Dec 2026. Deferral covers Chapter III only. |
| S8 | Gibson Dunn, "EU AI Act Omnibus Agreement — Postponed High-Risk Deadlines" | https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/ | No date change for prohibitions, AI literacy (2 Feb 2025) or GPAI (2 Aug 2025). New prohibition transition until 2 Dec 2026. Sandboxes deadline 2 Aug 2027. |

## Dates used by the skill

| Obligation group | Applies from | Basis |
|---|---|---|
| Art. 4 AI literacy; Art. 5(1)(a)-(h) prohibitions | 2025-02-02 | Art. 113(a) — S3, S4, S8 |
| Art. 5(1)(ba), (bb) (added by Reg. 2026/1744) | 2026-12-02 | Art. 113(a) as amended — S3, S4, S8 |
| GPAI model obligations Arts. 53, 55 | 2025-08-02 (models placed before then: 2027-08-02) | Art. 113(b), Art. 111(3) — S4, S5 |
| Art. 50 transparency | 2026-08-02 | Art. 113 general date — S3, S7 |
| Art. 50(2) marking, systems placed on the market before 2026-08-02 | 2026-12-02 | Art. 50(2) as amended — S2, S7 |
| Chapter III high-risk (Arts. 6-27), Annex III route | 2027-12-02 | Art. 113(c) as amended — S2, S3, S4 |
| Chapter III high-risk, Annex I route | 2028-08-02 | Art. 113(c) as amended — S2, S3, S4 |
| Arts. 72-73 (post-market monitoring, incidents) | Chapter III date | **Skill reading.** Chapter IX applies from 2 Aug 2026, but only to systems classified high-risk under Chapter III. Confirm with counsel. |

## Status of the law on 2026-10-18
- The high-risk dates are no longer a proposal: Reg. 2026/1744 is in force. They have moved once and could move again.
- The direct EUR-Lex operative text for Art. 113 could not be fetched in full. The dates rest on the OJ recitals (S2), the Commission page (S3) and two consolidated or legal-analysis sources (S4, S7, S8), which agree.
- Commission guidelines on high-risk classification (Art. 6(5)) and harmonised standards are still being produced. They do not change the dates, but they may change how a borderline system is classified.
- Re-verify the dates against EUR-Lex whenever this file is more than six months old.
