# From docs to agents — grading and rebuild plan

Date: 2026-10-17 · Scope: all 40 skills · Status: proposal, nothing changed yet

## The honest verdict

**Zero of 40 skills are executable agents today.** Here is why, in plain words:

| Fact | Count | What it means |
|---|---|---|
| Skills with a script that computes something | 14 | The script exists, but nothing runs it. The model reads a sentence like "run `scripts/estimate.py`" and, as the evals proved, mostly doesn't. effort-estimator has the best script in the repo and scored **lift 0.00** — the model never ran it. |
| Skills with no script at all | 26 | Pure advice. Invoking them produces prose that *describes* a WBS, a battle card, a risk register. The user still does the work. |
| Skills whose inputs are machine-declared | 0 | Inputs are a markdown table a human reads. No runner can check "is the rate card present?" |
| Skills whose output is machine-checked | 0 | Self-checks are checkbox lists for the model to "run". Nobody verifies them. |
| Runner that invokes a skill end-to-end | 0 | There is no `run_skill`. Thread 02's harness asks a model to *write about* the task, then asks another model if the writing was good. It never checks whether a file was produced. |

So the owner's description is accurate: as shipped, this is an operator's manual with no machine attached. The scripts (threads 01–02) are real and tested, but they are parked. The product gap is **the thing that turns inputs into outputs and proves it did**.

## The bar (restated as checks a runner can enforce)

A skill is an agent only if all four are true and verifiable:

| # | Requirement | How it is verified |
|---|---|---|
| 1 | **Declared inputs** — name, type, required, where it comes from, what to do if missing | Machine-readable in frontmatter. Runner refuses to start without required inputs; asks once; `--assume` lets the run proceed with labeled assumptions. Never invents. |
| 2 | **Executable tooling** — deterministic steps that do the math/transform/generation | An ordered `run` list in frontmatter. `script` steps execute; `llm` steps get the script outputs as context and must fill a template, not freestyle. |
| 3 | **Output contract** — named files with a format and checks | `outputs` list with per-file checks: exists, required sections/columns, no `[TO BE BASELINED]` without an owner, every number traceable to an input, schema valid. |
| 4 | **Proof** — evals that run the agent and check the files | `evals.json` cases carry `inputs` fixtures and `checks`; the harness runs the skill and scores *check pass rate*, not prose quality. |

## 1. Grade per skill

Grades: **A** = inputs → tools → checked output, runnable today · **B** = has a real script but the deliverable is still prose and nothing enforces the run · **C** = advice only.

### Presales (13)

