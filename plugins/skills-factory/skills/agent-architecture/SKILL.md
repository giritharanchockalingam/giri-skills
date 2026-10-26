---
name: agent-architecture
description: Use when the user asks to design an AI agent or agentic system — "should this be an agent", "single vs multi-agent", "design the LangGraph graph", "define the tools / MCP contracts", "where do humans approve". Produces a pattern decision (workflow vs single agent vs multi-agent) with rationale, a state and graph design, tool contracts, human-in-the-loop checkpoints, a failure-modes table with mitigations, and an agent design doc. Not for building MCP servers (use mcp-server-builder), RAG retrieval design (use rag-pipeline-design), or evaluation (use llm-eval-harness).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: architecture
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: answers, type: json, required: true, from: "answers.json: the six decision-tree questions (q1_steps_enumerable, q2_model_chooses_tools, q3_single_agent_fits, q4_blocker, q5_rubric_exists, q6_irreversible_actions) with optional evidence (layout: evals/fixtures/answers.json)"}
      - {name: design_doc, type: md, required: true, from: "agent design doc filled from assets/agent-design-doc.md"}
      - {name: contracts, type: json, required: true, from: "tool-contracts.json: list of tool contracts per assets/tool-contract.schema.json + failure_modes (layout: evals/fixtures/tool-contracts.json)"}
      - {name: name, type: string, required: false, default: "<agent>"}
    run:
      - {step: pattern, kind: script, cmd: "python3 -I scripts/pattern.py {answers} --out {out}/pattern.md --name {name}"}
      - {step: design-check, kind: script, cmd: "python3 -I scripts/design_check.py {design_doc} {contracts} --out {out}/design-check.csv --schema assets/tool-contract.schema.json --answers {answers}"}
    outputs:
      - {path: "{out}/pattern.md", checks: [exists, sections:["Rationale","Escalation trail","Rejected patterns","Human-in-the-loop","Budgets"], no_unowned_tbd]}
      - {path: "{out}/design-check.csv", checks: [exists, csv:[item,kind,present,issue], csv_rows:present~^yes$]}
    modes:
      new:      {case: agent-happy-path, bring: "your answers to six questions and a first design draft"}
      existing: {case: agent-mode-existing, bring: "your live agent's design doc, tool contracts and current answers"}
---

# Agent Architecture

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/agent-architecture --input <name>=<value> … --out <dir>` (see `--explain ai-platform/agent-architecture`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`pattern.md`, `design-check.csv`). A failed design check (exit 1) is the gate working: fix the doc or contracts and re-run.

## Starting points
- **New** — an agent idea: answer the six decision-tree questions and draft the design doc from `assets/agent-design-doc.md`; the skill picks the pattern and gates the draft and its tool contracts before build.
- **Existing** — an agent already running: bring its design doc, tool contracts and the six answers re-taken with production evidence; the skill re-derives the pattern, flags a doc whose declared pattern no longer matches the tree, and re-gates sections and contracts.

## When to use
- Designing a new agentic system or reviewing one: pattern, state, tools, control flow, HITL, failure handling.
- Framework-neutral by default; LangGraph patterns are given because they are the house standard (see `../../shared/stack-conventions.md`).
- NOT for: writing an MCP server (`mcp-server-builder`), retrieval tuning (`rag-pipeline-design`), scoring quality (`llm-eval-harness`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| Job to be done, in one sentence, with the success metric | yes | user |
| Actions the system may take (read-only vs write; external side effects) | yes | user |
| Available tools/APIs/data sources and their auth model | yes | user / repo |
| Autonomy appetite: who approves what, and the blast radius of a wrong action | yes | user; default to conservative if unstated |
| Latency and cost envelope | no | user; mark `[TO BE BASELINED — owner: ___]` |
| Non-functional constraints (data residency, PII, audit) | no | user |

If the job statement or the action list is missing, ask once. Never design an agent for an undefined task.

## Procedure
1. Read `../../shared/quality-bar.md`, `../../shared/stack-conventions.md`, `../../shared/token-efficiency.md`.
2. **Decide the pattern** with `references/decision-tree.md`. Default order of preference: deterministic workflow → single agent with bounded tools → multi-agent. Escalate only when the previous level fails a stated criterion. Record the criterion that forced the escalation.
3. **Design state and graph** with `references/langgraph-patterns.md`: typed state schema, nodes, edges, interrupt points, checkpointer, retry policy. One graph diagram (Mermaid) and one state table.
4. **Write tool contracts** with `references/mcp-tool-contracts.md` and `assets/tool-contract.schema.json`. Every tool: name, purpose, input schema, output schema, side-effect class (read / write / irreversible), idempotency, auth scope, timeout, error shape.
5. **Place HITL checkpoints** with `references/hitl-placement.md`. Minimum: before any irreversible side effect and before any external communication. State what the human sees and what they can do (approve / edit / reject).
6. **Fill the failure-modes table** from `references/failure-modes.md`: loops, tool misuse, context overflow, prompt injection, cascading multi-agent errors, cost runaway. Each has detection + mitigation + owner.
7. **Produce the design doc** from `assets/agent-design-doc.md`. Include evaluation hooks (hand off to `llm-eval-harness`) and observability fields (trace id, step count, tokens, cost, tool calls).
8. Run the self-check.

## Output
- `agent-design-<name>.md` from the template: decision, state schema, graph, tool contracts, HITL, failure modes, NFRs, open questions.
- Tool contracts additionally as JSON (one file per tool) when the user is going to implement.

## Self-check
- [ ] The pattern decision names the criterion that ruled out the simpler option
- [ ] State schema is typed; every field has an owner node and a reset rule
- [ ] Every tool has a side-effect class and an idempotency statement
- [ ] HITL before every irreversible or external-facing action
- [ ] Failure table covers loops, tool misuse, context overflow, prompt injection at minimum
- [ ] Step, token, cost, and wall-clock budgets are set (or `[TO BE BASELINED]`)
- [ ] No vendor benchmark claims; no "the model will figure it out"

## References
- `references/decision-tree.md` — workflow vs single agent vs multi-agent
- `references/langgraph-patterns.md` — state, graph, interrupts, checkpoints, retries
- `references/mcp-tool-contracts.md` — contract rules and anti-patterns
- `references/hitl-placement.md` — where humans go and what they see
- `references/failure-modes.md` — failure modes with detection and mitigation
- `scripts/pattern.py` — six decision-tree answers → `pattern.md` (pattern, rationale, rejected patterns)
- `scripts/design_check.py` — design doc + tool contracts → `design-check.csv`; exit 1 on a missing section or invalid contract, or (with `--answers`) when the doc's declared pattern differs from the decision tree's
