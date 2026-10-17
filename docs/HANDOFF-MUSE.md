# Handoff Brief — giri-skills — for Muse (executor)

## 1. Goal
`giri-skills` is a library of 40 Agent Skills (agentskills.io `SKILL.md` format) covering presales/solution architecture, enterprise app building (Next.js/Supabase/Vercel), AI platform/agentic work, and career management. Each skill is a routing layer (`SKILL.md`) plus method files, templates, offline Python tools, and eval cases, built to a Big 4 / Fortune 50 quality bar. It installs into Claude Code, Cursor, Codex, and any SKILL.md-compatible agent; vendor-owned knowledge (Vercel, Supabase, Sentry, superpowers) is wrapped by name, not copied.

Repo: https://github.com/giritharanchockalingam/giri-skills (private, branch `main`, HEAD `ba9e405`).

## 2. Current state

| Component | Status | Tested |
|---|---|---|
| Repo skeleton, `shared/` (4 rule files), `templates/skill-template/` | Done | — |
| `scripts/validate.py` (spec + repo rules), `install.sh`, `new-skill.sh` | Done | validate.py: 40 skills, 0 errors (Linux + macOS) |
| `.github/workflows/validate.yml` | Done | Pushed; CI result not yet confirmed |
| `.claude-plugin/marketplace.json`, `AGENTS.md`, `README.md`, `VENDORED.md`, `HANDOFF.md` | Done | — |
| **Presales (13)**: discovery-interview, client-research-brief, rfp-compliance-matrix, proposal-writer, sow-drafter, effort-estimator, solution-architecture-doc, exec-deck-redline, competitive-positioning, integration-migration-assessor, value-case-builder, account-plan, orals-prep | Done | 4 scripts smoke-tested by builder on synthetic input |
| **Build (12)**: project-bootstrap, spec-to-plan, supabase-schema-rls, nextjs-enterprise-conventions, test-strategy-tdd, security-review, observability-setup, ci-cd-vercel-github, safe-fix, handoff-and-thread-close, multi-tenant-saas-patterns, product-spec-prd | Done | scaffold.py (idempotency), rls_lint.py (good/bad migrations) smoke-tested |
| **AI platform (9)**: ai-strategy-coe, agent-architecture, mcp-server-builder, rag-pipeline-design, llm-eval-harness, ai-governance-risk, infra-gpu-sizing, slm-demo-builder, ai-use-case-canvas | Done | run_evals.py, eval_retrieval.py, size.py smoke-tested |
| **Career (6)**: jd-fit-scorer, resume-tailor, interview-prep, outreach-and-followup, application-tracker, offer-evaluator | Done | score.py, tracker.py, compare.py smoke-tested |
| Upstream skills installed on owner's Mac (`~/.agents/skills`): security-review, vercel-* (9), supabase (2), karpathy-guidelines | Done | — |
| superpowers + anthropics/skills via Claude Code plugin marketplace | Not started (owner action) | — |
| Behavioural evals (with-skill vs without, per `evals/evals.json`) | **Not started** | — |
| Independent script test suite (pytest) | **Not started** | — |
| Dedupe workflow YAMLs (`ci-cd-vercel-github/assets/workflows` ↔ `project-bootstrap/assets/workflows`) | Not started | — |
| `vendor/pins.txt` + `scripts/vendor-sync.sh` | Not started | — |
| Real inputs (rate-card.csv, master-resume.md, story-bank.md, profile-keywords.txt) | Owner-only; git-ignored | — |

## 3. Next step (execute exactly)

**Task: add an independent pytest suite for all 14 scripts + a validator test, wire into CI, open a PR.**

```bash
# 0. Setup
git clone https://github.com/giritharanchockalingam/giri-skills.git && cd giri-skills
git checkout -b test/script-suite
python3 --version   # need ≥3.12
python3 -m pip install --user pytest pandas openpyxl python-docx pypdf

# 1. Baseline — must pass before you touch anything
python3 scripts/validate.py                       # expect: Checked 40 skills, 0 errors
python3 -m compileall -q skills scripts && echo OK
for s in $(find skills -name '*.py' -path '*/scripts/*'); do python3 -I "$s" --help >/dev/null || echo "HELP FAIL: $s"; done

# 2. Build tests/ (new top-level dir)
#    tests/conftest.py            — fixtures: tmp_path copies of each skill's assets/*.example.* and evals
#    tests/test_validator.py      — validate.py exit 0 on repo; exit 1 on a tmp skill with bad name / >500 lines / missing evals
#    tests/test_<skill>_<script>.py — one file per script (14). Each: --help exits 0; happy path on the skill's own
#                                     assets/example input produces expected columns/keys; bad/missing input exits non-zero
#                                     with a message; no network (monkeypatch socket.socket to raise).
#    Scripts: presales/{client-research-brief/brief_skeleton.py, rfp-compliance-matrix/extract_requirements.py,
#             effort-estimator/estimate.py, integration-migration-assessor/score_inventory.py}
#             build/{project-bootstrap/scaffold.py, supabase-schema-rls/rls_lint.py}
#             ai-platform/{llm-eval-harness/run_evals.py, rag-pipeline-design/eval_retrieval.py, infra-gpu-sizing/size.py}
#             career/{jd-fit-scorer/score.py, application-tracker/tracker.py, offer-evaluator/compare.py}
#    Invoke scripts via subprocess ([sys.executable, "-I", path, ...]) — do NOT import them (they are not packages).

# 3. Run
python3 -m pytest -q tests/                        # target: all green, ≥3 tests per script
python3 scripts/validate.py                       # must still be 0 errors

# 4. Wire into CI: add to .github/workflows/validate.yml after "Repo validator":
#      - name: Script tests
#        run: pip install -q pytest pandas openpyxl python-docx pypdf && python3 -m pytest -q tests/
# 5. Fix only genuine script bugs found by tests (minimal diff, same file). Record each in docs/TEST-FINDINGS.md
#    as: script | input | observed | fix | commit.
# 6. Update HANDOFF.md ("Done this thread", "Changed files", "Next thread starts with").
git add -A && git commit -m "tests: pytest suite for 14 scripts + validator; CI wiring"
git push -u origin test/script-suite
gh pr create --fill --base main
```

