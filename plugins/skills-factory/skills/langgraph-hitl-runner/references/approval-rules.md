# Approval rules

What `scripts/build_hitl.py` enforces, mapped to the upstream langgraph-human-in-the-loop guidance (langchain-ai/langchain-skills, pinned in vendor/pins.json). The upstream file is the authority on LangGraph behaviour; this note records our rules and the scaffold shape.

## Errors (exit 1; no scaffold)
| Rule | Why |
|---|---|
| `graph` named; `interrupts` non-empty | Nothing to gate otherwise |
| `checkpointer` is memory, postgres or sqlite | Interrupts pause by saving state; without a checkpointer they cannot resume |
| `before_node` is a unique Python identifier, not a scaffold name | Becomes a node and function name |
| `reason` and `approver_role` present | The approver must know why, and someone must be accountable |
| `on_timeout` is reject, escalate or auto-approve | Silence needs a defined outcome |
| `timeout_minutes` positive when given | A window the scheduler can enforce |
| `high_impact` or `irreversible` gate has `timeout_minutes` | A high-stakes request must not wait forever unnoticed |
| `irreversible` gate never auto-approves on timeout | Silence must not trigger an action that cannot be undone |
| `editable_fields` are identifiers and, when `state_fields` is given, declared there | Approvers may only edit what the graph knows |

## Warnings
| Rule | Why |
|---|---|
| `memory` checkpointer | Paused threads vanish on restart; development only |
| `escalate` without `escalate_to` | Escalation approver becomes `[TO BE BASELINED — owner: Process owner]` |
| `on_timeout` without `timeout_minutes` | The policy never fires |
| `auto-approve` on any gate | Silence equals consent; a risk owner must accept it |

## Scaffold shape (`hitl.py`)
| Element | Implements |
|---|---|
| `GATES` dict | The approval matrix as data, read at run time |
| `approve_<node>` | `interrupt()` is the first call (code before it re-runs on resume); payload is JSON-serializable; routes with `Command(goto=...)` and has no static out-edge, so only one branch runs |
| `_apply_decision` | approve / edit / reject / escalate / timeout; edits outside `editable_fields` are refused; every decision appended to `decisions` (reducer `operator.add`) |
| `escalate_<node>` | Second-level interrupt for the escalation role |
| `<node>` stub | The gated action; side effects only here, idempotent |
| `make_checkpointer()` | InMemorySaver, SqliteSaver or PostgresSaver per spec; connection strings from environment variables, never in code |
| `build_graph()` | Compiles with the checkpointer |
| `start` / `resume` / `resume_on_timeout` | Same `thread_id` throughout; resume only via `Command(resume=...)`; timeouts resumed by an external scheduler |

Generated as text, verified with `compile()` and `ast.parse()`, never executed here (langgraph is not installed in the portal runtime).

## Limits
- Gates are wired linearly in spec order; merge them into the real graph (re-validate it with langgraph-runner).
- Parallel interrupts (several gates pending at once) need a resume map keyed by interrupt id; extend `resume` if your graph fans out.
