# Build / Buy / Partner Decision Factors

Decide per capability layer, not per use case: model, platform (gateway, orchestration, evals), application, and integration are separate decisions.

## Factors
| Factor | Favors build | Favors buy (product/SaaS) | Favors partner (SI/vendor co-build) |
|---|---|---|---|
| Differentiation | Core to how the business competes; proprietary data or workflow | Commodity capability (OCR, transcription, generic chat) | Differentiating but team lacks capacity or skills now |
| Data sensitivity and residency | Data cannot leave the tenant; strict residency | Vendor meets requirements contractually | Partner works inside the tenant |
| Fit of available products | No product fits the workflow without heavy customization | A product fits ≥ 80% out of the box (assumption) | Product fits partly; partner closes the gap |
| Team capability | Platform and AI engineering in place; eval discipline | No AI engineering capacity; small team | Capacity gap is temporary; knowledge transfer planned |
| Time to value | Can tolerate a build cycle | Needed in weeks | Needed soon but must be owned later |
| Total cost at scale | High volume where per-seat/per-token SaaS pricing exceeds build + run | Low/variable volume | Mixed |
| Control and roadmap | Need to change behavior frequently; own the roadmap | Accept vendor roadmap | Shared roadmap for a defined period |
| Lock-in and exit | Open models and portable orchestration preferred | Acceptable with data export and exit terms | Contract defines IP and handover |
| Compliance evidence | Can produce own documentation and evals | Vendor supplies certifications and model documentation | Shared |
| Integration depth | Deep integration with systems of record | Shallow (API/plugin) | Deep, partner-delivered |

## Patterns
| Situation | Typical decision |
|---|---|
| Document extraction, transcription, translation | Buy the capability; build the workflow around it |
| Internal knowledge assistant on proprietary docs | Build on the platform (gateway + RAG) with open or API models; buy nothing beyond platform components |
| Customer-facing agent on a vendor's system of record (CRM, ITSM) | Evaluate the vendor's native AI first; build only where the workflow is differentiating |
| Agentic back-office workflow across several systems | Build on the orchestration standard; partner for surge |
| Regulated decision support | Build or partner with full documentation; avoid black-box SaaS without model documentation |

## Record the decision
| Item | Value |
|---|---|
| Layer(s) decided | model / platform / application / integration |
| Decision | build / buy / partner |
| Two strongest factors | |
| Exit or revisit trigger | |
| Owner | |
