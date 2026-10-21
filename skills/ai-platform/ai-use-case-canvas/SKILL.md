---
name: ai-use-case-canvas
description: Use when the user wants to qualify a single AI idea quickly — "is this a good AI use case", "use AI to <do X>", "fill the canvas for X", "should we build or buy this", "what would it take" — including testing whether the idea needs AI at all (a fixed threshold or approval rule such as "does an order over $10k need director approval" is a deterministic rule, verdict Stop or re-scope). Produces a one-page canvas: problem and user, current process and baseline, proposed AI capability, data readiness, feasibility, value hypothesis, risks and tier, build/buy/partner decision, next 30-day step. Do not use for portfolio-level strategy (ai-strategy-coe), designing an agent or its graph and tools once the idea is qualified (agent-architecture), retrieval design (rag-pipeline-design), or a full risk review (ai-governance-risk).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: use-case
  version: 0.2.0
  author: giri-skills
  agent:
    modes:
      new:      {case: agent-happy-path, bring: "your answers to the canvas questions about one AI idea"}
      existing: {case: agent-mode-existing, bring: "updated answers plus the scores from the idea's last review"}
    inputs:
      - {name: answers, type: json, required: true, from: "answers.json: the canvas cells (problem_user, decision, current_process, capability, data, feasibility, value, risks), scores with evidence, build_buy factors, next_step (layout: evals/fixtures/answers.json)"}
      - {name: previous, type: json, required: false, from: "score.json from an earlier canvas of the same idea (re-review); decision.md then shows then-vs-now scores, verdict and decision"}
    run:
      - {step: canvas, kind: script, cmd: "python3 -I scripts/canvas.py {answers} --out-dir {out} --template assets/use-case-canvas.md [--previous {previous}]"}
    outputs:
      - {path: "{out}/canvas.md", checks: [exists, contains:"**Verdict:**", contains:"| 9 | Build / buy / partner |", no_unowned_tbd, max_lines:60]}
      - {path: "{out}/decision.md", checks: [exists, sections:["Factors stated","Verdict"], contains:"**Decision:**"]}
      - {path: "{out}/score.json", checks: [exists, json]}
---

# AI Use-Case Canvas

## How to run
This skill is executable. Collect the inputs below (one `answers.json`; blanks are allowed and become owned `[TO BE BASELINED]` markers), then run `python3 scripts/run_skill.py ai-platform/ai-use-case-canvas --input answers=<file> --out <dir>` (see `--explain ai-platform/ai-use-case-canvas`). Report the `run.json` results; do not hand-write the deliverables the script produces (`canvas.md`, `decision.md`, `score.json`).

## Starting points
- **New:** your answers about one idea fill the canvas, score it and make the build, buy or partner call.
- **Existing:** add the `score.json` from the idea's last canvas (`previous`); decision.md adds then-vs-now scores, priority, verdict and decision, so a re-review shows what moved and why.

## When to use
- First-pass qualification of one idea in under an hour; intake form for a CoE; pre-read for a sponsor conversation.
- NOT for: ranking many ideas (`ai-strategy-coe`), designing the solution, legal/compliance sign-off.

## Inputs required
| Input | Required | Source |
|---|---|---|
| The idea in one or two sentences, and who raised it | yes | user |
| The user of the output and the decision or task it affects | yes | user |
| Current process: steps, volume, time, error or cost signal (even rough) | yes | user; unknowns marked `[TO BE BASELINED — owner: ___]` |
| Data involved: where it lives, owner, access, sensitivity | yes | user |
| Constraints: budget envelope, timeline, vendor policy | no | user |

If the user/decision or the data description is missing, ask once; otherwise fill the canvas with explicit unknowns rather than stalling.

## Procedure
1. Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md`.
2. **Fill the canvas** from `assets/use-case-canvas.md` following `references/canvas-definition.md`: every box has content or a labeled unknown with an owner.
3. **Score** value, feasibility, data readiness, risk (1–5 each) using the rubric in `ai-strategy-coe/references/use-case-scoring.md`; compute priority = V × F × D ÷ R. Record the evidence per score.
4. **Decide build / buy / partner** with `references/build-buy-factors.md`; state the two strongest factors behind the decision.
5. **Set the verdict**: Proceed to design / Proceed after data readiness work / Park / Stop, plus the one 30-day step and its owner.
6. Hand off: Proceed → `agent-architecture` or `rag-pipeline-design`; risk tier medium/high → `ai-governance-risk` before build.
7. Run the self-check.

## Output
- `use-case-canvas-<name>.md`: one page; verdict first; canvas table; scores; build/buy; next step.

## Self-check
- [ ] Verdict and next step are the first two lines
- [ ] Baseline metric named, with value or `[TO BE BASELINED — owner: ___]`
- [ ] Data box names owner, access path, and sensitivity
- [ ] Scores have one evidence line each
- [ ] Build/buy decision cites factors, not preference
- [ ] Fits on one page (≤ 60 lines)
- [ ] No vendor named without a selection criterion

## References
- `references/canvas-definition.md` — boxes, prompts, and quality tests
- `references/build-buy-factors.md` — decision factors and patterns
- `scripts/canvas.py` — answers.json → `canvas.md` (filled, scored, verdict), `decision.md` (build/buy/partner citing factors), `score.json`
