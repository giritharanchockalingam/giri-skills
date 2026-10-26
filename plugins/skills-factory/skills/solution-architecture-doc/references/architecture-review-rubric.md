# Architecture Review Rubric

Score each criterion 0–3. Anything at ≤1 is a `[SHARPEN]` or `[ADD]` finding with rewritten content. Report the scored table first, then findings in document order.

| # | Criterion | 0 | 1 | 2 | 3 |
|---|---|---|---|---|---|
| 1 | Drivers stated and traceable | Absent | Generic ("modernize") | Specific, unsourced | Specific, sourced, each mapped to a design decision |
| 2 | Current state evidenced | Absent or invented | Diagram without sources | Sourced, gaps unmarked | Sourced, gaps marked with owners |
| 3 | Options considered | Single option | Options named, not scored | Scored, weights unexplained | Scored against weighted criteria tied to drivers |
| 4 | Target-state clarity | No diagram | Diagram without technology or responsibility | Clear containers and protocols | + ownership, data stores, trust boundaries |
| 5 | Integration map | Absent | List without patterns | Patterns and protocols | + volumes, SLAs, owners, waves (sourced or marked) |
| 6 | NFRs measurable | Absent | Adjectives | Targets without measurement method | Targets, method, source, design response |
| 7 | Decisions logged | None | Implicit in prose | ADRs without alternatives | ADRs with alternatives, consequences, owners, status |
| 8 | Migration plan | None | Phases without criteria | Waves with scope | + entry/exit, rollback, parallel run, decommission |
| 9 | Security and data | Absent | Mentioned | Identity and encryption covered | + classification, residency, secrets, DR with RPO/RTO |
| 10 | Operability | Absent | "Monitoring will be in place" | Tooling named | + SLOs, alert routing, environments and promotion, IaC |
| 11 | Numbers discipline | Invented figures | Unsourced figures | Mostly sourced | All sourced or `[TO BE BASELINED — owner: ___]` |
| 12 | Audience fit | Wrong depth | Mixed depth | Right depth, uneven | Right depth throughout; exec summary stands alone |
| 13 | Diagram quality | Do not render | Render, no captions | Captions | + legends, as-of dates, consistent naming with text |
| 14 | Risks and open items | Absent | Listed | With mitigations | With likelihood, impact, mitigation, owner, date |

## Common findings and rewrites
| Finding | Rewrite pattern |
|---|---|
| "The solution will be highly available and scalable." | NFR rows: availability 99.9% monthly at gateway, excluding ≤4h planned; horizontal scaling to 2× peak (peak = `[TO BE BASELINED — owner: ___]`) within 10 minutes |
| "We recommend <product> as the integration platform." with no alternatives | Add options table and ADR with the two alternatives and the scoring; keep the recommendation |
| Current-state diagram with 30 named products from memory | Reduce to evidenced systems; dash the rest; add gaps table |
| "Migration will be done in phases." | Wave table with scope IDs, criteria, rollback |
| Security section listing controls without data classification | Add classification table and map controls to classes |
| Product names for undecided components | Replace with role names and `[TO BE BASELINED — owner: ___]` |

## Review output format
1. Scored rubric table (criterion, score, one-line reason).
2. Findings in document order: `Section | Verdict ([KEEP]/[SHARPEN]/[CUT]/[ADD]/[TBD]) | Reason | Rewritten content or action`.
3. Clean revised document.
4. Open items with owners.
