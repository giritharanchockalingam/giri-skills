# PRD Method (fallback for product-management:write-spec)

## 1. Frame (one round of questions, each with a default)
| Question | Why it matters | Default if unanswered |
|---|---|---|
| What problem, for whom, observed how? | prevents solution-first PRDs | mark evidence as assumption |
| What happens if we do nothing? | tests urgency | "status quo acceptable for 1 quarter" |
| What metric moves, from what baseline, to what target, by when? | defines success | baseline `[TO BE BASELINED]`; target = relative (+20%) |
| Who is explicitly not served in v1? | forces non-goals | all personas not named |
| What constraints are fixed? (date, platform, compliance, budget) | shapes phasing | none |

## 2. Scoping rules
| Rule | Practice |
|---|---|
| v1 = smallest slice that moves the metric for the primary persona | cut anything that serves a secondary persona or a secondary metric |
| Non-goals are written as "will not …" with the reason and the phase it may return | ≥ 3 |
| Phases: v1 (ship), v1.1 (fast follow ≤ 4 weeks), later (needs new evidence) | each phase lists its own criteria |
| One PRD = one outcome | two outcomes → two PRDs |
| Dependencies named with owner | integration, data, legal, design |

## 3. User stories
`As a <persona>, I want <capability> so that <outcome>.`
Acceptance criteria per story (Given / When / Then), binary, testable; include the negative/permission case for anything tenant- or role-sensitive.

## 4. Metrics
| Type | Example | Instrumentation |
|---|---|---|
| Outcome (primary, 1) | export adoption: % of active tenants exporting ≥1/month | log event `action=invoice.export outcome=ok` grouped by tenant |
| Leading (≤ 2) | time-to-first-export after enabling | event timestamps |
| Guardrail (≤ 2) | p95 export latency < 5 s; support tickets on exports not up | logs; support tag |

Every metric: name, definition, source, baseline (sourced or TBD with owner), target, review date.

## 5. Risks and open questions
Risk table: risk, likelihood, impact, mitigation, owner. Open questions: question, owner, due date, decision default if unanswered by then.

## 6. Writing
Follow `shared/writing-style.md`: assertions as headings, ≤ 20-word sentences, tables for 3+ items, no banned words, no hedging in the recommendation.
