---
name: langgraph-hitl-runner
description: Use when a LangGraph agent needs human approval before an action — "add an approval step before the refund", "who approves this and what happens on timeout", "generate the interrupt/resume code", "check our approval points are safe". Produces validation.json (approver role, timeout policy for high-impact actions, no auto-approve on irreversible actions, checkpointer present), hitl.md (approval matrix, validation, resume flow, risks) and a syntax-checked interrupt()/Command(resume) scaffold hitl.py with a checkpointer and resume handlers; optional LLM review against the upstream langgraph-human-in-the-loop guidance. Not for the overall graph (langgraph-runner) or AI risk registers (ai-governance-risk).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: spec, type: json, required: true, from: "approval-points spec JSON: graph, checkpointer memory|postgres|sqlite, state_fields (optional), interrupts [{before_node, reason, approver_role, timeout_minutes, on_timeout reject|escalate|auto-approve, escalate_to, editable_fields, high_impact, irreversible}] (layout: assets/approvals.example.json)"}
      - {name: review, type: flag, required: false, flag: "--review", from: "yes to add an LLM review of the gates against the upstream langgraph-human-in-the-loop guidance"}
      - {name: graph_spec, type: json, required: false, from: "graph spec JSON of the existing agent (langgraph-runner layout); gates are checked against its nodes and state, with the edges to rewire"}
    run:
      - {step: build, kind: script, cmd: "python3 -I scripts/build_hitl.py --spec {spec} [--graph-spec {graph_spec}] --out-dir {out}", stdout: "{out}/build.log"}
      - {step: upstream-review, kind: llm, template: assets/hitl-review-template.md, context: ["../../../vendor/langgraph-human-in-the-loop/SKILL.md", "{out}/hitl.md", "{out}/validation.json", "{out}/hitl.py"], out: "{out}/hitl-review.md", skip_if_missing: [review]}
    outputs:
      - {path: "{out}/validation.json", checks: [exists, json, contains:"\"valid\": true"]}
      - {path: "{out}/hitl.md", checks: [exists, sections:["Approval matrix","Validation","Resume flow","Risks"], no_unowned_tbd, contains:"not executed"]}
      - {path: "{out}/hitl.py", checks: [exists, contains:"Command(resume=", cmd:"python3 scripts/check_syntax.py {path} --require build_graph --require make_checkpointer --require resume --require resume_on_timeout"]}
    modes:
      new:      {case: agent-happy-path, bring: "the approval points you want, written as a spec"}
      existing: {case: agent-mode-existing, bring: "your existing agent's graph spec and the approvals to add"}
---

# LangGraph HITL Runner

## In a conversation: write the approval gates now
- **The request names the gated actions** (e.g. finance approves refunds, a team lead approves customer emails): write the gates **in this reply**, in this order. (1) The approval-points spec as JSON in the `assets/approvals.example.json` layout — `graph`, `checkpointer`, `state_fields`, and per gate `before_node`, `reason`, `approver_role`, `timeout_minutes`, `on_timeout` (reject, escalate or auto-approve), `escalate_to`, `editable_fields`, `high_impact`, `irreversible`. Use only the roles the user named; every timeout, escalation role, editable field and checkpointer not stated is `[TO BE BASELINED — owner: Process owner]` (checkpointer: Engineering lead), and the reply asks for them once in one list. (2) The approval matrix table: gate, reason, approver role, timeout, on-timeout policy, escalation role, editable fields, high-impact, irreversible. (3) The rules that apply (`references/approval-rules.md`): a high-impact or irreversible gate needs a timeout; an irreversible action (money out, a sent email) never auto-approves on timeout; the memory checkpointer is development only — postgres or sqlite otherwise. (4) The resume flow: `start` runs to the `interrupt()` in `approve_<node>` (interrupt first — code before it re-runs on resume); the approver's decision comes back via `resume` with the **same `thread_id`** and `Command(resume=...)` only; `Command(goto=...)` routes to the action or to reject/escalate; side effects sit in the action node after approval and are idempotent; a scheduler calls `resume_on_timeout` because LangGraph has no timer; approver identity is checked in `resume`. (5) The `hitl.py` contents: `GATES`, the `approve_<node>` and `escalate_<node>` gates, action stubs, `make_checkpointer()`, `build_graph()`, `start` / `resume` / `resume_on_timeout`. Say `scripts/build_hitl.py` validates the spec and generates `hitl.py`, which is syntax-checked, not executed; code drafted in chat is a draft until that run. Then give the run command.
- **Nothing about the actions is given** ("add human approval to my agent"): ask once, in one list, for each action to gate, why, the approver role, timeout and on-timeout policy, escalation role, fields the approver may edit, whether it is high-impact or irreversible, and the checkpointer. Do not invent approvers or timeouts.
- **Asked for an unsafe gate** (auto-approve a payment or other irreversible action on silence, no checkpointer, no approver, a high-impact gate with no timeout): decline in one line per rule with the reason (silence must not trigger an action that cannot be undone; without a checkpointer an interrupt cannot resume), say the validation fails and no `hitl.py` is written, and offer the safe version: escalate or reject on timeout, a postgres checkpointer, a named approver.
- **An existing graph is given**: fit each gate to a real node, list the incoming edges to rewire to each `approve_<node>`, and name the tool nodes left ungated for the risk owner to accept or gate.

