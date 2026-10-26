# Human-in-the-Loop Checkpoint Placement

Rule: a human sits wherever a wrong action is expensive to reverse, not wherever the model is uncertain. Uncertainty is handled by evals and fallbacks; irreversibility is handled by people.

## Mandatory checkpoints
| Trigger | Checkpoint | What the human sees | Allowed decisions |
|---|---|---|---|
| Irreversible side effect (payment, deletion, record update in a system of record) | Before the commit step (two-phase tool) | Preview/diff, affected entities, agent's rationale, confidence inputs | Approve / Edit / Reject |
| External communication (email, SMS, ticket reply, post) | Before send | Full message, recipient, context summary | Approve / Edit / Reject |
| Access escalation (new scope, new data source) | Before the first call | Scope requested, reason | Approve once / Approve for session / Deny |
| Policy boundary (PII export, regulated decision: credit, employment, health, education record) | Before the decision is recorded | Inputs, decision, policy reference | Approve / Override with reason / Escalate |
| Budget exhaustion or circuit breaker | On trip | Steps taken, cost, last error | Continue with new budget / Stop |
| Low-confidence or conflicting tool results | Before continuing | Conflict summary | Choose / Provide info / Stop |

## Optional checkpoints (adopt by risk tier)
| Tier | Add |
|---|---|
| Low (internal, reversible) | Post-hoc sampling review (e.g., 5% of runs, assumption) |
| Medium (employee-facing, reversible) | Review of the plan before execution for runs over N steps |
| High (customer-facing or autonomous writes) | Approval on every write; batch approvals allowed with per-item diffs |

## Design rules
1. **Show the diff, not the chat.** Humans approve a change, not a transcript. Render before/after.
2. **Make approve the slow path only when it matters.** Reversible, low-value actions execute and are reported; do not train reviewers to click through.
3. **Timebox.** Every pending approval has an expiry and a safe default (usually "do nothing, notify").
4. **Record the decision** with who, when, what changed, and why; feed rejections into the eval set.
5. **Batch where possible.** Group approvals per task (10 ticket replies in one review screen) with per-item accept/reject.
6. **Edit beats reject.** If reviewers edit often, capture edits as training/eval data and tune the prompt or tool.
7. **Reviewer load is a capacity constraint.** Model it: runs/day × approval rate × minutes per review. If it exceeds capacity, reduce autonomy scope, not review quality.

## Metrics
| Metric | Purpose |
|---|---|
| Approval rate | High (>95%, assumption) suggests the checkpoint can move to sampling |
| Edit rate and edit distance | Prompt/tool quality signal |
| Time-to-decision | Reviewer load; SLA risk |
| Rejections by reason | Failure-mode taxonomy input |
| Overrides on policy checkpoints | Governance review input |
