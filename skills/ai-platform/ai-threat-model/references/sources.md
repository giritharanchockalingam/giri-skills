# Sources — ai-threat-model

| Source | URL | Used for | Checked |
|---|---|---|---|
| OWASP Gen AI Security Project — LLM Top 10 (2025 Top 10 Risk & Mitigations for LLMs and Gen AI Apps) | https://genai.owasp.org/llm-top-10/ | Ids LLM01:2025–LLM10:2025 and names (Prompt Injection; Sensitive Information Disclosure; Supply Chain; Data and Model Poisoning; Improper Output Handling; Excessive Agency; System Prompt Leakage; Vector and Embedding Weaknesses; Misinformation; Unbounded Consumption) | 2026-10-18 |
| OWASP Top 10 for Large Language Model Applications — project page | https://owasp.org/www-project-top-10-for-large-language-model-applications/ | Confirms the project links "Version 2025" to https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/ | 2026-10-18 |
| Hernan, Lambert, Ostwald, Shostack — "Uncover Security Design Flaws Using The STRIDE Approach", MSDN Magazine, Nov 2006 | https://learn.microsoft.com/en-us/archive/msdn-magazine/2006/november/uncover-security-design-flaws-using-the-stride-approach | STRIDE-per-element table (Figure 5): data flows T,I,D; data stores T,I,D; processes S,T,R,I,D,E; interactors S,R | 2026-10-18 |

The OWASP paraphrases in `assets/owasp-llm-top10-2025.csv` are one-sentence summaries written for this skill; they are not OWASP text. Applicability rules, severity rules and the mitigation catalogue are this skill's own method (see `method.md`), not OWASP or Microsoft guidance.
