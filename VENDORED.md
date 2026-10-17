# Vendored / Upstream Skills

Skills in this repo **wrap** upstream skills where a vendor or a top maintainer already owns the knowledge. Install the upstream set once; our skills detect it by name and fall back to their own `references/` when absent.

| Name used in our SKILL.md | Upstream repo | Install | Used by |
|---|---|---|---|
| `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:executing-plans`, `superpowers:test-driven-development`, `superpowers:systematic-debugging` | obra/superpowers | `/plugin marketplace add obra/superpowers-marketplace` → `/plugin install superpowers@superpowers-marketplace` | spec-to-plan, test-strategy-tdd, safe-fix |
| `security-review` | getsentry/skills | `npx skills add getsentry/skills --skill security-review` | security-review |
| `vercel-react-best-practices`, `vercel-composition-patterns`, `web-design-guidelines` | vercel-labs/agent-skills | `npx skills add vercel-labs/agent-skills` | nextjs-enterprise-conventions |
| `supabase`, `supabase-postgres-best-practices` | supabase/agent-skills | `npx skills add supabase/agent-skills` | supabase-schema-rls |
| `anthropics:webapp-testing`, `anthropics:mcp-builder`, `anthropics:skill-creator`, docx/pdf/pptx/xlsx | anthropics/skills | `/plugin marketplace add anthropics/skills` | test-strategy-tdd, mcp-server-builder, all document outputs |
| `karpathy-guidelines` | multica-ai/andrej-karpathy-skills | `npx skills add multica-ai/andrej-karpathy-skills` | safe-fix (behavioral baseline) |
| `product-management:write-spec` | Anthropic product-management plugin | bundled in Claude (Cowork/Code) | product-spec-prd |

## Pinning
To make installs reproducible, pin a commit in `vendor/pins.txt` (`owner/repo@sha`) and run `scripts/vendor-sync.sh` (TODO) — not yet automated. Until then, record the installed version here when you upgrade:

| Upstream | Pinned sha | Date |
|---|---|---|
| obra/superpowers | installed via plugin marketplace | 2026-10-16 |
| getsentry/skills | main | 2026-10-16 |
| vercel-labs/agent-skills | main (all 9) | 2026-10-16 |
| supabase/agent-skills | main | 2026-10-16 |
| anthropics/skills | TBD | — |

## Rule
Never copy upstream SKILL.md bodies into this repo. Wrap by name; keep our fallbacks complete enough to work alone.
