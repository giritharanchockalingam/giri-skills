---
name: slm-demo-builder
description: Use when the user asks to build a new SLM or agent showroom demo — "add a demo for X to the studio", "build a demo an exec can click through", "I need a demo spec and talk track". Produces a demo spec (persona, scenario, happy path, wow moments, failure handling), a synthetic data plan and generator approach, a UI stub definition, and a timed talk track with objection handling. Not for production builds (use the build-domain skills) or for sizing/evaluation.
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: spec, type: md, required: true, from: "demo spec (assets/demo-spec.md layout) with §7 entity field tables: | Field | Type | Example | Constraints | (fixture: evals/fixtures/demo-spec.md)"}
      - {name: rows, type: string, required: false, default: "200", from: "rows per entity unless the spec's volume table says otherwise"}
      - {name: seed, type: string, required: false, default: "42"}
      - {name: existing, type: dir, required: false, from: "the demo folder that ships today (data-manifest.json + data/); extended without moving planted rows"}
    run:
      - {step: synthetic, kind: script, cmd: "python3 -I scripts/gen_synthetic.py {spec} --out-dir {out} --rows {rows} --seed {seed} [--existing {existing}]"}
    outputs:
      - {path: "{out}/data-manifest.json", checks: [exists, json, contains:"\"pii_guard\": \"passed\"", contains:"\"email_domain\": \"example.com\""]}
    modes:
      new:      {case: agent-happy-path, bring: "a demo spec filled in from the template"}
      existing: {case: agent-mode-existing, bring: "your demo's current data folder and the updated spec"}
---

# SLM / Agent Demo Builder

## How to run
This skill is executable. Write the demo spec (with the §7 entity field tables), then run `python3 scripts/run_skill.py ai-platform/slm-demo-builder --input spec=<demo-spec.md> [--input rows=N --input seed=S] --out <dir>` (see `--explain ai-platform/slm-demo-builder`). Report the `run.json` results; do not hand-write the synthetic dataset the script produces (`data/<entity>.csv`, `data-manifest.json`). A spec that declares an SSN / credit-card / phone field is refused (exit 1) by the PII guard; fix the spec.

## Starting points
- **New** — generate seeded, PII-guarded synthetic data from a filled-in demo spec.
- **Existing** — pass the demo's current data folder as `existing` with the updated spec: existing rows keep their values (planted cases stay put), new columns, rows and entities are added, dropped columns removed, and the manifest records every change under `extended_from`.

## When to use
- Adding a demo to a showroom or experience studio; preparing a client-specific walkthrough; turning a prototype into a repeatable 10-minute story.
- NOT for: production hardening, infra sizing (`infra-gpu-sizing`), quality proof (`llm-eval-harness`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Audience (role, industry, what they care about) | yes | user |
| Business scenario and the one decision or task the demo shows | yes | user |
| Model/stack constraints (SLM on-prem, specific gateway, offline?) | yes | user |
| Time slot (5 / 10 / 20 min) and delivery (live / recorded / self-serve) | yes | user |
| Data constraints: no real client data; domain to synthesize | yes | user; default to synthetic |
| Existing studio conventions (UI shell, auth, tenancy) | no | repo |

If audience or scenario is missing, ask once.

## Procedure
1. Read `../../../shared/quality-bar.md`, `../../../shared/writing-style.md`, `../../../shared/stack-conventions.md`.
2. **Write the demo spec** from `assets/demo-spec.md` using `references/demo-spec-guide.md`: persona, before/after, 3–5 step happy path, two "wow" moments, one deliberate failure handled well (abstention or HITL), reset procedure.
3. **Plan synthetic data** with `references/synthetic-data.md`: entities, volumes, realism rules, seeded generation (deterministic), PII-free, edge cases planted for the talk track.
4. **Define the UI stub**: screens, inputs, outputs, states (loading, empty, error), what is mocked vs live. Keep the model call real; mock the systems of record unless they are sandboxed.
5. **Write the talk track** with `references/talk-track.md`: timed beats, lines per beat, click path, anticipated questions, objection handling, and the ask at the end.
6. **Define demo readiness checks**: cold-start time, scripted inputs produce expected outputs, reset works, offline fallback (cached responses) if the venue network fails.
7. Run the self-check.

## Output
- `demo-spec-<name>.md` (spec + data plan + UI stub + talk track + readiness checklist).
- Synthetic data generator outline (script skeleton or prompt) per the data plan.

## Self-check
- [ ] One business decision per demo; no feature tour
- [ ] Synthetic data only; no client names, no real PII; generator seeded
- [ ] A handled-failure moment is scripted (abstain / HITL), not hidden
- [ ] Talk track beats sum to the slot with 20% buffer
- [ ] Every claim in the talk track is demonstrable on screen or labeled as roadmap
- [ ] Reset and offline fallback defined
- [ ] No vendor benchmark numbers

## References
- `references/demo-spec-guide.md` — what a good demo spec contains
- `references/synthetic-data.md` — generation approach and realism rules
- `references/talk-track.md` — structure, timing, objection handling
- `scripts/gen_synthetic.py` — demo-spec.md §7 entity tables → seeded `data/<entity>.csv` + `data-manifest.json`; PII guard; emails only @example.com
