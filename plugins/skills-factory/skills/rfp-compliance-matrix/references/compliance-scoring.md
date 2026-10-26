# Compliance Scoring

## 1. Levels
| Code | Level | Rule | Evidence required |
|---|---|---|---|
| C | Comply | We meet the requirement as written today, with no caveat | Cite one of: a named capability in our catalog, a certification (with expiry), a delivered project of the same shape (internal reference ID only; never the client name in the matrix unless cleared), a product feature |
| P | Partial | We meet part of it, or meet it with a condition, a partner, or a roadmap commitment | State exactly what is met, what is not, and the mitigation |
| N | Non-comply | We do not meet it and no credible mitigation exists within the response window | State why and whether an exception will be requested |
| Q | Clarify | The requirement is ambiguous, conflicting, or depends on information we do not have | Clarification question ID |

Rules that prevent optimistic scoring:
- A `C` with the evidence cell empty is a `P`. The reviewer changes it; the author does not argue.
- "We can build it" is a `P` with mitigation "custom build — estimated in pricing", not a `C`.
- Certifications count only if current and in the correct scope (entity, region, service).
- A partner's capability is `P` until the partner has confirmed in writing; then `C` with the partner named as evidence.
- Commercial terms: `N` on "accept T&Cs without exception" if legal has any redline. Record redlines as the mitigation.

## 2. Row fields added by scoring
| Field | Description |
|---|---|
| Compliance | C / P / N / Q |
| Evidence | Cited item (catalog ref, cert, project ref, product feature) |
| Gap / condition | For P and N: what is missing |
| Mitigation | Partner · roadmap · custom build · exception request · alternative approach |
| Owner | Named person responsible for the response text |
| Response section | Where in the proposal the answer lives (section number) |
| Status | Not started · Drafted · Reviewed · Final |
| Clarification ID | CQ-nnn for Q rows |

## 3. Bid / no-bid gate
Compute after scoring. State the call on line 1 of the bid review.

| Test | BID | BID-WITH-CONDITIONS | NO-BID |
|---|---|---|---|
| Mandatory `N` count | 0 | 1–2, each with a credible clarification or exception path | ≥1 with no path |
| Mandatory `C` share | ≥ 80% | 60–79% | < 60% |
| Hidden mandatories (qualification thresholds, certifications, T&Cs) | All met | One open, resolvable before Q&A deadline | Any unmet |
| Deadline feasibility | Response effort ≤ 70% of available owner-days | 70–100% | > 100% |
| Evaluation weighting known | Yes | Clarification sent | Unknown and price-dominant with an incumbent |
| Incumbent signal (INC flags) | None or few | Several, wedge identified | RFP reads as written for the incumbent and no wedge |
| Strategic fit (our angle, vertical, reference value) | Strong | Moderate | Weak |

Decision rule: any NO-BID column hit on Mandatory N, Hidden mandatories, or Deadline feasibility → NO-BID. Two or more CONDITIONS → BID-WITH-CONDITIONS, conditions listed with owner and date.

Response effort estimate: `sections × average hours per section (default 6 for narrative, 2 for tabular) + 20% review`. Compare with owner availability stated by the user. If availability is unknown, mark `[TO BE BASELINED — owner: ___]` and flag feasibility as unassessed.

## 4. Clarification-question format
Questions are read by the client and often by competitors (answers are typically shared with all bidders). Write accordingly.

| Rule | Why |
|---|---|
| One question per item, referencing the clause ID | Traceability; forces a specific answer |
| Neutral wording; ask for the client's intent, not confirmation of our approach | Do not reveal gaps or strategy |
| Never ask something answered elsewhere in the RFP | Signals poor reading; wastes a question slot |
| Prefer questions whose answers change scope, price, or compliance | Slots are limited |
| Ask for scoring criteria and weights if absent | Shapes the whole response |
| Ask for volumes and counts whenever a requirement is unquantified | Feeds the estimate |

Template: `CQ-nnn | Clause <id> (p. <n>) | "<Question>" | Why it matters to us (internal) | Scope/price impact (internal)`

Examples of good wording:
- "Clause 4.3.2 references 'all existing integrations'. Can the Authority provide the count and list of integrations in scope, by system?"
- "Section 7 states data must reside in-region. Does this apply to backup and disaster-recovery copies as well as primary storage?"
- "Please confirm whether the evaluation applies weighted scoring, and if so, the relative weights of technical, commercial, and delivery criteria."

Examples of bad wording:
- "Would a solution based on <our platform> be acceptable?" (reveals approach)
- "Is SOC 2 Type I sufficient?" (reveals we lack Type II)

## 5. Bid review summary layout
1. Bottom line: `BID / BID-WITH-CONDITIONS / NO-BID` + three drivers.
2. Totals: table by category × compliance level; mandatory subset shown separately.
3. Mandatory non-compliances and partials: ID, text, gap, mitigation, owner.
4. Gaps and risks: full list.
5. Clarification questions: ordered by scope/price impact.
6. Response plan: section, owner, draft due, review due.
7. Administrative checklist: format, forms, signatures, references, delivery method, deadlines with page references.