**Success =** `pytest` green, `validate.py` 0 errors, CI green on the PR, `docs/TEST-FINDINGS.md` lists every bug fixed (or states "none"), no file outside `tests/`, `.github/`, `docs/`, `HANDOFF.md`, and the specific script being fixed was modified.

## 4. Environment

```
giri-skills/
├── README.md  AGENTS.md  VENDORED.md  HANDOFF.md  .gitignore
├── .claude-plugin/marketplace.json
├── .github/workflows/validate.yml
├── docs/CATALOG.md            design rationale + sources
├── shared/                    quality-bar.md · writing-style.md · token-efficiency.md · stack-conventions.md
├── templates/skill-template/  SKILL.md · references/ · assets/ · scripts/ · evals/evals.json
├── scripts/                   validate.py · install.sh · new-skill.sh
└── skills/
    ├── presales/<13 skills>
    ├── build/<12 skills>
    ├── ai-platform/<9 skills>
    └── career/<6 skills>
        └── <skill>/  SKILL.md · references/*.md · assets/* · scripts/*.py (some) · evals/evals.json
```

| Item | Value |
|---|---|
| Runtime | Python ≥3.12 (built on 3.13; 3.12 syntax only). Bash for `*.sh`. No Node required (npx `skills` CLI is optional installer only). |
| Deps | Scripts: stdlib only; optional `pandas`, `openpyxl`, `python-docx`, `pypdf` (graceful fallback if absent). Tests: `pytest`. |
| Install | `python3 -m pip install --user pytest pandas openpyxl python-docx pypdf` |
| Validate | `python3 scripts/validate.py` → must print `Checked 40 skills, 0 errors` |
| Compile | `python3 -m compileall -q skills scripts` |
| Shell lint | `for f in $(find scripts skills -name '*.sh'); do bash -n "$f"; done` |
| Tests (after step 3) | `python3 -m pytest -q tests/` |
| Script convention | argparse, `--help`, offline, run with `python3 -I`, exit non-zero on bad input |
| Skill rules | `SKILL.md` ≤300 lines, `name` == dir name, kebab-case, description ≤1024 chars, `evals/evals.json` required, references to `../../../shared/*.md` by relative path |

## 5. Must NOT

| Rule | Detail |
|---|---|
| No force-push, no history rewrite, no direct commits to `main` | Work on a branch; deliver a PR. |
| No deletion or renaming of any skill directory | Fix in place; minimal diffs. |
| No changes to `SKILL.md` content/descriptions | Behavioural tuning is a separate, owner-approved thread. |
| No real personal data | Never add résumé, rate, client, or account facts. `*.example.*` files stay fictional. Do not create the git-ignored real input files. |
| No credentials | None are needed. Do not add tokens, `.env` files, or secrets to the repo or CI. |
| No network in scripts/tests | Tests must pass offline; monkeypatch sockets. |
| No upstream copying | Never paste upstream SKILL.md bodies (superpowers, Sentry, Vercel, Supabase) into this repo — wrap by name only (see VENDORED.md). |
| No prod/cloud access | This repo touches no Vercel, Supabase, or GCP resources. Any script that appears to need them is a bug — report, don't configure. |
| Don't "fix" by regenerating files | Edit failing lines only. Never break one thing while fixing another. |

## Key files to send
- `README.md`, `HANDOFF.md`, `VENDORED.md`, `AGENTS.md`
- `docs/CATALOG.md`
- `shared/quality-bar.md`, `shared/token-efficiency.md`, `shared/stack-conventions.md`, `shared/writing-style.md`
- `scripts/validate.py`, `.github/workflows/validate.yml`
- `templates/skill-template/SKILL.md`, `templates/skill-template/evals/evals.json`
- One exemplar skill in full: `skills/presales/effort-estimator/` (SKILL.md, references/, assets/, scripts/estimate.py, evals/evals.json)
- Everything else it should pull via `git clone` (repo is private — give Muse a read/write deploy key or collaborator access scoped to this repo only).
