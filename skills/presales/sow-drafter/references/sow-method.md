# SOW Method

## 1. Purpose of the SOW
The proposal persuades; the SOW protects both parties. Everything in the SOW must be enforceable: numbered, bounded, testable, dated, owned. If a sentence cannot be the subject of a dispute, it does not belong.

## 2. Scope statements
Pattern: `S-nn | <Verb> <object> <boundary/quantity> <quality standard> <reference to appendix>`.

| Weak | Enforceable |
|---|---|
| "Migrate integrations to the new platform." | "S-03: Migrate the 42 interfaces listed in Appendix A from <platform X> to <platform Y>, including unit tests, integration tests against the client's UAT environment, and runbook entries per interface." |
| "Provide training." | "S-09: Deliver two 4-hour remote training sessions for up to 12 client developers on the platform operating model, with recorded sessions and slide decks delivered as D-11." |
| "Support go-live." | "S-12: Provide hypercare for 10 business days after each wave cutover, 08:00–18:00 client local time, with a named lead and a 2-hour response target for P1 issues." |

Out-of-scope mirror: for each S-nn where a reader could reasonably assume more, add `O-nn`. Standard O items: data cleansing, licenses, hardware/cloud consumption costs, third-party vendor fees, business process redesign, end-user training beyond stated sessions, environments provisioning, historical data migration unless listed, 24×7 support unless listed.

## 3. Scope-ambiguity scan
Run against every S-nn and D-nn. Register each hit with the resolution.
| Ambiguity | Question to resolve | Typical resolution |
|---|---|---|
| Unquantified noun ("the interfaces", "users", "reports") | How many, listed where? | Appendix list; count becomes an assumption and change trigger |
| "Including but not limited to" | What is the limit? | Remove the phrase; enumerate |
| Quality undefined ("production-ready", "best practice") | Which standard, tested how? | Reference the client's standard or ours by name; acceptance criterion |
| Environment unstated | Which environments, who provides them, by when? | Dependency with date |
| Time window unstated ("support", "hypercare") | Hours, days, response targets? | Explicit window and targets |
| Owner unstated ("will be reviewed") | By whom, in how many days? | Approver role and review window |
| Reuse implied ("existing assets") | Which assets, who owns them, licensed how? | IP clause reference; appendix |
| Dependency implied ("once access is granted") | By whom, by when, consequence? | Dependency register |

## 4. Deliverables vs activities
Deliverables are things that can be accepted; activities are work. Only deliverables carry acceptance and payment. Each deliverable row: `D-nn | Name | Description | Format | Acceptance criteria | Acceptance method | Review window | Approver | Deemed-acceptance rule | Milestone`.

Deemed acceptance: "If the client does not provide written acceptance or a documented, material deficiency list within <n> business days of delivery, the deliverable is deemed accepted." Material deficiency = failure against a stated acceptance criterion, not a preference.

## 5. Commercial linkage
| Model | Payment trigger | What the SOW must contain | Risk held by |
|---|---|---|---|
| Fixed price | Accepted milestone | Milestone table with deliverables per milestone, percentage schedule, acceptance rules; assumptions as change triggers | Supplier (scope), client (dependencies) |
| T&M | Monthly approved timesheets | Rate card by role, not-to-exceed, estimate as guidance, change control for NTE increase | Client |
| Milestone T&M (hybrid) | Monthly actuals capped per milestone | Both of the above | Shared |
| Run-rate / managed service | Monthly fee | Service catalog, SLAs, service credits, baseline volumes, volume bands, transition plan | Supplier (SLA), client (volume) |

All amounts: from the proposal pricing or estimate, cited by section; otherwise `[TO BE BASELINED — owner: ___]`. Rate cards referenced from `effort-estimator`'s rate-card file by name, never retyped.

## 6. Assumptions and dependencies
Assumption pattern: `A-nn | Statement | Basis (source) | If false: effort / schedule / price impact | Change control trigger: Y | Confirmed by (client role) by (date)`.
Dependency pattern: `DEP-nn | Client provides <what> | By <date or "T-n days before milestone"> | Consequence of delay: <day-for-day shift / re-plan / change request>`.

Rule: every number in the estimate is an assumption. Every item the client must provide is a dependency with a date.

## 7. Governance
| Forum | Cadence | Attendees | Decisions | Escalation |
|---|---|---|---|---|
| Daily stand-up | Daily | Delivery team | Blockers | Delivery lead |
| Project status | Weekly | PM both sides, workstream leads | Risks, issues, change requests < threshold | Engagement manager ↔ client PMO |
| Steering committee | Monthly or per gate | Sponsor, engagement partner, PMs | Gates, change requests ≥ threshold, priority conflicts | Executive sponsor both sides |

RACI: one A per deliverable; R may be several; C and I by role. Client roles with `[TO BE BASELINED — owner: ___]` if not named.

## 8. Change control
| Step | Content |
|---|---|
| Request | Either party; written; CR-nn; description, reason |
| Impact assessment | Supplier within 5 business days: effort, schedule, price, risk, affected deliverables |
| Approval | Below threshold (e.g., ≤ 2 person-days and no price change): PMs; above: steering committee; price changes: signatory authority per MSA |
| Documentation | Signed CR appended; baseline updated; assumptions register updated |
| Minor change | Clarifications with no effort/schedule/price impact: recorded in status report, no CR |

## 9. Legal flags (do not draft)
IP ownership and license-back of pre-existing materials · limitation of liability and caps · warranties and remedy period · termination for convenience and fees · data protection and processing roles · confidentiality · non-solicitation · insurance · export control · dispute resolution · order of precedence (MSA vs SOW). List each with the MSA clause reference and "confirm with counsel".
