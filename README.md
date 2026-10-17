# giri-skills

40 Agent Skills (agentskills.io format) for presales & solution architecture, enterprise app building, AI platform/agentic work, and career management — built to a Big 4 / Fortune 50 quality bar. Works with Claude Code, Claude (Cowork), Cursor, Codex, Gemini CLI, Copilot and any `SKILL.md`-compatible agent.

## Install

```bash
# Claude Code (plugin marketplace)
/plugin marketplace add giritharanchockalingam/giri-skills
/plugin install presales@giri-skills      # or build, ai-platform, career

# Any agent (universal, via vercel-labs/skills CLI)
npx skills add giritharanchockalingam/giri-skills            # install all
npx skills add giritharanchockalingam/giri-skills --skill proposal-writer

# Local clone (symlinks; add --copy to copy)
git clone https://github.com/giritharanchockalingam/giri-skills.git
cd giri-skills && scripts/install.sh claude     # or agents | cursor | codex
```

Then install the upstream skills these wrap (one-time): see [VENDORED.md](VENDORED.md).

## Layout

```
shared/        quality-bar, writing-style, token-efficiency, stack-conventions (every skill reads these)
skills/        presales/ · build/ · ai-platform/ · career/   — one folder per skill
  <skill>/     SKILL.md · references/ · assets/ · scripts/ · evals/evals.json
scripts/       validate.py (CI) · install.sh · new-skill.sh
templates/     skill-template/ (used by new-skill.sh)
docs/          CATALOG.md (design rationale and sources)
```

## Catalog

| Domain | Skill | Scripts |
|---|---|---|
| ai-platform | `agent-architecture` | — |
| ai-platform | `ai-governance-risk` | — |
| ai-platform | `ai-strategy-coe` | — |
| ai-platform | `ai-use-case-canvas` | — |
| ai-platform | `infra-gpu-sizing` | size.py |
| ai-platform | `llm-eval-harness` | run_evals.py |
| ai-platform | `mcp-server-builder` | — |
| ai-platform | `rag-pipeline-design` | eval_retrieval.py |
| ai-platform | `slm-demo-builder` | — |
| build | `ci-cd-vercel-github` | — |
| build | `handoff-and-thread-close` | — |
| build | `multi-tenant-saas-patterns` | — |
| build | `nextjs-enterprise-conventions` | — |
| build | `observability-setup` | — |
| build | `product-spec-prd` | — |
| build | `project-bootstrap` | scaffold.py |
| build | `safe-fix` | — |
| build | `security-review` | — |
| build | `spec-to-plan` | — |
| build | `supabase-schema-rls` | rls_lint.py |
| build | `test-strategy-tdd` | — |
| career | `application-tracker` | tracker.py |
| career | `interview-prep` | — |
| career | `jd-fit-scorer` | score.py |
| career | `offer-evaluator` | compare.py |
| career | `outreach-and-followup` | — |
| career | `resume-tailor` | — |
| presales | `account-plan` | — |
| presales | `client-research-brief` | brief_skeleton.py |
| presales | `competitive-positioning` | — |
| presales | `discovery-interview` | — |
| presales | `effort-estimator` | estimate.py |
| presales | `exec-deck-redline` | — |
| presales | `integration-migration-assessor` | score_inventory.py |
| presales | `orals-prep` | — |
| presales | `proposal-writer` | — |
| presales | `rfp-compliance-matrix` | extract_requirements.py |
| presales | `solution-architecture-doc` | — |
| presales | `sow-drafter` | — |
| presales | `value-case-builder` | — |

## Inputs you must supply (placeholders shipped as `*.example.*`)
| File | Used by |
|---|---|
| `skills/presales/effort-estimator/assets/rate-card.example.csv` → `rate-card.csv` | effort-estimator |
| `skills/career/resume-tailor/assets/master-resume.example.md` → `master-resume.md` | resume-tailor, interview-prep |
| `skills/career/interview-prep/assets/story-bank.example.md` → `story-bank.md` | interview-prep |
| `skills/career/jd-fit-scorer/assets/profile-keywords.example.txt` → `profile-keywords.txt` | jd-fit-scorer |

Real versions are git-ignored by default (see `.gitignore`); keep them local.

## Conventions
- A skill is a routing layer: `SKILL.md` ≤ 300 lines; depth lives in `references/`.
- No invented numbers — `[TO BE BASELINED — owner: ___]` instead.
- Client-facing outputs are built only from provided sources.
- Every skill ships `evals/evals.json` (happy path, missing input, fabrication attempt).
- `python3 scripts/validate.py` must pass before merge (runs in CI).

## Add a skill
```bash
scripts/new-skill.sh presales win-loss-review
# edit skills/presales/win-loss-review/SKILL.md, then
python3 scripts/validate.py
```

## License
MIT
