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

    ... --final prd-final.md --draft-only           # no model step: the checked script draft is the final PRD
    ... --existing PRD-v3.md --redline PRD-redline.md --final prd-final.md

--draft-only writes --final as the script draft with a label saying the sharpen step did not run.
--existing redlines a PRD the team already has against the brief and the review checklist, keeping its
storyline: every template section is [KEEP] (present and passes), [SHARPEN] (present but fails a check:
goal without a number, < 3 non-goals, metric without baseline/target, story without Given/When/Then,
open question without an owner), or [ADD] (missing: the brief-derived section is added, marked); every
figure in the existing PRD that the brief does not contain is [TBD] with an owner. --redline gets the
table; --final gets the existing PRD with the redline applied (sections untouched except markers).
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


FROM_BRIEF = {"Exec summary", "Problem", "Users", "Goals", "Non-goals", "Metrics", "Phases", "User stories", "Engineering handoff"}
REDLINE_SECTIONS = ["Exec summary", "Problem", "Users", "Goals", "Non-goals", "Metrics", "Phases",
                    "User stories", "Risks", "Open questions", "Engineering handoff"]
NUM_RE = re.compile(r"(?<![\w.])[$€£]?\d[\d,]*(?:\.\d+)?%?(?![\w])")
DRAFT_LABEL = "> Script draft — the model sharpen step was not run (draft only); every field comes from the brief."


def split_sections(md: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """(preamble lines, [(heading line, body lines)]) on `## ` headings."""
    pre, secs = [], []
    for ln in md.splitlines():
        if ln.startswith("## "):
            secs.append((ln, []))
        elif secs:
            secs[-1][1].append(ln)
        else:
            pre.append(ln)
    return pre, secs


def find_section(secs, name: str):
    n = name.lower()
    for i, (h, _) in enumerate(secs):
        t = re.sub(r"\s*\(.*\)\s*$", "", h[3:]).strip().lower()
        if n in t:
            return i
    return None


def figures(text: str) -> list[str]:
    """Figures worth sourcing: with %, a currency sign, or >= 2 digits (ISO dates and section numbers skipped)."""
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text)
    out = []
    for m in NUM_RE.finditer(text):
        tok = m.group(0)
        digits = re.sub(r"\D", "", tok)
        if tok.endswith("%") or tok[0] in "$€£" or len(digits) >= 2:
            out.append(tok)
    return out


def checks_for(name: str, body: str) -> str:
    """The reason a present section needs sharpening, or '' when it passes."""
    has_tbd = "[TO BE BASELINED" in body
    rows = [ln for ln in body.splitlines() if ln.strip().startswith(("-", "*", "|")) and not re.match(r"^\s*\|[-| ]+\|\s*$", ln)
            and not re.match(r"^\s*\|\s*(#|Non-goal|Metric|Goal|Question|Risk)\b", ln)]
    if not body.strip():
        return "section is empty"
    if name == "Goals" and not figures(body) and not has_tbd:
        return "no goal names a measurable target"
    if name == "Non-goals" and len(rows) < 3:
        return f"{len(rows)} non-goal(s); list at least 3 things a reader would assume are included"
    if name == "Metrics" and not re.search(r"baseline", body, re.I) and not has_tbd:
        return "metrics have no baseline"
    if name == "User stories" and not re.search(r"\bGiven\b.*\bThen\b", body, re.S):
        return "stories have no Given/When/Then acceptance criteria"
    if name == "Open questions" and not re.search(r"owner", body, re.I):
        return "open questions have no owner"
    return ""


def redline(existing: str, draft: str, brief_text: str, source: str) -> tuple[list[dict], str]:
    """Rows for the redline table and the existing PRD with the redline applied."""
    pre, secs = split_sections(existing)
    _, dsecs = split_sections(draft)
    rows, adds = [], []
    for name in REDLINE_SECTIONS:
        i = find_section(secs, name)
        if i is None:
            j = find_section(dsecs, name) if name in FROM_BRIEF else None
            rows.append({"section": name, "verdict": "ADD", "note": "missing — added from the brief" if j is not None
                         else "missing — write it (the brief does not cover it)"})
            body = dsecs[j][1] if j is not None else [TBD, ""]
            adds.append([f"## {name}", f"> [ADD] {rows[-1]['note']}"] + body)
            continue
        reason = checks_for(name, "\n".join(secs[i][1]))
        rows.append({"section": name, "verdict": "SHARPEN" if reason else "KEEP", "note": reason or "passes the checklist"})
        if reason:
            secs[i] = (secs[i][0], [f"> [SHARPEN] {reason}"] + secs[i][1])
    known = set(figures(brief_text))
    unsourced = []
    out_secs = []
    for h, body in secs:
        new_body = []
        for ln in body:
            figs = [f for f in figures(ln) if f not in known and not ln.lstrip().startswith(">")]
            for f in figs:
                unsourced.append({"section": re.sub(r"\s*\(.*\)\s*$", "", h[3:]).strip(), "figure": f})
            if figs:
                ln += " " + " ".join(f"[TO BE BASELINED — owner: Product owner — source for {f}]" for f in figs)
            new_body.append(ln)
        out_secs.append((h, new_body))
    for u in unsourced:
        rows.append({"section": u["section"], "verdict": "TBD", "note": f"figure {u['figure']} is not in the brief — source it or cut it"})
    note = (f"> Redlined against {source} by product-spec-prd (no model step): storyline kept; "
            "[SHARPEN] / [ADD] markers and owned to-be-baselined markers show what to change.")
    lines = list(pre[:1]) + ["", note] + list(pre[1:])
    for h, body in out_secs:
        lines += [h] + body
    for block in adds:
        lines += [""] + block
    return rows, "\n".join(lines).rstrip("\n") + "\n"


