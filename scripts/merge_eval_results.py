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
from behavioral_evals import skill_verdict  # noqa: E402  (one verdict rule for every scorecard)

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


def restate(row: str) -> str:
    """Recompute a scorecard row's verdict from its own numbers with the current rule (behavioral_evals.skill_verdict)."""
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    if len(cells) < 7:
        return row
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
    rows = {k: restate(v) for k, v in {**drows, **srows}.items()}
    dates = sorted({d.strip() for d in re.split(r"[,–]", dm["date"] + "," + sm["date"]) if d.strip()})
    span = dates[0] if len(dates) == 1 else f"{dates[0]}–{dates[-1]}"   # no spaces: the portal reads date=<token>
    spend = dm["spend"] + sm["spend"]
    out = ["# Behavioral eval scorecard",
           f"_provider={dm['provider']} model={dm['model']} runs={dm['runs']} seed={dm['seed']} date={span}_",
           f"_estimated spend: ${spend:.2f}_", "", *dhead, *[rows[k] for k in sorted(rows)]]
    (dst / "scorecard.md").write_text("\n".join(out) + "\n", encoding="utf-8")
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
        lines = p.read_text(encoding="utf-8").splitlines()
        out = [restate(l) if l.startswith("| ") and not l.startswith("| skill") and not re.match(r"^\|[-| ]+\|$", l) else l for l in lines]
        p.write_text("\n".join(out) + "\n", encoding="utf-8")
        print("restated", sum(1 for a, b in zip(lines, out) if a != b), "row(s)")
        sys.exit(0)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    r = merge(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"merged {r['merged']} skills ({r['added']} new, {r['replaced']} replaced); scorecard now {r['total']} skills; spend ${r['spend']:.2f}")
