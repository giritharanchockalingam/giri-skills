#!/usr/bin/env python3
"""Rank an AI use-case portfolio from a scoring CSV (assets/use-case-scoring.csv layout).

    python3 -I scripts/score_portfolio.py use-cases.csv --out-dir runs/x [--org "Acme"]

Input columns (asset layout; short aliases accepted): id, use_case, business_owner,
value_V|value, feasibility_F|feasibility, data_readiness_D|data_readiness, risk_R|risk,
baseline_metric, evidence|notes. Scores are 1-5.

Formula (references/use-case-scoring.md): priority = V x F x D / R, unweighted unless the
sponsor states a weighting (not supported here on purpose; record it in the notes).
Bands: Stop (V<=2, F=1 or R=5) -> Now (top quartile, R<=3, D>=3, owner + baseline named)
-> Next (second quartile, or top quartile blocked by D<=2 / missing owner or baseline)
-> Later (rest). A row missing any of the four scores is NOT ranked: it goes to the
"unscored" bucket with the missing axes named. Nothing is invented.

Writes: portfolio.csv (ranked rows only, score always filled), unscored.csv (rows that
could not be ranked, with reason), portfolio.md (ranked table, quadrant summary, unscored
list). Exit 1 on missing columns, a score outside 1-5, or no data rows. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: AI CoE lead]"
AXES = {"V": ("value_V", "value"), "F": ("feasibility_F", "feasibility"),
        "D": ("data_readiness_D", "data_readiness"), "R": ("risk_R", "risk")}
OUT_COLS = ["rank", "id", "use_case", "business_owner", "value_V", "feasibility_F", "data_readiness_D",
            "risk_R", "score", "quartile", "band", "band_reason", "baseline_metric", "evidence"]


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    if not rows:
        die(f"{p.name}: no data rows")
    header = rows[0].keys()
    for ax, names in AXES.items():
        if not any(n in header for n in names):
            die(f"{p.name}: missing column for {ax} (one of {list(names)})")
    for col in ("id", "use_case"):
        if col not in header:
            die(f"{p.name}: missing column '{col}'")
    return rows


def axis(row: dict, ax: str) -> str:
    for n in AXES[ax]:
        if n in row:
            return row[n]
    return ""


def quadrant(v: int, f: int) -> str:
    if v >= 3 and f >= 3:
        return "Quick win (V>=3, F>=3)"
    if v >= 3:
        return "Strategic bet (V>=3, F<3)"
    if f >= 3:
        return "Fill-in (V<3, F>=3)"
    return "Avoid (V<3, F<3)"


def main() -> int:
    ap = argparse.ArgumentParser(description="use-case scoring CSV -> ranked portfolio (csv + md)")
    ap.add_argument("use_cases", help="CSV in assets/use-case-scoring.csv layout")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--org", default="<Organization>")
    a = ap.parse_args()
    rows = read_rows(a.use_cases)

    ranked, unscored = [], []
    for i, r in enumerate(rows, 2):
        scores, missing = {}, []
        for ax in AXES:
            raw = axis(r, ax)
            if raw == "":
                missing.append(ax)
                continue
            if raw not in ("1", "2", "3", "4", "5"):
                die(f"row {i} ({r.get('id') or '?'}): {ax} must be 1-5, got {raw!r}")
            scores[ax] = int(raw)
        rec = {"id": r.get("id", ""), "use_case": r.get("use_case", ""),
               "business_owner": r.get("business_owner", ""),
               "baseline_metric": r.get("baseline_metric", ""),
               "evidence": r.get("evidence") or r.get("notes", "")}
        if missing:
            rec["reason"] = "missing score(s): " + ", ".join(missing)
            unscored.append(rec)
            continue
        rec.update({"value_V": scores["V"], "feasibility_F": scores["F"], "data_readiness_D": scores["D"],
                    "risk_R": scores["R"], "score": round(scores["V"] * scores["F"] * scores["D"] / scores["R"], 2)})
        ranked.append(rec)

    ranked.sort(key=lambda x: (-x["score"], x["id"]))
    n = len(ranked)
    for k, rec in enumerate(ranked, 1):
        rec["rank"] = k
        rec["quartile"] = math.ceil(k * 4 / n) if n else ""
        v, f, d, rr = rec["value_V"], rec["feasibility_F"], rec["data_readiness_D"], rec["risk_R"]
        if v <= 2 or f == 1 or rr == 5:
            rec["band"], rec["band_reason"] = "Stop", "V<=2, F=1 or R=5 (rubric Stop rule)"
        elif rec["quartile"] == 1 and rr <= 3 and d >= 3:
            if rec["business_owner"] and rec["baseline_metric"]:
                rec["band"], rec["band_reason"] = "Now", "top quartile, R<=3, D>=3, owner and baseline named"
            else:
                lack = [x for x, ok in (("owner", rec["business_owner"]), ("baseline", rec["baseline_metric"])) if not ok]
                rec["band"], rec["band_reason"] = "Next", "top quartile but no " + "/".join(lack) + " (rule 2: demote)"
        elif rec["quartile"] == 1 and d <= 2:
            rec["band"], rec["band_reason"] = "Next", "top quartile blocked by D<=2: fund data readiness first"
        elif rec["quartile"] == 1:
            rec["band"], rec["band_reason"] = "Next", "top quartile but R>3: mitigation plan before funding"
        elif rec["quartile"] == 2:
            rec["band"], rec["band_reason"] = "Next", "second quartile"
        else:
            rec["band"], rec["band_reason"] = "Later", f"quartile {rec['quartile']}"
        rec["evidence"] = rec["evidence"] or TBD
        rec["business_owner"] = rec["business_owner"] or TBD
        rec["baseline_metric"] = rec["baseline_metric"] or TBD

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "portfolio.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(ranked)
    with (out / "unscored.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "use_case", "business_owner", "reason"], extrasaction="ignore")
        w.writeheader()
        w.writerows(unscored)

    L = [f"# AI use-case portfolio — {a.org}", "",
         f"{n} use case(s) ranked by priority = V x F x D / R; {len(unscored)} unscored (missing axes, not ranked)."
         + (" Fewer than 8 candidates scored: the backlog is not fully elicited yet (rubric rule 1)." if n < 8 else ""),
         "", "## Ranked portfolio",
         "| Rank | ID | Use case | Owner | V | F | D | R | Score | Band | Why |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['rank']} | {r['id']} | {r['use_case']} | {r['business_owner']} | {r['value_V']} | {r['feasibility_F']} | "
          f"{r['data_readiness_D']} | {r['risk_R']} | {r['score']} | {r['band']} | {r['band_reason']} |" for r in ranked]
    if not ranked:
        L.append("| — | none ranked | | | | | | | | | |")
    L += ["", "## Band summary", "| Band | Count | IDs |", "|---|---|---|"]
    for band in ("Now", "Next", "Later", "Stop"):
        ids = [r["id"] for r in ranked if r["band"] == band]
        L.append(f"| {band} | {len(ids)} | {', '.join(ids) or '—'} |")
    L += ["", "## Quadrant summary (value vs feasibility)", "| Quadrant | Count | IDs |", "|---|---|---|"]
    quads = {}
    for r in ranked:
        quads.setdefault(quadrant(r["value_V"], r["feasibility_F"]), []).append(r["id"])
    for q in ("Quick win (V>=3, F>=3)", "Strategic bet (V>=3, F<3)", "Fill-in (V<3, F>=3)", "Avoid (V<3, F<3)"):
        L.append(f"| {q} | {len(quads.get(q, []))} | {', '.join(quads.get(q, [])) or '—'} |")
    L += ["", "## Unscored (not ranked — score before the next review)", "| ID | Use case | Owner | Missing |", "|---|---|---|---|"]
    L += [f"| {u['id']} | {u['use_case']} | {u['business_owner'] or TBD} | {u['reason']} |" for u in unscored] \
        or ["| none | | | |"]
    L += ["", "Scores are taken from the input file as supplied; no axis was inferred. "
          f"Evidence gaps are marked {TBD}."]
    (out / "portfolio.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"portfolio: {n} ranked, {len(unscored)} unscored -> {out}")
    return 0


if __name__ == "__main__":
    main()
