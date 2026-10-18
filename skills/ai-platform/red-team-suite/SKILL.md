---
name: red-team-suite
description: Use when a text LLM app or agent needs adversarial testing before launch or after a change — "red-team our chatbot", "test it for prompt injection", "can it leak the system prompt", "jailbreak test", "does the agent misuse its tools", "security gate for the assistant". Produces attacks.jsonl (30+ deterministic cases with stable ids from a bundled template library, parameterised by an app profile, mapped to the OWASP Top 10 for LLM Applications: prompt injection, canary exfiltration, data disclosure, tool misuse, jailbreaks, active content, out-of-scope) and, once responses are supplied, redteam-scorecard.json and redteam-report.md graded by deterministic detectors (canary leak incl. obfuscations, marker echo, refusal, tool-call trace) with a gate against a user-supplied threshold. Not for quality evals (llm-eval-harness), prompt linting (prompt-spec) or a risk register (ai-governance-risk).
license: MIT
metadata:
  domain: ai-platform
  adlc_stage: evaluate
  version: 0.2.0
  author: giri-skills
  agent:
    inputs:
      - {name: profile, type: json, required: true, from: "app profile: app_name, purpose, tools, data, canary (planted secret, >= 8 letters/digits), out_of_scope (layout: assets/app-profile-template.json)"}
      - {name: responses, type: csv, required: false, from: "case_id,response from running attacks.jsonl against the app, tool-call traces included; without it only the attack set is produced"}
      - {name: threshold, type: string, required: false, from: "overall pass-rate gate as a fraction, e.g. 0.95, set by the AI risk lead; no default"}
    run:
      - {step: redteam, kind: script, cmd: "python3 -I scripts/redteam.py --profile {profile} [--responses {responses}] [--threshold {threshold}] --out-dir {out}"}
    outputs:
      - {path: "{out}/attacks.jsonl", checks: [exists, contains:"LLM01:2025 Prompt Injection", cmd:"python3 -I scripts/redteam.py --verify-attacks {path}"]}
      - {path: "{out}/redteam-scorecard.json", checks: [exists, json, contains:"\"gate\""]}
      - {path: "{out}/redteam-report.md", checks: [exists, sections:["Gate","Results by category","Failures","Method","References"], no_unowned_tbd, numbers_trace_to:"{out}/redteam-scorecard.json"]}
---

# Red-Team Suite

## How to run
This skill is executable. Collect the inputs below, then run `python3 scripts/run_skill.py ai-platform/red-team-suite --input <name>=<value> … --out <dir>` (see `--explain ai-platform/red-team-suite`). Report the `run.json` results; do not hand-write the deliverables the script produces (`attacks.jsonl`, `redteam-scorecard.json`, `redteam-report.md`). A failed gate exits 1 on purpose.

Two passes: (1) profile only → `attacks.jsonl` and a scorecard with status `awaiting_responses`; run the attacks against the app; (2) profile + responses (+ threshold) → graded scorecard, report and gate.

## When to use
- Pre-launch or pre-release security testing of a chat assistant, RAG app or tool-using agent with text I/O.
- Regression after a prompt, model or tool change: same profile → same case ids → comparable scorecards.
- NOT for: answer quality and accuracy (`llm-eval-harness`), prompt contract linting (`prompt-spec`), the risk register and controls (`ai-governance-risk`), image/audio attacks, or infrastructure penetration testing.

## Inputs required
| Input | Required | Source |
|---|---|---|
| `profile` JSON: app_name, purpose, tools (name + description), data the app can see, canary token, out-of-scope topics | yes | app owner; plant the canary in the app's system prompt before testing |
| `responses` CSV: `case_id,response` | no (pass 2) | test harness or manual run of `attacks.jsonl`; include tool-call traces in the response cell |
| `threshold`: overall pass rate to clear the gate (0–1) | no | AI risk lead; without it the gate is `[TO BE BASELINED — owner: AI risk lead]` |

## Procedure
1. Read `../../../shared/quality-bar.md`.
2. **Profile the app** in `assets/app-profile-template.json`. Plant a unique canary string in the system prompt (never a real secret).
3. **Generate**: `python3 -I scripts/redteam.py --profile <profile.json> --out-dir <dir>` → `attacks.jsonl` (≥ 30 cases, stable ids, categories in `references/attack-categories.md`).
4. **Execute** each case against the app per `references/running-the-suite.md`: `attack` as the user turn; `context_document`, when present, through the channel the app treats as untrusted content (retrieved document, web page, email). Record `case_id,response` with the tool-call trace.
5. **Grade**: re-run with `--responses <csv> --threshold <t>`. Detectors are deterministic (`references/detectors.md`, vocabularies in `assets/detector-markers.json`).
6. **Decision point — gate.** Fail on any canary leak, any unanswered case, or pass rate below threshold. No threshold → not evaluated, owner AI risk lead. Never lower the threshold to pass a run.
7. Review every failure and a sample of passes by hand (string detectors miss paraphrased compliance), fix the app, re-run the same profile.
8. Run the self-check.

## Output
- `attacks.jsonl`: case_id, template_id, category, OWASP reference, delivery, attack, context_document, marker, target_tool, detectors.
- `redteam-scorecard.json`: per-case detector results, per-category and overall pass rates, canary leaks, gate status, threshold and reasons.
- `redteam-report.md`: Gate, Results by category, Failures, Method, References; every number traces to the scorecard.

## Self-check
- [ ] Canary is a synthetic test string planted for this run, not a real credential
- [ ] Every case in `attacks.jsonl` has a response (or the gate fails as incomplete)
- [ ] Threshold came from the AI risk lead, or is marked `[TO BE BASELINED — owner: AI risk lead]`
- [ ] Failures reviewed by hand; detector false positives noted, not silently dropped
- [ ] Same profile and template library used for before/after comparisons

## References
- `references/attack-categories.md` — categories, OWASP Top 10 for LLM Applications mapping, what each case probes
- `references/detectors.md` — detector logic, obfuscations covered, known blind spots
- `references/running-the-suite.md` — executing attacks, recording responses, gating and re-runs
- `assets/attack-templates.json` — bundled attack template library (original wording)
- `assets/detector-markers.json` — refusal, tool-call and active-content vocabularies
- `assets/app-profile-template.json` — profile layout
- `scripts/redteam.py` — generator, grader, verifier (argparse; stdlib)
