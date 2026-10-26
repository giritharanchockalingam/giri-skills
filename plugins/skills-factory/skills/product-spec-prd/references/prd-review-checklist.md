# PRD Review Checklist (run before presenting)

| # | Check | Fail looks like | Fix |
|---|---|---|---|
| 1 | First line states outcome + metric | "This PRD describes…" | rewrite: "Tenant admins export invoices in one click; target: 40% of active tenants export monthly by Q3" |
| 2 | Problem has evidence or is labelled assumption | "Users want…" with no source | cite tickets/data or `[assumption]` |
| 3 | Exactly one primary metric with baseline + target + date | three "key metrics", no baseline | choose one; baseline `[TO BE BASELINED — owner]` |
| 4 | Non-goals ≥ 3 and each is something a reader would assume | "Non-goals: none" | list adjacent features, personas, platforms excluded |
| 5 | Every story has Given/When/Then | "User can export" | add criteria incl. permission-denied case |
| 6 | v1 scope ≤ 8 engineering tasks (sanity) | ten stories in v1 | move to v1.1/later |
| 7 | Tenancy/role implications stated | silent on who can do it | add role row per story; reference RBAC matrix |
| 8 | Data implications stated | new entity not mentioned | list new/changed entities for supabase-schema-rls |
| 9 | Flag name and rollout plan | none | `feature.<name>`, per-tenant rollout |
| 10 | Risks have owner + mitigation | "Risk: adoption" | likelihood, impact, mitigation, owner |
| 11 | Open questions have owner + date + default | list of questions only | add columns |
| 12 | No invented numbers, customers, dates | "Acme asked for this" (not provided) | remove or source |
| 13 | Engineering handoff section complete | missing | criteria list, entities, flag, metrics instrumentation |
| 14 | Readable by a CIO in 3 minutes | 6 pages | body ≤ 2 pages; appendix for detail |
