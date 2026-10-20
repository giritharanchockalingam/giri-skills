# Page audit — 20 Oct 2026

**Rule (5 seconds, first-time viewer):** What is this page for? Is anything good or bad? What do I do next?
**Demo story every page must serve:** find a skill → trust it → run it → govern it.
Nothing below is changed until approved.

## Navigation

Today: 10 top-level sections and 16 sub-tabs. Proposed: 5 sections, one per step of the story.

| Proposed section | Holds | Why |
|---|---|---|
| **Find** (Home) | Describe the work → matching skill; browse by lifecycle stage | Step 1 |
| **Skills** | Library (ready to use first), skill pages | Steps 1–2 |
| **Playbooks** | Chained skills with approvals | Step 3 |
| **Connect** | Use from Claude, Cursor, any app | Step 3 |
| **Govern** | Inbox, publishing, evaluations, insights, admin | Step 4 |

## Page by page

| Page | What a newcomer sees today | Verdict | One-line purpose → next action |
|---|---|---|---|
| Home `/` | Five counters first (633 runs, 88%, 0 ready, 0 waiting); a footnote with three different skill counts | **Rewrite** | "Describe the work, get a tested skill." Search box first; one proof line (23 published, 88% runs succeed); drop zero counters |
| Library `/repo` | "24 healthy, 54 need work"; slug names; Lift −0.29, Trigger 0.67, "Fix both"; worst first | **Rewrite** | "Skills you can use today." Plain titles, ready-to-use first, one status word; scores move to the skill page |
| Publish pipeline `/pipeline` | Count line, six counters, library-moved banner listing 13 names, "closest to publishable" | **Rewrite** (move to Govern) | "What stands between each skill and release." Keep closest list; banner becomes one button |
| Evaluations `/evaluations` | Scorecard tables | **Keep** (move to Govern) | "Evidence each skill works." |
| Roles / Teams | "4 out of 11" without meaning | **Hide** | Not in the story; return when roles drive access |
| Runs `/activity` | Run history | **Keep** (Govern) | "Every run, who, result." |
| Reference skills `/upstream` | 50 vendored GitHub skills | **Hide** | Source material, not product |
| Catalog → Repositories | 63 repositories, Gold/Silver/Bronze, 0/2 scored | **Hide** | Engineering scorecard — a different product |
| Catalog → Services, Databases | Vercel and Supabase inventories | **Hide** | Same |
| Catalog → Delivery & more | 192 raw Port entities | **Remove** | Data dump; Port stays a back-end only |
| AI assets, Initiatives | Agent/MCP inventory; scorecard goals | **Hide** | Same as Catalog |
| Integrations | GitHub, Port setup | **Keep** (under Admin) | Setup, not demo |
| Playbooks `/agents` | Table of 6, mostly "draft", form titled "New agent" | **Rewrite** (light) | "Several skills in a row, with a person approving." Last-run result first; rename "agent" |
| Automations | GitHub App checklist, PR gate rules | **Hide** | Repository checks, not skills |
| Insights | 6 counters (one "—"), then a long list of "Deploys: successful Vercel…" lines | **Rewrite** | "What skills delivered." Runs, success, spend, hours saved; remove DORA list |
| Inbox | "Nothing waiting", one failed run with "1 step(s) not ok, 0 check(s) failed" | **Keep** (fix error text) | "Decisions waiting on you." |
| Assistant | Chat | **Keep** | "Ask in plain words." |
| Connect | Clear 1-2-3 steps; repeats six pipeline counters | **Keep** (drop counters) | "Use these skills from your tools." |
| Admin, Glossary | Settings | **Keep** (Govern) | — |

## Order of work after approval

1. Navigation down to 5 sections; hidden pages stay reachable by URL, no data deleted.
2. Library, Home, Catalog removal.
3. Insights, Pipeline, Playbooks, Connect, Inbox text.
