# AI Operating Models — central CoE, hub-and-spoke, federated

Pick the model from maturity and organizational breadth. The model is expected to change as maturity rises; say so in the roadmap.

## The three models
| Attribute | Central CoE | Hub-and-spoke | Federated |
|---|---|---|---|
| Who builds | CoE team builds and runs everything | CoE builds platform, standards, lighthouse cases; business "spokes" build on it | Business units build and run; a thin enablement group sets standards |
| Who owns outcomes | CoE (initially) | Business, with CoE co-ownership for lighthouses | Business |
| Platform | Owned by CoE | Owned by CoE (hub) | Shared services or per-BU |
| Governance | CoE gate on everything | Hub sets policy, spokes self-certify; hub audits | Policy council; BU risk owners |
| Speed to first value | Fast (focused team) | Medium | Slow at first, fast at scale |
| Scale ceiling | Low — the CoE becomes the bottleneck | High | High |
| Talent requirement | 1 strong team | Hub team + 1–3 AI-capable people per spoke | AI-capable people in every BU |
| Risk of shadow AI | Highest (BUs route around the gate) | Medium | Low if standards are strong, high if weak |

## When to choose
| Signal | Choose |
|---|---|
| Overall maturity 1–2; fewer than ~5 live use cases; talent concentrated in one team | **Central CoE** for 6–12 months, with an explicit transition plan to hub-and-spoke |
| Maturity 2–3; 3+ business units with distinct data and use cases; a platform exists or is funded | **Hub-and-spoke** (default for most mid-to-large enterprises) |
| Maturity 4+; BUs already employ AI engineers; strong data governance; regulated BUs need local risk ownership | **Federated** with a standards council |
| Highly regulated single business (e.g., one product line under one regulator) | Central CoE longer; federate only the consumer-facing layer |
| Holding company / conglomerate with unrelated businesses | Federated from the start; the hub is a standards and procurement function |

## Design decisions to state explicitly (for any model)
| Decision | Options | Recommendation rule |
|---|---|---|
| Reporting line of the CoE | CIO / CDO / COO / CEO staff | Where the data platform reports, unless the sponsor is elsewhere; never under a single BU |
| Funding | Central budget / chargeback / BU-funded | Central for platform and lighthouses; chargeback once consumption is metered (Platform level 4) |
| Intake | Open backlog / quarterly portfolio review / continuous | Quarterly review with a continuous fast lane for sub-threshold cases |
| Risk gate | CoE approves / BU self-certifies / tiered | Tiered: self-certify low-risk, CoE review medium, risk committee high |
| Build vs partner | In-house / SI / vendor product | Build what differentiates; buy commodity (document OCR, transcription); partner for surge capacity |

## Minimum CoE roles (hub-and-spoke, lean)
| Role | FTE guide | Note |
|---|---|---|
| CoE lead / head of AI | 1 | Owns roadmap and portfolio |
| AI platform engineer | 2–3 | Gateway, observability, CI/eval, cost |
| AI/agent engineer | 2–4 | Lighthouse builds, patterns, code review for spokes |
| Data engineer (liaison to data platform) | 1–2 | Data products for AI |
| AI product manager | 1 | Portfolio, baselines, value tracking |
| Risk / governance lead | 0.5–1 | Inventory, tiering, reviews; may sit in risk function |
| Enablement / change lead | 0.5–1 | Training, communities, adoption metrics |

FTE guides are structural, not a benchmark; size to portfolio and label as assumption in the deliverable.

## Transition triggers
| From → To | Trigger |
|---|---|
| Central → Hub-and-spoke | 2+ spokes have trained builders and the platform has self-service onboarding and eval gates |
| Hub-and-spoke → Federated | Value tracking is at level 4; governance controls are tested; spokes pass audits two quarters running |
| Any → Central (regression) | Serious incident, regulatory finding, or shadow-AI sprawl; temporary and time-boxed |
