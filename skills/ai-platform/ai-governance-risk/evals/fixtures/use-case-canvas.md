# AI Use-Case Canvas — Benefits enquiry assistant — 2026-10-01

**Verdict:** Proceed to design
**Next 30-day step:** pull 200 historical enquiries and label 50 with HR SME — owner: HR Ops Lead — by: 2026-10-31

| # | Box | Content |
|---|---|---|
| 1 | Problem and user | HR service-desk agents answer repetitive benefits enquiries from employees; 900/month, 12 min each (fictional Northwind HR) |
| 2 | Decision or task affected | Which policy clause applies and what the employee should do next; the agent sends the reply |
| 3 | Current process and baseline | Volume: 900/mo; time/unit: 12 min; error/cost: [TO BE BASELINED — owner: HR Ops Lead] |
| 4 | Proposed AI capability | Pattern: retrieve-and-answer; autonomy: draft |
| 5 | Data | Sources: HR policy library (SharePoint); owner: HR Ops Lead; access: role-based; sensitivity: PII (employee records, special categories possible); freshness: quarterly |
| 6 | Feasibility | Known pattern: y; integrations exist: y; team: y; eval definable: y |
| 7 | Value hypothesis | Type: cost; mechanism: cuts handling time per enquiry; estimate: assumption 12 -> 6 min; baseline signed by: HR Ops Lead |
| 8 | Risks and tier | Tier: medium; top risks: 1) privacy (employee records in prompts) 2) hallucination (wrong policy clause) 3) transparency (employee unaware a draft is AI-generated) |
| 9 | Build / buy / partner | Decision: build on platform; factors: 1) data sensitivity 2) proprietary policy corpus; exit trigger: vendor HR suite ships equivalent |

| Axis | Score | Evidence |
|---|---|---|
| Value | 3 | baseline from HR ticket export |
| Feasibility | 4 | RAG pattern proven on IT policies |
| Data readiness | 3 | owner named; quality unknown |
| Risk | 3 | employee-facing with human in the loop; PII |
| Priority (V×F×D÷R) | 12.0 | |

Hand-off: ai-governance-risk
