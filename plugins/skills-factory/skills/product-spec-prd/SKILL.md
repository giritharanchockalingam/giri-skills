---
name: product-spec-prd
description: Use when a product feature or capability needs defining before engineering planning — "write a PRD", "spec this feature", "what should v1 include", a vague idea that must become goals, non-goals, user stories, success metrics and phased scope. Produces docs/prd/<slug>.md from the PRD template, with acceptance criteria ready for spec-to-plan. Wraps the product-management:write-spec skill when installed. Not for technical plans (use spec-to-plan) or architecture decisions (ADR).
license: MIT
metadata:
  domain: build
  adlc_stage: requirements
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: brief, type: json, required: true, from: "brief.json: {feature, problem, users[], goals[], non_goals[], metrics[{name,target,baseline}], phases[{name,scope[]}]} (layout: evals/fixtures/brief.json)"}
      - {name: existing, type: md, required: false, from: "the team's existing PRD to redline against the brief (storyline kept; [KEEP]/[SHARPEN]/[ADD]/[TBD]); no model step"}
      - {name: draft_only, type: flag, required: false, flag: "--draft-only", from: "true to skip the model sharpen step: the checked script draft becomes prd-final.md"}
    run:
      - {step: prd, kind: script, cmd: "python3 -I scripts/prd.py {brief} --template assets/prd-template.md --out {out}/PRD.md --final {out}/prd-final.md {draft_only} [--existing {existing}] --redline {out}/PRD-redline.md"}
      - {step: sharpen, kind: llm, template: assets/prd-template.md, context: ["{out}/PRD.md", "references/prd-method.md", "references/prd-review-checklist.md"], out: "{out}/prd-final.md", skip_if_present: [existing, draft_only]}
    outputs:
      - {path: "{out}/PRD.md", checks: [exists, sections:["Problem","Users","Goals","Non-goals","Metrics","Phases","Engineering handoff"]]}
      - {path: "{out}/prd-final.md", checks: [exists, sections:["Problem","Goals","Non-goals","Metrics","Phases"], no_unowned_tbd]}
    modes:
      new: {case: agent-mode-new, bring: "a short brief: problem, users, goals, metrics, phases"}
      existing: {case: agent-mode-existing, bring: "your existing PRD and the brief's facts"}
---

# product-spec-prd

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py build/product-spec-prd --input <name>=<value> … --out <dir>` (see `--explain build/product-spec-prd`). Report the `run.json` results; do not hand-write the deliverables the scripts produce. Every brief field the script cannot find becomes `[TO BE BASELINED — owner: ___]`; the sharpen step may tighten wording but must not invent numbers, users or dates.

## Starting points
- **New** — your brief becomes a PRD on the template (`PRD.md`); the model step sharpens it into `prd-final.md`, or with `draft_only` the checked script draft is the final PRD. Nothing the brief does not say is invented.
- **Existing** — add `existing` (your current PRD): it is redlined section by section against the brief and the review checklist — [KEEP], [SHARPEN], [ADD], and every figure the brief does not back marked [TBD] with an owner — and `prd-final.md` is your PRD with the redline applied, storyline unchanged.

## When to use
- A feature idea, customer ask, or roadmap item needs a definition engineers can plan from.
- Scope disputes ("is X in v1?"), success metrics missing, phased rollout needed.
- NOT for: implementation plans (`spec-to-plan`), tech choices (`project-bootstrap/assets/adr-template.md`), whole-product strategy.

## Inputs required
| Input | Required | Source |
|---|---|---|
| Problem statement or feature idea | yes | user |
| Target users / personas | yes | `docs/SPEC.md` / user — ask once |
| Constraints (deadline, platform, compliance, budget) | no | user |
| Evidence (customer requests, data, support tickets) | no | user — mark absent as assumption |
| Existing product context (`docs/SPEC.md`, related PRDs) | yes if present | repo |

If a required input is missing, ask for it once; do not guess.

## Procedure
1. Read `../../shared/quality-bar.md`, `../../shared/writing-style.md`, then `docs/SPEC.md` and any related PRD.
2. **Frame.** If the upstream skill `product-management:write-spec` is installed (see VENDORED.md), invoke it for steps 2–4 and then apply the template and gates below; otherwise follow `references/prd-method.md`: problem → who → why now → what success looks like. Ask ≤5 questions with defaults, once. *(gate: plan inputs)*
3. **Draft** `docs/prd/<slug>.md` from `assets/prd-template.md`: goals (measurable), non-goals (explicit), user stories with acceptance criteria (Given/When/Then), phased scope (v1 / v1.1 / later), metrics with baseline and target, risks, open questions with owners, dependencies.
4. **Challenge.** Run `references/prd-review-checklist.md` against the draft: every goal has a metric; every story has a criterion; every non-goal is something a reader would assume included; v1 is the smallest slice that moves the metric.
5. **Present.** Post the exec summary (≤5 bullets) and the v1 scope table; wait for approval or redlines. Apply redlines per the redline convention (keep storyline, sharpen). *(gate: plan→approve)*
6. **Hand off.** Add a "Engineering handoff" section: acceptance criteria list ready for `spec-to-plan`, data/tenancy implications for `multi-tenant-saas-patterns`, flag name per `plans-and-flags` naming. *(gate: build via spec-to-plan)*
7. **Verify** after build: metrics instrumented (`observability-setup` log `action`/`outcome` events), success review date set. *(gate: verify)*
8. Update `docs/HANDOFF.md`.

## Output
| Artifact | Path |
|---|---|
| PRD | `docs/prd/<yyyy-mm-dd>-<slug>.md` |
| Exec summary | chat, ≤5 bullets |
| Engineering handoff | PRD §Engineering handoff → input to `spec-to-plan` |

## Self-check
- [ ] First line of the PRD states the outcome and the metric it moves
- [ ] Every goal measurable; baseline sourced or `[TO BE BASELINED — owner: ___]`
- [ ] Non-goals list ≥ 3 things readers would assume
- [ ] Every user story has Given/When/Then acceptance criteria
- [ ] v1 scope fits one `spec-to-plan` plan (≤ 8 tasks) or is split into phases
- [ ] Open questions have owners and dates
- [ ] No invented numbers, customers, or dates

## References
- `references/prd-method.md` — framing questions, scoping rules, metric design (fallback for write-spec)
- `references/prd-review-checklist.md` — challenge list used before presenting
- `assets/prd-template.md` — PRD template
- `scripts/prd.py` — brief.json → PRD.md on the template; missing arrays become `[TO BE BASELINED — owner: ___]` rows
