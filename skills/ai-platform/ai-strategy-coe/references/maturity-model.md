# AI Maturity Model — 5 levels × 5 dimensions

Score each dimension independently. Overall maturity = the **lowest** dimension score, not the average; the weakest dimension is the constraint on everything else.

## Levels
| Level | Name | One-line test |
|---|---|---|
| 1 | Ad hoc | Individuals experiment; nothing is repeatable or owned |
| 2 | Emerging | Pilots exist; some ownership; no shared platform or policy |
| 3 | Defined | Standard platform, intake, and policy exist and are used by most teams |
| 4 | Managed | Measured: value, risk, and cost tracked per use case; portfolio decisions are evidence-based |
| 5 | Optimizing | AI is in the operating rhythm; continuous improvement; business owns outcomes, CoE owns enablement |

## Criteria per dimension

### Data
| Level | Criteria (all must hold) |
|---|---|
| 1 | Data in silos; no catalog; access by personal request; quality unknown |
| 2 | Partial catalog; one or two curated domains; lineage absent; PII handling manual |
| 3 | Enterprise catalog with owners; documented quality rules for key domains; access via role; PII classified |
| 4 | Data products with SLAs; lineage automated; quality monitored with alerts; feature/vector stores governed |
| 5 | Data contracts enforced in CI; consumers self-serve; quality and freshness reported to business owners |

### Platform
| Level | Criteria |
|---|---|
| 1 | Laptop notebooks; API keys in personal accounts |
| 2 | Shared cloud project; some model access through a gateway; no environments separation |
| 3 | Approved model gateway with logging; dev/test/prod; CI for AI apps; secret management; one orchestration framework standard |
| 4 | Observability (traces, cost per call, eval scores) in production; prompt/model versioning; canary releases; rate and spend limits per team |
| 5 | Platform as product: SLAs, self-service onboarding, automated eval gates, model routing by cost/quality policy |

### Talent
| Level | Criteria |
|---|---|
| 1 | Enthusiasts only; no roles defined |
| 2 | Small data-science or innovation team; business users untrained |
| 3 | Defined roles (AI engineer, data engineer, product owner, risk reviewer); training path for builders and consumers; hiring plan |
| 4 | Communities of practice; career ladder; business "AI translators" in each major function; vendor/partner strategy |
| 5 | Capability measured and renewed; internal certifications; business leads own AI outcomes in their scorecards |

### Governance
| Level | Criteria |
|---|---|
| 1 | No policy; shadow AI usage unknown |
| 2 | Acceptable-use policy published; no enforcement; no model inventory |
| 3 | Intake and risk tiering; model inventory; human-review rules for high-risk; vendor/data terms reviewed |
| 4 | Controls tested (bias, privacy, security, hallucination); incident process; regulatory mapping (NIST AI RMF, EU AI Act where applicable) |
| 5 | Continuous assurance; audit evidence automated; board-level reporting |

### Value
| Level | Criteria |
|---|---|
| 1 | No business case; "innovation" budget |
| 2 | Pilots with anecdotal benefit; no baseline measured |
| 3 | Each use case has baseline, target, and owner; benefits tracked at portfolio level |
| 4 | Realized value reported quarterly to finance; kill decisions made on evidence; unit economics per use case |
| 5 | AI value embedded in business plans and P&L; portfolio rebalanced on return |

## Scoring rules
1. Score on evidence you were shown or told. Record the evidence line. No evidence → `[TO BE BASELINED — owner: ___]`.
2. Do not round up for intent ("we plan to…"). Plans score at the current level.
3. Present as a table: Dimension | Score | Evidence | Gap to next level | Owner.
4. State the overall level as the minimum and name the constraining dimension in the headline.

## Typical gap patterns (diagnostic, not prescriptive)
| Pattern | Usual cause | First move |
|---|---|---|
| Platform 3+, Value 1–2 | Technology-led program | Install baselines and benefit owners before new builds |
| Data 1–2, everything else 3 | Vendor demos drove the roadmap | Pick two data domains and productize them; defer RAG at scale |
| Governance 1, Platform 2 | Shadow AI | Gateway + inventory in 60 days; policy follows |
| Talent 2, Platform 4 | Platform team outran adoption | Enablement, office hours, embedded engineers in two functions |
