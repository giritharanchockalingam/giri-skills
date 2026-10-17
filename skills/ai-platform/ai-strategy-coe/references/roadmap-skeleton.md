# 12-Month AI Roadmap Skeleton

Four quarters, five workstreams. Each quarter has an exit criterion; do not advance a workstream whose exit criterion failed. Dates, headcount, and spend are `[TO BE BASELINED — owner: ___]` until the sponsor confirms.

## Workstreams
| Workstream | Owner (role) | Measures |
|---|---|---|
| W1 Foundations (platform, gateway, observability, CI/eval) | AI platform lead | Gateway coverage %, eval gate in CI, cost per call visible |
| W2 Data readiness | Data platform lead | Domains productized, catalog coverage, PII classification % |
| W3 Use cases (lighthouse + fast lane) | AI product manager | Cases live, baseline vs realized value |
| W4 Governance & risk | Risk lead | Inventory complete, tiering applied, reviews on cadence |
| W5 Talent & adoption | Enablement lead | Builders trained, consumers active, communities running |

## Quarter plan
| Quarter | W1 Foundations | W2 Data | W3 Use cases | W4 Governance | W5 Talent | Exit criterion |
|---|---|---|---|---|---|---|
| Q1 | Model gateway with logging; dev/test/prod; secrets; one orchestration standard | Pick 2 priority domains; assign owners; classify PII | Select 2 lighthouse + 2 fast-lane cases; baselines signed off | Policy v1; intake form; risk tiers; model inventory started | Role definitions; builder cohort 1 (10–20 people); exec briefing | Gateway live; 4 cases with baselines; policy published |
| Q2 | Tracing, cost per call, eval harness in CI; prompt/model versioning | Domain 1 productized (owner, quality rules, access by role) | Lighthouse 1 in production with HITL; fast-lane cases live | First risk reviews; incident process; vendor terms reviewed | Cohort 2; office hours; AI translators named per function | 1 lighthouse in prod with measured value; eval gate blocks regressions |
| Q3 | Canary/rollback; spend limits per team; self-service onboarding | Domain 2 productized; vector/feature store governed | Lighthouse 2 live; 3–5 further cases through fast lane; first kill decision | Controls tested (bias, privacy, security); NIST AI RMF mapping | Career ladder; community of practice; adoption metrics reported | Portfolio review with realized value; spokes onboarded self-service |
| Q4 | Model routing policy (cost/quality); platform SLA | Data contracts in CI for both domains | Scale lighthouse 1 to adjacent function; portfolio re-scored | Audit evidence automated for high-risk cases; board report | Internal certification; FY+1 capability plan | Operating-model transition decision (central → hub-and-spoke) with evidence |

## Rules
1. Nothing scales before it is measured: W3 scale items require W1 eval gate and W3 baselines.
2. One lighthouse per quarter at most until Platform maturity ≥ 3.
3. Each quarter ends with a portfolio review: realized value, cost, risk findings, kill/continue decisions.
4. Dependencies are stated per item: "requires Q1 gateway", "requires domain 1 productized".
5. Headcount and spend lines live in the roadmap's assumption table, not in the body.

## Roadmap risks (starter list)
| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Lighthouse chosen for visibility, not data readiness | High | Slips 2 quarters | Enforce D ≥ 3 for Now cases | AI PM |
| Platform built before any consumer | Medium | Low adoption, cost overrun | Platform items gated by use-case pull | Platform lead |
| Governance perceived as blocker | Medium | Shadow AI | Tiered gate; self-certify low-risk in ≤5 days | Risk lead |
| Talent concentrated in CoE | High | Scale ceiling | Embedded engineers rotate to spokes in Q3 | CoE lead |
| Value not baselined | High | Program cannot defend budget at FY+1 | No baseline, no build | Sponsor |
