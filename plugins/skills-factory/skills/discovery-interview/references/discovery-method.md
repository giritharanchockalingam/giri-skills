# Discovery Method

Purpose: turn a 45-minute conversation into qualified facts a proposal and an estimate can stand on. Discovery is hypothesis testing, not a survey.

## 1. Roles on the call
| Role | Who | Does |
|---|---|---|
| Lead | Solution architect / presales lead | Asks, follows the funnel, controls time |
| Scribe | Second person, never the lead | Captures verbatim quotes and numbers; flags "no number given" |
| Observer (optional) | Account exec | Watches decision dynamics: who defers to whom, who objects |

One voice asks. Two voices asking reads as an interrogation.

## 2. The funnel (order is the method)
| Stage | Goal | Share of time | Opening pattern |
|---|---|---|---|
| Situation | Establish current state in their words | 15% | "Walk me through how <process> works today, end to end." |
| Pain | Surface what breaks, where, how often | 25% | "Where does that break down? What happens when it does?" |
| Impact | Quantify pain in money, time, risk, people | 20% | "When that happens, what does it cost — hours, dollars, customers, audit findings?" |
| Urgency | Find the forcing event | 10% | "What changes if this is still the case in 12 months?" |
| Decision | Map who decides, how, with what money | 15% | "Who signs this, and what do they need to see to sign?" |
| Constraints | Non-negotiables: security, vendors, dates, staff | 15% | "What would make this a non-starter regardless of fit?" |

Rules:
- Technology questions come after Impact. Asking "are you on MuleSoft or Boomi?" first anchors the conversation on tools instead of outcomes.
- Every "we have a problem with X" gets the follow-up "how do you know?" — that is where the number lives.
- Silence after a question is a tool. Count to four before rescuing them.
- When they volunteer a number, repeat it back and ask for the source ("Is that from a report or a gut feel?"). Record which.

## 3. Pain / Impact / Urgency scoring rubric
Score each pain statement 1–5 on three axes. Record the evidence that justifies each score. A score without evidence is a 0 and the cell shows `[TO BE BASELINED — owner: ___]`.

| Score | Pain (severity) | Impact (quantified consequence) | Urgency (forcing event) |
|---|---|---|---|
| 5 | Stops a core business process; executives named it unprompted | Client stated a figure with a source (report, budget line, audit) | Hard date within 6 months (contract end, regulation, go-live, board commitment) |
| 4 | Degrades a core process; workarounds exist and cost real effort | Client stated a figure, source unclear | Hard date within 12 months |
| 3 | Affects a secondary process or one function | Client described consequence qualitatively with specifics (team, frequency) | Executive sponsor wants it "this year"; no hard date |
| 2 | Irritant; mentioned in passing | Vague ("it costs us a lot") | "Eventually"; no sponsor named |
| 1 | We inferred it; client did not say it | None stated | None |

Priority = Pain × Impact × Urgency. Rank descending. Anything with a 1 on any axis goes to "Parked" unless a hypothesis depends on it.

Matrix columns: `# | Pain (verbatim) | Who said it (title) | Pain | Impact | Urgency | Priority | Evidence / source | Hypothesis`

## 4. The five non-negotiable closes
Asked on every call, in the last 10 minutes. If any is unanswered, it is the first row of the gaps list.

| # | Close | Exact wording that works | What a bad answer sounds like |
|---|---|---|---|
| 1 | Decision owner | "If this goes ahead, whose name is on the approval?" | "It's a committee." → ask who chairs it |
| 2 | Budget state | "Is this funded, in a budget cycle, or would it need a business case first?" | "We'd find the money." → unfunded; the value-case-builder skill is needed |
| 3 | Timeline driver | "What date matters, and what happens if it is missed?" | "No hard date." → low urgency; price for a slower sales cycle |
| 4 | Incumbents and alternatives | "Who else is helping you with this today, and who else are you talking to?" | Refusal to say → assume an incumbent with a relationship advantage; see competitive-positioning |
| 5 | Success measure | "Twelve months after go-live, what number on your dashboard has moved?" | "Everything works better." → no measurable outcome; propose one and ask them to confirm |

## 5. Qualification gate
Apply after synthesis. Be direct; a PARK saved early is cheaper than a lost proposal.

| Criterion | PURSUE | PURSUE-WITH-CONDITIONS | PARK |
|---|---|---|---|
| Pain | At least one pain scored ≥4 with evidence | Pain ≥4 but evidence thin | Nothing above 3 |
| Money | Funded or in an active budget cycle | Business case needed; sponsor committed to build one with us | No budget path, no sponsor |
| Decision owner | Named, met or scheduled | Named, not yet met | Unknown or "committee" with no chair |
| Timeline | Forcing event within 12 months | Sponsor intent, no date | None |
| Access | We can reach the decision owner and a technical owner | One of the two | Neither |
| Competitive position | We are early or have a differentiating wedge | Incumbent exists; wedge identified | Incumbent entrenched, no wedge, late to the process |

Decision rule: any PARK column hit on Money or Decision owner → PARK. Two or more CONDITIONS → PURSUE-WITH-CONDITIONS, with the conditions listed as the first items in the gaps list, each with owner and date.

## 6. Anti-patterns
| Anti-pattern | Why it costs | Replace with |
|---|---|---|
| Pitching during discovery | Client stops disclosing; you lose the pain data | "We have views on that — can I hold them for the readout so I understand your side fully first?" |
| Accepting "it's slow / expensive" as a finding | Not estimable, not provable | "Slow compared to what, and measured how?" |
| Asking a question whose answer is in their 10-K or website | Signals no preparation | Run `client-research-brief` first; confirm, don't ask |
| Letting the loudest attendee answer everything | Missing the operator's view | Direct by name: "<Name>, you run this day to day — does that match?" |
| Leaving without next-step ownership | Deal drifts | Close with: who sends what, to whom, by when |
