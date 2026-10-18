---
name: code-review-runner
description: Use when a diff, branch or PR needs a first-pass review before a human or model reads it — "review this diff", "anything blocking in this PR", "check this change before merge", "did I leave secrets or debug prints in". Produces review.json and review.md (Summary, Blocking, Non-blocking, Tests, Files) from deterministic detectors on added lines only — hard-coded secrets and high-entropy literals, eval/exec, disabled TLS verification, SQL built by concatenation, swallowed broad exceptions, debug leftovers, owner-less TODO/FIXME, duplicated blocks, source changed without tests — each with file:line, rule and severity, plus size/risk stats and optional team rules; blocking findings fail the run. Runnable wrapper of the vendored code-review skill. Not for threat-model security review (use security-review) or applying fixes (use safe-fix).
license: MIT
metadata:
  domain: build
  adlc_stage: evaluate
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: diff, type: file, required: true, from: "unified diff of the change (`git diff <base>...HEAD > change.patch`)"}
      - {name: rules, type: csv, required: false, from: "team rules (layout: assets/rules-template.csv): custom regex rules and severity overrides for built-in rules"}
      - {name: spec, type: md, required: false, from: "the issue/spec the change implements; used only by the narrative step's Spec axis"}
      - {name: narrative, type: flag, required: false, flag: "--narrative", from: "true to have the LLM write the two-axis review (Standards, Spec) from the findings and the upstream method"}
    run:
      - {step: review, kind: script, cmd: "python3 -I scripts/review.py --diff {diff} [--rules {rules}] --json {out}/review.json --md {out}/review.md", expect_exit: [0, 1]}
      - {step: two-axis, kind: llm, template: assets/two-axis-review-template.md, context: ["../../../vendor/code-review/SKILL.md", "{out}/review.json", "{out}/review.md", "{spec}", "references/review-rules.md"], out: "{out}/review-two-axis.md", skip_if_missing: [narrative]}
    outputs:
      - {path: "{out}/review.json", checks: [exists, json, cmd:"python3 -I scripts/review.py --gate {path}"]}
      - {path: "{out}/review.md", checks: [exists, sections:["Summary","Blocking","Non-blocking","Tests","Files"], contains:"Verdict:"]}
---

# code-review-runner

Wraps `code-review` from mattpocock/skills (pinned in vendor/pins.json). Upstream reviews a change on two separate axes — Standards and Spec — with a Fowler smell baseline as judgement calls. This skill makes the deterministic part of the Standards axis executable and hands the upstream instructions to the optional narrative step by path (`../../../vendor/code-review/SKILL.md`), never by copy.

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/code-review-runner --input <name>=<value> … --out <dir>` (see `--explain build/code-review-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. The script always writes both outputs; the gate check on `review.json` then fails the run (exit 1) when any blocking finding remains, so a blocking diff is reported, never waved through.

## When to use
- Before merge: a quick, repeatable pass that catches the mechanical defects first.
- In CI: `review.py --gate review.json` as a required check.
- NOT for: threat modelling and authz reasoning (`security-review`), stack-specific conventions (`nextjs-enterprise-conventions`), fixing what it finds (`safe-fix`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `diff` | yes | Unified diff, three-dot against the merge base. Only added lines are scanned. |
| `rules` | no | Team rules CSV (`assets/rules-template.csv`): `rule_id,pattern,severity,message,file_glob`. A built-in id with empty pattern overrides its severity (`off` disables). |
| `spec` | no | Issue or spec text for the Spec axis of the narrative step. Without it the Spec axis reports "no spec available". |
| `narrative` | no | `true` runs the LLM step that writes the two-axis review. |

## Procedure
1. **Parse the diff** (`scripts/review.py`): files, status, hunks, added lines with new-file line numbers, removed-line counts.
2. **Stats**: files, hunks, +/-, size label (`--large-change`, default 400 changed lines), source vs test files, risky paths (auth, migrations, config, CI, env).
3. **Detect** on added lines: CR-SECRET, CR-EVAL, CR-TLS, CR-SQL-CONCAT (blocking); CR-SWALLOW, CR-DEBUG, CR-NO-TESTS (warning); CR-TODO, CR-DUP (info). See `references/review-rules.md`.
4. **Apply team rules** from the rules CSV; sort findings blocking → info, number F01….
5. **Write** `review.json` and `review.md`; exit 1 if anything is blocking.
6. **Gate**: `review.py --gate review.json` is the output check that fails the run on blocking findings.
7. Optional: with `narrative=true` the LLM fills `assets/two-axis-review-template.md` — Standards (from the findings) and Spec (from `spec`) kept separate, per the upstream method.

## Output
- `review.json` — stats, files, tests verdict, counts, verdict (PASS/BLOCK), findings `{id, rule, severity, file, line, evidence, message, fix}`; secrets redacted in evidence.
- `review.md` — Summary, Blocking, Non-blocking, Tests, Files.
- `review-two-axis.md` (only with `narrative=true`).

## Self-check
- [ ] Every finding has file:line, rule and severity; evidence never shows a full secret
- [ ] Only added lines were scanned; context and removed lines produce no findings
- [ ] Blocking findings fail the run through the gate check
- [ ] The Tests section states whether tests changed alongside source
- [ ] The Spec axis is not claimed by the script; it is the narrative step's job and needs a spec

## References
- `references/review-rules.md` — detector rules, severities, false-positive notes, overrides
- `assets/rules-template.csv` — team rules layout
- `assets/two-axis-review-template.md` — narrative template for the optional LLM step
- `scripts/review.py` — parser, detectors, renderer and gate (argparse; stdlib)
- Upstream method: `vendor/code-review/SKILL.md`
