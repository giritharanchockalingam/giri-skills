# Question Bank — Manufacturing

Scope: discrete and process manufacturers, industrial equipment, food and beverage, automotive tier suppliers, energy equipment. Buyer personas: CIO, VP Operations, VP Supply Chain, Plant Director, Head of Quality, CFO, Head of Engineering / PLM, Head of Digital / Industry 4.0.

## Typical pains (hypothesis seeds)
| Area | Pattern seen repeatedly | Usually owned by |
|---|---|---|
| ERP–MES–shop floor integration | Plants on different MES/ERP instances; production data reaches ERP late; manual production confirmations | VP Ops / CIO |
| Supply chain visibility | Supplier delays discovered at receipt; multi-tier visibility absent; expedites | VP Supply Chain |
| Transportation and logistics | Inbound/outbound freight managed by spreadsheet and email; carrier compliance; TMS underused | VP Supply Chain / Logistics Director |
| Quality and traceability | Non-conformance tracked manually; recall traceability slow; audit prep heavy | Head of Quality |
| Plant modernization | Legacy OT, unsupported HMIs, network segmentation gaps; IT/OT ownership unclear | Plant Director / CISO |
| Data and analytics | OEE calculated differently per plant; no trusted enterprise view | Head of Digital |
| Engineering handoff | PLM to ERP BOM sync manual; change orders lag production | Head of Engineering |
| Integration platform | Aging middleware; license cost; point-to-point sprawl between plants and corporate | CIO / VP Apps |
| AI | Predictive maintenance and demand pilots stuck in POC; data quality blocks scale | Head of Digital |

## Questions by funnel stage
### Situation
| # | Question | Persona | Listen for |
|---|---|---|---|
| M1 | Walk me through an order from customer PO to shipment — which systems and which plants touch it, and where does someone re-enter data? | VP Ops | Integration hops, plant variance |
| M2 | How many plants, ERP instances, and MES platforms, and how standardized are they? | CIO | Heterogeneity drives estimate |
| M3 | How do production results get from the shop floor to ERP — automated, batch, or clerk entry? | Plant Director | Latency, manual confirmation |
| M4 | How is inbound and outbound transportation planned and tracked today? | Logistics Director | TMS presence, carrier integration |

### Pain
| # | Question | Persona | Listen for |
|---|---|---|---|
| M5 | What was the last production disruption caused by a system or data failure, and how long did it take to recover? | VP Ops | Downtime, recovery effort |
| M6 | Where do you find out about supplier problems too late, and what do you do about it? | VP Supply Chain | Expedites, safety stock |
| M7 | What does a recall or customer quality audit look like in effort and elapsed time? | Head of Quality | Traceability gaps |
| M8 | Which plant's numbers does corporate trust least, and why? | Head of Digital / CFO | Data standardization |
| M9 | What happens when engineering releases a change — how long until production builds to it? | Head of Engineering | PLM–ERP sync |

### Impact
| # | Question | Persona | Listen for |
|---|---|---|---|
| M10 | What did the last disruption cost in lost output, overtime, and expedited freight? Is that from an incident review? | CFO / VP Ops | Figure and source |
| M11 | What is your annual expedite spend, and what share is avoidable with earlier visibility? | VP Supply Chain | Value lever |
| M12 | How many FTEs across plants do manual data entry or reconciliation between shop floor and ERP? | VP Ops | Labor baseline |
| M13 | What is the run cost of current middleware and the team maintaining plant interfaces? | CIO | Migration TCO baseline |
| M14 | What is a point of OEE worth at your largest plant? | Plant Director / CFO | Business-case lever |

### Urgency
| # | Question | Persona | Listen for |
|---|---|---|---|
| M15 | Is there an ERP upgrade, plant opening, acquisition integration, or platform end-of-support driving a date? | CIO | Forcing event |
| M16 | What has the board or CEO committed to publicly on operations, cost, or digital? | CFO | Executive commitment |

### Decision and constraints
| # | Question | Persona | Listen for |
|---|---|---|---|
| M17 | Is this an IT decision, an operations decision, or shared — and who breaks a tie? | CIO / VP Ops | Decision owner |
| M18 | Which constraints apply — OT network isolation, union work rules, customer quality standards (IATF, FDA, ISO), export controls? | CISO / Head of Quality | Hard gates |
| M19 | Where is your team's capacity — can plant SMEs be freed during the engagement, and when are the plant shutdown windows? | VP Ops | Availability, change windows |
| M20 | What has stopped previous Industry 4.0 or AI pilots from scaling? | Head of Digital | Data readiness, ownership, funding |

## Branch table
| If they say | Go to |
|---|---|
| "Every plant is different." | M2, M8; standardization is the first deliverable; size for a pilot plant |
| "We're moving to S/4 (or another ERP)." | M1, M13, M15; integration re-platform rides the ERP program |
| "Logistics is killing us." | M4, M6, M11; transportation visibility and carrier integration play |
| "We have a data lake but nobody uses it." | M8, M20; governance and trust before AI |

## Pre-reads worth requesting
Plant and system landscape map, interface inventory, last incident review, expedite and freight spend summary, ERP program timeline, OT/IT segmentation policy.