Wraps langgraph-human-in-the-loop from langchain-ai/langchain-skills (pinned in vendor/pins.json). The upstream skill is instructions only; this skill turns its requirements (checkpointer, thread id, interrupt first, resume with `Command(resume=...)`, idempotent side effects) into deterministic checks and a generated scaffold. Upstream text is not copied: the optional review step reads `vendor/langgraph-human-in-the-loop/SKILL.md` directly.

## Starting points
- **New** — validate an approval-points spec written from `assets/approvals.example.json` and generate the interrupt/resume scaffold.
- **Existing** — also pass the existing agent's graph spec as `graph_spec`: every gate must name a real node and real state fields, hitl.md adds "Fit to existing graph" (incoming edges to rewire to each `approve_<node>`) and names tool nodes left without a gate.

## When to use
- An agent will take an action a person must approve, edit or reject first (payments, outbound messages, record changes).
- Approval rules need writing down: who approves, how long they have, what happens on silence, what they may edit.
- NOT for: designing the rest of the graph (`langgraph-runner`), AI risk classification (`ai-governance-risk`), choosing whether an agent is the right pattern (`agent-architecture`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `spec` — approval-points JSON: graph name, checkpointer, one entry per gated node (reason, approver role, timeout, on-timeout policy, escalation role, editable fields, high-impact and irreversible flags) | yes | process owner + engineering lead; layout `assets/approvals.example.json` |
| `review` — flag for the optional LLM review against upstream guidance | no | user |

Roles, timeouts and policies come only from the spec. A missing approver role is an error; a missing escalation role becomes `[TO BE BASELINED — owner: Process owner]`.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. List every action that needs approval. Flag `high_impact` (money, customer-visible, regulated) and `irreversible` (cannot be undone) honestly: the rules key on these flags.
3. Fill `assets/approvals.example.json` and run the skill. `scripts/build_hitl.py` applies `references/approval-rules.md`.
4. On exit 1, fix the errors listed in `hitl.md`/`validation.json` and re-run. No `hitl.py` is written for an invalid spec.
5. On exit 0, `hitl.py` holds: `GATES` (the approval matrix as data), one `approve_<node>` gate per interrupt with `interrupt()` first and `Command(goto=...)` routing, optional `escalate_<node>` gates, action-node stubs, `make_checkpointer()` for the chosen backend, `build_graph()` compiled with the checkpointer, and `start` / `resume` / `resume_on_timeout` handlers. It was generated and syntax-checked, not executed.
6. Wire a scheduler to call `resume_on_timeout` (LangGraph has no timer) and authenticate approvers in `resume`.
7. Optional: pass `review=yes` for `hitl-review.md` on `assets/hitl-review-template.md`.
8. Run the self-check.

## Output
| File | Content | Checks |
|---|---|---|
| `validation.json` | valid flag, errors, warnings, normalised gates, scaffold status | json; `"valid": true` |
| `hitl.md` | Approval matrix, Validation, Resume flow, Risks | sections; no unowned TBD; says not executed |
| `hitl.py` | interrupt/resume scaffold | syntax check (`scripts/check_syntax.py`) with required handlers; contains `Command(resume=` |
| `hitl-review.md` (optional) | Upstream conformance, Gaps, Decisions needed | eval case `agent-with-review` |

## Self-check
- [ ] Every gate names an approver role; every high-impact or irreversible gate has a timeout and policy
- [ ] No irreversible action auto-approves on timeout; any auto-approve is accepted by a named risk owner
- [ ] Checkpointer is postgres or sqlite outside development
- [ ] Side effects sit in the action node after approval and are idempotent
- [ ] The same `thread_id` is used to start and resume; resume uses `Command(resume=...)` only
- [ ] A scheduler enforces timeouts; approver identity is checked in `resume`

## References
- `references/approval-rules.md` — each rule, why, and how the scaffold implements it
- `scripts/build_hitl.py` — validator and generator (argparse; stdlib)
- `scripts/check_syntax.py` — compile/ast check used by the output check
- `assets/approvals.example.json` — spec layout to copy
- `assets/hitl-review-template.md` — template for the optional review
- Upstream: `vendor/langgraph-human-in-the-loop/SKILL.md` (langchain-ai/langchain-skills, MIT, pinned in vendor/pins.json)

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/langgraph-hitl-runner --input <name>=<value> … --out <dir>` (see `--explain ai-platform/langgraph-hitl-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`hitl.py`, `hitl.md`, `validation.json`). A failed validation (exit 1) is the gate working: fix the spec and re-run.
