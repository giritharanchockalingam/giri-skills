# Acceptance-Criteria Patterns

Acceptance criteria are objective, testable, and tied to the deliverable. "Client satisfaction" is not a criterion. Use the pattern for the deliverable type; combine where needed.

## 1. Document deliverables (assessment report, architecture, plan, runbook)
| Criterion type | Pattern | Example |
|---|---|---|
| Completeness | Contains sections listed in Appendix <n> | "Contains all 9 sections of the target-architecture outline in Appendix D" |
| Traceability | Every <item> maps to <source> | "Every migration wave lists its interfaces by ID from the inventory in Appendix A" |
| Review | Reviewed by <role>; comments resolved or logged | "Reviewed by the client Enterprise Architect; all comments classified material/non-material; material comments resolved" |
| Format | Delivered as <format> in <repository> | "Delivered as PDF and Markdown in the client's project SharePoint" |

Acceptance method: review. Window: 5–10 business days. Deemed acceptance applies.

## 2. Software / integration deliverables (interfaces, services, components)
| Criterion type | Pattern | Example |
|---|---|---|
| Functional | Passes test cases in <test plan> with <threshold> | "Passes 100% of P1 and ≥95% of P2 test cases in the wave test plan; no open P1 defects" |
| Non-functional | Meets NFR-nn under <test> | "Sustains 200 requests/second with p95 latency ≤ 400 ms for 30 minutes in the client UAT environment (NFR-04)" |
| Parallel run | Output parity with legacy for <period> | "Produces identical outputs to the legacy interface for 5 consecutive business days of parallel run, variance log reviewed and signed" |
| Operability | Monitoring, alerts, runbook in place | "Dashboards and alert rules deployed; runbook entry delivered per interface" |
| Code quality | Static analysis and review gate | "No critical or high findings in <tool>; peer review recorded in the repository" |
| Security | Scan results | "No critical/high vulnerabilities in dependency and container scans at delivery date" |

Acceptance method: test execution witnessed or evidence package. Window: 5 business days after evidence delivery.

## 3. Migration / cutover deliverables (wave cutover, data migration)
| Criterion type | Pattern | Example |
|---|---|---|
| Cutover completion | <n> interfaces live, legacy disabled, rollback not invoked within <period> | "All 12 wave-2 interfaces live in production; legacy routes disabled; no rollback within 10 business days" |
| Data reconciliation | Record counts and control totals match within <tolerance> | "Migrated record counts match source 100%; control totals match within 0.01%" |
| Stability | Incident threshold during hypercare | "No P1 incidents attributable to migrated interfaces during the 10-day hypercare window; P2 incidents resolved within SLA" |

Acceptance method: cutover report with evidence. Window: hypercare period + 3 business days.

## 4. Service / run deliverables (managed service months)
| Criterion type | Pattern | Example |
|---|---|---|
| SLA attainment | Monthly service report shows SLAs met or credits applied | "Monthly report delivered by the 5th business day; SLA table per Appendix F; credits computed per schedule" |
| Volume bands | Actual volumes within contracted band or change request raised | "Transaction volume within Band B; above Band B triggers CR per clause 9" |

Acceptance method: monthly report review. Window: 5 business days.

## 5. Training and knowledge transfer
| Criterion type | Pattern | Example |
|---|---|---|
| Delivery | Sessions delivered, attendance recorded | "Two sessions delivered; attendance sheet signed; recordings and materials in repository" |
| Competency (optional) | Participants complete exercise | "At least 80% of participants complete the hands-on lab" |

## 6. Assessment and advisory outputs (recommendation, roadmap, business case)
| Criterion type | Pattern | Example |
|---|---|---|
| Decision readiness | Contains options, criteria, recommendation, costs with basis | "Presents ≥2 options scored against the agreed criteria (Appendix E), a recommendation, and cost ranges with stated assumptions" |
| Baseline sourced | Every baseline figure sourced or marked | "Every baseline figure carries a source or a `[TO BE BASELINED — owner: ___]` marker agreed with the sponsor" |
| Presentation | Presented to steering committee | "Presented at steering committee; decisions and actions minuted" |

## 7. Anti-patterns
| Avoid | Because | Replace with |
|---|---|---|
| "To the client's satisfaction" | Subjective; unlimited rework | Objective criteria above |
| "Industry best practice" | Undefined | Named standard, version |
| "Fully tested" | Undefined threshold | Test-plan pass rates and open-defect limits |
| "Production-ready" | Undefined | NFR pass + operability + security criteria |
| Criteria that depend on a client action without a dependency row | Supplier cannot control acceptance | Add DEP-nn with date and consequence |