| Skill | Grade | Blunt assessment | What "really doing it" means |
|---|---|---|---|
| effort-estimator | B | Best script in the repo (PERT/Monte Carlo, staffing, cost). Lift 0.00 because the model never runs it and the memo is freestyle. | Runner executes `estimate.py` → memo template auto-filled with P50/P80/P90, staffing, contingency; check: every number in the memo appears in the script's JSON. |
| rfp-compliance-matrix | B | Extractor pulls requirements to CSV. Compliance scoring, gaps, Q&A are prose. | Add `score_matrix.py`: CSV + capability inventory → C/P/N/Q column, gap list, bid/no-bid score. Output: matrix.csv + gaps.md; check: every requirement has a status + owner. |
| integration-migration-assessor | B | Inventory scorer with waves exists. TCO and readout are prose. | Add `tco.py` (inventory + rate inputs → run-rate/dual-run/decommission table); readout template filled from both scripts; check: every cost line cites an input row or is TBD-with-owner. |
| client-research-brief | B | "Skeleton" script writes headings. No research is done. | Keep offline; inputs = notes/links file the user collected. Script tiers sources, extracts named entities/dates into a facts table; check: every claim in brief cites a source id. |
| proposal-writer | C | Section library + win-theme worksheet. Model writes an essay. | `assemble.py`: win-themes.json + discovery pack + estimate memo → proposal.md from section library, with a placeholder registry; check: every `[TO BE BASELINED]` has owner, every figure traces to estimate/value-case files. |
| sow-drafter | C | Template only. | `sow_from_proposal.py`: parses proposal.md sections → SOW.md with deliverables table, assumptions auto-pulled, RACI stub; check: every deliverable has an acceptance criterion; every assumption in proposal appears in SOW. |
| discovery-interview | C | Six good question banks nobody assembles. | `build_pack.py`: vertical + personas + call length → question pack with time budget (20% reserved); `synthesize.py`: notes.md → pain/impact/urgency CSV + five-closes table; check: all five closes present or marked unknown. |
| exec-deck-redline | C | Rubric only. Model can't even see the deck. | `redline.py`: .pptx → per-slide text ledger CSV + unsourced-number list (needs **python-pptx — ask**); LLM fills `[KEEP]/[SHARPEN]/…` verdicts; check: every slide has a verdict, every number in the ledger has a source or TBD. |
| value-case-builder | C | Template; no math. | `value_model.py`: benefits.csv + costs.csv + discount rate → NPV, payback, P80 cost, sensitivity on top-3 assumptions; check: totals reconcile, every input row referenced. |
| solution-architecture-doc | C | Mermaid templates nobody fills. | `arch_doc.py`: components.json → C4 context/container Mermaid, integration map grouped by pattern, NFR table; check: Mermaid parses (bracket balance + node refs), every NFR has a numeric target or TBD-with-owner. |
| competitive-positioning | C | Battle-card template. | `battle_card.py`: our-capabilities.csv + their-claims.csv + CIO concerns → wedge table + objection grid; check: INTERNAL marker, every objection has acknowledge/reframe/proof/ask-back. |
| account-plan | C | Template. | `account_plan.py`: stakeholders.csv + pipeline.csv + services list → stakeholder map, white-space matrix, 90-day plays table; check: every play has owner + date. |
| orals-prep | C | Rubric and question bank. | `orals.py`: proposal.md + timing → timed script skeleton + number registry; check: no number in the script is absent from the proposal. |

### Build (12)

| Skill | Grade | Blunt assessment | What "really doing it" means |
|---|---|---|---|
| project-bootstrap | B | `scaffold.py` really writes SPEC/CLAUDE/HANDOFF/ADR/CI. Closest to an agent. | Add checks (files exist, YAML parses) and a `--target` input contract. Near-A. |
| supabase-schema-rls | B | `rls_lint.py` is a real linter. Migration writing is prose. | Add `gen_policies.py`: tables.json + model (tenant/owner/role) → migration SQL with rollback block; check: lint passes on its own output. |
| spec-to-plan | C | Wraps superpowers; otherwise prose. | `plan.py`: SPEC.md section → plan.md task table with acceptance-criteria and test stubs; check: every task has test + rollback. |
| nextjs-enterprise-conventions | C | Rules in prose. | `lint_conventions.py`: scans a repo for the rules in stack-conventions.md (Supabase calls in components, `console.log`, missing zod at server actions, service-role key client-side) → findings CSV. A real tool that fails CI. |
| test-strategy-tdd | C | Configs shipped, nothing generated. | `scaffold_tests.py`: feature spec + file list → vitest/playwright stubs in the right folders; check: files created, `vitest --run` passes on stubs. |
| security-review | C | Good method, no scanner. | `scan.py`: diff → findings CSV for the stack pitfalls (auth check missing in server action, raw SQL, secrets, SSRF sinks); LLM reasons on top of findings; check: every finding has severity + file:line. |
| observability-setup | C | Assets exist (logger.ts, health route, alert YAML) but nothing installs them. | `install.py --target repo`: writes the assets, patches env.example; check: files exist, `tsc --noEmit` passes. |
| ci-cd-vercel-github | C | Workflow YAMLs exist; not installed. | `install_ci.py`: writes workflows, validates YAML, checks required jobs; check: yaml parses, job names present. |
| safe-fix | C | Method only — and this is the one the owner cares most about. | `safefix.py baseline` captures test results before; `safefix.py verify` re-runs after and diffs: any newly failing test = collateral → exit 1. The "never break another thing" rule becomes executable. |
| handoff-and-thread-close | C | Template. | `handoff.py`: git log/diff since last HANDOFF → changed-files list auto-filled, open items carried forward; check: every section non-empty. |
| multi-tenant-saas-patterns | C | Reference patterns. | `tenancy_audit.py`: migrations → tables lacking tenant_id / RLS / leading index → report; `rbac_to_sql.py`: rbac-matrix.csv → policies SQL. |
| product-spec-prd | C | Template. Low payoff. | `prd.py` template fill + section check. Keep last. |

