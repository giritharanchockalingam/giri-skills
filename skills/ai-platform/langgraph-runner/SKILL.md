---
name: langgraph-runner
description: Use when the user has a LangGraph workflow to design or check and wants runnable output — "validate my LangGraph spec", "generate the StateGraph scaffold", "will this graph loop forever", "draw the graph". Produces validation.json (reachability, END reachability, cycle exits, dangling edges, router routes, state-field references, reducer warnings), graph.md (Mermaid diagram, validation, node table, how to run) and a syntax-checked StateGraph scaffold graph.py; optional LLM review against the upstream langgraph-fundamentals guidance. Not for choosing the agent pattern (agent-architecture), human approval gates (langgraph-hitl-runner) or RAG (langchain-rag-runner).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: build
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: spec, type: json, required: true, from: "graph spec JSON: name, state [{name, type, reducer}], nodes [{name, kind llm|tool|router|function, description, reads, writes}], edges [{from, to}], conditional_edges [{from, routes {label: to}}], entry, finish (layout: assets/graph-spec.example.json)"}
      - {name: review, type: flag, required: false, flag: "--review", from: "yes to add an LLM review of the scaffold against the upstream langgraph-fundamentals guidance"}
    run:
      - {step: build, kind: script, cmd: "python3 -I scripts/build_graph.py --spec {spec} --out-dir {out}", stdout: "{out}/build.log"}
      - {step: upstream-review, kind: llm, template: assets/graph-review-template.md, context: ["../../../vendor/langgraph-fundamentals/SKILL.md", "../../../vendor/langgraph-fundamentals/references/python.md", "{out}/graph.md", "{out}/validation.json", "{out}/graph.py"], out: "{out}/graph-review.md", skip_if_missing: [review]}
    outputs:
      - {path: "{out}/validation.json", checks: [exists, json, contains:"\"valid\": true"]}
      - {path: "{out}/graph.md", checks: [exists, sections:["Diagram","Validation","Nodes","How to run"], mermaid_parses, no_unowned_tbd]}
      - {path: "{out}/graph.py", checks: [exists, contains:"builder.compile(", cmd:"python3 scripts/check_syntax.py {path} --require State --require build_graph"]}
---

# LangGraph Runner

Wraps langgraph-fundamentals from langchain-ai/langchain-skills (pinned in vendor/pins.json). The upstream skill is instructions only; this skill turns its graph rules into deterministic checks and a generated scaffold. Upstream text is not copied here: the optional review step reads `vendor/langgraph-fundamentals/SKILL.md` and its Python reference directly.

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/langgraph-runner --input <name>=<value> … --out <dir>` (see `--explain ai-platform/langgraph-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`graph.py`, `graph.md`, `validation.json`). A failed validation (exit 1) is the gate working: fix the spec and re-run.

## When to use
- A LangGraph workflow has been sketched (nodes, state, routing) and needs checking before code is written.
- An existing graph spec changed and must be re-validated (orphans, infinite loops, dangling routes).
- NOT for: deciding whether to build an agent at all (`agent-architecture`), adding approval interrupts (`langgraph-hitl-runner`), retrieval design (`langchain-rag-runner`), running evals (`llm-eval-harness`).

## Inputs required
| Input | Required | Source |
|---|---|---|
| `spec` — graph spec JSON (state fields with type and reducer; nodes with kind, description, reads, writes; static and conditional edges; entry; finish nodes) | yes | user / architect; layout `assets/graph-spec.example.json` |
| `review` — flag for the optional LLM review against upstream guidance | no | user |

Nothing is inferred: a node, field, or route absent from the spec is an error, not a guess. Field types: str, int, float, bool, list, dict, any, messages. Reducers: `add` (operator.add) or `add_messages`.

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. Fill the spec from `assets/graph-spec.example.json`. One node per discrete step; classify each as llm, tool, router or function; declare every state field each node reads or writes.
3. Run the skill. `scripts/build_graph.py` applies the rules in `references/graph-validation-rules.md`: reachability from entry, END reachable from every node, a conditional exit on every cycle, no dangling edges, routers with at least two routes, START used only as the entry, declared state references, reducer warnings for multi-writer list fields, static-plus-conditional warnings.
4. On exit 1, read the Errors list in `graph.md` (or `validation.json`), fix the spec, re-run. No `graph.py` is written for an invalid spec.
5. On exit 0, `graph.py` holds a TypedDict state, one stub per node, one `route_<node>` function per conditional block, the edge wiring and `compile()`. It was generated and syntax-checked (`compile()` + `ast.parse`), not executed: langgraph is not imported at check time.
6. Optional: pass `review=yes` for `graph-review.md`, an LLM review on `assets/graph-review-template.md` using the upstream skill and the run outputs as context.
7. Run the self-check.

## Output
| File | Content | Checks |
|---|---|---|
| `validation.json` | valid flag, errors, warnings, stats, unreachable nodes, nodes with no path to END, cycles with their conditional exits, scaffold status | json; `"valid": true` |
| `graph.md` | Diagram (Mermaid), Validation, Nodes (+ state table), How to run | sections; mermaid parses; no unowned TBD |
| `graph.py` | StateGraph scaffold | syntax check via `scripts/check_syntax.py`; contains `builder.compile(` |
| `graph-review.md` (optional) | Upstream conformance, Design risks, Next changes | eval case `agent-with-review` |

## Self-check
- [ ] `validation.json` says `"valid": true`, and every warning is accepted or fixed
- [ ] Every loop has a conditional exit; END is reachable from every node
- [ ] List fields written by several nodes carry a reducer
- [ ] No node has both static and conditional out-edges unless both branches are meant to run
- [ ] `graph.md` states the scaffold was syntax-checked, not executed
- [ ] Stubs were implemented and the graph was run in a langgraph environment before anyone calls it working

## References
- `references/graph-validation-rules.md` — each rule, why it exists, and how it is computed
- `scripts/build_graph.py` — validator and generator (argparse; stdlib)
- `scripts/check_syntax.py` — compile/ast check used by the output check
- `assets/graph-spec.example.json` — spec layout to copy
- `assets/graph-review-template.md` — template for the optional review
- Upstream: `vendor/langgraph-fundamentals/SKILL.md` (langchain-ai/langchain-skills, MIT, pinned in vendor/pins.json)
