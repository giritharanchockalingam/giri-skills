#!/usr/bin/env python3
"""Eval regression set for the delivery pipeline itself (docs/HARNESS.md layer 6).

    python3 scripts/pipeline_eval.py run     --out DIR [--only G1,G3] [--tier core] [--parallel 3] [--sandbox docker] [--budget-usd 15] [--model M]
    python3 scripts/pipeline_eval.py score   --out DIR                       # scorecard.json + scorecard.md from the runs in DIR
    python3 scripts/pipeline_eval.py compare --out DIR [--baseline evals/pipeline/baseline.json] [--cost-tolerance 0.3]
    python3 scripts/pipeline_eval.py baseline --out DIR                      # write DIR's scorecard as the new baseline

Scenarios live in evals/pipeline/scenarios/<id>/ (scenario.json + brief.json): each is one real greenfield delivery
run, scored from its own run.json — exit, stages passed, tests, visual check, acceptance review, repair turns and
what triggered them, model spend, duration — against the scenario's expectations. A scenario that needs a database
gets a fresh one: EVAL_DATABASE_URL_TEMPLATE (e.g. postgresql://u:p@127.0.0.1:5432/{db}) is filled with a new name
and created through EVAL_DATABASE_ADMIN_URL with psql.

compare exits 1 on a regression: a scenario that passed in the baseline fails now, the pass rate drops, or the
median cost rises more than --cost-tolerance. Every number comes from a real run; a scenario that did not run is
NOT RUN, never a pass.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCEN = ROOT / "evals" / "pipeline" / "scenarios"
BASELINE = ROOT / "evals" / "pipeline" / "baseline.json"


def scenarios(only: str | None, tier: str | None) -> list[tuple[str, dict, Path]]:
    out = []
    for d in sorted(SCEN.iterdir()) if SCEN.is_dir() else []:
        f = d / "scenario.json"
        if not f.is_file():
            continue
        s = json.loads(f.read_text(encoding="utf-8"))
        if only and d.name not in only.split(","):
            continue
        if tier and s.get("tier") != tier:
            continue
        out.append((d.name, s, d))
    return out


def fresh_database(sid: str) -> str | None:
    tmpl, admin = os.environ.get("EVAL_DATABASE_URL_TEMPLATE"), os.environ.get("EVAL_DATABASE_ADMIN_URL")
    if not tmpl or not admin:
        return None
    name = f"eval_{sid.lower()}_{int(time.time())}"
    r = subprocess.run(["psql", admin, "-qc", f'CREATE DATABASE "{name}"'], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"could not create database {name}: {r.stderr.strip()[:200]}")
    return tmpl.replace("{db}", name)


def run_one(sid: str, s: dict, d: Path, out: Path, a) -> dict:
    run_dir = out / sid
    env = dict(os.environ)
    db_note = ""
    if s.get("database"):
        url = fresh_database(sid)
        if url:
            env["DATABASE_URL"] = url
        else:
            db_note = "no EVAL_DATABASE_URL_TEMPLATE/EVAL_DATABASE_ADMIN_URL: ran without a database"
    argv = [sys.executable, "-I", str(HERE / "deliver.py"), s.get("pipeline", "greenfield-app"), "--repo", str(run_dir / "app"),
            "--input", f"name={s.get('name', sid.lower())}", "--input", f"stack={s.get('stack', 'nextjs-ts')}",
            "--request", s["request"], "--brief", str(d / "brief.json"), "--builder", "claude-code", "--provider", "none",
            "--approve-all", "--dry", "--out", str(run_dir / "run"), "--sandbox", a.sandbox, "--acceptance", "on",
            *(["--model", a.model] if a.model else []), *(["--budget-usd", str(a.budget_usd)] if a.budget_usd else [])]
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(run_dir / "console.log", "w", encoding="utf-8") as fh:
        rc = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT, env=env).returncode
    (run_dir / "eval.json").write_text(json.dumps({"exit": rc, "duration_s": round(time.time() - t0, 1), "db_note": db_note}) + "\n")
    return score_one(sid, s, run_dir)


def score_one(sid: str, s: dict, run_dir: Path) -> dict:
    ev = json.loads((run_dir / "eval.json").read_text()) if (run_dir / "eval.json").is_file() else {}
    rj_p = run_dir / "run" / "run.json"
    if not rj_p.is_file():
        return {"id": sid, "title": s.get("title", ""), "result": "NOT RUN", "why": "no run.json"}
    rj = json.loads(rj_p.read_text(encoding="utf-8"))
    stages = rj.get("stages") or []
    code = next((x for g in stages for x in g.get("steps", []) if x.get("id") == "code"), {})
    acc = code.get("acceptance") or {}
    repairs = code.get("repairs") or []
    caught = {"tests": 0, "visual": 0, "acceptance": 0, "other": 0}
    for r in repairs:
        why = str(r.get("reason", ""))
        caught["visual" if why.startswith("visual check") else "acceptance" if why.startswith("acceptance review")
               else "tests" if why.startswith("tests") else "other"] += 1
    exp = s.get("expect") or {}
    passed_stages = sum((g.get("gate") or {}).get("verdict") == "pass" for g in stages)
    checks = {
        "exit": ev.get("exit") == exp.get("exit", 0),
        "stages": passed_stages >= int(exp.get("min_stages_passed", 0)),
        "acceptance": (acc.get("verdict") == exp["acceptance"]) if exp.get("acceptance") else True,
        "visual": ((code.get("visual") or {}).get("verdict") == exp["visual"]) if exp.get("visual") else True,
    }
    stopped = next((g for g in stages if g.get("status") != "passed"), None)
    return {"id": sid, "title": s.get("title", ""), "result": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "exit": ev.get("exit"), "stages_passed": f"{passed_stages}/{len(stages)}",
            "stopped_at": (stopped or {}).get("id"), "stop_detail": str(((stopped or {}).get("gate") or {}).get("detail", ""))[:300],
            "tests": (code.get("tests") or {}).get("summary"), "visual": (code.get("visual") or {}).get("verdict"),
            "acceptance": acc.get("verdict"), "acceptance_counts": acc.get("counts"), "repairs": len(repairs), "defects_caught": caught,
            "cost_usd": float((rj.get("llm") or {}).get("cost_usd") or 0), "duration_s": ev.get("duration_s"),
            "sandbox": (rj.get("sandbox") or {}).get("mode", "none"), "db_note": ev.get("db_note", "")}


def scorecard(out: Path, rows: list[dict]) -> dict:
    ran = [r for r in rows if r["result"] != "NOT RUN"]
    costs = [r["cost_usd"] for r in ran]
    card = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pipeline_commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True).stdout.strip(), "scenarios": rows,
            "pass_rate": round(sum(r["result"] == "PASS" for r in ran) / len(ran), 3) if ran else 0.0,
            "median_cost_usd": round(statistics.median(costs), 4) if costs else 0.0, "total_cost_usd": round(sum(costs), 4)}
    (out / "scorecard.json").write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Pipeline eval — {card['at']} (pipeline {card['pipeline_commit']})", "",
             f"Pass rate {card['pass_rate']:.0%} · median cost ${card['median_cost_usd']:.2f} · total ${card['total_cost_usd']:.2f}", "",
             "| Scenario | Result | Stages | Tests | Visual | Acceptance | Repairs (tests/visual/acceptance) | Cost | Time | Sandbox | Stopped at |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["result"] == "NOT RUN":
            lines.append(f"| {r['id']} | NOT RUN | | | | | | | | | {r.get('why', '')} |")
            continue
        c = r["defects_caught"]
        lines.append(f"| {r['id']} | **{r['result']}** | {r['stages_passed']} | {r['tests'] or '—'} | {r['visual'] or '—'} | {r['acceptance'] or '—'} | "
                     f"{r['repairs']} ({c['tests']}/{c['visual']}/{c['acceptance']}) | ${r['cost_usd']:.2f} | {r['duration_s'] or 0:.0f} s | {r['sandbox']} | "
                     f"{(r['stopped_at'] or '') + (': ' + r['stop_detail'][:80] if r['stop_detail'] else '')} |")
    (out / "scorecard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return card


def compare(card: dict, base: dict, tol: float) -> list[str]:
    regressions = []
    prev = {r["id"]: r for r in base.get("scenarios", [])}
    for r in card["scenarios"]:
        b = prev.get(r["id"])
        if b and b.get("result") == "PASS" and r.get("result") != "PASS":
            regressions.append(f"{r['id']}: passed in the baseline, {r.get('result')} now ({r.get('stopped_at')}: {r.get('stop_detail', '')[:120]})")
    if card["pass_rate"] < base.get("pass_rate", 0):
        regressions.append(f"pass rate {card['pass_rate']:.0%} < baseline {base['pass_rate']:.0%}")
    if base.get("median_cost_usd") and card["median_cost_usd"] > base["median_cost_usd"] * (1 + tol):
        regressions.append(f"median cost ${card['median_cost_usd']:.2f} > baseline ${base['median_cost_usd']:.2f} + {tol:.0%}")
    return regressions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--only")
    p.add_argument("--tier")
    p.add_argument("--parallel", type=int, default=3)
    p.add_argument("--sandbox", choices=["docker", "none"], default="docker")
    p.add_argument("--budget-usd", type=float)
    p.add_argument("--model")
    for name in ("score", "baseline"):
        sub.add_parser(name).add_argument("--out", type=Path, required=True)
    p = sub.add_parser("compare")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--baseline", type=Path, default=BASELINE)
    p.add_argument("--cost-tolerance", type=float, default=0.3)
    a = ap.parse_args(argv)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "run":
        sc = scenarios(a.only, a.tier)
        if not sc:
            print("no scenarios selected", file=sys.stderr)
            return 2
        with cf.ThreadPoolExecutor(max_workers=max(1, a.parallel)) as ex:
            rows = list(ex.map(lambda t: run_one(*t, out, a), sc))
        card = scorecard(out, rows)
        print((out / "scorecard.md").read_text())
        return 0 if card["pass_rate"] == 1.0 else 1
    if a.cmd in ("score", "baseline"):
        rows = [score_one(sid, s, out / sid) for sid, s, _ in scenarios(None, None) if (out / sid).is_dir()]
        card = scorecard(out, rows)
        if a.cmd == "baseline":
            BASELINE.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
            print(f"baseline written: {BASELINE} (pass rate {card['pass_rate']:.0%}, median ${card['median_cost_usd']:.2f})")
        else:
            print((out / "scorecard.md").read_text())
        return 0
    card = json.loads((out / "scorecard.json").read_text())
    if not a.baseline.is_file():
        print(f"no baseline at {a.baseline}: nothing to compare (write one with `baseline`)")
        return 0
    regs = compare(card, json.loads(a.baseline.read_text()), a.cost_tolerance)
    print("\n".join(f"REGRESSION: {r}" for r in regs) if regs else "no regression against the baseline")
    return 1 if regs else 0


if __name__ == "__main__":
    sys.exit(main())