### AI platform (9)

| Skill | Grade | Blunt assessment | What "really doing it" means |
|---|---|---|---|
| llm-eval-harness | B | `run_evals.py` runs and gates. Golden-set building is prose. | Add `build_golden.py` (transcripts/CSV → golden-set.csv with rubric columns); check: harness runs on its output. |
| rag-pipeline-design | B | `eval_retrieval.py` computes recall@k/MRR. Design choices are prose. | `design.py`: corpus stats (doc count, avg length, formats) + latency/cost targets → chunking/embedding/retrieval recommendation table + cost estimate; check: every recommendation cites an input. |
| infra-gpu-sizing | B | `size.py` is a real calculator. Deliverable is its output. Nearest to A in this domain. | Add input contract + check (no price defaults) → A. |
| ai-strategy-coe | C | Rubrics in CSV, no scorer. | `score_portfolio.py`: use-case scoring CSV → ranked portfolio; `maturity.py`: scorecard → level per dimension + roadmap skeleton; check: every roadmap item maps to a gap. |
| agent-architecture | C | Decision tree in prose. | `design_check.py`: agent-design-doc.md → validates sections, HITL points present, tool-contract JSON against schema; `pattern.py`: answers to 6 decision-tree questions → pattern + rationale. |
| mcp-server-builder | C | Spec essentials only. | `scaffold_mcp.py`: tools.json → server skeleton + tests; check: tests run green. |
| ai-governance-risk | C | Taxonomy + controls catalog, no register built. | `risk_register.py`: use-case canvas → register CSV with controls mapped from catalog; check: every High risk has a control + owner. |
| slm-demo-builder | C | Template. | `gen_synthetic.py`: demo-spec.md → synthetic dataset CSV/JSON; check: row count, no real PII patterns. |
| ai-use-case-canvas | C | Canvas template. | `canvas.py`: answers → scored canvas + build/buy call; check: all 8 cells filled or TBD-with-owner. |

### Career (6)

| Skill | Grade | Blunt assessment | What "really doing it" means |
|---|---|---|---|
| jd-fit-scorer | B | `score.py` computes a fit score. SKILL.md doesn't even call it. | Wire the run step; check: score + go/no-go present. → A with the runner. |
| application-tracker | B | `tracker.py` is a real CLI. | Wire run steps (add/update/aging); check: CSV valid. → A. |
| offer-evaluator | B | `compare.py` works. Not invoked. | Wire; check: COL indices supplied or output marked TBD. → A. |
| resume-tailor | C | Truth-lock is a rule the model is asked to obey. | `tailor.py`: JD + master-resume → keyword map + tailored bullets *drafted by LLM step*; `check_traceability.py`: every bullet cites `[MR-Lnn]` that exists → exit 1 otherwise. Truth-lock becomes enforced. |
| interview-prep | C | Story bank mapping is prose. | `prep.py`: JD competencies → story-bank mapping + gap list; check: every competency has ≥1 story or "GAP". |
| outreach-and-followup | C | Templates. Low payoff. | `fill.py` template fill + cadence dates; keep last. |

**Totals: A 0 · B 14 · C 26.** With the runner and checks, the 14 B-skills become A in one pass (phase 0). The 26 C-skills each need one deterministic script plus an output check (phases 1–4).

## 2. The rebuild — what changes in each skill

Smallest change that makes a skill runnable: **add one block to frontmatter, one script, one check**. The agentskills.io spec allows arbitrary keys under `metadata`, so this stays spec-compliant and every existing installer keeps working.

