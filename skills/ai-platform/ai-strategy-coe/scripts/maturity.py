#!/usr/bin/env python3
"""Maturity assessment + roadmap skeleton from a scorecard CSV (assets/maturity-scorecard.csv layout).

    python3 -I scripts/maturity.py maturity-scorecard.csv --out-dir runs/x \
        [--target 3] [--org "Acme"] [--model references/maturity-model.md] [--template assets/roadmap.md]

Input columns: dimension, score_1_to_5|score, evidence, gap_to_next_level, owner, baseline_status.
The `overall_min` row in the asset layout is ignored and recomputed.

Rules (references/maturity-model.md): a score without an evidence line is NOT a score — the
dimension is reported as `[TO BE BASELINED — owner: <owner, else --default-owner>]`. Overall level = the
minimum of the evidenced scores; the constraining dimension is named. A gap = any dimension
below --target (default 3) or unevidenced. Each gap becomes one roadmap item citing the next
level's criteria from the maturity model.

Writes: maturity.md (level per dimension, overall, gaps) and roadmap.md (assets/roadmap.md with
the Maturity table filled and a "Gap closure items" table, one item per gap). Exit 1 on missing
columns, a score outside 1-5 or no dimension rows. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
DIMS = ["data", "platform", "talent", "governance", "value"]
LEVEL_NAMES = {1: "Ad hoc", 2: "Emerging", 3: "Defined", 4: "Managed", 5: "Optimizing"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# who owns a gap the scorecard leaves unassigned (--default-owner); never a blank owner
FALLBACK = {"owner": "AI CoE lead"}


def own(owner: str) -> str:
    return owner or FALLBACK["owner"]


def tbd(owner: str) -> str:
    return f"[TO BE BASELINED — owner: {own(owner)}]"


def read_scorecard(path: str) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    if not rows:
        die(f"{p.name}: no data rows")
    header = rows[0].keys()
    if "dimension" not in header or not ("score_1_to_5" in header or "score" in header):
        die(f"{p.name}: needs columns dimension and score_1_to_5 (or score)")
    out = []
    for i, r in enumerate(rows, 2):
        dim = r["dimension"].lower()
        if dim == "overall_min" or not dim:
            continue
        raw = r.get("score_1_to_5", r.get("score", ""))
        if raw and raw not in ("1", "2", "3", "4", "5"):
            die(f"row {i} ({dim}): score must be 1-5 or blank, got {raw!r}")
        out.append({"dimension": dim, "score": int(raw) if raw else None, "evidence": r.get("evidence", ""),
                    "gap": r.get("gap_to_next_level", ""), "owner": r.get("owner", "")})
    if not out:
        die("no dimension rows")
    return out


def criteria_from_model(model_path: Path) -> dict[str, dict[int, str]]:
    """{dimension: {level: criteria}} parsed from the '### <Dimension>' tables of the maturity model."""
    out: dict[str, dict[int, str]] = {}
    if not model_path.is_file():
        return out
    current = None
    for line in model_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+(\w+)", line)
        if m:
            current = m.group(1).lower()
            out.setdefault(current, {})
            continue
        if current and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0].isdigit():
                out[current][int(cells[0])] = cells[1]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="maturity scorecard -> maturity.md + roadmap.md skeleton")
    ap.add_argument("scorecard")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--target", type=int, default=3, help="target level; dimensions below it are gaps")
    ap.add_argument("--org", default="<Organization>")
    ap.add_argument("--default-owner", default="AI CoE lead", help="owner of gaps the scorecard leaves unassigned")
    ap.add_argument("--model", default=str(SKILL / "references" / "maturity-model.md"))
    ap.add_argument("--template", default=str(SKILL / "assets" / "roadmap.md"))
    a = ap.parse_args()
    FALLBACK["owner"] = a.default_owner.strip() or FALLBACK["owner"]
    if not 1 <= a.target <= 5:
        die("--target must be 1-5")
    rows = read_scorecard(a.scorecard)
    crit = criteria_from_model(Path(a.model))

    for r in rows:
        r["evidenced"] = r["score"] is not None and bool(r["evidence"])
        if r["score"] is not None and not r["evidence"]:
            r["note"] = "score given without evidence — treated as unscored"
        elif r["score"] is None:
            r["note"] = "no score"
        else:
            r["note"] = ""
        r["level"] = f"{r['score']} ({LEVEL_NAMES[r['score']]})" if r["evidenced"] else tbd(r["owner"])
        r["is_gap"] = (not r["evidenced"]) or r["score"] < a.target
        nxt = (r["score"] + 1) if r["evidenced"] and r["score"] < 5 else None
        r["next_criteria"] = crit.get(r["dimension"], {}).get(nxt, "") if nxt else ""

    scored = [r for r in rows if r["evidenced"]]
    unscored = [r for r in rows if not r["evidenced"]]
    missing_dims = [d for d in DIMS if d not in {r["dimension"] for r in rows}]
    if scored:
        low = min(scored, key=lambda r: r["score"])
        overall = f"Level {low['score']} ({LEVEL_NAMES[low['score']]}) overall; constraining dimension: {low['dimension']}"
        if unscored:
            overall += f" — provisional: {len(unscored)} dimension(s) unscored"
    else:
        overall = f"Overall level {tbd('')} — no evidenced score"
    gaps = [r for r in rows if r["is_gap"]]

    L = [f"# AI maturity assessment — {a.org}", "", f"**{overall}.** Target level: {a.target}. "
         f"{len(gaps)} gap(s): {', '.join(r['dimension'] for r in gaps) or 'none'}.", "",
         "## Level per dimension", "| Dimension | Level | Evidence | Gap to next level | Owner | Note |",
         "|---|---|---|---|---|---|"]
    L += [f"| {r['dimension']} | {r['level']} | {r['evidence'] or tbd(r['owner'])} | "
          f"{r['gap'] or r['next_criteria'] or tbd(r['owner'])} | {own(r['owner'])} | {r['note']} |" for r in rows]
    L += [f"| {d} | {tbd('')} | not in scorecard | | {own('')} | missing row |" for d in missing_dims]
    L += ["", f"## Gaps (dimensions below target {a.target} or unscored)", "| Dimension | Current | Target | Next-level criteria | Owner |",
          "|---|---|---|---|---|"]
    L += [f"| {r['dimension']} | {r['level']} | {a.target} | {r['next_criteria'] or tbd(r['owner'])} | {own(r['owner'])} |"
          for r in gaps] or ["| none | | | | |"]
    L += ["", "Scores and evidence are taken from the scorecard as supplied; plans score at the current level (rule 2). "
          "Unevidenced scores are not counted toward the overall level."]
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "maturity.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    tpl_path = Path(a.template)
    if not tpl_path.is_file():
        die(f"template not found: {tpl_path}")
    tpl = tpl_path.read_text(encoding="utf-8").replace("<Organization>", a.org)
    by_dim = {r["dimension"]: r for r in rows}
    for d in DIMS:
        r = by_dim.get(d)
        cell = (f"| {d.capitalize()} | {r['level']} | {r['evidence'] or tbd(r['owner'])} | "
                f"{r['gap'] or r['next_criteria'] or tbd(r['owner'])} | {own(r['owner'])} |") if r else \
            f"| {d.capitalize()} | {tbd('')} | not in scorecard | | {own('')} |"
        tpl = re.sub(rf"^\| {d.capitalize()} \|.*$", cell.replace("\\", "\\\\"), tpl, count=1, flags=re.M)
    tpl = tpl.replace("- Maturity: Level <n> overall; constraining dimension: <dimension> (evidence: <line>)",
                      f"- Maturity: {overall}")
    items = ["", "## Gap closure items (one per gap; sequence into the quarter plan)",
             "| # | Dimension | From | To | Exit criterion (next-level criteria) | Owner | Quarter |", "|---|---|---|---|---|---|---|"]
    for k, r in enumerate(gaps, 1):
        to = (r["score"] + 1) if r["evidenced"] else a.target
        exit_c = r["next_criteria"] or ("baseline the dimension with evidence" if not r["evidenced"] else tbd(r["owner"]))
        items.append(f"| {k} | {r['dimension']} | {r['level']} | {to} | {exit_c} | {own(r['owner'])} | {tbd(r['owner'])} |")
    if not gaps:
        items.append("| — | none | | | | | |")
    tpl = tpl.replace("\n## Assumptions", "\n".join(items) + "\n\n## Assumptions", 1)
    (out / "roadmap.md").write_text(tpl, encoding="utf-8")
    print(f"maturity: {overall}; {len(gaps)} gap(s) -> {out}")
    return 0


if __name__ == "__main__":
    main()
