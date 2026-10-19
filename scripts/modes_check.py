#!/usr/bin/env python3
"""Greenfield / brownfield proof: every agent skill declares which starting points it serves, and each declared
starting point runs green on its own example.

  metadata.agent.modes:
    new:      {case: <eval case id>, bring: "what you bring when starting from scratch"}
    existing: {case: <eval case id>, bring: "what you bring when improving something that exists"}

Checks
  1. every agent skill declares at least one mode; a declared mode names an eval case that has inputs
  2. (--run) each declared mode's case runs with `run_skill.py --demo SKILL --mode M --provider none`:
     every check the eval case declares passes (its expected exit code included; default exit:0) and every
     output check the skill declares passes
  3. every lifecycle stage and business shelf has at least one skill for each mode that applies to it
     (shared/adlc-stages.json may narrow a stage's modes, with a `modes_why`)

Usage: python3 scripts/modes_check.py [--run] [--skills GLOB] [--json OUT]
Exit 0 when every check holds, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import skillmeta  # noqa: E402

MODES = ("new", "existing")


def declared(skill_dir: Path) -> tuple[dict, list[str]]:
    """(modes, problems) for one skill."""
    s = skillmeta.load_skill(skill_dir)
    agent = skillmeta.agent_block(s)
    if not agent:
        return {}, []
    modes = agent.get("modes")
    probs: list[str] = []
    if not isinstance(modes, dict) or not modes:
        return {}, ["declares no modes (metadata.agent.modes.new / .existing)"]
    ev = skill_dir / "evals" / "evals.json"
    cases = {c.get("id"): c for c in (json.loads(ev.read_text(encoding="utf-8")).get("cases", []) if ev.exists() else [])}
    for m, spec in modes.items():
        if m not in MODES:
            probs.append(f"unknown mode '{m}' (use: {', '.join(MODES)})")
            continue
        if not isinstance(spec, dict) or not spec.get("case") or not str(spec.get("bring", "")).strip():
            probs.append(f"mode '{m}' needs case and bring")
            continue
        c = cases.get(spec["case"])
        if not c or not c.get("inputs"):
            probs.append(f"mode '{m}': eval case '{spec['case']}' missing or has no inputs")
    return modes, probs


def run_mode(key: str, mode: str, case: dict, skill_dir: Path) -> tuple[bool, str]:
    """Run the mode's example; it passes when every check the eval case itself declares holds (its expected exit code
    included — default exit:0) AND every output check the skill declares holds."""
    from behavioral_evals import eval_case_checks  # the same check engine the behavioral evals use
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, str(ROOT / "scripts/run_skill.py"), "--demo", key, "--mode", mode,
                            "--provider", "none", "--out", td], capture_output=True, text=True, cwd=str(ROOT), timeout=300)
        rj = Path(td) / "run.json"
        if not rj.exists():
            return False, (r.stderr.strip().splitlines() or ["no run.json"])[-1][:160]
        run = json.loads(rj.read_text())
        bad = [c for c in run.get("checks", []) if not c.get("pass")]
        case_res = eval_case_checks(case.get("checks") or ["exit:0"], r.returncode, Path(td), skill_dir)
        bad_case = [c for c in case_res if not c["pass"]]
        if bad or bad_case:
            first = (bad[0].get("check", "") if bad else f"case check {bad_case[0]['check']}: {bad_case[0]['evidence']}")[:110]
            return False, f"exit {r.returncode}; {len(bad) + len(bad_case)} check(s) failed: {first}"
        return True, f"{len(run.get('checks', []))} output checks + {len(case_res)} case checks passed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="run every declared mode's example")
    ap.add_argument("--skills", default="skills/*/*")
    ap.add_argument("--json", help="write the per-skill result table here")
    a = ap.parse_args()
    stages = json.loads((ROOT / "shared/adlc-stages.json").read_text())
    places = [s["id"] for s in stages["stages"]] + [s["id"] for s in stages["shelves"]]
    # a stage may declare the starting points that apply to it (e.g. improve: existing only) — with a stated reason
    applies = {s["id"]: s.get("modes", list(MODES)) for s in stages["stages"] + stages["shelves"]}
    cover: dict[str, set[str]] = {p: set() for p in places}
    rows, failures = [], 0
    for sk in sorted(ROOT.glob(a.skills + "/SKILL.md")):
        sd = sk.parent
        key = f"{sd.parent.name}/{sd.name}"
        meta = skillmeta.load_skill(sd).get("metadata", {})
        if not skillmeta.agent_block(skillmeta.load_skill(sd)):
            continue
        modes, probs = declared(sd)
        stage = meta.get("adlc_stage")
        for st in stage if isinstance(stage, list) else [stage]:
            for m in modes:
                if st in cover and m in MODES:
                    cover[st].add(m)
        res = {"skill": key, "stage": stage, "modes": sorted(m for m in modes if m in MODES), "problems": probs, "runs": {}}
        if a.run and not probs:
            ev = json.loads((sd / "evals" / "evals.json").read_text(encoding="utf-8"))
            cases = {c.get("id"): c for c in ev.get("cases", [])}
            for m in sorted(modes):
                ok, why = run_mode(key, m, cases[modes[m]["case"]], sd)
                res["runs"][m] = {"ok": ok, "detail": why}
                if not ok:
                    probs.append(f"mode '{m}' run failed: {why}")
        failures += bool(probs)
        rows.append(res)
        mark = "FAIL" if probs else "ok  "
        print(f"{mark} {key:<48} {','.join(res['modes']) or '-':<14} {'; '.join(probs)[:110]}")
    gaps = [f"{p}: no '{m}' skill" for p in places for m in applies[p] if m not in cover[p]]
    print(f"\n{len(rows)} agent skills · {len(rows) - failures} pass · {failures} fail")
    print(f"both modes declared: {sum(1 for r in rows if len(r['modes']) == 2)} · one mode: {sum(1 for r in rows if len(r['modes']) == 1)}")
    print("stage coverage: " + ("every stage and shelf has new and existing" if not gaps else "GAPS — " + "; ".join(gaps)))
    if a.json:
        Path(a.json).write_text(json.dumps({"skills": rows, "gaps": gaps}, indent=2))
    return 1 if failures or gaps else 0


if __name__ == "__main__":
    sys.exit(main())
