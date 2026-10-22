#!/usr/bin/env python3
"""Merge a partial behavioral-eval run into an existing results directory.

Use when only some skills were (re-)evaluated, e.g. skills added after the last full run:

    python3 scripts/merge_eval_results.py evals/results/new-38 evals/results/full-openai

For every skill present in SRC, its trigger.csv / quality.csv rows and its scorecard.md row replace DST's; every other
skill is kept as it was. The scorecard header records both dates and the summed spend. Provider, model, runs and seed
must match, so verdicts stay comparable (the merge refuses otherwise). Writes DST in place; prints a summary.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from behavioral_evals import skill_verdict, skill_confidence, write_confidence  # noqa: E402  (one rule for every scorecard)

import json  # noqa: E402
SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"

HEADER_RE = re.compile(r"_provider=(\S+) model=(\S+) runs=(\d+) seed=(\d+) date=([^_]+)_")
SPEND_RE = re.compile(r"_estimated spend: \$([0-9.]+)_")


def read_scorecard(p: Path) -> tuple[dict, list[str], dict[str, str]]:
    text = p.read_text(encoding="utf-8")
    m, s = HEADER_RE.search(text), SPEND_RE.search(text)
    if not m:
        sys.exit(f"error: {p} has no provider/model header")
    meta = {"provider": m[1], "model": m[2], "runs": m[3], "seed": m[4], "date": m[5].strip(), "spend": float(s[1]) if s else 0.0}
    lines = text.splitlines()
    head = [l for l in lines if l.startswith("| skill") or re.match(r"^\|[-| ]+\|$", l)]
    rows = {l.split("|")[1].strip(): l for l in lines if l.startswith("| ") and not l.startswith("| skill") and not re.match(r"^\|[-| ]+\|$", l)}
    return meta, head, rows


def trigger_hits(trigger_rows: list[dict]) -> dict[str, list[bool]]:
    """Per-skill router hits scored against each case's target (see trigger_accuracy)."""
    targets: dict[tuple[str, str], str] = {}
    hits: dict[str, list[bool]] = {}
    for r in trigger_rows:
        key = r["skill"]
        if key == "(negative)":
            continue
        if (key, r["case_id"]) not in targets:
            f = SKILLS_ROOT / key / "evals" / "evals.json"
            cases = json.loads(f.read_text(encoding="utf-8")).get("cases", []) if f.is_file() else []
            case = next((c for c in cases if c.get("id") == r["case_id"]), {})
            targets[(key, r["case_id"])] = str(case.get("routes_to") or key.split("/")[-1])
        hits.setdefault(key, []).append(r["selected"] == targets[(key, r["case_id"])])
    return hits


def restate_confidence(results: Path) -> int:
    """Rewrite results/confidence.csv from its trigger.csv and quality.csv (95% intervals, borderline flag)."""
    hits = trigger_hits(read_csv(results / "trigger.csv")[1])
    q: dict[str, list[dict]] = {}
    for r in read_csv(results / "quality.csv")[1]:
        q.setdefault(r["skill"], []).append(r)
    keys = set(hits) | set(q)
    write_confidence(results, {k: skill_confidence(hits.get(k, []), q.get(k, [])) for k in keys})
    return len(keys)


def trigger_accuracy(trigger_rows: list[dict]) -> dict[str, float]:
    """Per-skill routing accuracy from saved router selections, scored against each case's target (its own skill, or
    the case's `routes_to` for a boundary case) so a rule change is applied without re-running the router."""
    targets: dict[tuple[str, str], str] = {}
    hits: dict[str, list[bool]] = {}
    for r in trigger_rows:
        key = r["skill"]
        if key == "(negative)":
            continue
        if (key, r["case_id"]) not in targets:
            f = SKILLS_ROOT / key / "evals" / "evals.json"
            cases = json.loads(f.read_text(encoding="utf-8")).get("cases", []) if f.is_file() else []
            case = next((c for c in cases if c.get("id") == r["case_id"]), {})
            targets[(key, r["case_id"])] = str(case.get("routes_to") or key.split("/")[-1])
        hits.setdefault(key, []).append(r["selected"] == targets[(key, r["case_id"])])
    return {k: sum(v) / len(v) for k, v in hits.items() if v}


