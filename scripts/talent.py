#!/usr/bin/env python3
"""Roles and talent pools: validate the shipped templates against the skill library and the agents.

  roles/<name>.json  {"name", "title", "description", "skills": [skill ids], "playbooks": [agent names]}
  pools/<name>.json  {"name", "title", "description", "members": [{"role", "label"?, "seats"?}], "playbooks": [agent names]}

Rules (the same ones the portal enforces in studio/lib/factory/talent.ts):
  - every skill a role lists exists; a role's playbook uses only skills the role has
  - every pool member is a shipped role; every skill step of a pool playbook is staffed by some member
  - library invariant: every skill belongs to at least one role (no orphan capability)

Usage:
  python3 scripts/talent.py              validate everything (exit 1 on any problem)
  python3 scripts/talent.py --coverage   print which roles bring each ADLC stage, per pool
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}$")


def skill_stages(root: Path = ROOT) -> dict[str, str]:
    out = {}
    for p in sorted((root / "skills").glob("*/*/SKILL.md")):
        m = re.search(r"^\s*adlc_stage:\s*([a-z-]+)", p.read_text(encoding="utf-8"), re.M)
        out[f"{p.parent.parent.name}/{p.parent.name}"] = m.group(1) if m else ""
    return out


def playbook_skills(root: Path = ROOT) -> dict[str, list[str]]:
    out = {}
    for p in sorted((root / "agents").glob("*/agent.json")):
        spec = json.loads(p.read_text(encoding="utf-8"))
        out[p.parent.name] = [s["skill"] for s in spec.get("steps", []) if "skill" in s]
    return out


def load_dir(d: Path) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))} if d.is_dir() else {}


def member_key(m: dict, i: int, members: list[dict] | None = None) -> str:
    """A member's name in the team: its label, else its role (role#2, #3… when the role repeats)."""
    if (m.get("label") or "").strip():
        return m["label"].strip()
    before = sum(1 for x in (members or [])[:i] if x.get("role") == m.get("role") and not (x.get("label") or "").strip())
    return m.get("role", "") + (f"#{before + 1}" if before else "")


def validate_role(spec: dict, skills: dict[str, str], playbooks: dict[str, list[str]]) -> list[str]:
    p = []
    if not SLUG.match(spec.get("name", "")):
        p.append("name must be a lowercase slug")
    for k in ("title", "description"):
        if not str(spec.get(k, "")).strip():
            p.append(f"missing '{k}'")
    have = spec.get("skills") or []
    if not have:
        p.append("the role has no skills")
    if len(set(have)) != len(have):
        p.append("a skill is listed twice")
    p += [f"skill {s} does not exist" for s in have if s not in skills]
    for pb in spec.get("playbooks") or []:
        if pb not in playbooks:
            p.append(f"playbook {pb} does not exist")
            continue
        missing = sorted({s for s in playbooks[pb] if s not in have})
        if missing:
            p.append(f"playbook {pb} uses skills this role does not have: {', '.join(missing)}")
    return p


def staff(pb_skills: list[str], members: list[tuple[str, list[str]]], stages: dict[str, str] | None = None) -> list[tuple[str, str | None]]:
    """Among members that have the skill, the specialist (most skills in that skill's stage) wins; ties go to team order."""
    stages = stages or {}
    out = []
    for s in pb_skills:
        st = stages.get(s)
        best = None
        for k, sk in members:
            if s not in sk:
                continue
            depth = sum(1 for x in sk if st and stages.get(x) == st)
            if best is None or depth > best[1]:
                best = (k, depth)
        out.append((s, best[0] if best else None))
    return out


def validate_pool(spec: dict, roles: dict[str, dict], playbooks: dict[str, list[str]]) -> list[str]:
    p = []
    if not SLUG.match(spec.get("name", "")):
        p.append("name must be a lowercase slug")
    for k in ("title", "description"):
        if not str(spec.get(k, "")).strip():
            p.append(f"missing '{k}'")
    ms = spec.get("members") or []
    if not ms:
        p.append("the pool has no members")
    keys = set()
    for i, m in enumerate(ms):
        if m.get("role") not in roles:
            p.append(f"member {i + 1}: role {m.get('role')} does not exist")
        k = member_key(m, i, ms)
        if k in keys:
            p.append(f"member {k} listed twice (give it a label)")
        keys.add(k)
    members = [(member_key(m, i, ms), roles.get(m.get("role"), {}).get("skills", [])) for i, m in enumerate(ms)]
    for pb in spec.get("playbooks") or []:
        if pb not in playbooks:
            p.append(f"playbook {pb} does not exist")
            continue
        gaps = sorted({s for s, who in staff(playbooks[pb], members) if who is None})
        if gaps:
            p.append(f"playbook {pb} has steps no member can staff: {', '.join(gaps)}")
    return p


def validate_all(root: Path = ROOT) -> list[str]:
    skills, playbooks = skill_stages(root), playbook_skills(root)
    roles, pools = load_dir(root / "roles"), load_dir(root / "pools")
    problems = []
    for name, spec in roles.items():
        if spec.get("name") != name:
            problems.append(f"roles/{name}.json: name '{spec.get('name')}' must match the file name")
        problems += [f"roles/{name}.json: {x}" for x in validate_role(spec, skills, playbooks)]
    for name, spec in pools.items():
        if spec.get("name") != name:
            problems.append(f"pools/{name}.json: name '{spec.get('name')}' must match the file name")
        problems += [f"pools/{name}.json: {x}" for x in validate_pool(spec, roles, playbooks)]
    owned = {s for r in roles.values() for s in r.get("skills") or []}
    problems += [f"skill {s} belongs to no role" for s in sorted(skills) if s not in owned]
    return problems


def coverage(pool: dict, roles: dict[str, dict], skills: dict[str, str], stages: list[str]) -> dict[str, list[str]]:
    out = {st: [] for st in stages}
    ms = pool.get("members") or []
    for i, m in enumerate(ms):
        for s in roles.get(m["role"], {}).get("skills", []):
            st = skills.get(s)
            if st in out and member_key(m, i, ms) not in out[st]:
                out[st].append(member_key(m, i, ms))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--coverage", action="store_true")
    a = ap.parse_args(argv)
    problems = validate_all()
    roles, pools = load_dir(ROOT / "roles"), load_dir(ROOT / "pools")
    if a.coverage:
        tax = json.loads((ROOT / "shared" / "adlc-stages.json").read_text())
        stages = [s["id"] for s in tax["stages"] + tax["shelves"]]
        skills = skill_stages()
        for name, pool in pools.items():
            print(f"{name}:")
            for st, who in coverage(pool, roles, skills, stages).items():
                print(f"  {st:<13} {', '.join(who) if who else '— gap'}")
    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    print(f"talent: {len(roles)} roles, {len(pools)} pools, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
