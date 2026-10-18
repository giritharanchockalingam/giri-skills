---
name: competitive-positioning
description: Use when the user asks how to win against a named competitor, an incumbent vendor or services provider, a platform vendor's services arm, or the status quo in a pursuit ("how do we win vs <X>", "build a battle card for <incumbent>"). Produces a battle card — their likely strengths and weaknesses as evidenced, our wedge, landmines to avoid, objection handling, ghost lines for the proposal, and the evaluation criteria we want the client to adopt — with every claim about a competitor sourced or marked as hypothesis. Do not use for general market research (client-research-brief) or for proposal prose (proposal-writer).
license: MIT
metadata:
  domain: presales
  adlc_stage: opportunity
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: ours, type: csv, required: true, from: "our-capabilities.csv: capability, evidence, strength 1-5 (layout: evals/fixtures/our-capabilities.csv)"}
      - {name: theirs, type: csv, required: true, from: "their-claims.csv: claim, source, strength 1-5 (layout: evals/fixtures/their-claims.csv)"}
      - {name: concerns, type: csv, required: true, from: "concerns.csv: stakeholder, concern — from discovery (layout: evals/fixtures/concerns.csv)"}
      - {name: client, type: string, required: false, default: "<Client>"}
      - {name: alternative, type: string, required: false, default: "<Alternative>"}
    run:
      - {step: card, kind: script, cmd: "python3 -I scripts/battle_card.py {ours} {theirs} {concerns} --out {out}/battle-card.md --client {client} --alternative {alternative}"}
    outputs:
      - {path: "{out}/battle-card.md", checks: [exists, contains:"INTERNAL — do not distribute", sections:["Wedge","Landmines","Objection handling","Intelligence gaps"]]}
---

# competitive-positioning

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py presales/competitive-positioning --input <name>=<value> … --out <dir>` (see `--explain presales/competitive-positioning`). Report the `run.json` results; do not hand-write the deliverables the scripts produce.

## When to use
- "How do we beat the incumbent at <client>?"
- "Build a battle card against <competitor type> for this pursuit."
- "The client's platform vendor is bidding services too — what is our angle?"
- NOT for: researching the client (`client-research-brief`), writing the proposal (`proposal-writer`), rehearsing objections live (`orals-prep` uses this output).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Pursuit context: client, initiative, decision criteria known, decision owner | yes | discovery synthesis / user |
| Alternative(s) we face: named competitor, incumbent, vendor services arm, in-house build, status quo | yes | user |
| Evidence about the alternative: public materials, client statements, RFP wording, prior encounters | no (but confidence drops without it) | files / user |
| Our cleared proof points and capability catalog | yes | file / user |
| Client's stated priorities and pains (from discovery) | yes | discovery synthesis |

If the alternative is unknown, ask once; if still unknown, build the card against "status quo" and "an incumbent-type provider" as labeled hypotheses.

## Procedure
Read `../../../shared/quality-bar.md` and `../../../shared/writing-style.md` first.

1. **Classify the alternative** per `references/competitive-method.md` §1 (incumbent services provider, platform vendor services, global SI, boutique, in-house, status quo). Each class has predictable strengths, weaknesses, and selling motions; use them as hypotheses, labeled as such, until evidence confirms.
2. **Build the evidence table** for the alternative: every strength/weakness claim carries a source (public material, client quote, RFP wording that mirrors their language, prior encounter) and a confidence rating. No evidence → `Hypothesis (class pattern)`; it never becomes a "fact" in any client-facing document.
3. **Map the client's decision criteria** (stated in RFP/discovery; else `[TO BE BASELINED — owner: ___]`) and score us vs the alternative on each, honestly, using the scoring in §3 of the method. Where we lose on a criterion, decide: neutralize (close the gap), reframe (change the criterion's weight in the client's mind), or concede (do not fight it; move the battle).
4. **Decision point — the wedge.** Identify the one or two criteria where we win and the client cares (from discovery). If no such intersection exists, say so: the recommendation is to reshape the opportunity (phase, scope, partner) or to qualify out. Do not manufacture a wedge.
5. **Landmines**: what we must not say or do (attacking the incumbent by name, disparaging the platform the client already bought, promising what their contract forbids, referencing other clients without clearance). Add client-specific sensitivities from discovery.
6. **Objection handling** with `references/objection-handling.md`: for each likely objection (the alternative's strengths restated as client concerns), write acknowledge → reframe → proof → ask-back. Proof only from cleared references.
7. **Ghost lines** for `proposal-writer`: the alternative's weakness stated as a general risk the client should evaluate, followed by how we remove it. No names.
8. **Evaluation criteria we want adopted**: three to five criteria phrased neutrally that favor our wedge; these go into clarification questions, discovery follow-ups, and the proposal's approach section.
9. **Write the battle card** on `assets/battle-card-template.md`. One page; internal only; marked so. Run the self-check.

## Output
- File: `battle-card-<client>-vs-<alternative>-<yyyy-mm-dd>.md` (internal, not for client distribution)
- Sections: Bottom line (win/lose assessment and wedge in two sentences) · Alternative profile (class, evidence table with confidence) · Criteria scorecard (us vs them with neutralize/reframe/concede) · Wedge · Landmines · Objection handling · Ghost lines · Evaluation criteria to seed · Intelligence gaps (what we need to learn, owner)

## Self-check
- [ ] Every claim about the alternative has a source and confidence, or is labeled hypothesis
- [ ] Scorecard is honest: at least one criterion where we lose is acknowledged
- [ ] Wedge sits at the intersection of "we win" and "client cares (sourced)"; or the card says there is none
- [ ] No competitor named in ghost lines or any content intended for client-facing use
- [ ] Objection proofs are cleared references only
- [ ] Landmines include client-specific sensitivities
- [ ] Card marked internal; no other-client specifics beyond cleared proof; no author history

## References
- `references/competitive-method.md` — alternative classes, evidence standards, criteria scoring, wedge logic, win/loss patterns
- `references/objection-handling.md` — objection patterns by alternative class with response structure
- `assets/battle-card-template.md` — one-page battle card