def render_redline(rows: list[dict], existing_name: str) -> str:
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("KEEP", "SHARPEN", "ADD", "TBD")}
    out = [f"# PRD redline — {existing_name}", "",
           f"**{counts['KEEP']} keep, {counts['SHARPEN']} sharpen, {counts['ADD']} add, {counts['TBD']} unsourced figure(s).** "
           "Storyline kept; nothing rewritten.", "", "## Redline table", "", "| Section | Verdict | Note |", "|---|---|---|"]
    out += [f"| {r['section']} | [{r['verdict']}] | {cell(r['note'])} |" for r in rows]
    out += ["", "## Unsourced figures", ""]
    tbd = [r for r in rows if r["verdict"] == "TBD"]
    out += [f"- {r['section']}: {r['note']} (owner: Product owner)" for r in tbd] or ["- none: every figure traces to the brief"]
    return "\n".join(out) + "\n"


def cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ").strip() or TBD


def main() -> int:
    ap = argparse.ArgumentParser(description="brief.json -> PRD.md on the template")
    ap.add_argument("brief")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--out", default="PRD.md")
    ap.add_argument("--final", default="", help="final PRD path (written with --draft-only or --existing)")
    ap.add_argument("--draft-only", action="store_true", help="no model step: write --final from the script draft")
    ap.add_argument("--existing", default="", help="the team's existing PRD to redline against the brief")
    ap.add_argument("--redline", default="", help="with --existing: write the redline table here")
    a = ap.parse_args()
    if a.existing and not Path(a.existing).is_file():
        die(f"existing PRD not found: {a.existing}")
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
    # user stories + acceptance criteria from the brief's stories/tasks (task, accept[, test]) — the draft never
    # invents them; without them the section stays the template and the pipeline stops for the product manager
    stories = [t for t in (as_list(brief.get("stories")) or as_list(brief.get("tasks"))) if isinstance(t, dict) and (t.get("accept") or t.get("acceptance"))]
    if stories:
        st = []
        for i, t in enumerate(stories, 1):
            who = cell(t.get("persona")) if t.get("persona") else (str(users[0]) if users else "a user")
            what, accept = cell(t.get("task") or t.get("story") or t.get("name")), cell(t.get("accept") or t.get("acceptance"))
            st += [f"### S{i} — As {who}, I want: {what}", f"- Given the v1 build, When the user exercises \"{what}\", Then {accept}"]
            if t.get("test"):
                st.append(f"- Verified by: {cell(t.get('test'))}")
        md = replace_section(md, "User stories", st)
        accept_line = "; ".join(cell(t.get("accept") or t.get("acceptance")) for t in stories)
    else:
        gaps.append("stories")
        accept_line = f"{TBD} (derive from the v1 scope rows above)"
    md = replace_section(md, "Engineering handoff", [
        f"- Acceptance criteria: {accept_line}",
        f"- Entities for supabase-schema-rls: {TBD}",
        f"- RBAC rows to add: {TBD}",
        "- Metrics instrumentation: events `action=<…>` with `outcome`" + (f" for {', '.join(cell(m.get('name')) for m in metrics)}" if metrics else ""),
        f"- Flag: `{flag}`"])
    md = md.replace("{{date}}", dt.date.today().isoformat())
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    if a.existing:
        ep = Path(a.existing)
        rows, merged = redline(ep.read_text(encoding="utf-8", errors="replace"), md, bp.read_text(encoding="utf-8"), bp.name)
        if a.redline:
            Path(a.redline).parent.mkdir(parents=True, exist_ok=True)
            Path(a.redline).write_text(render_redline(rows, ep.name), encoding="utf-8")
        if a.final:
            Path(a.final).write_text(merged, encoding="utf-8")
        print(f"redline: {ep.name} — " + ", ".join(f"{sum(1 for r in rows if r['verdict'] == v)} {v.lower()}"
                                                   for v in ("KEEP", "SHARPEN", "ADD", "TBD")))
    elif a.draft_only and a.final:
        lines = md.splitlines()
        Path(a.final).write_text("\n".join(lines[:1] + ["", DRAFT_LABEL] + lines[1:]) + "\n", encoding="utf-8")
    n_tbd = md.count("[TO BE BASELINED")
    print(f"PRD: {feature}; {len(goals)} goal(s), {len(metrics)} metric(s), {len(phases)} phase(s); "
          f"{n_tbd} marker(s) to baseline" + (f"; brief lacked: {', '.join(gaps)}" if gaps else "") + f" -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
