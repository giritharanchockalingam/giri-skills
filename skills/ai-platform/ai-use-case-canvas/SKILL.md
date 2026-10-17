---
name: ai-use-case-canvas
description: Use when the user wants to qualify a single AI idea quickly — "is this a good AI use case", "fill the canvas for X", "should we build or buy this", "what would it take". Produces a one-page canvas: problem and user, current process and baseline, proposed AI capability, data readiness, feasibility, value hypothesis, risks and tier, build/buy/partner decision, next 30-day step. Not for portfolio-level strategy (ai-strategy-coe), detailed design (agent-architecture, rag-pipeline-design), or a full risk review (ai-governance-risk).
license: MIT
metadata:
  domain: ai-platform
  version: 0.1.0
  author: giri-skills
---

# AI Use-Case Canvas

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
