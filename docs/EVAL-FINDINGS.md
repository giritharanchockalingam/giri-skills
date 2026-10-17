# EVAL-FINDINGS — behavioral evals (thread 02)

> Full run completed 2026-10-17: **40 skills, 120 cases, 2 runs, gpt-4.1-mini**
> (`--provider openai --model gpt-4.1-mini`). Scorecard:
> `evals/results/full-openai/scorecard.md`. Raw audit logs (git-ignored):
> `evals/results/full-openai/raw/calls.jsonl`.
> Pilot (presales only): `evals/results/pilot-openai/scorecard.md`.

## Method

- **Trigger accuracy**: for each eval case prompt, a router LLM picks one skill
  from all 40 `name: description` pairs (or `none`). 10 generic negative
  prompts measure per-skill false-positive rate.
- **Quality lift**: the same case is answered twice — baseline (shared
  `quality-bar.md` + `writing-style.md` only) vs with the full `SKILL.md` +
  references — and an LLM judge grades each `expected[]` item PASS/FAIL with
  evidence.
- **Verdicts**: `OK` = trigger ≥ 0.8 and lift ≥ +0.2 · `DESC` = trigger < 0.8
  (description problem) · `BODY` = lift < 0.2 (instructions don't change
  behavior) · `BOTH` = both.

## Caveats (read before acting on any proposal)

1. **The generator is gpt-4.1-mini, not Claude.** Lift numbers are a lower
   bound: a mini follows long SKILL.md bodies less faithfully, so BODY
   verdicts partly measure the model, not just the skill. Relative ranking
   across skills is the reliable signal.
2. **Small sample**: 3 cases × 2 runs. Lifts within ±0.1 are noise.
3. **The judge is also the mini.** Spot-checked: its evidence quotes are
   specific and well-reasoned, but borderline calls vary run to run.
4. Presales evals are the strictest in the repo (many `expected[]` items
   demand exact tables, templates, and `[TO BE BASELINED]` markers) — that
   domain's low lifts partly reflect eval strictness.

## Verdict counts

| Domain | OK | DESC | BODY | BOTH |
|---|---|---|---|---|
| presales (13) | 1 | 1 | 8 | 3 |
| build (12) | 6 | 2 | 2 | 2 |
| ai-platform (9) | 7 | 1 | 1 | 0 |
| career (6) | 1 | 1 | 4 | 0 |
| **Total (40)** | **15** | **5** | **15** | **5** |

OK skills (no action): proposal-writer, handoff-and-thread-close,
multi-tenant-saas-patterns, product-spec-prd, project-bootstrap,
supabase-schema-rls, test-strategy-tdd, agent-architecture,
ai-governance-risk, ai-strategy-coe, llm-eval-harness, mcp-server-builder,
rag-pipeline-design, slm-demo-builder, resume-tailor.

FP rates are 0.00 everywhere except slm-demo-builder (0.10 — one generic
prompt misrouted; not worth a description change).

## Ranked proposals

Ordered presales → build → ai-platform → career; within a domain BOTH first,
then DESC, then BODY (worst lift first). Description proposals are
paste-ready replacements for the `description:` frontmatter field. Body
proposals are directions for thread 03 — **this thread does not edit
SKILL.md**.

### presales

**1. effort-estimator — BOTH (trigger 0.67, lift 0.00).** The worst score in
the repo. Happy-path WBS case routed to integration-migration-assessor both
runs; with-SKILL outputs failed 6/6 on the WBS CSV, the P80 quote, and the
staffing table — the skill's three headline artifacts never materialized.
Description (paste-ready):

```
Use when the user asks to size, estimate, or price a services engagement: build a WBS with 3-point estimates, run PERT/Monte Carlo for P50/P80/P90 effort and duration, and produce a staffing table by role and phase with onshore/offshore mix. Never invents rate-card rates. Not for migration assessments (integration-migration-assessor), business-case benefits (value-case-builder), or proposal narrative (proposal-writer).
```

Body: make the output skeleton mandatory and ordered — WBS CSV first, then
P80 quote with rationale, then staffing table — and require invoking the
bundled PERT/Monte Carlo script rather than describing it.

