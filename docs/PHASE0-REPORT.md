# Phase 0 report — runner, output checks, agent eval mode; 12 skills wired

Date: 2026-10-17 · Branch: `agent/phase-0` · Plan: `docs/AGENT-REBUILD-PLAN.md` · Brief: `docs/HANDOFF-MUSE-03.md`

## Count correction: 12 wired, not 14
The plan's totals line says "B 14", but its per-skill tables grade exactly **12** skills B (presales 4, build 2, ai-platform 3, career 3; the C column sums to 28, not 26), and the brief's named list is the same 12. `tests/conftest.py` likewise tracked 12 scripts. All 12 named skills are wired; nothing outside that list was touched. `run_skill.py --list` therefore reports 12 agent skills.

## Wired skills
`*` = required input. "dry-run result" is from `python3 scripts/behavioral_evals.py agent --provider dry --out evals/results/agent-dry` (36 cases, 98/98 checks).

| Skill | Inputs | Run steps | Outputs | Checks used | Dry-run result | Sample `run.json` |
|---|---|---|---|---|---|---|
| presales/effort-estimator | `wbs`*, `rates`, `client`*, `iterations` | `model-json` → `model-report` → `memo` (llm) | estimate.json, estimate.md, estimate-memo.md | exists, json, no_unowned_tbd, numbers_trace_to, sections | ok=true, 8/8 checks | `docs/phase0-runs/presales__effort-estimator.run.json` |
| presales/rfp-compliance-matrix | `rfp`*, `capabilities`*, `min_words` | `extract` → `score` | requirements.csv, matrix.csv, gaps.md, bid-score.json | csv, exists, json, no_unowned_tbd, sections | ok=true, 9/9 checks | `docs/phase0-runs/presales__rfp-compliance-matrix.run.json` |
| presales/integration-migration-assessor | `inventory`*, `rates`*, `client`*, `waves` | `score` → `tco` → `readout` (llm) | scored.csv, tco.csv, tco.json, readout.md | csv, exists, json, no_unowned_tbd, numbers_trace_to, sections | ok=true, 10/10 checks | `docs/phase0-runs/presales__integration-migration-assessor.run.json` |
| presales/client-research-brief | `notes`*, `company`*, `purpose` | `skeleton` → `brief` (llm) | brief-skeleton.md, brief.md | cites_source_ids, exists, no_unowned_tbd, sections | ok=true, 6/6 checks | `docs/phase0-runs/presales__client-research-brief.run.json` |
| build/project-bootstrap | `target`*, `name`*, `multi_tenant` | `scaffold` | SPEC.md, CLAUDE.md, HANDOFF.md, 0001-stack.md, ci.yml, .env.example | exists, sections, yaml | ok=true, 8/8 checks | `docs/phase0-runs/build__project-bootstrap.run.json` |
| build/supabase-schema-rls | `migrations`*, `client_dirs`, `root` | `lint` | rls-lint.txt | cmd, contains, exists | ok=true, 3/3 checks | `docs/phase0-runs/build__supabase-schema-rls.run.json` |
| ai-platform/llm-eval-harness | `cases`*, `rubric`, `outputs`, `threshold` | `golden` → `evals` → `evals-recorded` | golden-set.csv, scorecard.json, scorecard.txt | contains, csv, exists, json | ok=true, 6/6 checks | `docs/phase0-runs/ai-platform__llm-eval-harness.run.json` |
| ai-platform/rag-pipeline-design | `eval_set`*, `k`, `min_recall`, `at` | `retrieval-metrics` | retrieval-metrics.json, retrieval-metrics.txt | contains, exists, json | ok=true, 4/4 checks | `docs/phase0-runs/ai-platform__rag-pipeline-design.run.json` |
| ai-platform/infra-gpu-sizing | `inputs`*, `overrides` | `size-json` → `size-table` | sizing.json, sizing.txt | contains, exists, json | ok=true, 4/4 checks | `docs/phase0-runs/ai-platform__infra-gpu-sizing.run.json` |
| career/jd-fit-scorer | `jd`*, `profile`*, `threshold` | `score-json` → `score-table` | fit.json, fit.md | contains, exists, json | ok=true, 5/5 checks | `docs/phase0-runs/career__jd-fit-scorer.run.json` |
| career/application-tracker | `tracker`*, `action`, `args`, `as_of` | `event` → `pipeline` → `aging` → `weekly` | tracker.csv, pipeline.json, aging.json, weekly-review.md | csv, exists, json | ok=true, 7/7 checks | `docs/phase0-runs/career__application-tracker.run.json` |
| career/offer-evaluator | `offers`*, `horizon`, `col`, `base_location`, `tax` | `compare-json` → `compare-table` | comparison.json, comparison.md | contains, exists, json | ok=true, 5/5 checks | `docs/phase0-runs/career__offer-evaluator.run.json` |

Every skill has three agent eval cases: happy path (`exit:0` + output checks), missing input (`exit:2` + `needs_input:<name>`), and a fabrication/honesty case (output carries `[TO BE BASELINED` instead of a number, or the gate fails loudly with `exit:1`).

