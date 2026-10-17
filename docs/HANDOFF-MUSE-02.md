# Muse — Thread 02: Behavioral evals (with-skill vs without) + trigger accuracy

Read `docs/HANDOFF-MUSE.md` first (goal, environment, must-nots still apply). Thread 01 (pytest suite) must be merged or rebased onto before starting.

## Objective
Measure, for all 40 skills: (a) **trigger accuracy** — does the skill's `description` cause the right skill to be selected for its eval prompts; (b) **output quality** — do outputs produced *with* `SKILL.md` loaded satisfy `evals/evals.json` `expected[]` more often than outputs produced *without* it. Deliver a scorecard and a ranked list of proposed description/instruction fixes. **Do not edit any `SKILL.md`** — proposals only; owner applies them in thread 03.

## Design (build exactly this)

| Component | Spec |
|---|---|
| `scripts/behavioral_evals.py` | argparse CLI. Modes: `trigger`, `quality`, `all`. Provider abstraction `LLM.complete(system, user) -> str`; implementations: `anthropic` (reads `ANTHROPIC_API_KEY` from env; model via `--model`, default `claude-sonnet-4-5`), `openai` (`OPENAI_API_KEY`), `dry` (returns canned text; for CI). Never prints or logs keys. Retries 3× with backoff; `--max-cases N` for cheap runs; `--skills <glob>` filter; `--seed`; `--runs K` (default 2) for variance. |
| Trigger mode | Build a router prompt: the 40 `name: description` pairs (from frontmatter) + one eval prompt → ask the model to return exactly one skill name or `none`. Score = correct selection rate per skill across all its eval cases × K runs. Also run every prompt against a 10-prompt **negative set** (generic coding/chat asks that should map to `none`) → false-positive rate per skill. |
| Quality mode | For each case: run twice — `without` (system = `shared/quality-bar.md` + `shared/writing-style.md` only) and `with` (same + full `SKILL.md` + file list of `references/`,`assets/`; include contents of any `references/*.md` ≤ 8 KB). Grade each output with an LLM judge: for each `expected[]` string return PASS/FAIL + one-line evidence. Judge prompt is in `evals/judge-prompt.md`; judge model may equal the generator model but must be called with `temperature=0`. Score = mean pass rate; **lift = with − without**. |
| Cost guard | Estimate tokens before running; abort if projected > `--budget-usd` (default 15) unless `--yes`. Print projection first. |
| Outputs | `evals/results/<YYYY-MM-DD>/trigger.csv` (skill, case_id, run, selected, correct), `quality.csv` (skill, case_id, run, mode, expected_idx, pass, evidence), `scorecard.md` (one table: skill · trigger acc · FP rate · without · with · lift · verdict), `raw/*.jsonl` (prompts + outputs, for audit). Results dir is committed; raw/ is `.gitignore`d. |
| Verdict rule | `OK` if trigger ≥ 0.8 and lift ≥ +0.2; `DESC` if trigger < 0.8 (description problem); `BODY` if lift < 0.2 (instructions don't change behavior); `BOTH`. |
| `docs/EVAL-FINDINGS.md` | For every non-OK skill: current description, observed failure (which prompts went where / which expected items failed in both modes), **proposed** new description or SKILL.md change (full text, ready to paste), rationale ≤ 2 lines. Ranked by domain order presales → build → ai-platform → career. |
| Tests | `tests/test_behavioral_evals.py`: `dry` provider end-to-end on 2 skills; CSV schemas; verdict rule; budget abort; key never appears in logs/output. |
| CI | Add a `dry` run to `.github/workflows/validate.yml` (no key, no network). Real runs are manual only. |

## Commands

```bash
cd giri-skills && git fetch origin && git checkout main && git pull
git checkout -b eval/behavioral-01
python3 -m pip install --user anthropic openai pytest

# build scripts/behavioral_evals.py, evals/judge-prompt.md, evals/negative-set.json, tests/test_behavioral_evals.py

# 1. Dry run — must pass with no key
python3 scripts/behavioral_evals.py all --provider dry --skills 'skills/presales/*' --out evals/results/dry
python3 -m pytest -q tests/ && python3 scripts/validate.py

# 2. Cheap real pilot (owner supplies key via env only — never in files)
export ANTHROPIC_API_KEY=...   # provided out-of-band
python3 scripts/behavioral_evals.py all --provider anthropic --skills 'skills/presales/*' --max-cases 2 --runs 1 --budget-usd 5
#    Inspect evals/results/<date>/scorecard.md. If judge output is unparseable or lift is nonsensical, fix the prompts before scaling.

# 3. Full run
python3 scripts/behavioral_evals.py all --provider anthropic --runs 2 --budget-usd 40 --yes

# 4. Write docs/EVAL-FINDINGS.md; update HANDOFF.md
git add -A && git commit -m "evals: behavioral eval harness + first scorecard + findings"
git push -u origin eval/behavioral-01 && gh pr create --fill --base main
```

## Success
- `scorecard.md` covers all 40 skills with trigger acc, FP rate, without/with/lift, verdict.
- `EVAL-FINDINGS.md` has a paste-ready proposal for every non-OK skill; zero `SKILL.md` files modified (`git diff --stat main -- skills/` shows no `SKILL.md`).
- pytest + validate.py + CI dry run green. No key in any committed file (`git grep -i "sk-ant\|sk-" -- . ':!*.md'` returns nothing).
- Total spend reported in PR description.

## Must-not additions for this thread
- No API key in repo, CI, logs, or raw outputs (redact if a model echoes it).
- No modifications under `skills/**/SKILL.md`, `references/`, `assets/`.
- Do not "improve" `evals.json` cases to make scores better; if a case is malformed, list it in EVAL-FINDINGS under "Broken cases" and skip it.
