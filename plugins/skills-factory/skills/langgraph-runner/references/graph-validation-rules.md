# Graph validation rules

How `scripts/build_graph.py` turns the upstream langgraph-fundamentals guidance (langchain-ai/langchain-skills, pinned in vendor/pins.json) into checks. The upstream file is the authority on LangGraph behaviour; this note records only what our script computes.

## Graph model
- Vertices: every spec node, plus `START` and `END`.
- Edges: `START -> entry`; each static edge; `finish node -> END`; each conditional route `from -[label]-> to`.
- Routes and static edges may target `END`. Nothing may target `START`.

## Errors (exit 1; no scaffold written)
| Rule | Computation | Why it matters |
|---|---|---|
| Spec shape | name, state, nodes, entry present; lists of objects | Nothing is inferred |
| Node names | unique Python identifiers; not START/END; not a scaffold name (`State`, `build_graph`, …) or a generated `route_<node>` name | Names become function names in `graph.py` |
| Node kind | one of llm, tool, router, function | Drives the diagram shape and review |
| Field types and reducers | type in str/int/float/bool/list/dict/any/messages; reducer `add` (list, int, float, str, messages) or `add_messages` (list, messages) | Reducers decide how concurrent or repeated writes merge |
| Dangling edges | every `from`/`to` is a node (or END for targets) | LangGraph rejects unknown nodes at compile time |
| START is entry-only | no edge or route into START | Loops must route through a named node |
| Reachability | BFS from `entry` over static and conditional edges; unreached nodes are errors | Orphans are dead code or missing wiring |
| END reachability | reverse BFS from END; any node that cannot reach END is an error | A run from that node can never finish |
| Cycle exits | Tarjan strongly connected components; each cycle (size > 1 or self-loop) needs a conditional edge leaving it | Static edges all fire, so a static-only loop never stops |
| Routers | a node of kind `router` has one `conditional_edges` block with >= 2 routes | A one-way router is a static edge in disguise |
| One conditional block per node | duplicate `from` in `conditional_edges` | Merge routes into one path map |
| State references | every `reads`/`writes` entry is a declared field | Prevents KeyError-shaped bugs |

## Warnings (exit 0)
| Rule | Computation |
|---|---|
| Static plus conditional out-edges on one node | both execute every run |
| List field with >= 2 writers and no reducer | last write wins; earlier writes are lost |
| Declared field nobody reads or writes | dead state |
| Node without a description | review gap |

## Scaffold
- Generated as text: TypedDict `State` (reducers via `Annotated`), one stub per node raising `NotImplementedError`, one `route_<node>` per conditional block returning a `Literal` of its labels, `add_node` / `add_edge` / `add_conditional_edges` wiring, `compile(checkpointer=...)`.
- Verified with `compile()` and `ast.parse()`. Not executed and langgraph not imported: the portal runtime does not have it. Outputs say so.

## Limits
- The spec does not model `Send` fan-out or `Command(goto=...)` returns; add those by hand after generation and re-review.
- Reachability treats every conditional route as possible; whether a route is ever taken depends on the router code.