**2. exec-deck-redline — BOTH (trigger 0.67, lift −0.07).** Adversarial
savings/dates case routed to value-case-builder both runs; slide verdicts
(`[KEEP]/[SHARPEN]/…`) missing 6/6, numbers never checked against memos.
Description (paste-ready):

```
Use when the user asks to redline, sharpen, or review an EXISTING executive deck, steering-committee pack, or pitch deck — slide-by-slide verdicts ([KEEP]/[SHARPEN]/[CUT]/[ADD]/[TBD]), rewritten slide titles as assertions, speaker notes, and [TO BE BASELINED — owner: ___] markers for every unsourced number. Keeps the original storyline; never replaces it. Not for savings/numbers analysis (value-case-builder), building a deck from scratch (proposal-writer), or document redlines (sow-drafter).
```

Body: require the verdict ledger as the first output block before any prose;
add a numbers-trace step (each figure → source memo or `[TO BE BASELINED]`).

**3. discovery-interview — BOTH (trigger 0.67, lift 0.19, just under the
bar).** Fabrication case routed to client-research-brief / value-case-builder
across runs; time budget (~20% for client questions) and persona/hypothesis
tagging missed ~50%.
Description (paste-ready):

```
Use when the user asks to prepare for, run, or synthesize a client discovery call or scoping workshop: a vertical-specific question bank (EdTech, Retail, Manufacturing, Travel) with persona and hypothesis tags, a time budget reserving ~20% for the client's questions, a pain/impact/urgency matrix, and the five closes (decision owner, budget state, timeline driver, incumbents, success measure). Feeds proposal-writer and effort-estimator. Not for background research (client-research-brief) or fabricated-answer drills (orals-prep).
```

Body: harden the time-budget rule and the five-closes checklist into a
required closing section.

**4. orals-prep — DESC (trigger 0.67, lift +0.31 — body is fine).** The
answers-with-new-numbers case went to competitive-positioning both runs.
Description (paste-ready):

```
Use when the user asks to prepare the TEAM for a pitch presentation, orals, bid defense, or steering-committee readout: timed script with speaker assignments, a likely-questions bank with sourced answers (no new numbers — every figure traceable to the proposal), red-team objections with responses, and a rehearsal plan with scoring rubric. Not for competitive analysis (competitive-positioning) or deck content rework (exec-deck-redline); both feed this skill.
```

**5. integration-migration-assessor — BODY (lift −0.12).** TCO lines never
cite the contract summary; readout never follows the assessment template or
hands off to effort-estimator / solution-architecture-doc (100% fail).
Body: make the readout template the output skeleton (not a reference to
consult); add a TCO citation rule — every cost line names its source or is
marked `[TO BE BASELINED]`.

**6. solution-architecture-doc — BODY (lift −0.11).** Target-state diagrams
never use the mermaid C4 templates; integration map never groups interfaces
by pattern; NFR table missing (all 100% fail).
Body: lead with the three mandatory artifacts (C4 diagrams from template,
integration map by pattern with waves, NFR table with measurable targets);
undecided products as `[TO BE BASELINED]` placeholders.

**7. value-case-builder — BODY (lift −0.10).** Delivery costs at P80, NPV at
the sourced discount rate, and sensitivity/break-even analysis all missing
(100% fail).
Body: require a CFO-grade calculation block — costs (delivery P80 citing the
estimate memo, run, dual-run, decommission timing), NPV with sourced rate,
sensitivity on top-3 assumptions with break-even values.

**8. competitive-positioning — BODY (lift +0.04).** Wedge never identified at
the intersection of independent baseline and the CIO's stated concern;
objection handling never demonstrates acknowledge/reframe/proof/ask-back;
card never marked INTERNAL (all 100% fail).
Body: turn the wedge formula into a worked example; make the objection
framework a fill-in structure rather than a named concept.

**9. account-plan — BODY (lift +0.08).** Stakeholder map with departure
exposure, white-space matrix, and 90-day plays with owners all missing
(100% fail).
Body: open with a "minimum viable output" checklist — stakeholder map,
white-space matrix, 90-day plays — each a required section, not optional
depth.

**10. rfp-compliance-matrix — BODY (lift +0.07).** No-C-without-evidence rule
never applied; bid review never opens with BID/BID-WITH-CONDITIONS/NO-BID;
clarification questions never reference clause IDs (all 100% fail).
Body: fix the output order — bid verdict with three drivers first, then the
compliance matrix with the evidence-citation rule enforced per row.

