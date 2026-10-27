# The delivery harness

The model writes the code. The harness decides what it is asked to do, where its code may run, what it may spend,
what counts as done and what is recorded. "An agent is only as reliable as its harness."

This document is the design and the status of the harness around `scripts/deliver.py` (one run = one change through
requirements → architecture → build → evaluate → deploy → operate) and `scripts/harness.py` (a goal = a DAG of runs).

## Why (evidence, Oct 26–27 2026)

| What happened | Which harness layer was missing |
|---|---|
| CAPE 2.0 was split into 7 slices and chained **by hand** (by the operator model, not the pipeline) | Task decomposition, DAG builder |
| A container restart lost the R2 run entirely; the chain was relaunched by hand | Durable state for the chain |
| 486 tests and every gate passed; an independent reviewer then found the goal's one non-negotiable (no stale data) NOT MET in 4 minutes | Result verification against **requirements**, not just structure |
| `npm install`, tests and benchmarks of model-written code ran on the host | Sandbox |
| Nobody knew what a run cost | Budget circuit breaker, telemetry |
| 13 of 13 approvals were `--approve-all` | Human-in-the-loop gate exercised for real |
| Two lexical false positives in the security skill hard-stopped runs (G3, R1) | Disputable gates (waivers) |
| Pipeline changes were validated by rerunning scenarios by hand | Eval regression set |

## The eight layers

| # | Layer | Mechanism | Where |
|---|---|---|---|
| 1 | **Requirements verification gate** | After tests, benchmark and visual check pass, an independent reviewer (fresh `claude -p` session, never sees the builder's summary) receives the acceptance criteria (PRD, brief goals, goal document) and the code. It must give every criterion MET / PARTLY / NOT_MET / UNVERIFIED **with evidence it produced** (a command it ran in the sandbox, file:line it read). NOT_MET, PARTLY on a must-have, or a critical/high defect fails the code step → the findings go back to the builder as a repair turn → tests → reviewer again, bounded by `--rounds`. Output `acceptance.json` + `acceptance.md` in the evidence. | `deliver.py` `run_acceptance` |
| 2 | **Goal decomposer + durable run DAG** | `harness.py plan` turns a goal document into `slices.json` (id, title, brief, depends_on, acceptance) — model-proposed, schema-validated, acyclic, every goal section covered or listed as out of scope. `harness.py run` executes slices in topological order, one `deliver.py` run each, checkpointing `state.json` after every transition; a restart resumes the first incomplete slice (and the run inside it with `--resume`). | `scripts/harness.py` |
| 3 | **Sandbox per run** | `--sandbox docker`: every command that executes project code (install, tests, benchmark, the app for the visual check, the reviewer's experiments) runs in a container: only the project and the step's evidence folder are writable, system folders read-only, `--network none` (install: host network for the registry only), CPU / memory / process limits, a wall-clock timeout. Postgres is reached through its unix socket, never the network. `--sandbox none` is explicit and printed in the evidence as NOT SANDBOXED. | `scripts/sandbox.py`, `deliver.py` |
| 4 | **Budget circuit breaker** | Every model call runs with `--output-format json`; cost, tokens, turns and duration are recorded per call. `--budget-usd` caps a run (each call gets `--max-budget-usd` = what is left); `--max-turns` caps a call. Exceeding the budget stops the run with a clear verdict, never silently. | `deliver.py` `run_claude` |
| 5 | **Telemetry** | `trace.json` in OTLP/JSON: one trace per run, a span per stage, step and model call, with cost, tokens, verdict, repair turn. `OTEL_EXPORTER_OTLP_ENDPOINT` (Langfuse, Arize, LangSmith, any OTLP collector) receives it at the end of the run. EVIDENCE.md gets a Cost line. | `scripts/telemetry.py` |
| 6 | **Eval regression set** | `evals/pipeline/` holds scenarios (G1 API+Postgres, G2 student UI, G3 Supabase RLS, CAPE slices) with expectations; `pipeline_eval.py` runs them through the harness, writes a scorecard (pass rate, defects caught, repair turns, cost, acceptance verdicts) and compares it with the committed baseline: a lower pass rate or a cost rise above the threshold is a regression. | `scripts/pipeline_eval.py` |
| 7 | **Human-in-the-loop gate, for real** | `harness.py` never passes `--approve-all` unless asked: it stops at each plan approval (exit 3, `needs_approval.json`), and `harness.py approve --slice ID --by NAME [--note]` records who approved what, then `run` continues. The slice plan itself is approved the same way before any slice runs. Auto-approval stays possible and stays labelled AUTO-APPROVED. | `harness.py`, existing approvals |
| 8 | **Disputable gates** | `.factory/waivers.json` (or `--waivers`): `{rule, file, line?, reason, by, expires}`. A finding that matches an unexpired waiver is removed from the gate's input and listed as WAIVED with its reason and owner in the evidence; a waiver without reason or owner is refused. Criticals cannot be waived. | `deliver.py` `apply_waivers` |

## What stays true

| Rule | How |
|---|---|
| Every verdict says who decided it | model, gate skill, reviewer, person (by name), or AUTO |
| Nothing unverified reads as passed | NOT RUN, UNVERIFIED, NOT SANDBOXED, AUTO-APPROVED, WAIVED are printed as such |
| The model never grades its own work | the reviewer is a separate session without the builder's narrative |
| Limits are explicit | rounds, turns, budget, time, CPU, memory are recorded in the evidence header |

## Status

| # | Layer | Status |
|---|---|---|
| 1 | Requirements verification gate | see git log on branch `harness-1` |
| 2 | Goal decomposer + run DAG | |
| 3 | Sandbox | |
| 4 | Budget | |
| 5 | Telemetry | |
| 6 | Eval set | |
| 7 | Human gate | |
| 8 | Waivers | |
