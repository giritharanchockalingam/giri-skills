# AI Risk Taxonomy and Tiering

## Categories
| Category | Definition | Example scenarios | Typical signals |
|---|---|---|---|
| Bias / fairness | Outputs systematically disadvantage a group | Résumé screening favors one demographic; loan pre-qualification differs by zip code; tutoring assistant gives lower-quality help in one language | Protected attributes or proxies in data; decisions about people |
| Privacy | Personal data collected, exposed, inferred, or retained beyond purpose | PII in prompts logged to a vendor; RAG surfaces another employee's record; model infers health status | PII, special categories, minors, cross-border transfer |
| Hallucination / accuracy | Confident false or unsupported output | Invented policy clause; wrong dosage; fabricated citation | No grounding; no abstention path; high-stakes facts |
| IP / copyright | Infringement or leakage of protected content | Training data provenance unclear; output reproduces licensed text; employee pastes source code into a public model | Generative output published externally; proprietary inputs |
| Security | Prompt injection, data exfiltration, tool abuse, model theft | Agent follows instructions embedded in an email; over-privileged tools; secrets in prompts | Agents with tools; untrusted content; external communications |
| Misuse | System used outside intended purpose | Internal drafting tool used for customer legal advice; chatbot used to generate harassment | Broad access; no scope controls |
| Operational | Reliability, drift, cost, vendor dependency | Model version change breaks workflow; cost spike; vendor outage | No eval gate; no fallbacks; single vendor |
| Transparency / accountability | Users unaware they interact with AI or cannot contest outcomes | No disclosure; no human appeal; decisions unexplained | Customer-facing; consequential decisions |
| Safety (physical / wellbeing) | Harm to people from advice or action | Health, safety, or financial guidance to vulnerable users | Vulnerable users; action-taking agents |

## Scoring
| Scale | Likelihood | Impact |
|---|---|---|
| 1 | Rare; strong preventive controls | Negligible; internal, reversible |
| 2 | Unlikely | Minor; limited users; reversible with effort |
| 3 | Possible | Moderate; customer or employee harm; regulatory inquiry possible |
| 4 | Likely | Major; legal exposure; material financial or reputational impact |
| 5 | Almost certain without controls | Severe; safety, rights, or regulatory breach |

Inherent score = likelihood × impact (1–25). Residual score re-scored after controls. Treat ≥ 15 as requiring executive sign-off; 8–14 as requiring named mitigations before launch; < 8 monitor.

## Internal tiering
| Tier | Criteria (any) | Review path |
|---|---|---|
| Low | Internal users; no personal data beyond business contact; human reviews every output; reversible | Self-certification; register entry |
| Medium | Employee-facing or customer-facing with human in the loop; personal data present; outputs influence but do not decide | CoE review; controls checklist; model card |
| High | Autonomous actions on people or money; decisions about employment, credit, education, health, legal status; minors or vulnerable users; special-category data; likely EU AI Act high-risk | Risk committee; full register; DPIA/equivalent; legal review; executive sign-off |

## Elicitation questions
1. What decision or action does the output influence, and who bears the consequence?
2. What is the worst plausible output, and who sees it before harm occurs?
3. What data enters the prompt, what is logged, and where does it go?
4. Can a user contest or correct an outcome?
5. What happens when the model is unavailable or wrong 5% of the time?
