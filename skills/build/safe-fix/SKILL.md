---
name: safe-fix
description: Use when the user reports a bug or says "fix this" — an error, stack trace, failing test, wrong behaviour, "works in staging not prod". Produces a reproduction, an isolated root cause with evidence, a minimal diff that touches only the failing path, a regression test that fails before and passes after, and full-suite verification — never collateral breakage, never data patches. Wraps superpowers systematic-debugging plus Karpathy-style guardrails when installed. Not for features (use spec-to-plan) or security findings without a repro (use security-review).
license: MIT
metadata:
  domain: build
  adlc_stage: improve
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: target, type: dir, required: true, from: "repo directory the test command runs in"}
      - {name: cmd, type: string, required: true, from: "the full test command, e.g. \"python3 -m pytest -q\" or \"npx vitest run\""}
      - {name: baseline, type: json, required: false, from: "baseline.json recorded by `safefix.py baseline` before the fix; without it the baseline is taken now (pre-fix state)"}
    run:
      - {step: baseline, kind: script, cmd: "python3 -I scripts/safefix.py baseline --target {target} --cmd {cmd} --out {out}/baseline.json", skip_if_present: [baseline]}
      - {step: verify, kind: script, cmd: "python3 -I scripts/safefix.py verify --target {target} --cmd {cmd} [--baseline {baseline}] --out {out}/verify.json"}
    outputs:
      - {path: "{out}/verify.json", checks: [exists, json, contains:"collateral"]}
    modes:
      existing: {case: agent-happy-path, bring: "your repo, its test command and the fix you made"}
---

# safe-fix

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/safe-fix --input <name>=<value> … --out <dir>` (see `--explain build/safe-fix`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Typical flow: run once before the fix (writes `baseline.json`), apply the fix, run again with `--input baseline=<dir>/baseline.json`; any newly failing test is collateral and the run exits 1.

## Starting points
- **Existing** — the test suite is snapshotted before the fix (or your recorded baseline is used), re-run after it, and any test that was green and is now red is reported as collateral damage.
- Only for existing: a fix always lands in code and a test suite that already exist; there is nothing to fix from scratch.

## When to use
- "Fix this bug", an error message, stack trace, failing CI job, "it used to work", production incident follow-up.
- NOT for: new behaviour (`spec-to-plan`), "clean this up" (`nextjs-enterprise-conventions`), pipeline-only failures (`ci-cd-vercel-github` troubleshooting), vulnerability review (`security-review`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Observed behaviour + expected behaviour | yes | user |
| Evidence: error text, stack, failing test name, `requestId`, logs, steps | yes (at least one) | user / logs |
| Environment where it happens (local / preview / prod) and version/sha | yes | user — ask once |
| Repo access | yes | repo |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../../shared/token-efficiency.md` (rules 2, 8, 9, 10 govern this skill) and `references/never-collateral.md`.
2. **Reproduce.** Write the smallest deterministic reproduction: a failing unit/integration test, or an exact command/request. If it cannot be reproduced, stop and gather more evidence (`references/safe-fix-method.md` §Reproduce). No fix without a repro. *(gate: repro exists and fails)*
3. **Isolate.** If the upstream skill `superpowers:systematic-debugging` is installed (see VENDORED.md), invoke it for this step; otherwise follow `references/safe-fix-method.md` §Isolate: trace from symptom to cause with evidence at each hop, bisect (git / inputs / layers), state the root cause in one sentence with file:line. Distinguish root cause from trigger.
4. **Plan the fix.** Post: root cause, the single path to change, files touched (expect 1–3), the regression test, blast radius (who else calls this), rollback. Wait for "go" if the fix touches shared code, schema, auth, or >3 files. *(gate: plan→approve)*
5. **Minimal diff.** Change only the failing path. No renames, no reformatting, no "while I'm here". If the fix needs a refactor, do the refactor as a separate, behaviour-preserving step with the suite green in between.
6. **Regression test.** The repro from step 2 becomes a permanent test named after the bug (`it('does not <bug> when <condition>')`). It must fail on the pre-fix code (verify by stashing the fix once) and pass after. *(gate: build→test)*
7. **Verify the whole, not the part.** Run lint, typecheck, the full unit suite, affected integration/e2e, and build. Re-check every caller of the changed function (grep) for changed assumptions. *(gate: test→verify)*
8. **Fix in code, not data.** If the bug produced bad rows, handle the scenario in code going forward and write a one-off, reviewed migration/backfill for the existing rows — never hand-edit data as the fix.
9. Report with `assets/fix-report.md`; update `docs/HANDOFF.md`.

## Output
| Artifact | Form |
|---|---|
| Root cause statement | one sentence, file:line, evidence |
| Diff | minimal; 1–3 files typical |
| Regression test | `tests/**`, named after the bug |
| Verification | command summary table |
| Fix report | `assets/fix-report.md` filled, in PR description |

## Self-check
- [ ] Repro existed and failed before the change
- [ ] Root cause stated with evidence (not "probably")
- [ ] Diff touches only the failing path; no formatting/renames/unrelated edits
- [ ] Regression test fails on old code, passes on new
- [ ] Full suite green; callers of changed code re-checked
- [ ] No data patched by hand; no `any`, no try/catch swallow, no test skipped or weakened
- [ ] Rollback stated

## References
- `references/safe-fix-method.md` — reproduce → isolate → minimal diff → regression test → verify, with techniques
- `references/never-collateral.md` — the guardrails (what a fix may never do)
- `references/common-bugs-stack.md` — recurring causes in Next.js/Supabase/Vercel apps
- `assets/fix-report.md` — report template
- `scripts/safefix.py` — `baseline` / `verify`: snapshots the test suite before a fix and fails (exit 1) on any newly failing test
