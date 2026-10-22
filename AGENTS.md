# AGENTS.md — giri-skills

Skills in this repo follow the agentskills.io format (`SKILL.md` + `references/`, `assets/`, `scripts/`, `evals/`). Load a skill when a task matches its description. Shared rules every skill applies: `shared/quality-bar.md`, `shared/writing-style.md`, `shared/token-efficiency.md`, `shared/stack-conventions.md`.

## Available skills

| Domain | Skill | When to use |
|---|---|---|
| ai-platform | `agent-architecture` (skills/ai-platform/agent-architecture) | Use when the user asks to design an AI agent or agentic system — "should this be an agent", "single vs multi-agent", "design the LangGraph g |
| ai-platform | `ai-governance-risk` (skills/ai-platform/ai-governance-risk) | Use when the user asks for an AI compliance or risk review — "assess the risks of this AI use case", "build our AI risk register", "write a  |
| ai-platform | `ai-strategy-coe` (skills/ai-platform/ai-strategy-coe) | Use when the user asks to design an enterprise AI strategy, stand up or assess an AI Center of Excellence (CoE), score an AI use-case portfo |
| ai-platform | `ai-use-case-canvas` (skills/ai-platform/ai-use-case-canvas) | Use when the user wants to qualify a single AI idea quickly — "is this a good AI use case", "fill the canvas for X", "should we build or buy |
| ai-platform | `infra-gpu-sizing` (skills/ai-platform/infra-gpu-sizing) | Use when the user asks to size GPU or inference infrastructure, compare self-hosting an LLM against renting GPUs or using an API, or estimat |
| ai-platform | `llm-eval-harness` (skills/ai-platform/llm-eval-harness) | Use when the user asks "is this agent/LLM app good enough", "build an eval set", "add a regression gate for prompts", "set up LLM-as-judge", |
| ai-platform | `mcp-server-builder` (skills/ai-platform/mcp-server-builder) | Use when the user asks to build, wrap, or review an MCP (Model Context Protocol) server — "expose our API as MCP tools", "build an MCP serve |
| ai-platform | `rag-pipeline-design` (skills/ai-platform/rag-pipeline-design) | Use when the user has a knowledge, search, or question-answering use case over documents — "design our RAG pipeline", "which chunking/embedd |
| ai-platform | `slm-demo-builder` (skills/ai-platform/slm-demo-builder) | Use when the user asks to build a new SLM or agent showroom demo — "add a demo for X to the studio", "build a demo an exec can click through |
| build | `ci-cd-vercel-github` (skills/build/ci-cd-vercel-github) | Use for any pipeline work on a Next.js + Supabase app deployed to Vercel via GitHub Actions — "set up CI", "add preview deploys", "deploy to |
| build | `handoff-and-thread-close` (skills/build/handoff-and-thread-close) | Use at the end of a working thread, before switching topics, or when context is getting long — "wrap up", "hand off", "close this thread", " |
| build | `multi-tenant-saas-patterns` (skills/build/multi-tenant-saas-patterns) | Use when designing or changing tenant isolation, roles/permissions, plans and feature flags, billing entitlements, or audit logging in a mul |
| build | `nextjs-enterprise-conventions` (skills/build/nextjs-enterprise-conventions) | Use whenever writing or reviewing Next.js (App Router) / React / TypeScript code in this stack |
| build | `observability-setup` (skills/build/observability-setup) | Use when an app is going to production or lacks visibility — "add logging", "set up Sentry", "health checks", "alerts", "we can't see what's |
| build | `product-spec-prd` (skills/build/product-spec-prd) | Use when a product feature or capability needs defining before engineering planning — "write a PRD", "spec this feature", "what should v1 in |
| build | `project-bootstrap` (skills/build/project-bootstrap) | Use when the user starts a new app or repo (Next.js + Supabase + Vercel by default) and needs the enterprise skeleton before any feature cod |
| build | `safe-fix` (skills/build/safe-fix) | Use when the user reports a bug or says "fix this" — an error, stack trace, failing test, wrong behaviour, "works in staging not prod" |
| build | `security-review` (skills/build/security-review) | Use pre-merge or pre-release to review a diff, PR or feature for security defects in the Next.js + Supabase + Vercel stack |
| build | `spec-to-plan` (skills/build/spec-to-plan) | Use when a feature request, ticket or SPEC section must become an executable plan before any code is written |
| build | `supabase-schema-rls` (skills/build/supabase-schema-rls) | Use for any Supabase data-model or auth change — new table, column, relationship, role, or policy |
| build | `perf-review-runner` (skills/build/perf-review-runner) | Use when the user asks for a performance review of a Next.js/Supabase repo before a traffic spike — N+1 queries, unbounded reads, select(*) |
| build | `tech-debt-audit-runner` (skills/build/tech-debt-audit-runner) | Use when the user joins or inherits a TypeScript/Next.js codebase and wants an audit of architecture and maintainability debt with a refa |
| build | `ui-component-quality` (skills/build/ui-component-quality) | Use when the user asks to review React/Next.js components before they ship — accessibility, loading/empty/error states, responsive layou |
| build | `test-strategy-tdd` (skills/build/test-strategy-tdd) | Use before implementing any feature, fix or refactor to decide what tests exist and write them first |
| career | `application-tracker` (skills/career/application-tracker) | Use when the user reports any application event (applied, recruiter screen booked, interview done, offer, rejection, ghosted) or asks for th |
| career | `interview-prep` (skills/career/interview-prep) | Use when the user has an interview scheduled (recruiter screen, hiring manager, panel, CIO/CEO, board-style case) for a senior director / VP |
| career | `jd-fit-scorer` (skills/career/jd-fit-scorer) | Use when the user pastes a job description (JD) or job link and asks whether to apply, how well they fit, or to score/rank roles |
| career | `offer-evaluator` (skills/career/offer-evaluator) | Use when the user receives a job offer (or expects one) and asks to evaluate it, compare offers or an offer against their current package, a |
| career | `outreach-and-followup` (skills/career/outreach-and-followup) | Use when the user needs to write or time a job-search message - referral ask, recruiter reply, post-interview thank-you, status check, decli |
| career | `resume-tailor` (skills/career/resume-tailor) | Use when the user asks to tailor, rewrite, or ATS-optimize their résumé for a specific job description (JD), or to produce a targeted execut |
| presales | `account-plan` (skills/presales/account-plan) | Use when the user asks to build or refresh a quarterly or annual account plan, account strategy, or account review for an existing or target |
| presales | `client-research-brief` (skills/presales/client-research-brief) | Use when the user asks to research a company, account, or prospect before a pitch, discovery call, or proposal ("research <company> before t |
| presales | `competitive-positioning` (skills/presales/competitive-positioning) | Use when the user asks how to win against a named competitor, an incumbent vendor or services provider, a platform vendor's services arm, or |
| presales | `discovery-interview` (skills/presales/discovery-interview) | Use when the user asks to prepare for, run, or synthesize a client discovery call, scoping workshop, or stakeholder interview in a presales  |
| presales | `effort-estimator` (skills/presales/effort-estimator) | Use when the user asks to size, estimate, or price a services engagement, build a WBS, produce P50/P80/P90 effort and duration, design a sta |
| presales | `exec-deck-redline` (skills/presales/exec-deck-redline) | Use when the user asks to rework, redline, sharpen, or review an executive deck, steering-committee pack, board slide set, or pitch deck |
| presales | `integration-migration-assessor` (skills/presales/integration-migration-assessor) | Use when the user asks to assess, score, plan, or build the case for migrating an integration or middleware estate between platforms (iPaaS  |
| presales | `orals-prep` (skills/presales/orals-prep) | Use when the user asks to prepare for a pitch presentation, orals, bid defense, shortlist interview, steering-committee presentation, or exe |
| presales | `proposal-writer` (skills/presales/proposal-writer) | Use when the user asks to write, structure, or redline a client proposal, RFP response narrative, or statement of qualifications |
| presales | `rfp-compliance-matrix` (skills/presales/rfp-compliance-matrix) | Use when an RFP, RFI, RFQ, or tender document is received and the user asks to inventory requirements, build a compliance matrix, assess bid |
| presales | `solution-architecture-doc` (skills/presales/solution-architecture-doc) | Use when the user asks to produce, review, or redline a target or solution architecture for a client — context and container views, integrat |
| presales | `sow-drafter` (skills/presales/sow-drafter) | Use when the user asks to convert an approved proposal into a Statement of Work, draft or redline an SOW, or tighten scope, deliverables, ac |
| presales | `value-case-builder` (skills/presales/value-case-builder) | Use when the user asks to build, structure, or review a business case, value case, ROI model, benefits case, or cost-benefit analysis for a  |

## Upstream skills (vendored, pinned — see vendor/pins.json)

| # | Skill | Source | Category | License |
|---|---|---|---|---|
| 1 | `find-skills` (vendor/find-skills) | vercel-labs/skills | engineering-workflow | MIT |
| 2 | `grill-me` (vendor/grill-me) | mattpocock/skills | engineering-workflow | MIT |
| 3 | `agent-browser` (vendor/agent-browser) | vercel-labs/agent-browser | framework-vendor | Apache-2.0 |
| 4 | `improve-codebase-architecture` (vendor/improve-codebase-architecture) | mattpocock/skills | engineering-workflow | MIT |
| 5 | `handoff` (vendor/handoff) | mattpocock/skills | engineering-workflow | MIT |
| 6 | `frontend-design` (vendor/frontend-design) | anthropics/skills | framework-vendor | Apache-2.0 |
| 7 | `domain-modeling` (vendor/domain-modeling) | mattpocock/skills | engineering-workflow | MIT |
| 8 | `vercel-react-best-practices` (vendor/vercel-react-best-practices) | vercel-labs/agent-skills | framework-vendor | MIT |
| 9 | `code-review` (vendor/code-review) | mattpocock/skills | engineering-workflow | MIT |
| 10 | `web-design-guidelines` (vendor/web-design-guidelines) | vercel-labs/agent-skills | framework-vendor | MIT |
| 11 | `microsoft-foundry` (vendor/microsoft-foundry) | microsoft/azure-skills | ai-agents-mcp-rag | MIT |
| 12 | `google-agents-cli-adk-code` (vendor/google-agents-cli-adk-code) | google/agents-cli | ai-agents-mcp-rag | Apache-2.0 |
| 13 | `supabase-postgres-best-practices` (vendor/supabase-postgres-best-practices) | supabase/agent-skills | framework-vendor | MIT |
| 14 | `writing-for-agents` (vendor/writing-for-agents) | mattpocock/skills | ai-agents-mcp-rag | MIT |
| 15 | `skill-creator` (vendor/skill-creator) | anthropics/skills | engineering-workflow | Apache-2.0 |
| 16 | `vercel-composition-patterns` (vendor/vercel-composition-patterns) | vercel-labs/agent-skills | framework-vendor | MIT |
| 17 | `brainstorming` (vendor/brainstorming) | obra/superpowers | engineering-workflow | MIT |
| 18 | `supabase` (vendor/supabase) | supabase/agent-skills | framework-vendor | MIT |
| 19 | `systematic-debugging` (vendor/systematic-debugging) | obra/superpowers | engineering-workflow | MIT |
| 20 | `writing-plans` (vendor/writing-plans) | obra/superpowers | engineering-workflow | MIT |
| 21 | `shadcn` (vendor/shadcn) | shadcn/ui | framework-vendor | MIT |
| 22 | `test-driven-development` (vendor/test-driven-development) | obra/superpowers | engineering-workflow | MIT |
| 23 | `verification-before-completion` (vendor/verification-before-completion) | obra/superpowers | engineering-workflow | MIT |
| 24 | `pptx` (vendor/pptx) | anthropics/skills | documents-productivity-business | Anthropic source-available |
| 25 | `executing-plans` (vendor/executing-plans) | obra/superpowers | engineering-workflow | MIT |
| 26 | `subagent-driven-development` (vendor/subagent-driven-development) | obra/superpowers | engineering-workflow | MIT |
| 27 | `copywriting` (vendor/copywriting) | coreyhaines31/marketingskills | documents-productivity-business | MIT |
| 28 | `pdf` (vendor/pdf) | anthropics/skills | documents-productivity-business | Anthropic source-available |
| 29 | `docx` (vendor/docx) | anthropics/skills | documents-productivity-business | Anthropic source-available |
| 30 | `xlsx` (vendor/xlsx) | anthropics/skills | documents-productivity-business | Anthropic source-available |
| 31 | `webapp-testing` (vendor/webapp-testing) | anthropics/skills | framework-vendor | Apache-2.0 |
| 32 | `deploy-to-vercel` (vendor/deploy-to-vercel) | vercel-labs/agent-skills | framework-vendor | MIT |
| 33 | `mcp-builder` (vendor/mcp-builder) | anthropics/skills | ai-agents-mcp-rag | Apache-2.0 |
| 34 | `workers-best-practices` (vendor/workers-best-practices) | cloudflare/skills | framework-vendor | Apache-2.0 |
| 35 | `sales-enablement` (vendor/sales-enablement) | coreyhaines31/marketingskills | documents-productivity-business | MIT |
| 36 | `customer-research` (vendor/customer-research) | coreyhaines31/marketingskills | documents-productivity-business | MIT |
| 37 | `web-perf` (vendor/web-perf) | cloudflare/skills | framework-vendor | Apache-2.0 |
| 38 | `vercel-optimize` (vendor/vercel-optimize) | vercel-labs/agent-skills | framework-vendor | MIT |
| 39 | `stripe-best-practices` (vendor/stripe-best-practices) | stripe/ai | framework-vendor | MIT |
| 40 | `doc-coauthoring` (vendor/doc-coauthoring) | anthropics/skills | documents-productivity-business | Apache-2.0 |
| 41 | `competitor-profiling` (vendor/competitor-profiling) | coreyhaines31/marketingskills | documents-productivity-business | MIT |
| 42 | `internal-comms` (vendor/internal-comms) | anthropics/skills | documents-productivity-business | Apache-2.0 |
| 43 | `claude-api` (vendor/claude-api) | anthropics/skills | ai-agents-mcp-rag | Apache-2.0 |
| 44 | `karpathy-guidelines` (vendor/karpathy-guidelines) | multica-ai/andrej-karpathy-skills | engineering-workflow | MIT |
| 45 | `security-review` (vendor/security-review) | getsentry/skills | framework-vendor | Apache-2.0 |
| 46 | `langgraph-fundamentals` (vendor/langgraph-fundamentals) | langchain-ai/langchain-skills | ai-agents-mcp-rag | MIT |
| 47 | `langchain-rag` (vendor/langchain-rag) | langchain-ai/langchain-skills | ai-agents-mcp-rag | MIT |
| 48 | `langgraph-human-in-the-loop` (vendor/langgraph-human-in-the-loop) | langchain-ai/langchain-skills | ai-agents-mcp-rag | MIT |
| 49 | `deep-agents-core` (vendor/deep-agents-core) | langchain-ai/langchain-skills | ai-agents-mcp-rag | MIT |
| 50 | `eval-engineering` (vendor/eval-engineering) | langchain-ai/langchain-skills | ai-agents-mcp-rag | MIT |
