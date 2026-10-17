# HANDOFF — giri-skills — 2026-10-17 (thread 02)
## State: behavioral eval harness built on branch `eval/behavioral-01`; dry run + pytest + validate.py green; PR pending. No real-model run yet (waiting on API key).
## Done this thread
- Built `scripts/behavioral_evals.py` (modes trigger/quality/all; providers anthropic/openai/dry; retries; cost guard with budget abort; scorecard + CSV + raw jsonl outputs)
- Added `evals/judge-prompt.md`, `evals/negative-set.json` (10 prompts); `evals/results/*/raw/` git-ignored
- Added `tests/test_behavioral_evals.py` (8 tests: dry e2e, CSV schemas, verdict rule, budget abort/override, key-leak, glob filter, fixtures); full suite 100 passed, 1 skipped
- Fixed 2 harness bugs found during dry runs: skill key/domain off-by-one (`parts[1]/parts[2]` → `parts[0]/parts[1]`); argparse `append` + list default made `--skills` match everything
- Wired a `dry` behavioral-evals run into CI (presales scope, no key, no network)
- Scanned all 120 eval cases: none malformed
- Wrote `docs/EVAL-FINDINGS.md` scaffold (populated after the real run; proposals go to owner for thread 03)
## Changed files
- `scripts/behavioral_evals.py` (new)
- `evals/judge-prompt.md`, `evals/negative-set.json` (new)
- `tests/test_behavioral_evals.py` (new)
- `.github/workflows/validate.yml` (added Behavioral evals (dry) step)
- `.gitignore` (ignore evals/results/*/raw/)
- `docs/EVAL-FINDINGS.md` (new)
- `docs/HANDOFF-MUSE-02.md` (added by owner: thread 02 brief)
- `HANDOFF.md` (this update)
## Open items (owner)
- Merge PR `eval/behavioral-01` once CI is green
- Provide `ANTHROPIC_API_KEY` out-of-band (env only) for the pilot: `python3 scripts/behavioral_evals.py all --provider anthropic --skills 'skills/presales/*' --max-cases 2 --runs 1 --budget-usd 5` — then the full run (`--runs 2 --budget-usd 40 --yes`); harness prints the spend projection first
- After the full run: fill in `docs/EVAL-FINDINGS.md` with paste-ready proposals; owner applies them in thread 03 (this thread never edits `SKILL.md`)
- (carried over) Supply real inputs: rate-card.csv, master-resume.md, story-bank.md, profile-keywords.txt
- (carried over) Install upstream skills per VENDORED.md and pin shas; superpowers + anthropics/skills via marketplace
- (carried over) Dedupe workflow YAMLs (ci-cd-vercel-github/assets/workflows ↔ project-bootstrap/assets/workflows)
- (carried over) `vendor/pins.txt` + `scripts/vendor-sync.sh`
## Next thread starts with
"Read HANDOFF.md. With the API key in env, run the pilot on presales, inspect the scorecard, fix any judge/router prompt issues, then run the full behavioral eval. Populate docs/EVAL-FINDINGS.md with paste-ready description proposals for every non-OK skill."
