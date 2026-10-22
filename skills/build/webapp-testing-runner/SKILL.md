---
name: webapp-testing-runner
description: Use when you need end-to-end browser tests for a web app's user flows and want them generated from a plain flow list — "write Playwright tests for these flows", "generate e2e tests for login and checkout", "turn these user journeys into tests", "check my flow selectors". Produces test_flows.py (pytest-playwright, headless Chromium, networkidle waits, role/text/label/test-id locators) and flows-report.md (Flows with a coverage matrix, Generated tests, Warnings, How to run) after validating the flows JSON (known actions, required fields, brittle selector warnings); the file is verified with compile() and labelled generated, not executed, because the portal cannot launch a browser. Runnable wrapper of the vendored webapp-testing skill. Not for running the tests, visual regression, load testing, unit tests, or setting up vitest/playwright in a repo that has none (use test-strategy-tdd).
license: MIT
metadata:
  domain: build
  adlc_stage: evaluate
  version: 0.2.0
  author: giri-skills
  fits:
    stacks: [nextjs, react]
    request_kinds: [feature, hardening, greenfield]
  agent:
    inputs:
      - {name: flows, type: json, required: true, from: "user flows JSON (layout: assets/flows-template.json): base_url (URL or ${BASE_URL} placeholder) and flows[{name, steps[{action, selector?, value?}]}]"}
      - {name: narrative, type: flag, required: false, flag: "--narrative", from: "true to have the LLM write a test-plan review (reconnaissance, selector fixes, gaps) from the report and the upstream method"}
      - {name: existing, type: dir, required: false, from: "your current e2e test folder (pytest-playwright or Playwright TS); flows it already covers are not generated again"}
    run:
      - {step: generate, kind: script, cmd: "python3 -I scripts/gen_tests.py --flows {flows} [--existing {existing}] --test-out {out}/test_flows.py --report {out}/flows-report.md"}
      - {step: plan-review, kind: llm, template: assets/test-plan-review-template.md, context: ["../../../vendor/webapp-testing/SKILL.md", "{out}/flows-report.md", "{out}/test_flows.py", "references/flow-format.md"], out: "{out}/test-plan-review.md", skip_if_missing: [narrative]}
    outputs:
      - {path: "{out}/test_flows.py", checks: [exists, contains:"GENERATED, NOT EXECUTED", cmd:"python3 -I scripts/gen_tests.py --verify-compiles {path}"]}
      - {path: "{out}/flows-report.md", checks: [exists, sections:["Flows","Generated tests","Warnings","How to run"], contains:"not executed"]}
    modes:
      new: {case: agent-happy-path, bring: "the user flows you want tested"}
      existing: {case: agent-mode-existing, bring: "the user flows and your current end-to-end tests"}
---

# webapp-testing-runner

Wraps `webapp-testing` from anthropics/skills (pinned in vendor/pins.json). Upstream drives a live browser with native Python Playwright; the portal cannot launch one, so this skill turns the same method (headless Chromium, wait for `networkidle`, descriptive selectors) into a generator plus static checks, and passes the upstream instructions to the optional review step by path (`../../../vendor/webapp-testing/SKILL.md`), never by copy.

## In a conversation: write the tests now
- **The flows are stated in the conversation** (flows JSON or plain steps): write both outputs **in this reply** — `test_flows.py` with one `test_<flow>` per flow using the pytest-playwright `page` fixture, `page.wait_for_load_state("networkidle")` after every `goto`, `role=`/`text=`/`label=`/`placeholder=`/`testid=` mapped to `get_by_role`/`get_by_text`/`get_by_label`/`get_by_placeholder`/`get_by_test_id`, the base URL read from the `BASE_URL` environment variable, and `GENERATED, NOT EXECUTED` in the module docstring; then `flows-report.md` — Flows (coverage matrix: steps per action, assertions, selector kinds), Generated tests, Warnings (nth-child/nth-of-type, XPath, generated class names, long CSS chains, each with a better selector kind; flows not starting with `goto` or without an `expect_*` step), How to run (`pip install pytest-playwright && playwright install chromium`, then `BASE_URL=… pytest test_flows.py`). State plainly that the tests were generated and compile-checked, not executed; claim no pass/fail.
- **Validate first**: known actions only (`goto`, `click`, `fill`, `expect_text`, `expect_url` — `hover` is not one), required fields per action, unique flow names, non-empty steps, base_url present. Any error: report every error, write no test file, and say the run failed.
- **Existing e2e tests supplied**: match each flow to the existing test that covers it, list it with the covering test and do not regenerate it; generate only the gaps, and still report selector warnings for every flow.
- **The request says a flows file or test folder is here but its contents are not in the conversation**: still write the skeleton now — one test function per flow the request names, the report sections above, and every selector, value or URL not given as `[TO BE BASELINED — owner: ___]` naming the flows file. With a review request, also lay out the test-plan review per `assets/test-plan-review-template.md` (Reconnaissance plan, Selector review, Gaps, How to run) per the upstream method. Never reply with only a request for files.
- **No flows at all** ("write e2e tests for my app"): ask once for the flows JSON (`assets/flows-template.json`) — pages, selectors and URLs are never invented.

