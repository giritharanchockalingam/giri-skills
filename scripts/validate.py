#!/usr/bin/env python3
"""Validate every skill in skills/ against the agentskills.io spec + repo rules.

Checks: SKILL.md exists; YAML frontmatter has name + description; name matches
directory, is kebab-case, <=64 chars; description <=1024 chars; body <=500 lines;
referenced relative files exist; evals/evals.json present and parseable.
Skills at metadata.version >= 0.2.0 must also declare metadata.agent with >= 1 run
step and >= 1 output check, every check name in scripts/check_output.py's vocabulary,
every script/template/context path present, and every eval-case fixture path present.
Exit 1 on any failure. Run: python3 scripts/validate.py
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_output  # noqa: E402
import skillmeta  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
AGENT_MIN_VERSION = (0, 2, 0)
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
    key = None
    for line in text[4:end].splitlines():
        if line and not line.startswith(" ") and ":" in line:
            key, _, v = line.partition(":")
            key = key.strip()
            fm[key] = v.strip()
        elif key and line.startswith(" ") and line.strip():
            # multi-line scalar continuation (e.g. a folded description)
            fm[key] = (fm[key] + " " + line.strip()).strip()
    return fm

def _rel_paths_in(text: str):
    """Skill-relative paths referenced by a step: scripts/x.py, assets/x, references/x."""
    return re.findall(r"(?<![\w{/])((?:scripts|assets|references)/[\w./-]+)", text)


def check_agent(d: Path, rel, errors: list[str]) -> None:
    """Rules for skills at version >= 0.2.0 (see docs/AGENT-REBUILD-PLAN.md §3)."""
    skill = skillmeta.load_skill(d)
    version = skillmeta.version_tuple(skill["metadata"].get("version", "0"))
    agent = skillmeta.agent_block(skill)
    if version < AGENT_MIN_VERSION:
        return
    if not agent:
        errors.append(f"{rel}: version >= 0.2.0 but metadata.agent missing"); return
    names = set()
    for i in agent.get("inputs", []) or []:
        if not isinstance(i, dict) or not i.get("name"):
            errors.append(f"{rel}: agent input without a name"); continue
        names.add(str(i["name"]))
        if i.get("default") and str(i.get("type")) in ("csv", "json", "md", "txt", "file", "sql", "dir") \
                and not (d / str(i["default"])).exists():
            errors.append(f"{rel}: default for input '{i['name']}' missing: {i['default']}")
    run = agent.get("run") or []
    if not run:
        errors.append(f"{rel}: metadata.agent.run has no steps")
    for st in run:
        if not isinstance(st, dict) or not st.get("step"):
            errors.append(f"{rel}: run step without a name"); continue
        kind = st.get("kind", "script")
        if kind == "llm":
            for key in ("template", "out"):
                if not st.get(key):
                    errors.append(f"{rel}: llm step '{st['step']}' lacks {key}")
            if st.get("template") and not (d / str(st["template"])).exists():
                errors.append(f"{rel}: llm step '{st['step']}' template missing: {st['template']}")
            for c in st.get("context") or []:
                c = str(c)
                if "{" not in c and not (d / c).exists():
                    errors.append(f"{rel}: llm step '{st['step']}' context missing: {c}")
        else:
            cmd = str(st.get("cmd", ""))
            if not cmd:
                errors.append(f"{rel}: script step '{st['step']}' lacks cmd"); continue
            for p in _rel_paths_in(cmd):
                if not (d / p).exists():
                    errors.append(f"{rel}: step '{st['step']}' references missing file: {p}")
            for tok in re.findall(r"\{(\w+)\}", cmd):
                if tok not in names and tok not in ("out", "skill_dir"):
                    errors.append(f"{rel}: step '{st['step']}' uses undeclared input {{{tok}}}")
    outputs = agent.get("outputs") or []
    n_checks = 0
    for o in outputs:
        if not isinstance(o, dict) or not o.get("path"):
            errors.append(f"{rel}: output without a path"); continue
        for c in o.get("checks") or []:
            n_checks += 1
            name, _ = check_output.parse_spec(str(c))
            if name not in check_output.VOCAB:
                errors.append(f"{rel}: unknown check '{name}' on {o['path']}")
            elif name in check_output.RUN_LEVEL:
                errors.append(f"{rel}: run-level check '{name}' not allowed on an output")
    if n_checks == 0:
        errors.append(f"{rel}: metadata.agent.outputs has no checks")
    ev = d / "evals" / "evals.json"
    if ev.exists():
        try:
            cases = json.loads(ev.read_text(encoding="utf-8")).get("cases", [])
        except Exception:
            cases = []
        n_agent_cases = 0
        for c in cases:
            if "inputs" not in c:
                continue
            n_agent_cases += 1
            for k, v in (c.get("inputs") or {}).items():
                if k not in names:
                    errors.append(f"{rel}: eval case {c.get('id')} uses undeclared input '{k}'")
                v = str(v)
                if v.startswith("evals/") and not (d / v).exists():
                    errors.append(f"{rel}: eval case {c.get('id')} fixture missing: {v}")
            for chk in c.get("checks") or []:
                spec = chk.get("check", "") if isinstance(chk, dict) else str(chk)
                name, _ = check_output.parse_spec(spec)
                if name not in check_output.VOCAB:
                    errors.append(f"{rel}: eval case {c.get('id')} unknown check '{name}'")
        if n_agent_cases == 0:
            errors.append(f"{rel}: no eval case carries inputs (agent cases required at >= 0.2.0)")


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
        check_agent(d, rel, errors)
    vendor = ROOT / "vendor"
    vcount = 0
    for md in sorted(vendor.glob("*/SKILL.md")):
        vcount += 1
        fm = frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        if not fm or not fm.get("name") or not fm.get("description"):
            errors.append(f"vendor/{md.parent.name}: SKILL.md missing name/description frontmatter")
        if not (md.parent / "UPSTREAM.md").exists():
            errors.append(f"vendor/{md.parent.name}: UPSTREAM.md missing (run scripts/vendor_sync.py)")
    print(f"Checked {count} skills + {vcount} vendored, {len(errors)} errors")
    for e in errors: print("  -", e)
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
