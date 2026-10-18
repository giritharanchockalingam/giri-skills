---
name: systematic-debugging-runner
description: Use when a test fails, a build breaks or an exception shows up and you want the evidence organised before anyone touches the code — "why is this test failing", "debug this stack trace", "did my change break this", "root-cause this error". Produces debug.json and debug-log.md (Symptom, Evidence, Hypotheses, Next experiment, Fix gate) by parsing a Python, JS/TS or Java failure log, finding the innermost in-repo frame, correlating frames with the lines a recent diff touched (regression-likely vs not) and ranking hypotheses that each carry a falsifying test; the fix gate stays closed until one is confirmed. Runnable wrapper of the vendored systematic-debugging skill. Not for applying the fix (use safe-fix) or for performance profiling.
license: MIT
metadata:
  domain: build
  adlc_stage: improve
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: log, type: file, required: true, from: "failure log: pytest/unittest output, Jest/Vitest/Node output, or a Java stack trace (paste into a .txt file)"}
      - {name: diff, type: file, required: false, from: "unified diff of recent changes (`git diff <last-green>...HEAD > recent.patch`); without it no regression check"}
      - {name: repro, type: file, required: false, from: "reproduction steps, one per line (layout: assets/repro-template.md); without it the first experiment is to establish a repro"}
      - {name: narrative, type: flag, required: false, flag: "--narrative", from: "true to have the LLM write the investigation narrative from the debug log and the upstream method"}
    run:
      - {step: debug-log, kind: script, cmd: "python3 -I scripts/debug_log.py --log {log} [--diff {diff}] [--repro {repro}] --json {out}/debug.json --md {out}/debug-log.md"}
      - {step: investigation, kind: llm, template: assets/investigation-template.md, context: ["../../../vendor/systematic-debugging/SKILL.md", "../../../vendor/systematic-debugging/root-cause-tracing.md", "{out}/debug.json", "{out}/debug-log.md", "references/debug-method.md"], out: "{out}/investigation.md", skip_if_missing: [narrative]}
    outputs:
      - {path: "{out}/debug.json", checks: [exists, json, cmd:"python3 -I scripts/debug_log.py --validate {path}"]}
      - {path: "{out}/debug-log.md", checks: [exists, sections:["Symptom","Evidence","Hypotheses","Next experiment","Fix gate"], contains:"Fix allowed: NO", no_unowned_tbd]}
---

# systematic-debugging-runner

Wraps `systematic-debugging` from obra/superpowers (pinned in vendor/pins.json). The upstream skill is the method; this skill makes its first three phases (read the error, check recent changes, form testable hypotheses) a deterministic run, and passes the upstream instructions to the optional narrative step by path (`../../../vendor/systematic-debugging/SKILL.md`), never by copy.

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/systematic-debugging-runner --input <name>=<value> … --out <dir>` (see `--explain build/systematic-debugging-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. A log with no parsable exception stops the run (script exit 2) instead of inventing a symptom.

## When to use
- A failing test, CI job or crash with a stack trace, before proposing any fix.
- "Did my change break this?" — supply the diff and read the classification.
- NOT for: applying or verifying the fix (`safe-fix`), security review of a diff (`security-review`), performance profiling, flaky-test statistics across many runs.

## Inputs required
| Input | Required | Source |
|---|---|---|
| `log` | yes | Test output or stack trace as text. Python tracebacks and pytest output, JS/TS (Node, Jest, Vitest), Java (incl. `Caused by:` chains). |
| `diff` | no | Unified diff since the last green build. Without it the classification is `no-diff`. |
| `repro` | no | Exact steps to reproduce (assets/repro-template.md). Missing → marked `[TO BE BASELINED — owner: Reporting engineer]` and made experiment 1. |
| `narrative` | no | `true` runs the LLM step that writes the investigation narrative. |

## Procedure
1. **Parse the log** (`scripts/debug_log.py`): error type and message (the deepest Java `Caused by:`; the last Python exception), stack frames (file, line, function), stored innermost first.
2. **Find the innermost in-repo frame**: skip site-packages, node_modules, runtime and JDK/JUnit frames (`references/debug-method.md`).
3. **Correlate with the diff**: a frame overlaps by file (path-suffix or Java package path) and by line (inside a changed hunk). Any overlap → `regression-likely`.
4. **Rank hypotheses by evidence**: changed line in the stack (3) > changed file or error-type signal at an in-repo frame (2) > weak (1). Each has one falsifying test and status `untested`.
5. **Next experiment**: establish a repro if none was given, then run the top hypothesis's falsifying test.
6. **Fix gate**: always written closed. It opens only when a hypothesis is confirmed by its experiment and a failing test reproduces the defect; after three failed fixes, stop and question the design.
7. Optional: with `narrative=true` the LLM fills `assets/investigation-template.md` from the debug log and the upstream method.

## Output
- `debug.json` — symptom, frames (with in-repo and overlap flags), classification, ranked hypotheses, next experiments, gate. Checked by `debug_log.py --validate` (ranked, every hypothesis falsifiable, gate not open without confirmation).
- `debug-log.md` — Symptom, Evidence, Hypotheses, Next experiment, Fix gate.
- `investigation.md` (only with `narrative=true`) — narrative per `assets/investigation-template.md`.

## Self-check
- [ ] Error type and message are quoted from the log, never paraphrased into a different error
- [ ] Every hypothesis has a falsifying test and the table is ranked by evidence score
- [ ] Regression claims rest on a frame that the diff touches, not on timing alone
- [ ] Missing repro is marked with an owner and is experiment 1
- [ ] The fix gate says NO; no fix is proposed in any output

## References
- `references/debug-method.md` — parsing rules, in-repo heuristics, scoring and the gate
- `assets/repro-template.md` — reproduction steps layout
- `assets/investigation-template.md` — narrative template for the optional LLM step
- `scripts/debug_log.py` — parser, correlator and contract validator (argparse; stdlib)
- Upstream method: `vendor/systematic-debugging/` (SKILL.md, root-cause-tracing.md)
