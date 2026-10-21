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
      - {name: current_spec, type: json, required: false, from: "graph spec JSON of the graph running today; adds the node/edge/state diff and flags changes that break resuming persisted threads"}
    run:
      - {step: build, kind: script, cmd: "python3 -I scripts/build_graph.py --spec {spec} [--current-spec {current_spec}] --out-dir {out}", stdout: "{out}/build.log"}
      - {step: upstream-review, kind: llm, template: assets/graph-review-template.md, context: ["../../../vendor/langgraph-fundamentals/SKILL.md", "../../../vendor/langgraph-fundamentals/references/python.md", "{out}/graph.md", "{out}/validation.json", "{out}/graph.py"], out: "{out}/graph-review.md", skip_if_missing: [review]}
    outputs:
      - {path: "{out}/validation.json", checks: [exists, json, contains:"\"valid\": true"]}
      - {path: "{out}/graph.md", checks: [exists, sections:["Diagram","Validation","Nodes","How to run"], mermaid_parses, no_unowned_tbd]}
      - {path: "{out}/graph.py", checks: [exists, contains:"builder.compile(", cmd:"python3 scripts/check_syntax.py {path} --require State --require build_graph"]}
    modes:
      new:      {case: agent-happy-path, bring: "a graph spec for the agent you plan"}
      existing: {case: agent-mode-existing, bring: "the spec of the graph running today plus your new spec"}
---

# LangGraph Runner

Wraps langgraph-fundamentals from langchain-ai/langchain-skills (pinned in vendor/pins.json). The upstream skill is instructions only; this skill turns its graph rules into deterministic checks and a generated scaffold. Upstream text is not copied here: the optional review step reads `vendor/langgraph-fundamentals/SKILL.md` and its Python reference directly.

## In a conversation: validate the graph now
**Never**
- Never invent nodes, state fields or routes: anything absent from the spec is an error, not a guess.
- Never write or show a `graph.py` scaffold for a spec with any error: the run **stops (exit 1)**, `validation.json` and `graph.md` are still written and `graph.md` says "No scaffold was written".
- Never call the scaffold tested or working: it is "generated and syntax-checked (`compile()` + `ast.parse`), not executed" — langgraph is not imported.
- Never rename the outputs: `validation.json`, `graph.md`, `graph.py`, and (review only) `graph-review.md`.

**Every reply that has or refers to a spec — including "here is my spec" with the file not shown — starts with these lines (copy them):**
1. "Runs `python3 -I scripts/build_graph.py --spec <spec.json> [--current-spec <live-spec.json>] --out-dir <dir>`."
2. "`validation.json` reports `valid` (true/false), the errors and the warnings."
3. "`graph.md` shows the Mermaid diagram (## Diagram), the validation table (## Validation), the node table plus state table (## Nodes) and how to run (## How to run)."
4. "`graph.py` (StateGraph scaffold) is generated and syntax-checked, not executed; it is written only when the spec is valid."
If the spec's content is not in the conversation, follow those lines with the expected section skeletons and ask once for the spec per `assets/graph-spec.example.json`; never stop at only a request.

**Procedure (rules from `references/graph-validation-rules.md` / `scripts/build_graph.py`; check node by node from the supplied spec)**
1. Graph = spec nodes + START + END; edges = START → entry, each static edge, each finish node → END, each conditional route `from -[label]-> to`.
2. Errors (exit 1): spec shape (name, state, nodes, entry); node names unique Python identifiers, not START/END/`State`/`build_graph`; kind in llm|tool|router|function; field type in str/int/float/bool/list/dict/any/messages, reducer `add` or `add_messages` compatible with the type; dangling edge (from/to not a node or END); any edge or route into START; node not reachable from entry; END not reachable from a node; a cycle (SCC of size > 1 or self-loop) with no conditional edge leaving it ("has no conditional exit"); a `router` with < 2 routes; two conditional blocks from one node; a reads/writes entry that is not a declared field ("undeclared state field 'x'").
3. Warnings (exit 0): a node with static AND conditional out-edges; a list field written by ≥ 2 nodes without a reducer; a declared field nobody reads or writes; a node without a description.
4. Missing or non-JSON spec → **stops (exit 2)** and asks for it.

**Reply layout**: a working table first (rule → nodes/fields checked → pass/error/warning), then `valid: true|false` with exit code, then graph.md (Diagram as a mermaid flowchart, Validation, Nodes + state, How to run), then the graph.py shape (TypedDict `State` with `Annotated` reducers, one stub per node, one `route_<node>` per conditional block returning a `Literal` of its labels, `add_node`/`add_edge`/`add_conditional_edges` wiring, `builder.compile(...)`) with the syntax-checked-not-executed statement.
- **Invalid spec**: list each error with its fix; say "stops (exit 1); no graph.py written".
- **Review requested** (`review=yes`): after the script outputs, write `graph-review.md` on `assets/graph-review-template.md` — Bottom line, **## Upstream conformance** (the six area rows, citing the upstream `vendor/langgraph-fundamentals/SKILL.md` and its Python reference as the source), **## Design risks** (each with an owner), **## Next changes** (each with an owner) — and say the upstream langgraph-fundamentals skill is its context.
- **Current spec given** (`current_spec`): add "## Changes vs current graph" — nodes added/removed/kind changed, edges (as from, to, route label over the edge set above) added/removed, state fields added/removed/changed (`type/reducer -> type/reducer`); total_changes = nodes + edges + state (+1 if entry changed). A removed field or a changed type or reducer is listed in `resume_breaking_fields`: threads checkpointed under the current graph cannot resume safely.

## Starting points
- **New** — validate a graph spec written from `assets/graph-spec.example.json` and generate the StateGraph scaffold.
- **Existing** — also pass the spec of the graph running today as `current_spec`: graph.md adds "Changes vs current graph" (nodes, edges/routes and state fields added, removed or changed) and flags state changes that break resuming threads already checkpointed.

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

## How to run (automation, when commands can run)
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/langgraph-runner --input <name>=<value> … --out <dir>` (see `--explain ai-platform/langgraph-runner`). Report the `run.json` results; do not hand-write the deliverables the scripts produce (`graph.py`, `graph.md`, `validation.json`). A failed validation (exit 1) is the gate working: fix the spec and re-run.
