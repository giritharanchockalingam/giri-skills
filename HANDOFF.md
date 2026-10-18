# HANDOFF — giri-skills — 2026-10-17 (evening)
## State: all 40 skills are executable agents; main @ post-phase-5 merge; 553 tests green; studio v4 (agent verdicts) in progress
## Done this thread
- Graded all 40 against the agent bar (docs/AGENT-REBUILD-PLAN.md): 0 were agents
- Phase 0: scripts/run_skill.py (--list/--explain/--demo/--input/--assume, needs_input exit 2, run.json), scripts/check_output.py (check vocabulary), scripts/skillmeta.py, `agent` mode in behavioral_evals.py, validate.py rules for v0.2.0 skills
- Phases 1–5: 28 new deterministic scripts; every skill has metadata.agent, "How to run", fixtures, 3 agent eval cases, pytest coverage
- Dry agent eval: 121 cases, 421/421 checks; --demo sweep 40/40 ok
- Studio deployed at https://giri-skills-studio.vercel.app (auto-deploys from main, root studio/)
## Changed files
- scripts/*, skills/**/{SKILL.md,scripts/,evals/}, tests/*, docs/{AGENT-REBUILD-PLAN,PHASE0-REPORT}.md, requirements-optional.txt, studio/
## Open items (owner)
- Run the agent evals with a REAL provider once (`behavioral_evals.py agent --provider anthropic`) — dry mode skips numbers_trace_to / real-mode no_unowned_tbd; first live test of the LLM steps (proposal-writer, exec-deck-redline, security-review, product-spec-prd, resume-tailor, outreach)
- Supply real inputs (rate-card.csv, master-resume.md, story-bank.md, profile-keywords.txt) and try --demo → real run on one live opportunity
- `pip install python-pptx` for .pptx decks in exec-deck-redline (optional)
- Thread 03 description fixes from EVAL-FINDINGS (25 proposals) still unapplied
## Next thread starts with
"Read HANDOFF.md. Run `python3 scripts/behavioral_evals.py agent --provider anthropic --out evals/results/agent-live --budget-usd 20` with ANTHROPIC_API_KEY set; report every failed check with its evidence; fix scripts/templates (not evals) until Works ≥ 36/40; then apply the 25 description proposals from docs/EVAL-FINDINGS.md and re-run trigger mode."
