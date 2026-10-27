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

## Status (branch `harness-1`)

| # | Layer | Status | Commit | Proven by |
|---|---|---|---|---|
| 1 | Requirements verification gate | Built | `deliver.py run_acceptance` | `tests/test_harness_acceptance.py` (7) + live calibration on the CAPE R3 build (see below) |
| 2 | Goal decomposer + run DAG | Built | `scripts/harness.py` | `tests/test_harness_dag.py` (9): validation, order, crash-resume, approvals, budget |
| 3 | Sandbox | Built (docker, hostroot image) | `scripts/sandbox.py` | `tests/test_harness_sandbox.py` (7, real containers); G1's 73 tests incl. 50-concurrent Postgres and its visual check pass inside |
| 4 | Budget | Built | `deliver.py run_claude` | `tests/test_harness_budget_telemetry.py` |
| 5 | Telemetry | Built (OTLP/JSON file + export) | `scripts/telemetry.py` | same file; export to a real local HTTP collector |
| 6 | Eval set | Built (G1–G3 core) | `scripts/pipeline_eval.py`, `evals/pipeline/` | `tests/test_pipeline_eval.py` on the real G1 run records; baseline written by the first full eval run |
| 7 | Human gate | Built | `harness.py approve`, `deliver.py approve` | `tests/test_harness_dag.py` |
| 8 | Waivers | Built | `deliver.py apply_waivers` | `tests/test_harness_waivers.py` (5) |

## Operating it

```bash
# one goal, end to end (dry: local copies; drop --dry to open real PRs that a person merges)
python3 scripts/harness.py plan    --goal docs/GOAL.md --dir runs/goal-1 --name myapp --budget-usd 3
python3 scripts/harness.py approve --dir runs/goal-1 --by "<your name>"
python3 scripts/harness.py run     --dir runs/goal-1 --dry --sandbox docker --budget-usd 60 --model claude-sonnet-5-5
python3 scripts/harness.py status  --dir runs/goal-1          # where it stopped and why; `approve --slice` when a slice waits

# the pipeline's own regression check (before merging a pipeline or skill change)
EVAL_DATABASE_URL_TEMPLATE='postgresql://u:p@127.0.0.1:5432/{db}' EVAL_DATABASE_ADMIN_URL='postgresql://u:p@127.0.0.1:5432/postgres' \
  python3 scripts/pipeline_eval.py run --out runs/eval-$(date +%F) --tier core --sandbox docker --budget-usd 15
python3 scripts/pipeline_eval.py compare --out runs/eval-$(date +%F)
```

Requirements: Docker for `--sandbox docker`; with a local Postgres, the box reaches it through its unix socket, so the
database user needs password (not peer) authentication on the socket (`local all <user> scram-sha-256` in pg_hba.conf).

## Calibration of the acceptance gate (live, Oct 27 2026)

Three runs of the gate on the CAPE R3 build, which an independent review had found to violate the goal's
non-negotiable (revalidation stamps the newest version on a result computed from older data; the commit is accepted).

| Run | Gate change | Verdict | Experiments | Critical defect found | Other real defects | Cost |
|---|---|---|---|---|---|---|
| 1 | reviewer may experiment | FAIL | 0 (read only) | no | dead cache (high), handler does not revalidate, global over-invalidation | $0.60 |
| 2 | experiments required (one nudge, then refused) | FAIL | 8, all broken by a mount bug (fixed) | **yes** (as medium) | + per-learner versions ignore a second learner (high) | ~$0.70 |
| 3 | node_modules visible in the box | FAIL | 3 working | no | + a PS event breaks idempotent retry of a committed plan (verified by experiment) | $0.78 |

Reading: the gate stopped the defective slice every time, for real defects backed by evidence, at under $1 a review.
It does **not** reliably find the single most important defect (1 of 3). Next steps for this layer: two independent
reviewers per round (union of findings), and reviewer probes written from the goal's non-negotiables before review.

## Known limits

| Limit | Consequence |
|---|---|
| The builder (`claude -p`) runs on the host; only its file tools are allowed (no shell) | Its own process is not in the box; the code it writes never runs outside the box |
| The openai-compat builder's repair command runs through its own module, not the sandbox | Use `--builder claude-code` with `--sandbox docker` |
| Slices run one at a time | Independent slices are not yet forked in parallel |
| Docs (C4, ADRs, rollout) are judged only by the acceptance reviewer, not by a dedicated gate | A document can pass with generic content if the criteria do not ask for specifics |
| One reviewer per round is non-deterministic | It stops defective work reliably but may miss the worst defect (calibration above) |
