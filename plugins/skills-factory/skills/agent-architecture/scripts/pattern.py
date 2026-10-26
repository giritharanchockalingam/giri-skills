#!/usr/bin/env python3
"""Pattern decision from answers to the six decision-tree questions (references/decision-tree.md).

    python3 -I scripts/pattern.py answers.json --out pattern.md [--name "Ticket triage agent"]

answers.json keys and allowed values (all six required; anything else is an error):
  q1_steps_enumerable        yes|no   Can the steps be enumerated in advance for every input?
  q2_model_chooses_tools     yes|no   Must the model choose which tools to call, in what order?
  q3_single_agent_fits       yes|no   Can one model with <= ~10 tools and one context finish within budget?
  q4_blocker                 too_many_tools|distinct_expertise|exceeds_context|parallel_subtasks|
                             adversarial_review|none   Why not (first that applies)?
  q5_rubric_exists           yes|no   Does the output have an objective rubric worth a second model call?
  q6_irreversible_actions    yes|no   Does the system take irreversible or external-facing actions?
Optional: "evidence": {q1_...: "one line of evidence"} — quoted in the rationale when present.

Writes pattern.md: chosen pattern, the criterion that forced each escalation, rationale citing
every answer, rejected patterns with the reason, and the mandatory HITL / budget notes. Nothing is
inferred from an unanswered question: a missing or invalid answer exits 1 and names it. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: AI architect]"
YN = ("yes", "no")
QUESTIONS = {
    "q1_steps_enumerable": (YN, "Can the steps be enumerated in advance for every input?"),
    "q2_model_chooses_tools": (YN, "Does the task need the model to choose tools and order from intermediate results?"),
    "q3_single_agent_fits": (YN, "Can one model with <= ~10 tools and one context window finish within budget?"),
    "q4_blocker": (("too_many_tools", "distinct_expertise", "exceeds_context", "parallel_subtasks",
                    "adversarial_review", "none"), "Why can a single agent not finish? (first that applies)"),
    "q5_rubric_exists": (YN, "Is there an objective rubric and does a wrong output cost more than a second model call?"),
    "q6_irreversible_actions": (YN, "Does the system take irreversible or external-facing actions?"),
}
PATTERNS = ["Workflow", "Router + workflow", "Single agent", "Single agent + tool routing",
            "Single agent + external memory", "Supervisor + specialists", "Orchestrator + workers",
            "Generator + evaluator"]
Q4 = {
    "too_many_tools": ("Single agent + tool routing", "tool descriptions + prompt exceed the context budget (Q4a)"),
    "distinct_expertise": ("Supervisor + specialists", "two or more tool groups need conflicting instructions or data scopes (Q4b)"),
    "exceeds_context": ("Single agent + external memory", "long task exceeds one context; checkpointed subtasks, still one agent (Q4c)"),
    "parallel_subtasks": ("Orchestrator + workers", "independent subtasks; wall-clock SLO cannot be met sequentially (Q4d)"),
    "adversarial_review": ("Generator + evaluator", "output must be critiqued against a rubric before release (Q4e)"),
}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load_answers(path: str) -> tuple[dict, dict]:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{p.name}: invalid JSON: {e}")
    if not isinstance(data, dict):
        die(f"{p.name}: expected an object with the six question keys")
    evidence = data.get("evidence") or {}
    answers = {}
    missing, bad, unknown = [], [], []
    for k in data:
        if k not in QUESTIONS and k != "evidence":
            unknown.append(k)
    for q, (allowed, _) in QUESTIONS.items():
        v = str(data.get(q, "")).strip().lower()
        if v == "":
            missing.append(q)
        elif v not in allowed:
            bad.append(f"{q}={v!r} (allowed: {'|'.join(allowed)})")
        else:
            answers[q] = v
    if unknown:
        die(f"unknown keys {unknown}; allowed: {list(QUESTIONS)} + evidence")
    if missing:
        die(f"unanswered question(s): {missing} — answer them; the pattern is not inferred")
    if bad:
        die("invalid answer(s): " + "; ".join(bad))
    return answers, evidence


def decide(ans: dict) -> tuple[str, list[str], dict[str, str]]:
    """Return (pattern, escalation trail, rejected {pattern: reason})."""
    trail, rejected = [], {}
    if ans["q1_steps_enumerable"] == "yes":
        pattern = "Workflow"
        trail.append("Q1 = yes: steps are enumerable, so code decides the path (stop)")
    elif ans["q2_model_chooses_tools"] == "no":
        pattern = "Router + workflow"
        rejected["Workflow"] = "Q1 = no: branching cannot be enumerated for every input"
        trail.append("Q2 = no: the model only classifies; a router picks one of the known paths (stop)")
    else:
        rejected["Workflow"] = "Q1 = no: branching cannot be enumerated for every input"
        rejected["Router + workflow"] = "Q2 = yes: the model must choose tools and order from intermediate results"
        if ans["q3_single_agent_fits"] == "yes":
            pattern = "Single agent"
            trail.append("Q3 = yes: one model, bounded tools, one context, within budget (stop)")
        else:
            blocker = ans["q4_blocker"]
            if blocker == "none":
                pattern = "Single agent"
                trail.append("Q3 = no but Q4 = none: no escalation criterion named, so the single agent stays "
                             f"until evals show it fails — record the failing criterion first ({TBD})")
            else:
                pattern, why = Q4[blocker]
                rejected["Single agent"] = f"Q3 = no: {why}"
                trail.append(f"Q4 = {blocker}: {why} -> {pattern}")
    if ans["q5_rubric_exists"] == "yes" and pattern != "Generator + evaluator":
        trail.append("Q5 = yes: add a bounded Generator + evaluator loop (<= 3 iterations) around the final output")
    elif ans["q5_rubric_exists"] == "no" and pattern == "Generator + evaluator":
        trail.append("Q5 = no contradicts Q4 = adversarial_review: an evaluator needs an objective rubric — "
                     f"define the rubric or fall back to Single agent ({TBD})")
    for p in PATTERNS:
        if p != pattern and p not in rejected:
            rejected[p] = "not reached: the tree stopped at a cheaper control structure" \
                if PATTERNS.index(p) > PATTERNS.index(pattern) else "ruled out earlier in the tree"
    return pattern, trail, rejected


def main() -> int:
    ap = argparse.ArgumentParser(description="decision-tree answers -> pattern.md")
    ap.add_argument("answers")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="<agent>")
    a = ap.parse_args()
    ans, ev = load_answers(a.answers)
    pattern, trail, rejected = decide(ans)
    hitl = ("Q6 = yes: HITL checkpoint before every irreversible or external-facing action (two-phase tools, "
            "approve / edit / reject)" if ans["q6_irreversible_actions"] == "yes"
            else "Q6 = no: no irreversible actions declared; post-hoc sampling review is enough (re-check if a write tool is added)")
    L = [f"# Pattern decision — {a.name}", "",
         f"**Decision:** {pattern} because {trail[0] if trail else TBD}.", "",
         "## Rationale (every answer cited)", "| Question | Answer | Evidence | Effect |", "|---|---|---|---|"]
    effects = {
        "q1_steps_enumerable": "yes -> Workflow; no -> continue",
        "q2_model_chooses_tools": "no -> Router + workflow; yes -> continue",
        "q3_single_agent_fits": "yes -> Single agent; no -> Q4",
        "q4_blocker": "names the escalation criterion",
        "q5_rubric_exists": "yes -> add Generator + evaluator loop",
        "q6_irreversible_actions": "yes -> mandatory HITL before commit",
    }
    for q, (_, text) in QUESTIONS.items():
        L.append(f"| {text} | {ans[q]} | {ev.get(q, '') or TBD} | {effects[q]} |")
    L += ["", "## Escalation trail"] + [f"{i}. {t}" for i, t in enumerate(trail, 1)]
    L += ["", "## Rejected patterns", "| Pattern | Reason |", "|---|---|"]
    L += [f"| {p} | {r} |" for p, r in rejected.items()]
    L += ["", "## Human-in-the-loop", f"- {hitl}", "",
          "## Budgets (set before build)", "| Budget | Value |", "|---|---|",
          f"| Max steps | {TBD} |", f"| Max tokens / cost per run | {TBD} |", f"| Max wall-clock | {TBD} |",
          f"| Fan-out cap | {'n/a' if pattern != 'Orchestrator + workers' else TBD} |", "",
          "Next: fill `assets/agent-design-doc.md` §2 from this table and run `scripts/design_check.py` on the result."]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"pattern: {pattern} -> {a.out}")
    return 0


if __name__ == "__main__":
    main()
