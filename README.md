# giri-skills

40 executable Agent Skills (agentskills.io format, each one a configurable agent: declared inputs → deterministic scripts → checked deliverables) for presales & solution architecture, enterprise app building, AI platform/agentic work, and career management — built to a Big 4 / Fortune 50 quality bar. Works with Claude Code, Claude (Cowork), Cursor, Codex, Gemini CLI, Copilot and any `SKILL.md`-compatible agent.

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
scripts/       run_skill.py (agent runner) · check_output.py · behavioral_evals.py · validate.py (CI) · install.sh · new-skill.sh
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
| presales | `account-plan` | account_plan.py |
| presales | `client-research-brief` | brief_skeleton.py |
| presales | `competitive-positioning` | battle_card.py |
| presales | `discovery-interview` | build_pack.py, synthesize.py |
| presales | `effort-estimator` | estimate.py |
| presales | `exec-deck-redline` | redline.py (optional python-pptx) |
| presales | `integration-migration-assessor` | score_inventory.py |
| presales | `orals-prep` | orals.py |
| presales | `proposal-writer` | assemble.py |
| presales | `rfp-compliance-matrix` | extract_requirements.py |
| presales | `solution-architecture-doc` | arch_doc.py |
| presales | `sow-drafter` | sow_from_proposal.py |
| presales | `value-case-builder` | value_model.py |

## Upstream skills (50, vendored)

The 50 most-installed public skills (skills.sh ranking) are vendored under `vendor/` and pinned by commit — superpowers workflow, Vercel/React/Next, Supabase, Stripe, Cloudflare, LangChain/LangGraph, Sentry security, Anthropic document skills, marketing, and more. Ranking + evidence: [catalog/TOP-50.md](catalog/TOP-50.md). Terms and update commands: [VENDORED.md](VENDORED.md).

## Inputs you must supply (placeholders shipped as `*.example.*`)
| File | Used by |
|---|---|
| `skills/presales/effort-estimator/assets/rate-card.example.csv` → `rate-card.csv` | effort-estimator |
| `skills/career/resume-tailor/assets/master-resume.example.md` → `master-resume.md` | resume-tailor, interview-prep |
| `skills/career/interview-prep/assets/story-bank.example.md` → `story-bank.md` | interview-prep |
| `skills/career/jd-fit-scorer/assets/profile-keywords.example.txt` → `profile-keywords.txt` | jd-fit-scorer |

Real versions are git-ignored by default (see `.gitignore`); keep them local.

## Run a skill as an agent
Skills at `metadata.version >= 0.2.0` declare inputs, run steps and checked outputs in `metadata.agent` (12 wired in phase 0, all 13 presales skills after phases 1–2; see `docs/PHASE0-REPORT.md`).
```bash
python3 scripts/run_skill.py --list                      # agent skills and their inputs
python3 scripts/run_skill.py --explain presales/effort-estimator
python3 scripts/run_skill.py --demo presales/effort-estimator   # run it on its own fixtures, see run.json
python3 scripts/run_skill.py presales/effort-estimator --input wbs=./wbs.csv --input rates=./rates.csv --input client=Acme --out ./runs/acme --provider dry
cat ./runs/acme/run.json                                 # steps, checks, ok
python3 scripts/behavioral_evals.py agent --provider dry  # run every agent eval case; scorecard gets Works/Partial/Broken
```
A missing required input exits 2 with `needs_input.json`; `--assume name=value` proceeds with a labeled assumption. `--provider dry` fills `llm` steps with the unfilled template (CI); `anthropic`/`openai` read the key from the environment only.

Every script is stdlib-only. One optional dependency exists: `exec-deck-redline` reads `.pptx` decks through python-pptx (`pip install -r requirements-optional.txt`); without it, export the deck to `deck.md` with `--- slide N ---` separators (the eval fixtures use that form, so tests and CI never need the package).

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
