# Decision Tree — workflow vs single agent vs multi-agent

Principle: the cheapest control structure that meets the success metric wins. An LLM in the control loop is a cost and a risk; pay it only when the task demands it.

## Tree
```
Q1. Can the steps be enumerated in advance for every input?
    YES → Deterministic WORKFLOW (LLM calls as steps; code decides the path)   → stop
    NO  ↓
Q2. Does the task need the model to choose which tools to call, in what order, based on intermediate results?
    NO  → WORKFLOW with a classifier/router step                                 → stop
    YES ↓
Q3. Can one model, with ≤ ~10 tools and one context window, finish the task within budget?
    YES → SINGLE AGENT (tool loop with step/budget limits)                      → stop
    NO  ↓
Q4. Why not? Pick the first that applies:
    a. Too many tools / instructions for one prompt     → SINGLE AGENT + tool routing (group tools; select subset per turn)
    b. Distinct expertise with different prompts/data    → SUPERVISOR + SPECIALISTS (multi-agent, hierarchical)
    c. Long task exceeding context                       → SINGLE AGENT + external memory + checkpointed subtasks (still one agent)
    d. Parallelizable independent subtasks               → ORCHESTRATOR + WORKERS (fan-out/fan-in, workers stateless)
    e. Adversarial review needed (generate vs critique)  → GENERATOR + EVALUATOR loop (2 agents, bounded iterations)
Peer-to-peer "swarm" of agents talking freely → NOT RECOMMENDED for enterprise; use (b) or (d) with explicit handoff rules.
```

## Pattern summary
| Pattern | Control lives in | Use when | Avoid when | Typical budget |
|---|---|---|---|---|
| Workflow | Code | Path is knowable; auditability matters; high volume | Inputs are open-ended | Fixed |
| Router + workflow | Code, one classification | 2–10 known paths | Paths change often | Fixed per path |
| Single agent | Model, bounded by step limit | Open-ended but single domain; tools ≤ ~10 | Tools conflict or exceed context | Step cap 10–25 (assumption; tune per task) |
| Supervisor + specialists | Supervisor model routes; specialists bounded | Distinct domains, prompts, or data scopes | Specialists need shared mutable state | Supervisor steps × specialist caps |
| Orchestrator + workers | Code fan-out; workers single agents | Parallel independent subtasks (per document, per account) | Subtasks depend on each other | N × worker cap |
| Generator + evaluator | Code loop | Quality must be checked before release; evaluator has a rubric | No objective rubric exists | ≤ 3 iterations |

## Criteria that force escalation (record the one you hit)
| From | To | Criterion |
|---|---|---|
| Workflow | Single agent | Branching cannot be enumerated; >~20% of inputs need a path the code did not anticipate |
| Single agent | Tool routing | Tool descriptions + system prompt exceed ~30% of the context budget, or tool-choice error rate exceeds target in evals |
| Single agent | Supervisor + specialists | Two or more tool groups need conflicting instructions or different data-access scopes |
| Single agent | Orchestrator + workers | Wall-clock SLO cannot be met sequentially; subtasks are independent |
| Any | Generator + evaluator | Output has a rubric and the cost of a wrong output exceeds the cost of a second model call |

## Anti-patterns
| Anti-pattern | Why it fails | Fix |
|---|---|---|
| Multi-agent for status | Doubles cost and failure surface with no capability gain | Collapse to single agent; prove the single agent fails first |
| Agents sharing one mutable scratchpad | Race conditions, context pollution, untraceable decisions | Explicit typed handoffs; each agent owns its state slice |
| Unbounded loops ("until done") | Cost runaway; infinite retries on a stuck tool | Step cap, token cap, wall-clock cap, and a terminal "give up" state with HITL |
| Agent writes to production systems without a gate | Irreversible harm from one bad reasoning step | Side-effect class = write/irreversible ⇒ HITL or dry-run + confirm |
| Model decides authorization | Prompt injection becomes privilege escalation | AuthZ in code and in the tool server; the model only selects among pre-authorized tools |
