---
name: prompt-spec
description: Use when a production prompt must be written, versioned or changed under control — "turn this prompt into a spec", "lint our prompt", "version this system prompt", "add regression tests for the prompt", "check the prompt fits the token budget", "the examples don't match the output schema". Produces prompt.md (rendered system/user template with a version header), prompt-lint.json (findings with severity) and prompt-tests.jsonl (one regression case per example, ready for an eval harness) from a prompt spec JSON (id, semver version, role, task with {{variables}}, declared variables, JSON output schema, constraints, examples, max input tokens). Lints variable declarations both ways, required variables per example, example outputs against the schema (stdlib JSON Schema subset) and a chars/4 token estimate; any error blocks rendering. Not for running the evals (llm-eval-harness), choosing a model (model-selection) or adversarial testing (red-team-suite).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: spec, type: json, required: true, from: "prompt spec JSON: id, version, role, task, variables, output_schema, constraints, examples, max_input_tokens (layout: assets/prompt-spec-template.json)"}
      - {name: previous, type: json, required: false, from: "prompt spec JSON of the version in production; every change is classified major/minor/patch and the version bump is enforced"}
    run:
      - {step: lint-render, kind: script, cmd: "python3 -I scripts/prompt_spec.py --spec {spec} [--previous {previous}] --out-dir {out}"}
    outputs:
      - {path: "{out}/prompt-lint.json", checks: [exists, json, contains:"\"status\": \"pass\"", contains:"chars / 4"]}
      - {path: "{out}/prompt.md", checks: [exists, sections:["System","User","Variables","Regression cases"], contains:"<!-- prompt-spec:", no_unowned_tbd]}
      - {path: "{out}/prompt-tests.jsonl", checks: [exists, contains:"\"prompt_version\"", cmd:"python3 -I scripts/prompt_spec.py --verify-tests {path}"]}
    modes:
      new:      {case: agent-happy-path, bring: "a prompt spec written from the template"}
      existing: {case: agent-mode-existing, bring: "the new spec plus the spec of the version in production"}
---

# Prompt Spec

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/prompt-spec --input <name>=<value> … --out <dir>` (see `--explain ai-platform/prompt-spec`). Report the `run.json` results; do not hand-write the deliverables the script produces (`prompt.md`, `prompt-lint.json`, `prompt-tests.jsonl`). Any error-severity finding exits 1 on purpose: `prompt-lint.json` is written, the prompt and tests are not.

## Starting points
- **New** — lint a spec written from `assets/prompt-spec-template.json`, render the versioned prompt and its regression cases.
- **Existing** — also pass the spec of the version in production as `previous`: each change is classed major, minor or patch for callers and consumers, the version must rise by at least that level (`E-VERSION-BUMP` blocks the render otherwise), and prompt.md adds "Changes since v<previous>".

## When to use
- Moving a prompt from a notebook or chat into a product: give it an id, a semver version and a contract.
- Changing a live prompt: bump the version, re-lint, regenerate the regression cases.
- Reviewing a prompt someone else wrote for undeclared variables, broken examples or budget overruns.
- NOT for: running cases against a model and gating on scores (`llm-eval-harness` consumes `prompt-tests.jsonl`), model choice (`model-selection`), jailbreak/injection testing (`red-team-suite`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `spec` JSON: `id`, `version`, `role`, `task`, `variables[{name, description, required}]`, `output_schema`, `constraints[]`, `examples[{inputs, output}]`, `max_input_tokens` | yes | prompt owner; `assets/prompt-spec-template.json` shows the layout |

`max_input_tokens` is the owner's budget for this call (model context minus output and safety margin); the skill does not pick it. Examples are real or representative cases the owner signs off; the skill does not write them.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. **Write the spec** from `assets/prompt-spec-template.json` following `references/spec-format.md`: role is stable instructions; task carries every per-request `{{variable}}`; output is JSON with a schema.
3. **Run** `python3 -I scripts/prompt_spec.py --spec <spec.json> --out-dir <dir>`. The linter applies the rules in `references/lint-rules.md`: variables declared ⇄ used, required variables present per example, example outputs valid against `output_schema` (subset: `type`, `properties`, `required`, `enum`, `items`), token estimate (chars/4, labelled an estimate) within `max_input_tokens`.
4. **Decision point — errors.** Fix the spec, never the outputs; the prompt and tests render only from a clean spec. Warnings (missing descriptions, unsupported schema keywords, no constraints) are reviewed and either fixed or accepted in the PR.
5. **Version** per `references/versioning.md`: change to role/constraints/schema → MINOR or MAJOR; wording-only task change → PATCH. The case ids embed the version, so regressions are traceable.
6. **Hand off** `prompt-tests.jsonl` to the eval harness; verify with `python3 -I scripts/prompt_spec.py --verify-tests <dir>/prompt-tests.jsonl`.
7. Run the self-check.

## Output
- `prompt-lint.json`: status, severity counts, token estimates per example and for the template, findings `{code, severity, where, message}`.
- `prompt.md`: header comment and table (id, version, spec SHA-256, budget, estimate), System, User, Variables, Regression cases.
- `prompt-tests.jsonl`: per example `id` (`<prompt>@<version>#ex-NN`), inputs, rendered `system` and `input`, `expected`, `output_schema`, assertions (`json_valid`, `json_schema`, `equals` on enum/boolean fields).

## Self-check
- [ ] `prompt-lint.json` status is pass, with warnings reviewed
- [ ] Version bumped for any change since the last release
- [ ] Every example is a case the owner accepts as correct, not an invented one
- [ ] Token figures are reported as estimates (chars/4), not tokenizer counts
- [ ] `--verify-tests` passes on `prompt-tests.jsonl`

## References
- `references/spec-format.md` — field-by-field spec format and the supported JSON Schema subset
- `references/lint-rules.md` — every finding code, severity and fix
- `references/versioning.md` — semver for prompts and how case ids carry it
- `assets/prompt-spec-template.json` — spec layout to copy
- `scripts/prompt_spec.py` — linter, renderer, test-case verifier (argparse; stdlib)