```yaml
metadata:
  domain: presales
  version: 0.2.0
  agent:
    inputs:
      - {name: wbs, type: csv, required: true, from: "user file (assets/wbs-template.csv)"}
      - {name: rates, type: csv, required: false, from: "user rate card; without it: effort only"}
      - {name: client, type: string, required: true}
    run:
      - {step: estimate, kind: script, cmd: "python3 -I scripts/estimate.py {wbs} --rates {rates} --iterations 20000 --json --out {out}/estimate.json"}
      - {step: memo, kind: llm, template: assets/estimate-summary-template.md, context: ["{out}/estimate.json", "references/estimation-method.md"], out: "{out}/estimate-memo.md"}
    outputs:
      - {path: "{out}/estimate.json", checks: [exists, json]}
      - {path: "{out}/estimate-memo.md", checks: [exists, sections:["Bottom line","Basis of estimate","Assumptions","Risks"], no_unowned_tbd, numbers_trace_to:"{out}/estimate.json"]}
```

Rules for every skill:
- **Missing required input** → runner asks once (stdin or returns a `needs_input` result to the caller). With `--assume key=value` the run proceeds and the output carries `[ASSUMED: …]`. The runner never fabricates.
- **`script` steps** are deterministic, offline, stdlib-only (existing rule), exit non-zero on bad input.
- **`llm` steps** always get a template and the script outputs; the prompt is "fill this template from these files; leave `[TO BE BASELINED — owner: ___]` where the files don't say". No freestyle.
- **Checks** are a fixed vocabulary implemented once in `scripts/check_output.py`: `exists`, `json`, `csv:[cols]`, `yaml`, `sections:[…]`, `no_unowned_tbd`, `numbers_trace_to:<file>`, `cites_source_ids:<file>`, `mermaid_parses`, `max_lines:N`, `cmd:"…"` (run a command, expect exit 0).

### Effort vs payoff, in build order

Effort: S = ½ day, M = 1 day, L = 2 days (per skill, including tests + eval fixtures). Payoff = how often the owner needs this and how much manual work the script removes.

| Phase | Skills | Effort | Payoff | Why this order |
|---|---|---|---|---|
| **0 — Runner + wire the 14 B-skills** | runner, check_output, eval mode; effort-estimator, rfp-compliance-matrix, integration-migration-assessor, client-research-brief, project-bootstrap, supabase-schema-rls, llm-eval-harness, rag-pipeline-design, infra-gpu-sizing, jd-fit-scorer, application-tracker, offer-evaluator (+ build_golden, tco, score_matrix) | L for runner, S each | **Highest** — turns 14 parked scripts into working agents with no new domain code | Proves the pattern before writing 26 new scripts |
| **1 — Presales core** | value-case-builder (M), proposal-writer (L), sow-drafter (M), discovery-interview (M), solution-architecture-doc (M) | ~5 days | High — the daily presales chain: discovery → estimate → value case → proposal → SOW | These five chain into each other; outputs of one are inputs of the next |
| **2 — Presales rest** | exec-deck-redline (M, needs python-pptx), competitive-positioning (S), account-plan (S), orals-prep (S) | ~2 days | Medium | Standalone; redline is the one that needs a dependency decision |
| **3 — Build** | safe-fix (M), nextjs-enterprise-conventions (M), security-review (M), observability-setup (S), ci-cd-vercel-github (S), handoff (S), spec-to-plan (M), test-strategy-tdd (M), multi-tenant (M), product-spec-prd (S) | ~6 days | High for safe-fix / conventions / security (they protect every other project); low for prd | safe-fix first — it is the owner's standing rule made executable |
| **4 — AI platform** | ai-strategy-coe (M), agent-architecture (M), ai-governance-risk (S), mcp-server-builder (M), ai-use-case-canvas (S), slm-demo-builder (S) | ~3.5 days | Medium | Mostly scoring/validation scripts over existing CSV assets |
| **5 — Career** | resume-tailor (M), interview-prep (S), outreach (S) | ~1.5 days | High for resume-tailor (truth-lock enforced); low for outreach | Last per owner's order |

Dependency decisions needed from the owner: **python-pptx** (exec-deck-redline; otherwise the user exports slides to text first) and nothing else. YAML is avoided by using JSON inputs; frontmatter YAML is parsed by the existing minimal parser extended for nested lists.

## 3. What the factory needs to run them

### The runner — `scripts/run_skill.py`

```
python3 scripts/run_skill.py presales/effort-estimator \
    --input wbs=./wbs.csv --input rates=./rates.csv --input client=Acme \
    --out ./runs/acme-estimate --provider anthropic
```

