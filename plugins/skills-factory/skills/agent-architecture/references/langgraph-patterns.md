# LangGraph State and Graph Design Patterns

House standard for orchestration (`shared/stack-conventions.md`). Patterns are framework-portable; LangGraph names are used for precision. Verify API names against the installed version before coding; names here are conceptual.

## 1. State design
| Rule | Practice |
|---|---|
| Typed state | `TypedDict` or pydantic model. No free-form dicts. Every field documented: type, owner node, reset rule. |
| Reducers for append-only fields | Messages and tool-call logs use an append reducer; scalar fields are overwritten by the last writer. |
| Separate durable from working state | Durable: task id, inputs, decisions, outputs, approvals. Working: scratch reasoning, retrieved chunks, retry counters. Working state is prunable. |
| Budgets live in state | `step_count`, `tokens_used`, `cost_usd`, `started_at`. Guard nodes read them; a budget node ends the run. |
| Private per-subgraph state | Specialists get an input/output schema; they do not see the supervisor's full state. |
| No secrets in state | Credentials come from the tool layer at call time; state is checkpointed and may be inspected. |

Minimal state table (copy into the design doc):
| Field | Type | Owner node | Reducer | Reset rule |
|---|---|---|---|---|
| task_id | str | entry | overwrite | never |
| messages | list[Message] | all | append | never (pruned by summarizer node) |
| plan | list[Step] | planner | overwrite | on replan |
| tool_results | list[ToolResult] | tool node | append | never |
| approvals | dict[str, Approval] | hitl node | merge | never |
| step_count | int | guard | overwrite | never |
| final_output | Output | finalizer | overwrite | never |

## 2. Graph shapes
| Shape | Nodes | Edges | Use |
|---|---|---|---|
| Linear workflow | A → B → C | static | Enumerable path |
| Router | classify → {pathA, pathB, fallback} | conditional on classification | Known branches |
| Tool loop (ReAct) | model ↔ tools, guard | conditional: tool_calls? → tools; else → end; guard checks budget each cycle | Single agent |
| Plan-execute | planner → executor(loop) → replanner | conditional on remaining steps | Longer tasks; plan is inspectable |
| Supervisor | supervisor → {specialist_i} → supervisor | conditional on supervisor choice; each specialist is a subgraph | Multi-domain |
| Map-reduce | fan-out (Send API or equivalent) → worker → reduce | dynamic parallel edges | Per-item processing |
| Generate-evaluate | generate → evaluate → (pass? end : generate), max N | conditional on score | Quality gate |

Every graph has: an entry node that validates inputs, a guard node (budget + policy), a terminal success node, and a terminal failure node that writes a structured reason. No graph ends by exception.

## 3. Interrupts and HITL
| Need | Mechanism |
|---|---|
| Approval before a side effect | `interrupt` before the tool node; resume with the human decision written to `approvals` |
| Human edits the plan | Interrupt after planner; human-edited plan replaces state.plan |
| Timeboxed approval | Checkpoint persists; a scheduler resumes with "expired" → failure or safe default |
| Audit | Every interrupt writes who/when/decision/diff to state and to the trace |

Interrupts require a checkpointer; without persistence an interrupt is a crash.

## 4. Checkpointing and memory
| Concern | Pattern |
|---|---|
| Durability | Postgres-backed checkpointer in prod; in-memory only for tests |
| Thread model | One thread id per task/conversation; never share threads across tenants |
| Pruning | Summarizer node compacts `messages` when tokens exceed a threshold; keep last K turns verbatim and a summary |
| Long-term memory | Separate store keyed by tenant/user; retrieved into working state by a node, never written by the model directly |
| Replay | Checkpoints enable time-travel debugging; keep retention policy aligned with data-retention rules |

## 5. Retries, timeouts, idempotency
| Rule | Practice |
|---|---|
| Tool timeouts | Every tool call has a timeout; the tool node maps timeouts to a structured error, not an exception |
| Retry policy | Exponential backoff for transient tool errors (max 3, assumption); zero retries for non-idempotent writes unless the tool proves idempotency via a key |
| Model retries | Retry on malformed tool-call JSON once with a corrective message; then fail to HITL |
| Idempotency keys | Derived from task_id + step id; passed to every write tool |
| Circuit breaker | Guard node trips after N consecutive tool failures and routes to failure node |

## 6. Observability fields (emit on every node)
`trace_id, thread_id, tenant_id, node, step_count, model, prompt_version, tokens_in, tokens_out, cost_usd, latency_ms, tool_name?, tool_status?, error_code?`

## 7. Testing the graph
| Level | What |
|---|---|
| Unit | Each node with mocked model/tool responses; reducers; guard thresholds |
| Graph | Golden traces: given recorded tool outputs, the graph takes the expected path |
| Eval | `llm-eval-harness` against a golden set; regression gate in CI |
| Chaos | Tool timeouts, malformed JSON, injected instructions in tool output |
