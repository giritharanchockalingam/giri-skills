# Demo Spec Guide

A demo shows one decision getting easier. Everything else is removed.

## Spec sections
| Section | Content | Test |
|---|---|---|
| Audience and persona | Who watches; who the on-screen user is; what they are measured on | A viewer recognizes themselves in 10 seconds |
| Before / after | The task today (clicks, minutes, errors) vs with the system | One number changes (time, steps, error rate) — labeled illustrative if not measured |
| Happy path | 3–5 steps, each with input, system action, visible output | Every step shows something on screen |
| Wow moments | Two moments where the system does what a human would not bother to do (cross-reference, cite, draft, act with approval) | Audience leans in |
| Handled failure | A planted input the system should not answer or should escalate; shows abstention, citation of uncertainty, or HITL approval | Builds trust more than a perfect run |
| Scope boundary | What the demo does not show (roadmap vs real) | No claim exceeds what is on screen |
| Architecture glance | One diagram: UI → gateway → SLM/agent → tools/data; where data stays | Answers "where does my data go" |
| Reset and fallback | Script to reset state; cached outputs for offline | Demo recoverable in < 1 minute |

## Rules
1. Lead with the business outcome, not the model.
2. SLM positioning: smaller, local, cheaper, private — show the trade-off (narrow scope) rather than hiding it.
3. Agentic positioning: show the plan and the approval step; autonomy without visibility reads as risk to executives.
4. Keep it under 10 clicks for a 10-minute slot.
5. Every on-screen number is synthetic and labeled "sample data" in the UI footer.
6. One demo per business decision. Variants for other verticals change data and copy, not flow.

## Demo tiers
| Tier | Scope | Build effort guide |
|---|---|---|
| Walkthrough | Scripted inputs, real model, mocked systems | Days |
| Interactive | Free-form inputs within a guarded domain, synthetic systems with state | 1–3 weeks |
| Pilot-grade | Client sandbox data, real integrations, evals | Project, not a demo |
Effort guides are assumptions; size per case.
