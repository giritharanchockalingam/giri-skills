# Brief: building a new executable skill in giri-skills

Read this whole file before writing anything. It is the contract every new skill meets.

## Where things go (ONLY these paths — touch nothing else)
- `skills/ai-platform/<name>/SKILL.md`
- `skills/ai-platform/<name>/scripts/<script>.py` (stdlib only; no network imports; must also run in-process under `runpy`)
- `skills/ai-platform/<name>/assets/` (templates, catalogs, policy CSVs the user copies)
- `skills/ai-platform/<name>/references/` (method notes, sources, limits)
- `skills/ai-platform/<name>/evals/evals.json` + `evals/fixtures/*` (fictional data, labelled fictional in a `#` comment line or a note)
- `tests/test_aiplatform_<short>.py` (pytest; scripts invoked via `conftest.run_script`, never imported)

Do NOT edit: `README.md`, `AGENTS.md`, `docs/`, `roles/`, `pools/`, `agents/`, `studio/`, `scripts/`, `tests/conftest.py`, other skills. The integrator regenerates shared files.

## Study first (copy their patterns exactly)
- `skills/ai-platform/pii-data-inventory/` — SKILL.md layout, agent block, evals.json, TBD-owner rule, leak check
- `skills/ai-platform/llm-cost-model/` and `skills/ai-platform/ai-release-plan/` — gate/verdict pattern, kv-csv facts inputs
- `tests/test_aiplatform_pii.py` — test style; `tests/conftest.py` — `run_script`, `REPO_ROOT`
- `scripts/check_output.py` docstring — the ONLY check vocabulary allowed in `outputs[].checks` and eval `checks`
- `scripts/run_skill.py --explain ai-platform/pii-data-inventory` — how inputs substitute into `cmd` (`{name}`, optional `[--flag {name}]`, `{out}`)
- `shared/quality-bar.md`, `shared/writing-style.md`

## SKILL.md rules
- Frontmatter: `name`, `description` (starts "Use when…", quoted trigger phrases, what it produces, and a "Not for … (use <other-skill>)" clause), `license: MIT`, `metadata: {domain: ai-platform, adlc_stage: <one of strategy|use-case|data|requirements|architecture|build|evaluate|govern|deploy|operate|improve>, version: 0.2.0, author: giri-skills, agent: {inputs, run, outputs}}`.
- Body sections in this order: `# Title`, `## How to run`, `## When to use` (bullets, last bullet "NOT for: …"), `## Inputs` (table: input · required · source · if missing), `## Procedure`, `## Output`, `## Self-check`, `## References`.
- Agent block: script steps only (`kind: script`). Every output has `exists` plus at least two substantive checks (csv columns, csv_rows regex, sections, contains, no_unowned_tbd, cmd self-check). Prefer a `cmd:` check that re-verifies the output with the script's own `--verify` mode.

## Behaviour rules (non-negotiable)
1. **No invented facts.** Every number is computed from the inputs or comes from a cited source file in `assets/`/`references/`. Unknown values are `[TO BE BASELINED — owner: <named role>]` (a role, never blank).
2. **Missing required input → exit 2** and write `needs_input.json` via the runner (the runner does this when a required input is absent — just declare `required: true`).
3. **Verdict skills** (pass/fail gates) exit 1 when the verdict is "no" but still write complete outputs; document it as a gate.
4. Deterministic: same inputs → byte-identical outputs (sort keys, fixed rounding, no timestamps unless an input `--as-of` date is given; default as-of from the input data, never `today()` silently — if a date is needed and not supplied, require it or mark TBD).
5. Regulatory/framework content (EU AI Act, NIST AI RMF, OWASP LLM Top 10, GDPR, SPDX licences, etc.) must be **verified with WebSearch/WebFetch** against the primary source and recorded in `references/sources.md` with URLs and the date checked. Do not reproduce copyrighted standard text (e.g. ISO); IDs and short paraphrases only. Public-domain (NIST) and EU law text may be quoted briefly.
6. State limits plainly in the report (e.g. "not a legal determination", "sample-based").

## Evals (evals/evals.json) — at least 5 cases
- 1–2 prompt-only cases (`prompt`, `expected`), plus agent cases with `inputs` and `checks`:
  - `agent-happy-path` (exit 0, several `contains:` checks on exact computed values you hand-verified)
  - `agent-missing-<input>` (exit 2, `needs_input:<name>`)
  - a "does not invent" case (missing optional input → TBD with owner, `no_unowned_tbd`)
  - a gate/edge case (verdict exit 1, or a boundary value)
- Run: `python3 scripts/behavioral_evals.py agent --provider dry --skills 'skills/ai-platform/<name>' --out /tmp/claude-0/-home-claude/048f21b7-0a7d-5365-b359-57a990058db7/scratchpad/ev-<name>` → every check must pass.

## Tests (tests/test_aiplatform_<short>.py) — at least 8 tests
Hand-computed expectations for the core math/rules, edge cases (empty, malformed input → clear error, exit code), determinism, the TBD-owner rule, and the verify mode. No network.

## Done means (run all, paste the tail of each in your final report)
```
python3 scripts/validate.py
python3 scripts/run_skill.py --demo ai-platform/<name> --provider dry --out /tmp/claude-0/-home-claude/048f21b7-0a7d-5365-b359-57a990058db7/scratchpad/demo-<name>
python3 scripts/behavioral_evals.py agent --provider dry --skills 'skills/ai-platform/<name>' --out /tmp/claude-0/-home-claude/048f21b7-0a7d-5365-b359-57a990058db7/scratchpad/ev-<name>
python3 -m pytest -q tests/test_aiplatform_<short>.py tests/test_offline.py
python3 scripts/run_skill.py --demo ai-platform/<name> --inproc --provider dry --out <another dir>   # in-process path
```
Final report (≤ 200 words): skill id, adlc_stage, inputs, outputs, checks, eval pass count, test count, sources verified, any limits.

## Working alongside other builders
Several skills are built at the same time. `python3 scripts/validate.py` and `tests/test_offline.py` scan every skill, so they may report errors in OTHER agents' half-finished folders — ignore those; only errors under your own skill folders must be zero. Never edit another skill's files to make a check pass.