def restate(row: str, acc: dict[str, float] | None = None) -> str:
    """Recompute a scorecard row's verdict from its own numbers with the current rule (behavioral_evals.skill_verdict);
    with `acc`, the routing accuracy is recomputed from the saved router rows first."""
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    if len(cells) < 7:
        return row
    if acc and cells[0] in acc:
        cells[1] = f"{acc[cells[0]]:.2f}"
    num = lambda x: float(x) if re.fullmatch(r"-?\d+(\.\d+)?", x) else None
    cells[6] = skill_verdict(num(cells[1]), num(cells[3]), num(cells[4]))
    return "| " + " | ".join(cells) + " |"


def read_csv(p: Path) -> tuple[list[str], list[dict]]:
    with p.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def merge(src: Path, dst: Path) -> dict:
    sm, _, srows = read_scorecard(src / "scorecard.md")
    dm, dhead, drows = read_scorecard(dst / "scorecard.md")
    for k in ("provider", "model", "runs", "seed"):
        if sm[k] != dm[k]:
            sys.exit(f"error: {k} differs ({sm[k]} vs {dm[k]}); verdicts would not be comparable")
    skills = set(srows)
    for name in ("trigger.csv", "quality.csv"):
        sf, sr = read_csv(src / name)
        df, dr = read_csv(dst / name)
        if sf != df:
            sys.exit(f"error: {name} columns differ")
        kept = [r for r in dr if r["skill"] not in skills]
        with (dst / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=df)
            w.writeheader()
            w.writerows(sorted(kept + sr, key=lambda r: r["skill"]))
    acc = trigger_accuracy(read_csv(dst / "trigger.csv")[1])
    rows = {k: restate(v, acc) for k, v in {**drows, **srows}.items()}
    dates = sorted({d.strip() for d in re.split(r"[,–]", dm["date"] + "," + sm["date"]) if d.strip()})
    span = dates[0] if len(dates) == 1 else f"{dates[0]}–{dates[-1]}"   # no spaces: the portal reads date=<token>
    spend = dm["spend"] + sm["spend"]
    out = ["# Behavioral eval scorecard",
           f"_provider={dm['provider']} model={dm['model']} runs={dm['runs']} seed={dm['seed']} date={span}_",
           f"_estimated spend: ${spend:.2f}_", "", *dhead, *[rows[k] for k in sorted(rows)]]
    (dst / "scorecard.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    restate_confidence(dst)
    return {"merged": len(skills), "replaced": len(skills & set(drows)), "added": len(skills - set(drows)), "total": len(rows), "spend": spend}


def unevaluated(dst: Path, skills_root: Path) -> list[str]:
    """Skills in the library (skills/<domain>/<name>/SKILL.md) with no quality rows in DST."""
    have = {r["skill"] for r in read_csv(dst / "quality.csv")[1]}
    return sorted(str(p.parent.relative_to(skills_root)) for p in skills_root.glob("*/*/SKILL.md") if str(p.parent.relative_to(skills_root)) not in have)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--unevaluated":   # prints --skills args for behavioral_evals.py
        print(" ".join(f"--skills skills/{s}" for s in unevaluated(Path(sys.argv[2]), Path(__file__).parents[1] / "skills")))
        sys.exit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "--restate":   # re-apply the current verdict rule to a scorecard in place
        p = Path(sys.argv[2]) / "scorecard.md"
        acc = trigger_accuracy(read_csv(Path(sys.argv[2]) / "trigger.csv")[1])
        lines = p.read_text(encoding="utf-8").splitlines()
        out = [restate(l, acc) if l.startswith("| ") and not l.startswith("| skill") and not re.match(r"^\|[-| ]+\|$", l) else l for l in lines]
        p.write_text("\n".join(out) + "\n", encoding="utf-8")
        print("restated", sum(1 for a, b in zip(lines, out) if a != b), "row(s);", restate_confidence(Path(sys.argv[2])), "confidence row(s)")
        sys.exit(0)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    r = merge(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"merged {r['merged']} skills ({r['added']} new, {r['replaced']} replaced); scorecard now {r['total']} skills; spend ${r['spend']:.2f}")
