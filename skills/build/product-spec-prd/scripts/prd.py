#!/usr/bin/env python3
"""Fill the PRD template from a structured brief — nothing invented, gaps marked.

    python3 -I scripts/prd.py brief.json --template assets/prd-template.md --out PRD.md

brief.json:
  {"feature": "Invoice export", "problem": "…", "users": ["Tenant admin", …],
   "goals": ["…"], "non_goals": ["…"], "metrics": [{"name": "…", "target": "…", "baseline": "…"}],
   "phases": [{"name": "v1", "scope": ["…"], "excludes": ["…"], "exit": "…"}],
   "evidence": [{"claim": "…", "source": "…", "date": "…"}], "constraints": ["…"], "flag": "feature.exports"}
Only `feature` and `problem` are required. Every missing or empty array becomes a
`[TO BE BASELINED — owner: Product owner]` row; metric baselines default to the same marker. Sections filled:
header line, exec summary, Problem, Users, Goals, Non-goals, Metrics, Phases, Engineering handoff,
Flag. The LLM step then sharpens the result on the same template. Exit 1 on missing/invalid brief. Stdlib.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "assets" / "prd-template.md"
TBD = "[TO BE BASELINED — owner: Product owner]"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def as_list(v) -> list:
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def replace_section(md: str, heading_startswith: str, body: list[str]) -> str:
    lines, out, i = md.splitlines(), [], 0
    while i < len(lines):
        ln = lines[i]
        out.append(ln)
        i += 1
        if ln.startswith("## ") and ln[3:].lower().startswith(heading_startswith.lower()):
            out += body
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            if i < len(lines):
                out.append("")
    return "\n".join(out) + "\n"


def cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ").strip() or TBD


def main() -> int:
    ap = argparse.ArgumentParser(description="brief.json -> PRD.md on the template")
    ap.add_argument("brief")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--out", default="PRD.md")
    a = ap.parse_args()
    bp, tp = Path(a.brief), Path(a.template)
    if not bp.is_file():
        die(f"brief not found: {bp}")
    if not tp.is_file():
        die(f"template not found: {tp}")
    try:
        brief = json.loads(bp.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        die(f"brief is not valid JSON: {e}")
    if not isinstance(brief, dict):
        die("brief must be a JSON object")
    feature = str(brief.get("feature", "")).strip()
    problem = str(brief.get("problem", "")).strip()
    if not feature or not problem:
        die("brief needs non-empty 'feature' and 'problem'")
    users, goals, non_goals = as_list(brief.get("users")), as_list(brief.get("goals")), as_list(brief.get("non_goals"))
    metrics = [m if isinstance(m, dict) else {"name": str(m)} for m in as_list(brief.get("metrics"))]
    phases = [p if isinstance(p, dict) else {"name": str(p)} for p in as_list(brief.get("phases"))]
    evidence = [e if isinstance(e, dict) else {"claim": str(e)} for e in as_list(brief.get("evidence"))]
    constraints = as_list(brief.get("constraints"))
    flag = str(brief.get("flag") or "").strip() or f"feature.{re.sub(r'[^a-z0-9]+', '_', feature.lower()).strip('_')}"
    gaps = []

    md = tp.read_text(encoding="utf-8").replace("{{TITLE}}", feature)
    m0 = metrics[0] if metrics else {}
    head = (f"**{feature}: {problem.rstrip('.')}. Target {cell(m0.get('name')) if metrics else TBD} "
            f"from {cell(m0.get('baseline')) if m0.get('baseline') else TBD} to "
            f"{cell(m0.get('target')) if m0.get('target') else TBD} by {cell(m0.get('by')) if m0.get('by') else TBD}.**")
    md = re.sub(r"^\*\*\{\{Outcome sentence\}\}.*\*\*$", lambda _: head, md, count=1, flags=re.M)
    md = md.replace("| Flag | `feature.<name>` |", f"| Flag | `{flag}` |")
    exec_summary = [f"- Problem: {problem}",
                    f"- Who: {', '.join(map(str, users)) if users else TBD}",
                    f"- What: {feature}",
                    f"- Success: {'; '.join(f'{cell(m.get('name'))} → {cell(m.get('target')) if m.get('target') else TBD}' for m in metrics) if metrics else TBD}",
                    f"- Scope: v1 = {'; '.join(map(str, as_list(phases[0].get('scope')))) if phases and as_list(phases[0].get('scope')) else TBD}; "
                    f"later = {', '.join(cell(p.get('name')) for p in phases[1:]) if len(phases) > 1 else TBD}"]
    md = replace_section(md, "Exec summary", exec_summary)
    prob = ["| Evidence | Source | Date |", "|---|---|---|"]
    prob += [f"| {cell(e.get('claim'))} | {cell(e.get('source')) if e.get('source') else TBD} | {cell(e.get('date')) if e.get('date') else TBD} |"
             for e in evidence] or [f"| {TBD} (no evidence supplied — assumption) | {TBD} | {TBD} |"]
    if not evidence:
        gaps.append("evidence")
    prob += ["", f"Problem statement: {problem}", "", f"What happens if we do nothing: {TBD}"]
    if constraints:
        prob += ["", "Constraints: " + "; ".join(map(str, constraints))]
    md = replace_section(md, "Problem", prob)
    us = ["| Persona | Role (RBAC) | Job to be done | Today's workaround |", "|---|---|---|---|"]
    us += [f"| {cell(u)} | {TBD} | {TBD} | {TBD} |" for u in users] or [f"| {TBD} | {TBD} | {TBD} | {TBD} |"]
    if not users:
        gaps.append("users")
    md = replace_section(md, "Users", us)
    gl = ["| # | Goal | Metric | Baseline | Target | Review date |", "|---|---|---|---|---|---|"]
    for i, g in enumerate(goals, 1):
        m = metrics[i - 1] if i - 1 < len(metrics) else {}
        label = "G1 (primary)" if i == 1 else f"G{i} (leading)"
        gl.append(f"| {label} | {cell(g)} | {cell(m.get('name')) if m else TBD} | "
                  f"{cell(m.get('baseline')) if m.get('baseline') else TBD} | {cell(m.get('target')) if m.get('target') else TBD} | {TBD} |")
    if not goals:
        gl.append(f"| G1 (primary) | {TBD} | {TBD} | {TBD} | {TBD} | {TBD} |")
        gaps.append("goals")
    gl.append(f"| Guardrail | {TBD} | {TBD} | {TBD} | {TBD} | {TBD} |")
    md = replace_section(md, "Goals", gl)
    ng = ["| Non-goal | Reason | Revisit in |", "|---|---|---|"]
    ng += [f"| {cell(n)} | {TBD} | {TBD} |" for n in non_goals] or [f"| {TBD} | {TBD} | {TBD} |"]
    if not non_goals:
        gaps.append("non_goals")
    md = replace_section(md, "Non-goals", ng)
    mt = ["| Metric | Baseline | Target | Source / instrumentation | Review date |", "|---|---|---|---|---|"]
    mt += [f"| {cell(m.get('name'))} | {cell(m.get('baseline')) if m.get('baseline') else TBD} | "
           f"{cell(m.get('target')) if m.get('target') else TBD} | {cell(m.get('source')) if m.get('source') else TBD} | {TBD} |"
           for m in metrics] or [f"| {TBD} | {TBD} | {TBD} | {TBD} | {TBD} |"]
    if not metrics:
        gaps.append("metrics")
    md = replace_section(md, "Metrics", mt)
    ph = ["| Phase | Includes | Excludes | Exit criterion |", "|---|---|---|---|"]
    ph += [f"| {cell(p.get('name'))} | {'; '.join(map(str, as_list(p.get('scope')))) or TBD} | "
           f"{'; '.join(map(str, as_list(p.get('excludes')))) or TBD} | {cell(p.get('exit')) if p.get('exit') else TBD} |"
           for p in phases] or [f"| v1 | {TBD} | {TBD} | {TBD} |", f"| Later | {TBD} | {TBD} | needs evidence: {TBD} |"]
    if not phases:
        gaps.append("phases")
    md = replace_section(md, "Phases", ph)
    md = replace_section(md, "Engineering handoff", [
        f"- Acceptance criteria: {TBD} (derive from the v1 scope rows above)",
        f"- Entities for supabase-schema-rls: {TBD}",
        f"- RBAC rows to add: {TBD}",
        "- Metrics instrumentation: events `action=<…>` with `outcome`" + (f" for {', '.join(cell(m.get('name')) for m in metrics)}" if metrics else ""),
        f"- Flag: `{flag}`"])
    md = md.replace("{{date}}", dt.date.today().isoformat())
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    n_tbd = md.count("[TO BE BASELINED")
    print(f"PRD: {feature}; {len(goals)} goal(s), {len(metrics)} metric(s), {len(phases)} phase(s); "
          f"{n_tbd} marker(s) to baseline" + (f"; brief lacked: {', '.join(gaps)}" if gaps else "") + f" -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
