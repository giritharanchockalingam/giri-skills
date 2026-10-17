# EVAL-FINDINGS — behavioral evals (thread 02)

> Status 2026-10-17: the harness (`scripts/behavioral_evals.py`) is built and
> verified with the `dry` provider. **No real-model run has happened yet**
> (waiting on an API key) — so there are no trigger/quality findings to report.
> This file will be populated after the pilot (`--skills 'skills/presales/*'`,
> `--max-cases 2 --runs 1`) and the full run. Proposals below are
> paste-ready description / SKILL.md changes, ranked presales → build →
> ai-platform → career. The owner applies them in thread 03; this thread
> never edits `SKILL.md`.

## Verdict key

`OK` = trigger ≥ 0.8 and lift ≥ +0.2 · `DESC` = trigger < 0.8 (description
problem) · `BODY` = lift < 0.2 (instructions don't change behavior) ·
`BOTH` = both problems.

## Findings

_(pending real run — pilot command in `docs/HANDOFF-MUSE-02.md`)_

## Broken cases

None. All 120 eval cases across the 40 skills have a non-empty `prompt` and a
non-empty `expected[]` list (scanned 2026-10-17).

## Harness notes

- The brief said "14 scripts" for thread 01; the repo contains 12 — all covered.
- Dry-run calibration: trigger accuracy 0.00 (dry router always answers
  `none`), quality 1.00 in both modes (canned judge passes everything),
  lift 0.00 → verdict `BOTH` for every skill. These numbers are pipeline
  checks, not skill assessments.