**11. client-research-brief — BODY (lift +0.10).** Initiatives never labeled
hypotheses with signal tiers; sources appendix never lists URLs with access
dates and tiers (100% fail).
Body: make the sources appendix and hypothesis labeling required sections
with an explicit schema, not closing niceties.

**12. sow-drafter — BODY (lift +0.14).** Estimate quantities never appear as
assumptions with consequences; client dependencies lack dates; RACI never
enforces one-A-per-row (all 100% fail).
Body: add an SOW clause checklist as mandatory sections — assumptions with
consequences and change-control triggers, dated client dependencies, RACI
with exactly one A per row.

### build

**13. nextjs-enterprise-conventions — DESC (trigger 0.33 — worst routing in
the repo, lift +0.30 so the body works).** Happy-path code writing went to
spec-to-plan and the conventions-violation review went to safe-fix, both
runs. The description reads as generic "writing or reviewing code."
Description (paste-ready):

```
Use to check code against the enterprise Next.js conventions checklist — server/client component rules, data-access layering, zod at boundaries, typed Result<T,E> errors, structured logging, naming and folder conventions — when writing new code or reviewing a diff for conventions violations. Produces compliant code plus a checklist result. Not for planning work (spec-to-plan), bug fixing (safe-fix), or security audits (security-review).
```

**14. spec-to-plan — BOTH (trigger 0.67, lift −0.20).** The "too-big" case
went to multi-tenant-saas-patterns both runs; with-SKILL outputs skip the
pre-plan discipline (read SPEC/CLAUDE.md/HANDOFF, one round of ≤5
clarifying questions with defaults).
Description (paste-ready):

```
Use when a feature request, ticket, or SPEC section must be decomposed into an executable plan before any code is written — including oversized specs that need splitting. Produces a task-gated plan (docs/plans/<slug>.md) with files to touch, acceptance criteria, test list, rollback, and explicit plan→approve→build→test→verify gates. Starts by reading SPEC, CLAUDE.md, and HANDOFF, then asks at most 5 clarifying questions with defaults in one round. Not for bug fixes (safe-fix) or product definition (product-spec-prd).
```

Body: move the pre-plan checklist (read the three docs, one question round)
to a hard preamble the model must show its work for.

**15. security-review — DESC (trigger 0.67, lift +0.56 — body is strong).**
Happy-path review went to safe-fix both runs.
Description (paste-ready):

```
Use when the user asks to REVIEW a diff, PR, or feature for security defects before merge or release — not to fix a bug. Produces a reasoning-based review (threat model per change: authz, injection, secrets, RLS bypass, SSRF, IDOR, mass assignment, server-action pitfalls) with severity-rated findings and fixes applied in code. For the Next.js + Supabase + Vercel stack. Bug fixing without a security angle belongs to safe-fix.
```

**16. ci-cd-vercel-github — BOTH (trigger 0.67, lift +0.10).** "Pipeline is
failing" case went to safe-fix both runs despite the description naming it.
Description (paste-ready):

```
Use for CI/CD pipeline work on a Next.js + Supabase app deployed to Vercel via GitHub Actions — set up CI, preview deploys, prod deploys, rollback, and FAILING PIPELINE runs (yaml, runners, secrets, gates). Produces ci.yml, preview.yml, prod.yml, the environment/secret matrix, and a rollback runbook. A failing pipeline is a workflow problem and belongs here; failing application code belongs to safe-fix. Not for test authoring (test-strategy-tdd) or alerting (observability-setup).
```

Body: require the three workflow files plus the rollback runbook as the
output list; prod.yml must show tag-on-main verification, staging→prod
migration behind the Environment gate, and health-endpoint smoke tests.

**17. safe-fix — BODY (lift 0.00).** Root cause as one sentence with
file:line and evidence missing 6/6; diff not limited to the failing path;
regression test never shown red-first.
Body: make the ritual a numbered mandatory sequence — (1) one-sentence root
cause with file:line and evidence, (2) minimal diff on the failing path
only, (3) regression test named after the bug, shown failing before the fix.

