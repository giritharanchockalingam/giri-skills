# Brief — "Starting new" and "Improving what exists" for every skill

Goal: every skill works, provably, for both greenfield ("new": starting from scratch) and brownfield ("existing":
improving, assessing or extending something that already exists) — or says plainly that only one applies and why.

## What to add, per skill (SKILL.md `metadata.agent`)

```yaml
    modes:
      new:      {case: <eval case id>, bring: "<what the person brings, ≤ 12 plain words>"}
      existing: {case: <eval case id>, bring: "<what the person brings, ≤ 12 plain words>"}
```

- `new` = the person has nothing yet (an idea, answers to questions, a brief, a template filled in).
- `existing` = the person brings something real that already exists: an existing migration folder, a live request
  log, last quarter's risk register, a deck to redline, an existing PRD, a running repo, a current WBS/inventory.
  An `existing` run must *read and act on* that artifact (assess it, find gaps, extend it, redline it) — not ignore it.
- `bring` is shown in the UI. Plain words, no file names, no jargon. e.g. "your answers to six questions about the
  idea", "your existing Supabase migrations folder", "the request log from production".
- Each mode points to an eval case in `evals/evals.json` that has `inputs` (fixture paths start `evals/`).
  Reuse `agent-happy-path` where it genuinely is that mode. Otherwise add a case with id `agent-mode-new` or
  `agent-mode-existing`, with fixtures under `evals/fixtures/`, plus the same `expect` style the file already uses.
- Add a short `## Starting points` section to the SKILL.md body (2–4 lines): what each mode does with your input.

## Rules (non-negotiable)

1. No fake runs. Each declared mode must pass:
   `python3 scripts/run_skill.py --demo <domain/name> --mode <new|existing> --provider none`
   → exit 0 and every declared output check passes. Verify with
   `python3 scripts/modes_check.py --run --skills "skills/<domain>/<name>"`.
2. Fixtures are fictional and labelled as such (first line/comment or a `_note` column/field, the way existing
   fixtures in the repo do it). Realistic, internally consistent, no real company or person.
3. If the skill's scripts cannot genuinely handle the brownfield input (e.g. a generator that only creates from
   scratch), **extend the script** so it does (e.g. accept an existing file and merge/diff/redline against it), with
   unit tests in `tests/test_<domain>_<name>*.py` (follow the existing test style). Enterprise quality; no hacks.
   Do not break existing behaviour: existing tests must keep passing.
4. Only if a mode truly does not apply (e.g. a postmortem always concerns an incident that happened), declare just
   the one mode and say why in one line under `## Starting points` ("Only for existing: …").
5. Do not touch files outside your assigned skills, `tests/` for those skills, and nothing in `studio/`.
   Do not commit. Do not edit `scripts/` shared files.
6. Finish by running, for your skills: `python3 scripts/modes_check.py --run --skills "skills/<domain>/*"` (or per
   skill) and the skills' tests (`python3 -m pytest -q tests -k <name>`). Report a table:
   skill | modes | case ids | script changes (y/n) | result.
