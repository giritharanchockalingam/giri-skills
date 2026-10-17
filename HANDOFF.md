# HANDOFF — giri-skills — 2026-10-17
## State: pytest suite for 12 scripts + validator added on branch `test/script-suite`; 91 passed, 2 skipped; validate.py 0 errors; PR pending owner merge
## Done this thread
- Added `tests/` (conftest.py, test_validator.py, test_offline.py, 12 per-script test files): 91 passed, 2 skipped (docx/pypdf-absent branches; both installed in CI)
- Wired script tests into `.github/workflows/validate.yml` ("Script tests" step after "Repo validator")
- No genuine script bugs found; 3 initial failures were wrong test expectations, fixed in tests (see docs/TEST-FINDINGS.md)
- Note: repo contains 12 scripts, not 14 as the brief stated (the brief's own enumerated list also names 12)
## Changed files
- `tests/` (new, 15 files)
- `.github/workflows/validate.yml` (added Script tests step)
- `docs/TEST-FINDINGS.md` (new)
- `HANDOFF.md` (this update)
## Open items (owner)
- Merge PR `test/script-suite` once CI is green (one tap: Compare & pull request)
- (carried over) Supply real inputs: rate-card.csv, master-resume.md, story-bank.md, profile-keywords.txt
- (carried over) Install upstream skills per VENDORED.md and pin shas; superpowers + anthropics/skills via Claude Code plugin marketplace
- (carried over) Behavioural evals (with-skill vs without, per evals/evals.json); tune descriptions for triggering
- (carried over) Dedupe workflow YAMLs (ci-cd-vercel-github/assets/workflows ↔ project-bootstrap/assets/workflows)
- (carried over) `vendor/pins.txt` + `scripts/vendor-sync.sh`
## Next thread starts with
"Read HANDOFF.md. Merge PR test/script-suite if CI is green. Then run behavioural evals for skills/presales (evals.json per skill) with and without the skill; report trigger accuracy and output quality."