What it does, in order:
1. Loads `SKILL.md`, parses `metadata.agent`. Fails clearly if absent ("not an agent skill yet").
2. Resolves inputs. Required and missing → prints the one question and exits 2 with `needs_input.json` (so a chat agent or Muse can supply it and re-run). `--assume` fills it with a label.
3. Runs `run` steps in order. `script` → subprocess with `python3 -I`, stdout/stderr captured to `{out}/logs/`. `llm` → calls the provider abstraction already in `behavioral_evals.py` (`make_provider`) with: shared quality-bar + writing-style, the template, the listed context files. Writes the file. `--provider dry` writes the template with placeholders (for CI).
4. Runs every check from `outputs` via `scripts/check_output.py`. Writes `{out}/run.json`: inputs used, assumptions, steps with exit codes and durations, checks with pass/fail and evidence, overall `ok`.
5. Exit 0 only if all required outputs exist and all checks pass.

Also: `python3 scripts/run_skill.py --list` (which skills are agents, which inputs they take) and `--explain <skill>` (prints the input contract in plain words — this is what a chat front-end shows the user).

~300 lines, stdlib only, reuses the provider code. Tested with the `dry` provider in CI.

### How Claude Code / Cowork invoke it

SKILL.md body gets a 3-line "How to run" section at the top: *"This skill is executable. Collect the inputs below, then run `scripts/run_skill.py <skill> …`. Report `run.json` results; do not hand-write the deliverables the scripts produce."* That is the instruction the model follows instead of improvising. The markdown stays the operator's manual; the run block is the product.

### Evals evolve: from "did the text help?" to "did the agent do the job?"

Thread 02 stays as-is (trigger accuracy is still the right test for descriptions). Quality scoring gains a third mode:

| Mode | Question | How scored | Status |
|---|---|---|---|
| `trigger` | Does the description route the prompt here? | Router pick rate | exists |
| `quality` | Does the prose improve with SKILL.md? | LLM judge on `expected[]` | exists; keep for prose-only outputs |
| **`agent`** (new) | **Does running the skill produce the deliverable and pass its checks?** | Deterministic: `run_skill.py` per case → check pass rate; judge only for `llm`-step files, and only on rubric items a check can't express | new |

`evals.json` per case gains:
```json
{"id":"happy-path-wbs","inputs":{"wbs":"evals/fixtures/wbs.csv","rates":"evals/fixtures/rates.csv","client":"Acme"},
 "checks":["exit:0","exists:estimate.json","numbers_trace_to:estimate.json","sections:Bottom line"],
 "expected":["Quotes P80 with rationale"]}
```
Fixtures live in `evals/fixtures/` (fictional). A missing-input case asserts `exit:2` and that `needs_input.json` names the right input. The fabrication case asserts the output contains `[TO BE BASELINED` rather than a number.

Scorecard verdicts become: **Works** (agent pass rate ≥ 0.9), **Partial**, **Broken**, plus the existing description verdict. The studio ingests the new column with no UI change beyond one label.

### CI

`validate.py` adds: every skill at version ≥ 0.2.0 must have `metadata.agent` with ≥1 run step and ≥1 output check; every check name must be in the vocabulary; every fixture path must exist. `pytest tests/test_run_skill.py` runs the 14 phase-0 skills with `--provider dry` against their fixtures.

## 4. What this gives the owner, concretely

Before: "Use effort-estimator" → three pages of prose about how to estimate.
After: "Use effort-estimator on wbs.csv with rates.csv for Acme" → `estimate.json`, `estimate-memo.md` with P80 quoted and every number traceable, `run.json` saying which checks passed — or a single question ("I need the rate card, or say `--assume rates=none` for effort-only").

Same shape for all 40. Each one is a configurable agent: declared inputs, deterministic tooling, a checked deliverable, and an eval that runs it.

## 5. Recommended next thread

Phase 0 only: build the runner, `check_output.py`, the `agent` eval mode, and wire the 14 B-skills. Deliver as one PR with `run.json` samples for each of the 14. Then the owner decides whether the pattern earns phases 1–5.
