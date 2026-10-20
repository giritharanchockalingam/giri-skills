# Page audit — 20 Oct 2026 (persona version)

Skills Factory is an enterprise portal, not a demo. Every page must pass one test:
**which real person uses it, for what job — and in 5 seconds can they tell what it is, whether anything is good or bad, and what to do next?**
Nothing below is changed until approved.

## Personas and navigation

| Persona | Job | Section | Pages |
|---|---|---|---|
| Employee | Find a skill that works; run it in the portal or from Claude / Cursor / an app | **Use** | Home, Library, Playbooks, Connect, Assistant |
| Skill owner | Build, test and publish skills | **Build** | Publish pipeline, Evaluations, Reference skills |
| Governance / risk | Approve releases, audit runs, track spend and value | **Govern** | Inbox, Runs, Insights, Audit log |
| Platform team | Point skills at real systems; enforce them on code changes | **Platform** | Repositories, Services, Databases, Automations, Initiatives |
| Admin | Access, keys, integrations, policies | **Admin** | Administration, Roles, Teams, Integrations, Glossary |

Today: 10 top-level sections, 16 sub-tabs, no persona grouping. Proposed: 5 sections above.

## Page by page

| Page | Persona | What a newcomer sees today | Verdict | Purpose line → next action |
|---|---|---|---|---|
| Home `/` | Employee | Five counters first (two are 0); footnote with three different skill counts | **Rewrite** | "Describe the work, get a tested skill." Search first; one proof line; no zero counters |
| Library `/repo` | Employee | "24 healthy, 54 need work"; slugs; Lift −0.29, Trigger 0.67, "Fix both"; worst first | **Rewrite** | "Skills you can use today." Plain titles, ready first, one status word; scores on the skill page |
| Playbooks `/agents` | Employee | Table of 6, mostly draft; form titled "New agent" | **Rewrite (light)** | "Several skills in a row, a person approves." Rename agent; last result first |
| Connect | Employee | Clear 1-2-3 steps; repeats six pipeline counters | **Keep** | Drop counters |
| Assistant | Employee | Chat | **Keep** | — |
| Publish pipeline | Skill owner | Count line, six counters, banner listing 13 names, closest list | **Rewrite** | "What stands between each skill and release." Banner → one button |
| Evaluations | Skill owner | Scorecard tables | **Keep** | Explain Lift / Trigger in place |
| Reference skills | Skill owner | 50 vendored skills | **Keep** | "Public skills you can import." |
| Inbox | Governance | Empty state; failed run shows "1 step(s) not ok, 0 check(s) failed" | **Keep, fix text** | Readable failure reason |
| Runs | Governance | Run history | **Keep** | — |
| Insights | Governance | 6 counters (one "—"); long list of "Deploys: successful Vercel…" lines | **Rewrite** | "What skills delivered": runs, success, spend, hours saved; DORA as a summary, not a list |
| Repositories | Platform | 63 repos, Gold/Silver/Bronze, 0/2 scored, no link to skills | **Reframe** | "Where skills run." Lead with "N repositories have skills applied, M don't"; scorecard secondary |
| Services, Databases | Platform | Raw inventories | **Reframe** | Show which skills apply to each |
| Automations | Platform | GitHub App checklist, PR gate rules | **Reframe** | "Run skills on every pull request." Checklist collapses to one "ready" line |
| Initiatives, AI assets | Platform | Goals and agent/MCP inventory | **Keep** under Platform | Purpose line on each |
| Delivery & more | — | 192 raw Port entities | **Remove** | No persona has a job it serves; Port stays a back-end |
| Roles, Teams | Admin | "4 out of 11" with no meaning | **Keep, close gap** | Roles should decide who can run which skill — today they don't (enterprise gap) |
| Integrations, Admin, Glossary | Admin | Setup pages | **Keep** | — |

## Order of work after approval

1. Navigation: 5 persona sections; every page gets a one-line purpose; remove Delivery & more tab (data kept).
2. Use: Library, Home.
3. Platform: Repositories reframe around skills applied.
4. Govern / Build: Insights, Pipeline, Inbox text, Playbooks rename.
5. Enterprise gap: role-based access to skills (separate design, approval first).