## Starting points
- **New** — every flow is validated and turned into a pytest-playwright test (generated and compile-checked, never executed here).
- **Existing** — add your current e2e folder: its tests are read, flows they already cover are listed with the covering test and not generated again, and only the gaps are written.

## When to use
- Turning a list of user journeys into a Playwright suite the team can run locally or in CI.
- Reviewing flow selectors for brittleness before the suite is written.
- NOT for: executing tests or reporting pass/fail (needs a browser), unit/integration test scaffolding (`test-strategy-tdd`), visual or load testing.

## Inputs required
| Input | Required | Source |
|---|---|---|
| `flows` | yes | JSON per `assets/flows-template.json`. Actions: `goto`(value), `click`(selector), `fill`(selector, value), `expect_text`(value[, selector]), `expect_url`(value). |
| `narrative` | no | `true` runs the LLM step that writes the test-plan review. |

The base URL is never guessed: the generated file reads `BASE_URL` from the environment; a placeholder in the JSON makes tests skip until it is set.

## Procedure
1. **Validate** (`scripts/gen_tests.py`): base_url present, flows non-empty, unique names, known actions, required fields per action, string types. Any error → report with the errors, no test file, exit 1.
2. **Warn** on selector style: nth-child/nth-of-type, XPath, generated class names, long CSS chains (warning); bare CSS (info); flows not starting with `goto` or with no `expect_*` step.
3. **Generate** `test_flows.py`: one `test_<flow>` per flow using the pytest-playwright `page` fixture; `goto` is followed by `wait_for_load_state("networkidle")`; `role=`/`text=`/`label=`/`placeholder=`/`testid=` map to `get_by_*` locators.
4. **Verify** with `compile()` and stamp `GENERATED, NOT EXECUTED` in the module docstring.
5. **Report** `flows-report.md`: coverage matrix (steps per action, assertions, selector kinds per flow), static-check result, warnings, how to run (incl. the upstream `with_server.py` helper).
6. Optional: with `narrative=true` the LLM fills `assets/test-plan-review-template.md`.

## Output
- `test_flows.py` — runnable with `BASE_URL=… pytest test_flows.py` after `pip install pytest-playwright && playwright install chromium`.
- `flows-report.md` — Flows, Generated tests, Warnings, How to run.
- `test-plan-review.md` (only with `narrative=true`).

## Self-check
- [ ] Every flow became exactly one test function; names are unique
- [ ] Every flow has at least one assertion, or a warning says it does not
- [ ] Brittle selectors are listed under Warnings with a better alternative kind
- [ ] The file compiles and says GENERATED, NOT EXECUTED; no pass/fail result is claimed anywhere
- [ ] No URL or credential was invented; values come from the flows file

## References
- `references/flow-format.md` — flow JSON schema, selector mapping, warning rules
- `assets/flows-template.json` — input layout
- `assets/test-plan-review-template.md` — narrative template for the optional LLM step
- `scripts/gen_tests.py` — validator, generator and compile check (argparse; stdlib)
- Upstream method: `vendor/webapp-testing/SKILL.md` (and its server-lifecycle helper, vendor/webapp-testing/scripts/with_server.py)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/webapp-testing-runner --input <name>=<value> … --out <dir>` (see `--explain build/webapp-testing-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Say plainly that the tests were generated and compiled, not executed; results exist only after the user runs them.
