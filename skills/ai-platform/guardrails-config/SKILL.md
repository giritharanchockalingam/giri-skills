---
name: guardrails-config
description: Use when the user needs input/output guardrails for an LLM app or agent — "set up guardrails", "block prompt injection", "mask PII in prompts and replies", "limit which tools the agent can call", "test our guardrail policy before go-live". Compiles a policy JSON (blocked topics, PII handling per type, length limits, tool allowlist, extra injection markers) into a deterministic guardrails.json and ships scripts/guard.py, a pure-Python rule engine (importable and CLI) that returns allow, mask or block; runs the user's test cases and reports pass/fail per case in guardrail-tests.json and guardrails.md. Masked outputs never echo raw PII. Exit 1 if any case's actual decision differs from expected. Not for the risk register (ai-governance-risk), model-quality evals (llm-eval-harness) or a semantic moderation model.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: deploy
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: policy, type: json, required: true, from: "guardrail policy (layout: assets/policy-template.json) - blocked_topics, pii_handling, max_input_chars, max_output_chars, allowed_tools, optional injection_markers"}
      - {name: tests, type: csv, required: false, from: "test cases case_id,direction,text,expected[,tool] (layout: assets/test-inputs-template.csv); absent = tests to be baselined"}
      - {name: baseline, type: json, required: false, from: "the compiled guardrails.json live today; the run diffs the new rules against it (tightened/loosened) and replays the tests on both"}
    run:
      - {step: compile-and-test, kind: script, cmd: "python3 -I scripts/build_guardrails.py --policy {policy} [--tests {tests}] [--baseline {baseline}] --out {out}"}
    outputs:
      - {path: "{out}/guardrails.json", checks: [exists, json, cmd:"python3 scripts/guard.py --rules {path} --validate"]}
      - {path: "{out}/guardrail-tests.json", checks: [exists, json, cmd:"python3 scripts/guard.py --scan-pii {path}"]}
      - {path: "{out}/guardrails.md", checks: [exists, sections:["Rule set","PII handling","Tool allowlist","Test results","Limits"], no_unowned_tbd, cmd:"python3 scripts/guard.py --scan-pii {path}"]}
    modes:
      new:      {case: agent-happy-path, bring: "your guardrail policy and test cases"}
      existing: {case: agent-mode-existing, bring: "the rule set live today plus your revised policy"}
---

# Guardrails Config

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/guardrails-config --input <name>=<value> … --out <dir>` (see `--explain ai-platform/guardrails-config`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`guardrails.json`, `guardrail-tests.json`, `guardrails.md`). A test case whose actual decision differs from its expected one fails the run (exit 1) on purpose; fix the policy or the expectation, never the output.

## Starting points
- **New** — compile a policy written from `assets/policy-template.json` and test it with your cases.
- **Existing** — also pass the `guardrails.json` live today as `baseline`: every rule change is marked tightened or loosened, each test case is replayed on both rule sets, and loosened rules are flagged for sign-off ("Changes vs live rules").

## When to use
- Before deploying an LLM app or agent: a first, deterministic layer for prompt-injection markers, banned topics, PII, length and tool access.
- Turning a written policy into enforceable rules plus a regression suite that runs in CI.
- NOT for: the risk register and controls catalogue (`ai-governance-risk` — this skill implements some of its controls); answer-quality evals (`llm-eval-harness`); semantic content moderation or jailbreak classifiers (layer one on top; see Limits).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `policy` JSON: `blocked_topics`, `pii_handling` {email, phone, card, ssn: mask/block/allow}, `max_input_chars`, `max_output_chars`, `allowed_tools`, optional `injection_markers` | yes | AI security lead and Data protection officer; every value is a policy decision |
| `tests` CSV: `case_id, direction (in/out), text, expected (allow/block/mask)`, optional `tool` | no | product and security team; fixture rows labelled fictional; real PII never belongs in a test file |

A PII type missing from `pii_handling` is compiled as un-actioned (allow) and reported `[TO BE BASELINED — owner: Data protection officer]`. Without `tests`, Test results read `[TO BE BASELINED — owner: AI security lead]`. Unknown policy keys exit 2 (typos never silently disable a rule).

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Write the policy from `assets/policy-template.json` with `references/guardrail-design.md` (what each rule type catches and misses).
3. Write test cases from `assets/test-inputs-template.csv`: at least one allow, one block and one mask per rule type, plus evasion variants (case, spacing, line breaks) and tool calls on and off the allowlist.
4. Run the agent (above) or the script: `python3 -I scripts/build_guardrails.py --policy policy.json --tests cases.csv --out <dir>`.
5. Fix mismatches by changing the policy (or a wrong expectation) and re-run until exit 0.
6. Wire `scripts/guard.py` into the app: `from guard import load_rules, evaluate` on every user input (`direction="in"`), model output (`"out"`) and tool call (`tool=`); block or replace text per the decision. Add the test CSV to CI.
7. Run the self-check.

## Output
- `guardrails.json`: schema id, policy sha256, limits, ordered rules (blocked_topic, injection, pii with pattern, validator, mask token, action), tool allowlist (default deny), unconfigured PII types.
- `guardrail-tests.json`: per case expected, actual, pass, rule-id reasons, PII counts, redacted text; totals.
- `guardrails.md`: sections Rule set, PII handling, Tool allowlist, Test results, Limits. The Limits section must open with this Known limitations note: "The prompt-injection rules match fixed phrases (`assets/injection-phrases.txt` plus your `injection_markers`); a reworded attack — e.g. "kindly set aside what you were told" — can evade them. Treat this skill as a baseline policy, not a complete prompt-injection defense. Before client-facing use, layer it with model-level and system-level controls."
- `scripts/guard.py`: the runtime engine (CLI exit 0 allow/mask, 1 block; `--validate`; `--scan-pii FILE`).

## Self-check
- [ ] Every policy value came from the user; gaps carry an owned `[TO BE BASELINED]` marker
- [ ] Tests cover allow, block and mask for each rule type, plus evasion variants and tool calls
- [ ] Every case matches (exit 0) before deployment
- [ ] The Limits section of guardrails.md opens with the Known limitations note on fixed-phrase injection matching
- [ ] No raw PII in outputs: `guard.py --scan-pii` passes on guardrail-tests.json and guardrails.md
- [ ] Limits section kept; a semantic layer is planned where keyword rules are not enough

## References
- `references/guardrail-design.md` — rule types, precedence, PII detectors, evasion handling, deployment pattern, standards by name
- `scripts/build_guardrails.py` — compiler + test runner (argparse; stdlib; exit 0 / 1 mismatch / 2 input)
- `scripts/guard.py` — rule engine (importable + CLI; stdlib)
- `assets/injection-phrases.txt` — bundled prompt-injection marker phrases (starter list)
- `assets/policy-template.json`, `assets/test-inputs-template.csv` — input layouts
