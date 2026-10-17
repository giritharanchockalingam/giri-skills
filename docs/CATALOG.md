# giri-skills — Catalog for Review (v0.1, 2026-10-16)

Redline this file. Strike, rename, merge, or add rows. Build starts on your "go".

## 1. What the research says (sources at bottom)

| Repo / standard | Why it matters to this build | Take |
|---|---|---|
| agentskills.io spec (Anthropic-originated, open) | `SKILL.md` = YAML (`name`, `description`, optional `license`, `compatibility`, `metadata`, `allowed-tools`) + body <500 lines; `scripts/`, `references/`, `assets/`; progressive disclosure; `skills-ref validate` | **Standard we follow** |
| anthropics/skills (~179k★) | skill-creator, docx/pdf/pptx/xlsx, mcp-builder, webapp-testing, template, marketplace install | **Adopt** doc skills + skill-creator; don't rebuild |
| obra/superpowers (~290k★) | brainstorm → write-plan → execute-plan, TDD, systematic-debugging, code-review subagent, YAGNI | **Adopt** as the engineering workflow spine; ours layer on top |
| alirezarezvani/claude-skills (~20k★, 200+ skills) | c-level-advisor, pm-skills, cost-estimator, architecture-pattern-selector, assumption-challenger, grill-me, senior-* personas | **Borrow patterns**; rewrite for your quality bar |
| VoltAgent/awesome-agent-skills (~31k★, 1,400 official) | Vercel react/next best practices, Vercel web-design-guidelines, Supabase, Stripe, Sentry security-review, Trail of Bits, Expo | **Adopt** vendor-official skills for your stack |
| getsentry/skills security-review | Teaches reasoning, not a checklist — the only security skill reviewers rated worth installing | **Adopt** |
| multica-ai/andrej-karpathy-skills | Behavioral guardrails: no assumptions, minimal diffs, verify before claiming done | **Adopt** (matches your "never break one thing fixing another") |
| coreyhaines31/marketingskills | Pattern for a skill repo with CLI tools per skill | Pattern only |
| Aimpoint Digital apd-agent-skills | Consultancy presales skills (proposal→SOW, scoping, likelihood-to-close, client research) | Closest analog to your presales needs; **build our own** |
| Installers | `npx skills add <owner/repo>`, `/plugin marketplace add <owner/repo>`, openskills (AGENTS.md sync) | Repo must work with all three |

**Design principle:** adopt what the vendors own (framework/tool knowledge); build what only you own (your presales method, your quality bar, your stack conventions, your career narrative).

## 2. Repo architecture

```
giri-skills/
├── README.md                      install, catalog, conventions
├── .claude-plugin/marketplace.json  → /plugin marketplace add <you>/giri-skills
├── AGENTS.md                      openskills/Codex/Cursor discovery
├── shared/                        referenced by every skill (never duplicated)
│   ├── quality-bar.md             Big 4 / Fortune 50 standard, tables-over-prose, no filler
│   ├── token-efficiency.md        your rules doc (plan-then-build, fix-don't-redo, batch, HANDOFF)
│   ├── writing-style.md           exec voice, redline conventions, "to be baselined" + owner
│   └── stack-conventions.md       Next.js 15 / Supabase / Vercel / Python conventions
├── skills/
│   ├── presales/…                 (domain 1)
│   ├── build/…                    (domain 2)
│   ├── ai-platform/…              (domain 3)
│   └── career/…                   (domain 4)
├── scripts/
│   ├── validate.sh                skills-ref validate on every skill (CI)
│   ├── install.sh                 copies to ~/.claude/skills / .agents/skills
│   └── new-skill.sh               scaffold from template
├── .github/workflows/validate.yml
└── VENDORED.md                    pinned upstream skills we adopt (superpowers, sentry, vercel…) + versions
```

Every skill: `SKILL.md` (<300 lines, routing layer) → `references/` (method, checklists) → `assets/` (templates) → `scripts/` (deterministic work in Python). Each ships with 2–3 eval prompts in `evals/` so we can test with-skill vs without.

## 3. Proposed skills (build order = table order)

### Domain 1 — Presales & Solution Architecture (build first)

