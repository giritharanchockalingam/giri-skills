# Question Bank — Travel and Hospitality

Scope: travel management companies, online travel agencies, airlines, hotel groups, cruise and tour operators, corporate travel platforms. Buyer personas: CIO, CTO, Chief Product Officer, VP Operations, VP Customer Service, CFO, Head of Data, Head of Distribution.

## Typical pains (hypothesis seeds)
| Area | Pattern seen repeatedly | Usually owned by |
|---|---|---|
| Booking and content integration | GDS, NDC, direct-connect, hotel aggregators, rail, car; content fragmentation; connector maintenance burden | Head of Distribution / CTO |
| Disruption management | Irregular operations handled manually; rebooking volume spikes; customer comms lag | VP Ops / VP Customer Service |
| Customer service scale | Contact-center cost per transaction high; bots shallow; agents toggle many systems | VP Customer Service |
| Mid-office and back-office | Ticketing, invoicing, reconciliation, duty-of-care reporting manual; commission leakage | CFO / VP Ops |
| Legacy core | Aging booking engines, mainframe or monolithic PSS/CRS; expensive change | CIO / CTO |
| Data | Traveler profile scattered; personalization and policy compliance hampered | Head of Data / CPO |
| Partner and API platform | B2B partner onboarding slow; API gateway gaps; rate-limit and SLA incidents | CTO |
| Seasonality and resilience | Peak-travel outages; scaling cost | CTO |
| AI | Pressure for agentic booking/servicing assistants; risk on accuracy and fare rules | CPO / CTO |

## Questions by funnel stage
### Situation
| # | Question | Persona | Listen for |
|---|---|---|---|
| T1 | Walk me through a booking that gets disrupted — from the schedule change to the traveler being re-accommodated and invoiced. Which systems and which humans touch it? | VP Ops | Manual steps, latency, system count |
| T2 | Which content sources and channels do you integrate (GDS, NDC, direct, aggregators), and who maintains those connectors? | Head of Distribution | Connector count, maintenance load |
| T3 | How many bookings per day at peak, and what is the ratio of self-service to agent-assisted? | CTO / VP CS | Scale, servicing mix |
| T4 | Which platforms are near contract end or end-of-support in the next 24 months? | CIO | Forcing events |

### Pain
| # | Question | Persona | Listen for |
|---|---|---|---|
| T5 | What happened during the last major disruption event — how did volumes, handle times, and customer complaints move? | VP CS | Incident pattern, cost |
| T6 | When a supplier changes an API or a GDS releases a new version, how long does it take you to adapt and what breaks? | CTO | Change cost, fragility |
| T7 | Where does revenue leak — unclaimed commissions, unused tickets, refund reconciliation? | CFO | Mid/back-office gaps |
| T8 | What do agents complain about most in their desktop? How many systems do they open for one case? | VP CS | Agent productivity |
| T9 | Which partner onboarding took longest last year, and why? | CTO / Head of Distribution | API platform maturity |

### Impact
| # | Question | Persona | Listen for |
|---|---|---|---|
| T10 | What did the last disruption event cost in overtime, compensation, and lost bookings? Is that from a post-event review? | CFO / VP Ops | Figure and source |
| T11 | What is your cost per serviced transaction, and what share could move to self-service or automation? | VP CS / CFO | Value lever |
| T12 | How much revenue is lost or delayed to reconciliation and commission leakage annually? | CFO | Back-office value |
| T13 | What is the run cost of maintaining connectors and the integration estate today? | CTO | Migration TCO baseline |

### Urgency
| # | Question | Persona | Listen for |
|---|---|---|---|
| T14 | Which date matters — a peak season, a supplier mandate (e.g., NDC cut-over), a platform renewal, a new market launch? | CTO / CIO | Forcing event |
| T15 | What has leadership committed to customers or the board on servicing or digital this year? | CPO | Executive commitment |

### Decision and constraints
| # | Question | Persona | Listen for |
|---|---|---|---|
| T16 | Who decides — Technology, Product, or Operations — and how are priorities set between them? | CIO / CPO | Decision owner |
| T17 | Is budget tied to a transformation program or to run-cost reduction? | CFO | Funding shape |
| T18 | PCI, GDPR and regional privacy, duty-of-care obligations, accessibility — which gates apply to a partner? | CISO / Counsel | Hard gates |
| T19 | How much of the work can your teams carry, and what are your change-freeze windows around peak? | CTO | Capacity, calendar |
| T20 | Where do you stand on AI handling customer-facing booking or servicing — policy, pilots, red lines? | CPO | AI readiness |

## Branch table
| If they say | Go to |
|---|---|
| "NDC is forcing our hand." | T2, T6, T14; supplier-mandate urgency; integration and content play |
| "Servicing cost is the issue." | T5, T8, T11, T20; agent desktop and automation play |
| "Our core is 20 years old." | T4, T6, T13; modernization and strangler-pattern play |
| "We tried a chatbot; customers hated it." | T8, T20; ask what it could not do; agentic assistant with fare-rule grounding |

## Pre-reads worth requesting
Connector and interface inventory, last disruption post-event review, contact-center KPIs (AHT, CPT, containment), platform contract end dates, partner onboarding backlog.
