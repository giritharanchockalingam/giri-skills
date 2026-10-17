# Regulatory and Framework Mapping (summary level)

This is a planning aid. It is not legal advice. Obligations, tiers, and timelines must be confirmed by counsel against the current text of each regulation.

## NIST AI Risk Management Framework — four functions
| Function | Purpose | What to show in the review | Controls (catalog) |
|---|---|---|---|
| Govern | Policies, roles, accountability, culture | AI policy; inventory; tiering; roles (owner, reviewer, risk lead); training | C01, C18, C19, C21 |
| Map | Context, intended use, impacts, stakeholders | Use-case description; users and affected parties; data flows; out-of-scope uses; tier rationale | C02, C13, C20 |
| Measure | Evaluate and track risks with metrics | Eval harness results; bias tests; security tests; monitoring metrics | C06, C07, C08, C10, C16, C22 |
| Manage | Prioritize, respond, and recover | Controls with owners; HITL; incident process; rollback; vendor fallback; periodic review | C04, C05, C09, C11, C12, C14, C15, C17 |

Coverage table for the deliverable: Function | Evidence present | Gaps | Owner.

## EU AI Act — risk tiers (summary)
| Tier | Summary description | Typical examples (illustrative) | Headline implication |
|---|---|---|---|
| Unacceptable | Practices prohibited outright | Social scoring by public authorities; manipulative techniques causing harm; certain biometric categorization | Do not build |
| High-risk | Systems in listed domains or safety components of regulated products | Employment decisions (recruitment, promotion), access to education and student assessment, credit scoring, essential services, law enforcement, critical infrastructure | Risk management system, data governance, technical documentation, logging, transparency, human oversight, accuracy/robustness/security, conformity assessment, registration |
| Limited risk (transparency) | Systems with specific transparency duties | Chatbots interacting with people; AI-generated or manipulated content; emotion recognition in some contexts | Disclose AI interaction; label synthetic content |
| Minimal risk | Everything else | Spam filters, internal drafting aids | Voluntary codes; general law still applies |
| General-purpose AI models | Separate obligations for model providers; additional for systemic-risk models | Foundation model providers | Mostly provider-side; deployers inherit documentation needs |

Deployer vs provider: an organization that builds on a vendor model and puts a system into service in its own name may carry deployer obligations and, in some configurations, provider obligations. Flag this for counsel when the system is customized substantially or re-branded.

Tiering questions for the review:
1. Does the system make or materially influence decisions in employment, education, credit, essential services, or law enforcement? → likely high-risk.
2. Do people interact with it without knowing it is AI? → transparency duty.
3. Does it generate content presented to the public? → labeling duty.
4. Is it purely internal productivity with human review? → minimal, with general data-protection law still applying.

## Other regimes to name when applicable (confirm with counsel)
| Regime | Trigger |
|---|---|
| GDPR / UK GDPR and other data-protection laws | Personal data of residents; automated decision-making provisions; DPIA triggers |
| US state privacy and AI laws (e.g., Colorado AI Act, state consumer privacy laws) | Consumer-facing consequential decisions; state residents |
| Sector rules: FERPA (education records), HIPAA (health), GLBA/ECOA/FCRA (finance, credit), EEOC guidance (employment) | Sector data or decisions |
| ISO/IEC 42001 (AI management system) | When the organization wants certifiable governance |
| Contractual and procurement requirements | Client or vendor obligations on AI use |

Deliverable line (mandatory): "Summary mapping for planning purposes; legal review required to confirm obligations."
