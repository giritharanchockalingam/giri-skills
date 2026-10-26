# Talk Track Structure

Timing shown for a 10-minute slot; scale proportionally. Keep 20% buffer for questions.

| Beat | Time | Purpose | What to say / do |
|---|---|---|---|
| 1. Hook | 0:00–0:45 | Name the decision and its cost today | "Today <persona> spends <X, illustrative> doing <task>. Watch it take <Y>." |
| 2. Context | 0:45–1:30 | Persona, data, boundary | "<Persona> opens the studio; sample data from a <vertical> company; everything runs on an SLM inside the tenant." |
| 3. Happy path | 1:30–5:00 | 3–5 steps, narrate what the system is doing, not the UI | "It pulled the policy, cited section 4, drafted the response." Pause on each output. |
| 4. Wow moment 1 | within beat 3 | The cross-reference or action a human would skip | Point at the citation or the plan |
| 5. Handled failure | 5:00–6:30 | Trust | Ask the planted out-of-scope question; show the abstention or the approval screen; "It does not guess." |
| 6. Wow moment 2 | 6:30–7:15 | Agentic action with approval | Approve; show the system of record updated (mocked) with an audit entry |
| 7. Under the hood | 7:15–8:00 | One diagram | Where data stays; what is model, tool, and policy |
| 8. Close and ask | 8:00–8:30 | Next step | "Pilot on your data in <timeframe — to be baselined>: we need <two inputs> from you." |
| Buffer | 8:30–10:00 | Q&A | |

## Delivery rules
1. Narrate intent before clicking ("I'll ask it something it should refuse").
2. Never say "the model is smart"; say what it did and what checked it.
3. Numbers on screen are sample data; say so once.
4. If something breaks: switch to cached outputs, keep narrating; do not debug live.

## Anticipated questions (prepare answers with evidence or "to be baselined")
| Question | Answer frame |
|---|---|
| Where does our data go? | Diagram; tenant boundary; no training on inputs; logging policy |
| How accurate is it? | Eval approach and gate; pilot measures on their data; no benchmark claims |
| What happens when it is wrong? | Handled-failure beat; HITL; audit trail; feedback loop |
| Why a small model? | Scope, cost, residency, latency; trade-off named |
| Can it do X? | On screen = yes; otherwise roadmap, labeled |
| What does a pilot take? | Inputs needed, duration, success criteria — to be baselined with their team |

## Objection handling
| Objection | Response |
|---|---|
| "We tried a chatbot and it hallucinated" | Grounding + citations + abstention shown; eval gate before release |
| "Our data is messy" | Demo on synthetic data; pilot starts with a data-readiness check (ai-use-case-canvas) |
| "Security will block it" | Architecture glance: gateway, scopes, HITL, logs; governance review path |
| "Too expensive" | SLM/API cost levers; sizing done from their volumes (infra-gpu-sizing) |
