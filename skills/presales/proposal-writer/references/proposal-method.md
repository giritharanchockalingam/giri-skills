# Proposal Method

## 1. Proposal shapes
| Shape | When | Emphasis | Pricing structure placeholder | Typical length |
|---|---|---|---|---|
| Assessment | Client needs a decision (migrate? which platform? how much?) before committing | Method, deliverables, decision criteria, speed | Fixed fee; `[TO BE BASELINED — owner: ___]` | 8–12 pages |
| Delivery | Scope is known; client wants it built or migrated | Approach, phases, team, quality, risk | Phase or milestone pricing; T&M with cap or fixed by wave | 20–40 pages |
| Managed service | Client wants run responsibility transferred | SLAs, operating model, transition, continuous improvement | Monthly run-rate with tiers; transition fee | 20–30 pages |
| Hybrid (assess → deliver → run) | Large modernization with unknowns | Gated phases; exit criteria per gate | Fixed assessment + estimated delivery range + indicative run-rate | 30–50 pages |

Decision rule: if discovery left the gaps list with volumes unknown, the first phase is an assessment regardless of what the client asked for. Price the assessment firmly and the rest as a range with named drivers.

## 2. Section intent (what each must achieve)
| Section | Must achieve | Fails when |
|---|---|---|
| Executive summary | Decision-maker can approve from this page alone | Starts with our history; no numbers; longer than a page |
| Understanding of needs | Client reads it and says "they listened" | Paraphrases the RFP back; no quotes, no numbers, no consequence |
| Objectives and success measures | Agreed definition of done | Vague outcomes ("improved efficiency") with no metric or baseline owner |
| Approach and methodology | Client sees the path and the gates | Generic methodology slide; no decision points; no exit criteria |
| Solution | Technical credibility for the architect reviewer | Product pitch; no fit to their estate; no NFRs |
| Scope and deliverables | No ambiguity about what is in and out | Deliverables without acceptance criteria; out-of-scope list missing |
| Timeline | Dates the client can plan around | Gantt without dependencies on the client; no freeze windows |
| Team and governance | Confidence the right people show up and decisions get made | Org chart without allocation percentages; escalation path missing |
| Risks and assumptions | Honest; every assumption a change-control trigger | Boilerplate risks; assumptions hidden in footnotes |
| Pricing | Clear structure, clear basis, clear exclusions | Numbers without basis; unclear what triggers change |
| Why us / proof | Evidence for each win theme | Logo wall; uncleared references; claims without numbers |
| Compliance appendix | Every mandatory requirement answered | Cross-references that do not resolve |

## 3. Evidence rules
| Claim type | Acceptable evidence | Not acceptable |
|---|---|---|
| Client situation | Their words (discovery quotes), their documents, their filings | Our assumption about their pain |
| Outcome commitment | Value case with sourced baseline; or outcome stated as hypothesis with baselining as phase-1 deliverable | Invented percentage improvement |
| Our capability | Cleared reference with outcome numbers; certification with scope; product feature | "Extensive experience"; uncleared client names |
| Effort/price | Estimate output (P50/P80), rate card | Round numbers chosen to look good |
| Timeline | Estimate critical path + client dependency dates | Dates picked to match the RFP without checking feasibility |

Reference clearance states: `cleared-named` · `cleared-anonymized` · `not-cleared`. Only the first two may appear; the matrix is internal.

## 4. Registers
### Risk register
| ID | Risk | Likelihood (H/M/L) | Impact (H/M/L) | Mitigation | Owner (ours / client) | Trigger / early signal |
|---|---|---|---|---|---|---|

Minimum coverage: client-side availability, data quality, environment access, third-party vendor dependency, scope growth, key-person, security/compliance approvals, cutover windows.

### Assumption register
| ID | Assumption | Basis (source) | If false → consequence | Change-control trigger (Y/N) | Owner to confirm |
|---|---|---|---|---|---|

Every quantity in the estimate (interface count, user count, environments, sites) is an assumption row.

## 5. Review gates
| Gate | When | Reviewer | Pass criteria |
|---|---|---|---|
| Pink (storyline) | After win themes and exec-summary outline | Pursuit lead | Themes proven; shape chosen; exec summary outline approved |
| Red (draft) | Full draft | Independent reviewer not on the writing team | Scores each section against §2; every number sourced; compliance cross-refs resolve |
| Gold (final) | After pricing and legal | Partner / sponsor | Price-to-win check; risk register signed; format compliance; submission checklist complete |

Red-team scoring per section (0–3): 0 missing · 1 generic · 2 specific but unproven · 3 specific, proven, in client's terms. Sections at ≤1 go back to the author.

## 6. Writing rules specific to proposals
- Client's name appears more often than ours. Count it.
- Each section opens with the "so what" for the evaluator, then the detail.
- Mirror the client's terminology (their program names, their KPI names, their org names). Do not rename their initiatives.
- Benefits precede features. "Cuts term-start incident recovery from days to hours by …" not "We use event-driven architecture".
- Active voice, present tense for approach, future tense for commitments.
- Avoid "we understand that" openers; state the fact and cite its source.
- Length: shorter beats longer at equal evidence. Evaluators score, they do not read.
