# Muse — Thread 03: Phase 0 — runner + wire the 14 scripted skills

Read `docs/AGENT-REBUILD-PLAN.md` first (approved 2026-10-17; python-pptx approved for phase 2, not needed here). Prior must-nots from `docs/HANDOFF-MUSE.md` apply. Branch: `agent/phase-0`. Deliver one PR.

## Deliverables

| # | File | Spec |
|---|---|---|
| 1 | `scripts/run_skill.py` | Runner per plan §3: parse `metadata.agent` from SKILL.md frontmatter (extend the existing minimal YAML parser to nested lists/maps — no pyyaml); resolve inputs (`--input k=v`, `--assume k=v`; required+missing → write `{out}/needs_input.json` and exit 2); run `script` steps via `subprocess([sys.executable,"-I",…])` with `{input}`/`{out}` substitution and logs in `{out}/logs/`; run `llm` steps via `make_provider()` imported from `scripts/behavioral_evals.py` (`dry` provider writes the template with placeholders); run checks; write `{out}/run.json`; exit 0 only when all checks pass. Flags: `--list`, `--explain <skill>`, `--provider`, `--model`, `--out`. Stdlib only. ~300 lines. |
| 2 | `scripts/check_output.py` | Check vocabulary: `exists`, `json`, `csv:[cols]`, `yaml` (minimal), `sections:[…]`, `no_unowned_tbd`, `numbers_trace_to:<file>`, `cites_source_ids:<file>`, `max_lines:N`, `cmd:"…"`, `exit:N`. Each returns `{check, pass, evidence}`. Importable + CLI. |
| 3 | `metadata.agent` block in 14 SKILL.md files | effort-estimator, rfp-compliance-matrix, integration-migration-assessor, client-research-brief, project-bootstrap, supabase-schema-rls, llm-eval-harness, rag-pipeline-design, infra-gpu-sizing, jd-fit-scorer, application-tracker, offer-evaluator (+ the two new scripts below). Bump `version: 0.2.0`. Add a 3-line "How to run" section at the top of the body (plan §3). Do not rewrite the rest of the body. |
| 4 | New scripts (3) | `rfp-compliance-matrix/scripts/score_matrix.py` (requirements CSV + capabilities CSV → C/P/N/Q + gaps.md + bid score); `integration-migration-assessor/scripts/tco.py` (scored inventory + rate inputs CSV → run-rate/dual-run/decommission table; no default prices); `llm-eval-harness/scripts/build_golden.py` (transcript/CSV → golden-set.csv). Argparse, offline, `--help`, exit non-zero on bad input. |
| 5 | `evals/fixtures/` per wired skill + `evals.json` cases gain `inputs` and `checks` (plan §3 format) | Fictional fixtures only. Each skill: happy path (`exit:0` + output checks), missing-input (`exit:2`, `needs_input.json` names the input), fabrication (output contains `[TO BE BASELINED` / `[ASSUMED` rather than a number). |
| 6 | `scripts/behavioral_evals.py` — new mode `agent` | Runs `run_skill.py` per case with `--provider dry` by default (real provider optional), scores check pass rate; writes `agent.csv` (skill, case_id, check, pass, evidence) and adds `agent pass` + verdict `Works/Partial/Broken` (≥0.9 / ≥0.5 / else) columns to `scorecard.md`. Existing `trigger`/`quality` untouched. |
| 7 | `scripts/validate.py` | For skills at version ≥ 0.2.0: `metadata.agent` present, ≥1 run step, ≥1 output check, every check name in vocabulary, every fixture path exists. |
| 8 | `tests/test_run_skill.py`, `tests/test_check_output.py` | Dry-provider end-to-end on all 14; each check type; needs_input exit code; `--assume` labeling; key never logged. |
| 9 | CI | Add `python3 scripts/behavioral_evals.py agent --provider dry --out evals/results/ci-agent` to `.github/workflows/validate.yml`. |
| 10 | `docs/PHASE0-REPORT.md` | Table: skill · inputs · run steps · outputs · checks · dry-run result · sample `run.json` path. Plus anything that didn't fit the vocabulary. |

## Commands
```bash
cd giri-skills && git fetch origin && git checkout main && git pull && git checkout -b agent/phase-0
python3 -m pip install --user pytest pandas openpyxl python-docx pypdf
# build …
python3 scripts/run_skill.py --list
python3 scripts/run_skill.py presales/effort-estimator --input wbs=skills/presales/effort-estimator/evals/fixtures/wbs.csv --input rates=skills/presales/effort-estimator/evals/fixtures/rates.csv --input client=Acme --out /tmp/acme --provider dry && cat /tmp/acme/run.json
python3 scripts/validate.py && python3 -m pytest -q tests/
python3 scripts/behavioral_evals.py agent --provider dry --out evals/results/agent-dry
git add -A && git commit -m "phase 0: skill runner, output checks, agent eval mode; 14 skills wired" && git push -u origin agent/phase-0 && gh pr create --fill --base main
```

## Success
- `run_skill.py --list` shows 14 agents; all 14 pass dry runs with `run.json ok:true`.
- `validate.py` 0 errors; pytest green; CI green.
- `scorecard.md` shows `agent pass` for 14 skills (others blank, not failing).
- No SKILL.md body rewritten beyond the "How to run" section and frontmatter; no changes to the 26 unwired skills.
- No API keys anywhere.
