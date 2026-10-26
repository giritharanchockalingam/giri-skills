# Architecture Method

## 1. Depth by audience
| Audience | Views | NFR depth | ADRs | Length |
|---|---|---|---|---|
| CIO / steering committee | Context, container, wave plan | Top 6 NFRs as a table | Top 3 decisions summarized; index to the rest | 6–10 pages |
| Architecture review board | + component (critical containers), deployment, security, data | Full checklist | All, with alternatives | 15–30 pages |
| Delivery team | + sequence diagrams for critical flows, environment matrix, interface specs by reference | Full + test approach per NFR | All | As needed |

Produce the CIO version first; the ARB version extends it. Never produce ARB depth for a CIO audience.

## 2. Current-state evidence rules
| Rule | Practice |
|---|---|
| Source every box | Tag each system/container with `[src: doc/slide/interview]` |
| Draw only what is evidenced | Unknown integrations are dashed with `?`; listed in a gaps table with the client owner who can confirm |
| No inferred products | If the discovery said "an ESB", draw "ESB `[TO BE BASELINED — owner: ___]`", not a product name |
| Invite correction | Caption: "Baseline from <sources>; to be validated with <client role> on <date>" |
| Count what you can | Interface counts, environments, regions — from inventory; otherwise marked |

## 3. Option scoring
Criteria and default weights; adjust weights to the client's stated drivers and show the adjustment.
| Criterion | Weight (default) | 1 | 3 | 5 |
|---|---|---|---|---|
| Fit to drivers (objectives, constraints) | 25 | Meets few | Meets most | Meets all incl. constraints |
| Delivery risk | 20 | Big-bang, unproven in this estate | Phased with some unknowns | Incremental, reversible, proven patterns |
| Cost shape (capex/opex, run-rate direction) | 15 | Raises run-rate | Neutral | Lowers run-rate; fits budget shape |
| Time to first value | 15 | > 12 months | 6–12 months | < 6 months |
| Operability (skills, observability, support) | 15 | New skills, thin tooling | Partial | Existing skills, mature tooling |
| Lock-in / exit | 10 | Proprietary, hard to exit | Moderate | Open standards, portable |

Score table: `Option | per-criterion score × weight | Total | Key risk | Key benefit`. The recommendation references the table; the ADR records it. If two options score within 10%, say so and name the deciding qualitative factor.

Typical option sets:
| Decision | Options |
|---|---|
| Migration approach | Strangler by wave · Big-bang cutover · Hybrid (core big-bang, periphery strangler) |
| API layer | Single gateway · Federated gateways by domain · Gateway + service mesh |
| Integration style | Sync REST/GraphQL · Event backbone (Kafka/pub-sub) · Hybrid by interaction type |
| Hosting | Single cloud · Multi-cloud by workload · On-prem + cloud burst |
| Identity | Central IdP with federation · Per-platform · Hybrid with brokered SSO |
| Data integration | ELT to warehouse · CDC streaming · Virtualization |

## 4. Views
| View | Shows | Mermaid template |
|---|---|---|
| Context (C1) | System, users, external systems | `C4Context` |
| Container (C2) | Deployable units, data stores, protocols | `C4Container` |
| Component (C3) | Inside a critical container | `C4Component` |
| Deployment | Environments, regions, zones, scaling | `C4Deployment` |
| Integration map | Table + optional flow diagram | `flowchart` |
| Critical flows | Sequence of calls for 2–3 key journeys | `sequenceDiagram` |
| Security | Trust boundaries, identity flows, secrets, data classes | Annotated container view |

Every diagram: title, caption (what it shows and as-of date), legend if non-standard notation.

## 5. Migration wave planning
| Step | Rule |
|---|---|
| Wave criteria | Dependency order (foundations first), risk (low-risk early to prove the pattern, highest-risk in a middle wave with max attention, never last), business value, freeze windows, team ramp |
| Wave 0 | Platform foundation: landing zone, CI/CD, observability, security baseline, reference implementation, test harness. No business interfaces |
| Wave 1 | 10–20% of scope, low-complexity, representative of patterns; proves the factory |
| Middle waves | Balanced by complexity; dependencies resolved within or before the wave |
| Final wave | Long-tail and deprecations; legacy decommission |
| Per wave | Scope list (IDs), entry criteria, exit criteria, rollback approach, parallel-run period, cutover window, hypercare |
| Decommission | Explicit tasks and dates; licensing savings only after decommission |

Wave table: `Wave | Scope (IDs, count) | Complexity mix | Dependencies | Entry criteria | Exit criteria | Rollback | Window`.

## 6. Decision log
Significant decisions get an ADR; the document carries an index: `ADR | Title | Status (proposed/accepted/superseded) | Owner | Date | Impact`. Decisions the client must make stay `proposed` with the client owner named and a decision-by date; they feed the dependency register in the SOW.

## 7. Security, data, operability minimums (any audience)
| Area | Minimum content |
|---|---|
| Identity and access | IdP, protocols (OIDC/SAML/OAuth2), service identity, RBAC model, admin access path |
| Data | Classification levels, residency, encryption at rest/in transit, retention, PII handling, backup and DR (RPO/RTO) |
| Secrets | Vault/KMS, rotation, no secrets in code or config repos |
| Observability | Logs, metrics, traces; correlation ID; dashboards; alert routing; SLO reporting |
| Environments | Dev/test/UAT/perf/prod; promotion path; data masking; IaC |
| Resilience | Failure modes per container, retries, circuit breakers, idempotency, DLQ for async |