**18. observability-setup — BODY (lift +0.18).** lib/logger.ts with
redaction, /api/health endpoints with tests, and alert rules with
threshold/window/tier/runbook/owner all missing (100% fail).
Body: required output checklist — logger with redaction + request context,
both health endpoints with tests, alert rules each with threshold, window,
tier, runbook, owner, plus an SLO table per journey.

### ai-platform

**19. ai-use-case-canvas — DESC (trigger 0.67, lift +0.45 — body is
strong).** The "should we even use AI" disqualifier case went to
agent-architecture both runs.
Description (paste-ready):

```
Use when the user wants to qualify — or disqualify — a single AI idea quickly: "is this a good AI use case", "fill the canvas for X", "should we build or buy". Produces a one-page canvas (problem, baseline, AI capability, data readiness, feasibility, value hypothesis, risks, build/buy/partner, next 30-day step), including an explicit NOT-AI verdict when the idea doesn't qualify. Not-AI verdicts stay here. Not for portfolio strategy (ai-strategy-coe), detailed design (agent-architecture, rag-pipeline-design), or full risk review (ai-governance-risk).
```

**20. infra-gpu-sizing — BODY (lift +0.10).** Recommendation with revisit
triggers missing 100%; monthly cost table with breakeven hours missing
50%+.
Body: required output — monthly cost table (rental, self-host, API) with
breakeven hours, GPU count with utilization target and spare as stated
assumptions, latency check, and a recommendation with revisit triggers.

### career

**21. outreach-and-followup — DESC (trigger 0.67, lift +0.36 — body is
strong).** Post-interview thank-you-with-repair went to interview-prep both
runs.
Description (paste-ready):

```
Use when the user needs to WRITE or time a job-search message — referral ask, recruiter reply, post-interview thank-you or repair note, status check, decline, negotiation opener — by LinkedIn or email, for senior director / VP / executive IT roles. This skill writes the message (2-3 goal-labelled variants, subject line, follow-up cadence); preparing for the interview itself is interview-prep. Facts come only from the user's inputs; no invented names, dates, or claims.
```

**22. application-tracker — BODY (lift 0.00).** CSV never actually edited
(100% fail — the model just asks for the file); reply length constraint
ignored.
Body: spell out the exact edit procedure — read CSV, move the row, set
last_touch, write back, confirm in ≤50 words showing the updated row.
Consider invoking the bundled `tracker.py` script instead of hand-editing.

**23. interview-prep — BODY (lift +0.08).** Competency-to-story
traceability table with STRONG/ADEQUATE/GAP ratings and the panel question
list mapped to story IDs missing 6/6.
Body: make the traceability table the centerpiece required section; gaps
stated honestly with a handling approach.

**24. jd-fit-scorer — BODY (lift +0.14).** Gap table missing mitigations;
red flags missing penalties; verdict line not first.
Body: fix the output order — verdict with score/100 on line one, then
evidence, then gap table with a mitigation per GAP and red flags with
penalties or "none detected".

**25. offer-evaluator — BODY (lift +0.08).** COL indices cited without
source/date (6/6); decision matrix arithmetic hidden behind
`[TO BE BASELINED]` markers; negotiation levers missing.
Body: require arithmetic shown in the decision matrix (weights sum to 100,
weighted totals computed); COL indices must cite source and date, never
assumed.

## Broken cases

None. All 120 eval cases have a non-empty `prompt` and a non-empty
`expected[]` list.

## Spend

- Pilot (presales, 26 case-runs): projected $1.96 under Sonnet pricing due
  to a missing price-table entry (fixed); actual ~$0.25.
- Full run (120 cases × 2 runs, 1210 calls): projected $11.84 — conservative
  by design (assumes every call emits max_tokens); actual expected ~$2.
- Total real spend for thread 02 evals: roughly **$2–3**.

## Harness notes

- Fixed during the pilot: `gpt-4.1-mini` / `gpt-4.1` / `gpt-4.1-nano`
  pricing added to `scripts/behavioral_evals.py` (previously fell back to
  Sonnet pricing with a warning).
- The cost projection assumes worst-case output tokens; it overstates real
  spend by ~5x. Kept conservative on purpose as a budget guard.
- Environment notes for future runs are in the root `AGENTS.md`
  (SDK reinstall after VM replacement, `no_proxy` sanitizing, brotli
  removal for the httpx2 fork).
