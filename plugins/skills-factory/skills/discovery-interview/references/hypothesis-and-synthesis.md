# Hypotheses and Synthesis

## 1. Writing hypotheses before the call
A hypothesis is a falsifiable claim about the client's situation that, if true, changes what we propose. Write 3–5. More than five means you are guessing; fewer than three means you have not done the research brief.

Format (one row each):
| ID | Hypothesis (claim) | If true, we propose | Evidence that confirms | Evidence that kills | Question(s) that test it |
|---|---|---|---|---|---|

Sources for hypotheses, in order of reliability:
1. Trigger event the client disclosed (contract renewal, new CIO, M&A, audit finding, platform EOL).
2. Public signals from `client-research-brief` (job postings naming platforms, earnings-call initiatives, regulatory filings).
3. Vertical patterns from the question banks (the "typical pains" tables).
4. Our prior engagements of the same shape — pattern only; never cite the other client to this client.

Hypothesis quality test:
- Specific enough that one answer could kill it. "They have integration problems" is not a hypothesis. "Their order-to-fulfil integration runs on point-to-point jobs maintained by two named people, and the risk of their departure is the real driver" is.
- Names an owner persona. Pain without an owner is not a sales opportunity.
- Points to a proposal shape (assessment, factory, managed service, build). If it does not change the proposal, drop it.

## 2. Listening for absence
The highest-value findings are often what the client did not say. During synthesis, check each of these explicitly and record the absence in the gaps list:

| What is absent | What it usually means | Gap-list action |
|---|---|---|
| No number attached to a pain | Either unmeasured (opportunity: we baseline it) or politically sensitive | Ask the operator, not the executive, for the figure |
| No decision owner named | Early-stage, or the sponsor is testing the market | Ask the sponsor directly in the follow-up |
| No incumbent mentioned | There is one; they do not want to say | Check public contract/vendor signals; ask again at the technical session |
| No date | Low urgency or a date they are embarrassed by (a slipped program) | Ask "what did the original plan say?" |
| Technical owner absent from the call | Executive-only view; integration reality unknown | Request a 60-minute technical session as a condition of proposal |
| Success measure undefined | Outcome not agreed internally | Propose two candidate KPIs in the follow-up and ask them to choose |

## 3. Synthesis procedure
1. **Read fully first.** Do not extract while reading. Mark the three moments where the tone changed (frustration, deflection, enthusiasm) — those are where the real pain and the real politics are.
2. **Verbatim extraction.** Every pain row carries the quote. Paraphrase loses the number and the emotion, both of which you will need in the proposal's problem statement.
3. **Score** using `discovery-method.md` §3. Resist scoring Impact above 2 without a stated figure.
4. **Reconcile with hypotheses.** For each: `CONFIRMED (quote)`, `KILLED (quote)`, or `UNTESTED (why)`. Untested hypotheses become questions for the next session.
5. **Build the gaps list** by walking the downstream needs:
   - `proposal-writer` needs: problem statement with figures, success measure, decision owner, timeline, constraints.
   - `effort-estimator` needs: counts (APIs, interfaces, users, sites, SKUs, courses, bookings), environments, team availability, data volumes.
   - `value-case-builder` needs: current cost baseline, run-rate, headcount on the process, error/rework rates.
   Every missing item is a row: `Gap | Needed by (skill/deliverable) | Likely holder (client role) | Our owner | Ask-by date`.
6. **Qualify** with the gate in `discovery-method.md` §5. Write the call on line 1.
7. **Write the follow-up note** last, from the synthesis, not from memory. Client-facing: no scores, no internal commentary, no hypothesis labels.

## 4. Synthesis output anti-patterns
| Anti-pattern | Fix |
|---|---|
| "The client is experiencing significant challenges with…" | Quote them. "<Title>: 'We re-key every order over $50k by hand.'" |
| Impact scored 4 because "it sounded expensive" | Score 2; add gap row for the figure |
| Gaps list with no owners | Not a list; a wish. Every row has an owner on our side |
| Qualification buried on page 3 | Line 1 |
| Follow-up note that restates our capabilities | Cut. State what we heard, what we bring next, what we need from them |

## 5. Multi-stakeholder interviews
When running 3+ interviews on one opportunity, add a stakeholder consistency check:
| Topic | Exec view | Operator view | Technical view | Conflict? | Resolution owner |
|---|---|---|---|---|---|

Conflicts between layers (exec says "we need AI", operator says "we need the nightly batch to stop failing") are the most useful finding in the pack. Surface them under "Divergent views" in the synthesis; they shape phasing in the proposal.
