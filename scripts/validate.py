#!/usr/bin/env python3
"""Validate every skill in skills/ against the agentskills.io spec + repo rules.

Checks: SKILL.md exists; YAML frontmatter has name + description; name matches
directory, is kebab-case, <=64 chars; description <=1024 chars; body <=500 lines;
referenced relative files exist; evals/evals.json present and parseable.
Exit 1 on any failure. Run: python3 scripts/validate.py
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINK_RE = re.compile(r"`((?:references|assets|scripts|evals)/[^`]+)`|\]\(((?:references|assets|scripts|evals)/[^)]+)\)")

def frontmatter(text: str) -> dict | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm

def main() -> int:
    errors: list[str] = []
    count = 0
    for skill_md in sorted(SKILLS.rglob("SKILL.md")):
        count += 1
        d = skill_md.parent
        rel = d.relative_to(ROOT)
        text = skill_md.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if fm is None:
            errors.append(f"{rel}: missing YAML frontmatter"); continue
        name, desc = fm.get("name", ""), fm.get("description", "")
        if not name: errors.append(f"{rel}: missing name")
        if name != d.name: errors.append(f"{rel}: name '{name}' != dir '{d.name}'")
        if not NAME_RE.match(name or "x") or len(name) > 64: errors.append(f"{rel}: bad name format")
        if not desc: errors.append(f"{rel}: missing description")
        if len(desc) > 1024: errors.append(f"{rel}: description >1024 chars")
        body_lines = text.count("\n")
        if body_lines > 500: errors.append(f"{rel}: SKILL.md {body_lines} lines (>500)")
        for m in LINK_RE.finditer(text):
            p = m.group(1) or m.group(2)
            if "<" in p or "*" in p: continue
            if not (d / p).exists(): errors.append(f"{rel}: referenced file missing: {p}")
        ev = d / "evals" / "evals.json"
        if not ev.exists():
            errors.append(f"{rel}: evals/evals.json missing")
        else:
            try: json.loads(ev.read_text())
            except Exception as e: errors.append(f"{rel}: evals.json invalid: {e}")
    print(f"Checked {count} skills, {len(errors)} errors")
    for e in errors: print("  -", e)
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
