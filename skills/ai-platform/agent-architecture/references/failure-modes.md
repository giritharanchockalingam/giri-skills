# Agent Failure Modes — detection and mitigation

Copy the relevant rows into the design doc; every row needs an owner.

| # | Failure mode | Symptom | Detection | Mitigation (design-time) | Mitigation (run-time) |
|---|---|---|---|---|---|
| 1 | Infinite / long loop | Same tool called repeatedly; step count climbs; no state change | Step cap; repeated-call detector (same tool + same args hash N times); no-progress check on state diff | Terminal states for "cannot proceed"; plan-execute with finite plan | Guard node ends run → HITL with trace |
| 2 | Tool misuse (wrong tool, wrong args) | Validation errors; tool returns "not found"; model retries with guesses | Schema validation errors per run; tool-choice accuracy in evals | Narrow tools; "when not to use" in descriptions; enums; examples; fewer tools per phase | One corrective retry with the validation message; then fail to HITL |
| 3 | Hallucinated tool or parameter | Call to a non-existent tool; invented ids | Unknown-tool error; id format checks | Strict tool list; id formats in schema; read-before-write pattern (fetch the entity first) | Reject call; return structured error; cap retries |
| 4 | Context overflow | Truncated history; model forgets instructions; quality degrades late in run | Token count per turn vs limit; eval score vs run length | Summarizer node; trim tool outputs; paginate; retrieval instead of stuffing | Compact state; restart subtask from checkpoint |
| 5 | Prompt injection via tool output | Agent follows instructions found in a document, email, or web page | Canary strings in test corpora; instruction-like patterns in tool output; unexpected tool calls after a read | Treat tool output as data (delimiters + provenance); no high-privilege tools in the same phase as untrusted reads; authZ in code | Block tool calls that follow an untrusted read without a plan step; HITL on anomaly |
| 6 | Data exfiltration | Sensitive data sent to an external tool or communication | DLP checks on outbound tool args; scope checks | Egress allow-list; PII redaction before external calls; scopes per phase | Block and alert |
| 7 | Cost runaway | Spend spikes; many parallel workers | Per-run cost in state; per-tenant daily budget | Token/cost caps; worker fan-out cap; cheaper model for routine steps | Kill switch per tenant; degrade to workflow mode |
| 8 | Non-idempotent retry | Duplicate orders, double refunds | Duplicate detection on write tools | Idempotency keys; two-phase writes | Reconcile job; HITL |
| 9 | Stale or conflicting state | Agent acts on data that changed mid-run | Version/ETag checks on write | Read-then-write with version; optimistic concurrency | Abort and replan |
| 10 | Cascading multi-agent error | Supervisor trusts a specialist's wrong output; errors compound | Specialist output validation; confidence fields; evaluator agent | Typed handoffs; validators between agents; evaluator loop for high-stakes | Fail the task, not the next agent |
| 11 | Silent degradation (model/prompt drift) | Eval scores drop after model or prompt change | Eval gate in CI; production sampling evals | Version prompts/models; canary rollout | Rollback prompt/model version |
| 12 | Over-refusal / under-action | Agent stops on benign tasks | Refusal rate metric | Clear policy in prompt; examples of allowed actions | Route to HITL with reason |
| 13 | Tool outage | Timeouts; empty results | Error rate per tool | Circuit breaker; fallback tool or cached data; degrade gracefully | Pause runs; notify |
| 14 | Unobservable decisions | Cannot explain why an action was taken | Missing trace fields | Mandatory observability fields per node; rationale captured at HITL points | N/A — fix at design time |

## Prompt-injection specifics
| Layer | Control |
|---|---|
| Input | Delimit and label untrusted content; strip or escape instruction-like markup; size caps |
| Prompt | State explicitly that content inside delimiters is data; list the only authorities (system, user, approved tools) |
| Tools | Least privilege per phase; no external_comm or irreversible tools active while reading untrusted content |
| Policy | Deny-list of actions regardless of instruction (export all records, change auth, disable logging) enforced in code |
| Testing | Injection corpus in evals (direct, indirect via documents, via tool errors); pass criterion: zero unauthorized tool calls |

## Budget defaults to state in the design doc (assumptions, tune per task)
| Budget | Default |
|---|---|
| Max steps per run | 25 |
| Max tokens per run | set from cost envelope |
| Max wall-clock | set from SLO |
| Max consecutive tool failures | 3 |
| Max fan-out workers | 10 |
| Max generate-evaluate iterations | 3 |