| # | Skill | Trigger (description) | Produces | Bundled assets | Borrowed from |
|---|---|---|---|---|---|
| 1 | `discovery-interview` | Prep for or synthesize a client discovery call | Question bank by vertical, pain/impact/urgency matrix, gaps list | question-banks/{edtech,retail,mfg,travel}.md | apd scoping, grill-me |
| 2 | `client-research-brief` | "Research <company> before a pitch" | 1-page brief: filings, tech stack signals, leadership, news, likely initiatives | script: web digest → table; template | apd client-research |
| 3 | `rfp-compliance-matrix` | RFP/RFI received | Requirement inventory → compliance matrix (Y/Partial/N + owner), gaps, Q&A list | script: PDF/DOCX extractor; xlsx template | agensi capture pack |
| 4 | `proposal-writer` | Write/redline a proposal | On-template proposal: exec summary, approach, team, timeline, risks, pricing placeholders | section library, win-theme worksheet | buildermethods, seb1n |
| 5 | `sow-drafter` | Convert approved proposal → SOW | SOW with scope, deliverables, assumptions, acceptance criteria, change control, RACI | SOW template, assumptions checklist | apd proposal-to-sow |
| 6 | `effort-estimator` | Size an engagement | WBS + 3-point estimates, staffing pyramid, onshore/offshore mix, margin sanity | script: Monte Carlo on CSV; rate-card template (your rates, not invented) | cost-estimator |
| 7 | `solution-architecture-doc` | Produce a target architecture | C4-style context/container views, integration map, NFRs, decision log, migration waves | Mermaid templates, NFR checklist, ADR template | engineering:architecture |
| 8 | `exec-deck-redline` | Rework an executive deck | Slide-by-slide redline (keep storyline, sharpen), speaker notes, "to be baselined" markers | redline rubric, storyline checklist | your stated preference |
| 9 | `competitive-positioning` | "How do we win vs <competitor/incumbent>" | Battle card: their strengths, our wedge, landmines, objection handling | battle-card template | competitive-brief |
| 10 | `integration-migration-assessor` | MuleSoft→Apigee, Informatica, any platform migration | Inventory → complexity scoring → wave plan → TCO/ROI model | script: API inventory scorer; TCO xlsx | your Migration Factory work |
| 11 | `value-case-builder` | Build the business case | Benefits tree, cost/savings model, payback, sensitivity; every number sourced or marked TBD | xlsx model template | finance-skills |
| 12 | `account-plan` | Quarterly account strategy | White-space map, stakeholder map, risks, 90-day plays, pipeline table | account-plan template | c-level-advisor |
| 13 | `orals-prep` | Prepare for a pitch/orals | Timed script, likely Qs with answers, red-team objections | orals rubric | agensi orals |

### Domain 2 — Enterprise App Building (vibe-coding to enterprise grade)

| # | Skill | Trigger | Produces | Bundled assets | Borrowed from |
|---|---|---|---|---|---|
| 14 | `project-bootstrap` | New app/repo | SPEC.md, CLAUDE.md, HANDOFF.md, ADR folder, CI skeleton, env matrix, branch rules | templates for all; Next.js+Supabase+Vercel starter checklist | claude-code-bootstrap, your token rules |
| 15 | `spec-to-plan` | Feature request → plan | Spec → task-gated plan with acceptance criteria, test list, rollback | wraps superpowers brainstorm/write-plan with your gates | superpowers |
| 16 | `supabase-schema-rls` | Any data-model or auth change | Migration SQL, RLS policies, typed client, seed, rollback | script: policy linter; RLS patterns ref | Supabase official skill |
| 17 | `nextjs-enterprise-conventions` | Any Next.js/React code | Enforces Vercel react/next rules + your folder/naming/error/logging conventions | wraps Vercel skills + stack-conventions.md | Vercel official |
| 18 | `test-strategy-tdd` | Before any implementation | Test pyramid for the feature, Playwright/Vitest scaffolds, coverage gate | wraps superpowers TDD + anthropic webapp-testing | superpowers, anthropics |
| 19 | `security-review` | Pre-merge / pre-release | Reasoning-based review (authz, injection, secrets, RLS bypass, SSRF), fixes in code | wraps sentry security-review + Supabase/Vercel specifics | getsentry |
| 20 | `observability-setup` | App goes to prod | Structured logs, error tracking, health endpoints, alert rules, dashboards | templates per stack | engineering |
| 21 | `ci-cd-vercel-github` | Pipeline work | GitHub Actions: lint→test→build→preview→prod, env promotion, rollback | workflow YAML templates | deploy-checklist |
| 22 | `safe-fix` | "Fix this bug" | Reproduce → isolate → minimal diff → regression test → verify; never collateral breakage | wraps superpowers systematic-debugging + Karpathy guardrails | superpowers, Karpathy |
| 23 | `handoff-and-thread-close` | End of a working thread | HANDOFF.md update, changed-files list, next-thread prompt | handoff template | your token rules |
| 24 | `multi-tenant-saas-patterns` | Tenant isolation, billing, RBAC | Tenant model, RBAC matrix, plan/feature flags, audit log | reference patterns | HMS/AgentHive work |
| 25 | `product-spec-prd` | Product feature definition | PRD with goals/non-goals, metrics, phased scope | wraps product-management:write-spec | PM plugin |

### Domain 3 — Data/AI Platform & Agentic