## What was built
| File | Role |
|---|---|
| `scripts/skillmeta.py` | Stdlib parser for the YAML subset in frontmatter (nested maps, lists, flow maps/lists). `load_skill()`; used by the runner, validator and eval harness. |
| `scripts/run_skill.py` | Runner: `--list`, `--explain`, inputs → `needs_input.json` (exit 2) / `--assume` → script steps (`python3 -I`, logs in `{out}/logs/`) → `llm` steps via `make_provider()` → checks → `run.json`. |
| `scripts/check_output.py` | Check vocabulary (below); importable and CLI. |
| `scripts/behavioral_evals.py` | New `agent` mode; `trigger`/`quality`/`all` unchanged. Writes `agent.csv`; scorecard gains `agent pass` + `Works/Partial/Broken`, merging into an existing scorecard when one is present. |
| `scripts/validate.py` | Rules for version ≥ 0.2.0: `metadata.agent` present, ≥1 step, ≥1 check, vocabulary, script/template/context/fixture paths exist, inputs declared, ≥1 agent eval case. |
| `score_matrix.py`, `tco.py`, `build_golden.py` | New domain scripts (argparse, stdlib, `--help`, exit 1 on bad input). |
| `tests/test_run_skill.py`, `tests/test_check_output.py`, `tests/test_presales_score_matrix.py`, `tests/test_presales_tco.py`, `tests/test_aiplatform_build_golden.py`, additions to `test_validator.py` / `test_behavioral_evals.py` / `test_offline.py` | 207 tests pass (99 before). |
| `.github/workflows/validate.yml` | Adds the agent dry step. |

## Runner conventions that went beyond the plan's sketch
| Convention | Why |
|---|---|
| `stdout: "{out}/x.json"` on a script step | `estimate.py --json`, `score.py --json`, `compare.py --json`, `size.py`, `tracker.py` print to stdout; the plan's `--json --out` form would have written nothing for `estimate.py`. |
| `[--rates {rates}]` optional groups in `cmd` | Dropped when an optional input is absent, so one step serves both cases without `--rates ''`. |
| Input types `args` (shell-split), `flag` (emits the flag when truthy), `path` (may not exist yet), `copy: true` (works on a copy in `{out}`) | `--set` overrides, `--multi-tenant`, scaffold targets, and a tracker that mutates its CSV. |
| `skip_if_present` alongside `skip_if_missing` | llm-eval-harness runs the gate on user outputs when given, else on the outputs recorded from the cases file. |
| Eval `checks` entries | Strings `exit:N`, `needs_input:<name>`, `exists:<file>`; any other file check is `{"file": "<relpath>", "check": "<spec>"}`. |
| `numbers_trace_to` accepts a list of files; numbers match on rounding (83.1 traces to 83.089) | Readouts cite two script outputs; LLM steps round. |

## What did not fit the check vocabulary
| Gap | Handling |
|---|---|
| "Output contains `[TO BE BASELINED` rather than a number" (fabrication cases) | Added `contains:"…"` to the vocabulary. |
| "`needs_input.json` names the input" | Added run-level `needs_input:<name>`. |
| "Every requirement has a status + owner" (rfp), "every cost line cites an input row" (tco), "harness runs on its output" (llm-eval), "score + go/no-go present" | Enforced inside the scripts themselves (unmatched → `Q` with CQ id; empty source → `[TO BE BASELINED]`; `run_evals.py` is the next step; `cmd:` check re-runs the linter). The vocabulary only sees `csv:[...]`, `contains`, `cmd`. A per-row CSV predicate check (`csv_rows:<col>!=""`) would express these directly — candidate for phase 1. |
| `no_unowned_tbd` in dry mode | Templates carry `owner: ___` by design; dry mode checks marker format only, real mode requires a named owner. |
| `numbers_trace_to` / `cites_source_ids` in dry mode | Skipped (template is unfilled). They are only meaningful with a real provider; not exercised in CI. |
| rls_lint / eval gates that legitimately fail | A failing gate fails the run (`exit:1`) and the eval asserts exactly that, so an honest failure is a pass for the agent. |
| `mermaid_parses` | Implemented (bracket balance + ≥1 edge) since the plan lists it; no phase-0 skill uses it. |

## Verification
```
python3 scripts/run_skill.py --list                                   # 12 agent skills
python3 scripts/validate.py                                           # Checked 40 skills, 0 errors
python3 -m pytest -q tests/                                           # 207 passed, 2 skipped
python3 scripts/behavioral_evals.py agent --provider dry --out evals/results/agent-dry   # 36 cases, 98/98 checks
python3 -m compileall -q scripts skills
```

## Not done / for the owner
- Real-provider runs (`--provider anthropic|openai`) were not exercised here (no key, by design). `numbers_trace_to`, `cites_source_ids` and the real-mode `no_unowned_tbd` get their first live test then.
- `evals/results/*/runs/` and `runs/` are git-ignored (per-case outputs); `agent.csv` + `scorecard.md` are committed.
- Phases 1–5 (26 C-skills) need one deterministic script each; the runner, checks and eval mode need no change for them.
