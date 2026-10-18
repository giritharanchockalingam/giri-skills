#!/usr/bin/env python3
"""Turn one SPEC.md section into a task-gated plan.

    python3 -I scripts/plan.py SPEC.md --section "Invoice export" [--template assets/plan-template.md] \
        --out plan.md --tasks tasks.csv [--slug invoice-export]

The section (first heading containing --section, case-insensitive; body up to the next heading of
the same or higher level) is read for tasks: every top-level `-`/`*` bullet or `1.` item is a task.
Sub-bullets fill its fields when they start with a recognised key (case-insensitive):
  accept | acceptance | ac   -> acceptance criterion
  test | tests               -> test to write
  rollback | revert          -> rollback
  files | file               -> files to touch
  size                       -> S | M | L
Inline `(accept: …; test: …; rollback: …)` after the task text works too. A field the spec does not
give is `[TO BE BASELINED — owner: ___]` — never invented. Writes plan.md on the template (Tasks,
Gates, Rollback filled) and tasks.csv (id, task, acceptance, test, rollback, files, size). More than
8 tasks is reported as a split warning. Exit 1 when the file, the section or any task is missing. Stdlib.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "assets" / "plan-template.md"
TBD = "[TO BE BASELINED — owner: ___]"
KEYS = {"accept": "acceptance", "acceptance": "acceptance", "ac": "acceptance", "test": "test", "tests": "test",
        "rollback": "rollback", "revert": "rollback", "files": "files", "file": "files", "size": "size"}
ITEM_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
GATES = [("plan", "spec section + repo read", "this file: file table, tasks, risks, rollback"),
         ("approve", "plan posted", "explicit \"go\" from the user"),
         ("build", "task N started", "diff limited to task N's file list"),
         ("test", "task N code done", "task N tests pass AND full unit suite passes"),
         ("verify", "all tasks done", "lint + typecheck + unit + build green; e2e on touched paths; criteria ticked")]


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def find_section(md: str, heading: str) -> list[str]:
    lines, out, level = md.splitlines(), [], None
    for ln in lines:
        m = re.match(r"^(#+)\s+(.*)$", ln)
        if m:
            if level is None:
                if heading.lower() in m.group(2).lower():
                    level = len(m.group(1))
                continue
            if len(m.group(1)) <= level:
                break
        elif level is not None:
            out.append(ln)
    if level is None:
        die(f"section not found: {heading!r}")
    return out


def split_fields(text: str) -> tuple[str, dict]:
    """'Export CSV (accept: …; test: …)' -> ('Export CSV', {...})."""
    fields = {}
    m = re.search(r"\(([^()]*\b(?:accept|acceptance|ac|tests?|rollback|revert|files?|size)\s*:[^()]*)\)\s*$", text, re.I)
    if m:
        for part in re.split(r";\s*", m.group(1)):
            k, _, v = part.partition(":")
            key = KEYS.get(k.strip().lower())
            if key and v.strip():
                fields[key] = v.strip()
        text = text[:m.start()].strip()
    return text.strip(), fields


def parse_tasks(lines: list[str]) -> list[dict]:
    tasks, base_indent = [], None
    for ln in lines:
        m = ITEM_RE.match(ln)
        if not m:
            continue
        indent, text = len(m.group(1).expandtabs(4)), m.group(2).strip()
        if base_indent is None:
            base_indent = indent
        if indent <= base_indent:
            title, fields = split_fields(text)
            tasks.append({"task": title, **fields})
        elif tasks:
            k, _, v = text.partition(":")
            key = KEYS.get(k.strip().lower().lstrip("*_").rstrip("*_"))
            if key and v.strip():
                tasks[-1][key] = v.strip()
    for i, t in enumerate(tasks, 1):
        t["id"] = f"T{i}"
        for key in ("acceptance", "test", "rollback", "files"):
            t.setdefault(key, TBD)
        size = str(t.get("size", "")).upper()[:1]
        t["size"] = size if size in ("S", "M", "L") else "M"
    return tasks


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


def main() -> int:
    ap = argparse.ArgumentParser(description="SPEC section -> task-gated plan")
    ap.add_argument("spec", help="SPEC.md")
    ap.add_argument("--section", required=True, help="heading text of the section to plan")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--out", default="plan.md")
    ap.add_argument("--tasks", default="tasks.csv")
    ap.add_argument("--slug", default="", help="plan slug (default: from the section heading)")
    a = ap.parse_args()
    spec = Path(a.spec)
    if not spec.is_file():
        die(f"spec not found: {spec}")
    tmpl = Path(a.template)
    if not tmpl.is_file():
        die(f"template not found: {tmpl}")
    body = find_section(spec.read_text(encoding="utf-8", errors="replace"), a.section)
    tasks = parse_tasks(body)
    if not tasks:
        die(f"section {a.section!r} has no bullet or numbered items to plan from")
    slug = a.slug or re.sub(r"[^a-z0-9]+", "-", a.section.lower()).strip("-")
    today = dt.date.today().isoformat()

    task_blocks = []
    for t in tasks:
        task_blocks += [f"### {t['id']} — {t['task']} ({t['size']})",
                        f"- Files: {t['files']}", f"- Acceptance: {t['acceptance']}", f"- Tests: {t['test']}",
                        f"- Rollback: {t['rollback']}", "- Status: ☐ built ☐ tests pass ☐ full suite pass", ""]
    task_blocks.pop()  # trailing blank
    if len(tasks) > 8:
        task_blocks.insert(0, f"> **Split warning:** {len(tasks)} tasks exceed the 8-task limit — split into two plans (two threads).\n")
    md = tmpl.read_text(encoding="utf-8").replace("{{SLUG}}", slug).replace("{{DATE}}", today)
    md = md.replace("| Source | SPEC §__ / ticket __ |", f"| Source | SPEC §{a.section} |")
    sizes = "".join(t["size"] for t in tasks)
    md = md.replace("| Size | S / M / L (sum of tasks) |", f"| Size | {sizes} ({len(tasks)} tasks) |")
    md = replace_section(md, "Tasks", task_blocks)
    gates = ["| Gate | Entry | Exit evidence |", "|---|---|---|"] + [f"| {g} | {e} | {x} |" for g, e, x in GATES]
    gates += ["", "A gate without its exit evidence is not passed. Order: plan → approve → build → test → verify."]
    md = md.replace("## Risks", "## Gates\n" + "\n".join(gates) + "\n\n## Risks", 1)
    rollback = [f"- {t['id']}: {t['rollback']}" for t in tasks]
    rollback.append(f"- Whole feature: {TBD} (revert tag / disable flag / down-migration)")
    md = replace_section(md, "Rollback", rollback)
    out, tasks_path = Path(a.out), Path(a.tasks)
    out.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    with tasks_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "task", "acceptance", "test", "rollback", "files", "size"])
        w.writeheader()
        w.writerows(tasks)
    n_tbd = sum(1 for t in tasks for k in ("acceptance", "test", "rollback", "files") if t[k] == TBD)
    print(f"plan: {len(tasks)} task(s) from SPEC §{a.section}, {n_tbd} field(s) to be baselined -> {out}, {tasks_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