| # | Skill | Trigger | Produces | Bundled assets | Borrowed from |
|---|---|---|---|---|---|
| 26 | `ai-strategy-coe` | Enterprise AI strategy / CoE design | Maturity assessment, operating model, use-case portfolio scoring, governance, 12-month roadmap | scoring rubric, roadmap template | c-level, your SEI work |
| 27 | `agent-architecture` | Design an agent/agentic system | Pattern selection (single/multi-agent, LangGraph/MCP), state design, tool contracts, HITL points, failure modes | decision tree, LangGraph/MCP reference | architecture-pattern-selector, your agentic-stack |
| 28 | `mcp-server-builder` | Build an MCP server | Spec-compliant server, tool schemas, auth, tests | wraps anthropic mcp-builder | anthropics |
| 29 | `rag-pipeline-design` | Knowledge/RAG use case | Chunking/embedding/retrieval choices, eval set, guardrails, cost model | eval harness script | engineering |
| 30 | `llm-eval-harness` | "Is this agent good enough?" | Golden set, rubric, automated scoring, regression gate in CI | script: eval runner (pytest) | anthropic skill-eval pattern |
| 31 | `ai-governance-risk` | Compliance / risk review | Risk register (bias, privacy, hallucination, IP), controls, model cards | NIST AI RMF checklist ref | ra-qm-skills |
| 32 | `infra-gpu-sizing` | Self-host vs rent, GPU/inference sizing | Workload model, cost comparison, recommendation | xlsx calculator | your GPU evaluation |
| 33 | `slm-demo-builder` | New SLM/agent showroom demo | Demo spec, synthetic data, UI stub, talk track | demo template | your SLM Studio |
| 34 | `ai-use-case-canvas` | Qualify an AI idea | One-page canvas: problem, data readiness, feasibility, value, risk, build/buy | canvas template | product-brainstorming |

### Domain 4 — Job Search & Career (build last)

| # | Skill | Trigger | Produces | Bundled assets | Borrowed from |
|---|---|---|---|---|---|
| 35 | `jd-fit-scorer` | Paste a JD | Fit score (must-haves, nice-to-haves, red flags), gap list, go/no-go | scoring rubric | — |
| 36 | `resume-tailor` | Tailor résumé to a JD | ATS-aligned bullets, keyword map, before/after diff; truth-locked to your master résumé | master-resume.md (you supply), bullet bank | — |
| 37 | `interview-prep` | Interview scheduled | STAR stories mapped to competencies, likely questions, 90-day plan draft, questions to ask | story bank template | grill-me |
| 38 | `outreach-and-followup` | Recruiter/referral messages | LinkedIn/email variants by goal, follow-up cadence | message templates | stakeholder-update |
| 39 | `application-tracker` | Any application event | Pipeline table (stage, next action, date), weekly review | xlsx/markdown tracker | pm-skills |
| 40 | `offer-evaluator` | Offer received | Comp/benefits/relocation comparison, negotiation levers, decision matrix | xlsx template | hard-call |

## 4. Decisions needed from you

| # | Question | Default if no answer |
|---|---|---|
| A | GitHub org/user and repo name | `<your-user>/giri-skills`, private |
| B | Vendor upstream skills into the repo (pinned copies) or install side-by-side? | Pin copies in `vendor/` + VENDORED.md (reproducible, offline) |
| C | Any skill to cut/merge? (40 is a lot; I'd ship 1–13 first) | Build in 4 PRs, one per domain |
| D | Inputs you must supply before build: rate card (6), master résumé (36), token-efficiency rules doc (shared/) | I'll leave `assets/*.example.md` placeholders and mark TBD |
| E | Language for scripts | Python 3.12, stdlib + pandas/openpyxl only |

## 5. Build plan (after your go)

| Step | Output | Est. threads |
|---|---|---|
| 1 | Repo skeleton, shared/, scripts, CI, marketplace.json, README | 1 |
| 2 | Domain 1 skills (13) + evals | 2 |
| 3 | Domain 2 skills (12) + evals, vendored superpowers/sentry/vercel | 2 |
| 4 | Domain 3 skills (9) + evals | 1–2 |
| 5 | Domain 4 skills (6) + evals | 1 |
| 6 | Validation run (skills-ref), install test in Claude Code + Cowork, HANDOFF.md | 1 |

## Sources
- https://agentskills.io/specification
- https://github.com/anthropics/skills
- https://github.com/obra/superpowers
- https://github.com/VoltAgent/awesome-agent-skills
- https://github.com/alirezarezvani/claude-skills
- https://github.com/getsentry/skills (security-review)
- https://github.com/multica-ai/andrej-karpathy-skills
- https://agentskills.aimpointdigital.com/Pre-Sales
- https://www.taskade.com/blog/claude-code-skills
- https://claudefa.st/blog/tools/skills/best-claude-code-skills
- https://timonweb.com/ai/i-checked-5-security-skills-for-claude-code-only-one-is-worth-installing/
