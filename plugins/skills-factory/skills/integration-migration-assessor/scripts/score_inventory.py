#!/usr/bin/env python3
"""Validate, score, band, and wave-assign an integration/API inventory CSV.

Input columns: see assets/inventory-columns.md. Factor columns:
  pattern, transformation, target_connector, endpoint_count, volume_class,
  error_handling, security, test_coverage, documentation, criticality
Optional: calls_90d, endpoint_status, freeze_tag, depends_on.

Scoring (references/complexity-scoring.md): each factor 1-5, weighted,
normalized to 0-100. Blank or unrecognized factor values score 3 and are
counted as unknown; they are never treated as simple. Bands: Simple 0-30,
Medium 31-55, Complex 56-75, Very complex 76-100.

Waves: retirement candidates and decommissioning endpoints are excluded.
Wave 1 takes representative Simple items (one per pattern first, up to the
wave-1 share); remaining items are balanced across middle waves by weighted
score, with depends_on ordering enforced (a dependent never precedes its
prerequisite) and Very complex items kept out of the final wave.

Usage:
    python3 -I score_inventory.py inventory.csv --validate
    python3 -I score_inventory.py inventory.csv --out scored.csv --waves 4
    python3 -I score_inventory.py inventory.csv --out scored.csv --wave1-share 0.15 --summary

Exit codes: 0 ok; 2 input error; 4 validation failed (with --validate).
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

FACTORS: list[tuple[str, str, int, dict[str, int] | None]] = [
    # (column, factor_id, weight, value->score map or None for numeric endpoint_count)
    ("pattern", "f1", 15, {"sync": 1, "async": 3, "batch": 3, "orchestration": 5}),
    ("transformation", "f2", 15, {"none": 1, "mapping": 2, "moderate": 3, "heavy": 5}),
    ("target_connector", "f3", 15, {"native": 1, "partial": 3, "none": 5}),
    ("endpoint_count", "f4", 10, None),
    ("volume_class", "f5", 10, {"low": 1, "medium": 3, "high": 5}),
    ("error_handling", "f6", 10, {"default": 1, "custom": 3, "compensation": 5}),
    ("security", "f7", 8, {"basic": 1, "oauth-pii": 3, "regulated": 5}),
    ("test_coverage", "f8", 7, {"automated": 1, "manual": 3, "none": 5}),
    ("documentation", "f9", 5, {"current": 1, "partial": 3, "none": 5}),
    ("criticality", "f10", 5, {"low": 1, "medium": 3, "high": 5}),
]
TOTAL_WEIGHT = sum(w for _, _, w, _ in FACTORS)
REQUIRED = ["interface_id", "name", "source_system", "target_system"]
BANDS = [(30, "Simple"), (55, "Medium"), (75, "Complex"), (100, "Very complex")]


def band_of(score: float) -> str:
    for upper, name in BANDS:
        if score <= upper:
            return name
    return "Very complex"


def score_factor(col: str, raw: str, mapping: dict[str, int] | None) -> tuple[int, bool, bool]:
    """Return (score, unknown, review_flag)."""
    v = (raw or "").strip().lower()
    if not v:
        return 3, True, False
    if mapping is None:  # endpoint_count numeric
        try:
            n = int(float(v))
        except ValueError:
            return 3, True, True
        return (1 if n <= 2 else 3 if n <= 4 else 5), False, False
    if v in mapping:
        return mapping[v], False, False
    return 3, True, True  # unrecognized value: unknown + review


def validate(rows: list[dict], fieldnames: list[str]) -> list[str]:
    problems: list[str] = []
    missing = [c for c in REQUIRED if c not in fieldnames]
    if missing:
        problems.append(f"missing required columns: {missing}")
    missing_factors = [c for c, *_ in FACTORS if c not in fieldnames]
    if missing_factors:
        problems.append(f"missing factor columns (will score as unknown): {missing_factors}")
    ids = Counter((r.get("interface_id") or "").strip() for r in rows)
    dups = [k for k, n in ids.items() if k and n > 1]
    if dups:
        problems.append(f"duplicate interface_id: {dups[:10]}{' ...' if len(dups) > 10 else ''}")
    blanks = sum(1 for r in rows if not (r.get("interface_id") or "").strip())
    if blanks:
        problems.append(f"{blanks} rows with blank interface_id")
    return problems


def score_rows(rows: list[dict]) -> None:
    for r in rows:
        total = 0.0
        unknown = 0
        review = False
        for col, fid, w, mapping in FACTORS:
            s, unk, rev = score_factor(col, r.get(col, ""), mapping)
            r[f"{fid}_score"] = s
            total += s * w
            unknown += int(unk)
            review = review or rev
        # conflict check: pass-through sync with no connector but 'none' transformation is plausible; flag heavy+sync
        r["weighted_score"] = round(total / TOTAL_WEIGHT / 5 * 100, 1)
        r["unknown_factors"] = unknown
        r["band"] = band_of(r["weighted_score"])
        calls = (r.get("calls_90d") or "").strip()
        retire = False
        try:
            retire = calls != "" and float(calls) <= 0
        except ValueError:
            pass
        if (r.get("endpoint_status") or "").strip().lower() == "decommissioning":
            retire = True
        r["retire_candidate"] = "Y" if retire else "N"
        r["review_flag"] = "Y" if review else "N"


def assign_waves(rows: list[dict], waves: int, wave1_share: float) -> None:
    candidates = [r for r in rows if r["retire_candidate"] == "N"]
    for r in rows:
        r["wave"] = "retire" if r["retire_candidate"] == "Y" else ""
    if not candidates or waves < 2:
        for r in candidates:
            r["wave"] = "1"
        return
    by_id = {r["interface_id"]: r for r in candidates}
    # Wave 1: representative simples, one per pattern first
    simples = sorted((r for r in candidates if r["band"] == "Simple"), key=lambda r: r["weighted_score"])
    if not simples:  # no Simple band: prove the factory on the lowest-scored items instead
        simples = sorted(candidates, key=lambda r: r["weighted_score"])
    n_w1 = max(1, int(round(len(candidates) * wave1_share)))
    wave1: list[dict] = []
    seen_patterns: set[str] = set()
    for r in simples:
        p = (r.get("pattern") or "").lower()
        if p not in seen_patterns and len(wave1) < n_w1:
            wave1.append(r); seen_patterns.add(p)
    for r in simples:
        if r not in wave1 and len(wave1) < n_w1:
            wave1.append(r)
    for r in wave1:
        r["wave"] = "1"
    remaining = [r for r in candidates if r["wave"] == ""]
    middle = list(range(2, waves + 1))
    # Balance by weighted score across middle waves; Very complex never in the last wave
    loads = {w: 0.0 for w in middle}
    for r in sorted(remaining, key=lambda r: -r["weighted_score"]):
        allowed = middle[:-1] if (r["band"] == "Very complex" and len(middle) > 1) else middle
        w = min(allowed, key=lambda k: loads[k])
        r["wave"] = str(w); loads[w] += r["weighted_score"]
    # Enforce dependencies: dependent wave >= prerequisite wave (iterate to fixpoint)
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False; guard += 1
        for r in candidates:
            deps = [d.strip() for d in (r.get("depends_on") or "").split(";") if d.strip()]
            for d in deps:
                pre = by_id.get(d)
                if pre is None or pre["wave"] in ("", "retire"):
                    continue
                if int(r["wave"]) < int(pre["wave"]):
                    r["wave"] = pre["wave"]; changed = True


def summary(rows: list[dict]) -> str:
    L = []
    bands = Counter(r["band"] for r in rows)
    total = len(rows)
    L.append("| Band | Count | Share |")
    L.append("|---|---|---|")
    for _, name in BANDS:
        L.append(f"| {name} | {bands.get(name, 0)} | {bands.get(name, 0)/total*100 if total else 0:.0f}% |")
    unk = sum(1 for r in rows if r["unknown_factors"] > 0)
    L.append("")
    L.append(f"Interfaces with >=1 unknown factor: {unk} ({unk/total*100 if total else 0:.0f}%)"
             + ("  — PROVISIONAL (>25%)" if total and unk / total > 0.25 else ""))
    L.append(f"Retirement candidates: {sum(1 for r in rows if r['retire_candidate']=='Y')}; review flags: {sum(1 for r in rows if r['review_flag']=='Y')}")
    L.append("")
    L.append("| Wave | Count | Σ score | Simple | Medium | Complex | Very complex |")
    L.append("|---|---|---|---|---|---|---|")
    wv: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        wv[r["wave"]].append(r)
    for w in sorted(wv, key=lambda k: (k == "retire", int(k) if k.isdigit() else 0)):
        rs = wv[w]
        c = Counter(r["band"] for r in rs)
        L.append(f"| {w} | {len(rs)} | {sum(r['weighted_score'] for r in rs):.0f} | {c.get('Simple',0)} | {c.get('Medium',0)} | {c.get('Complex',0)} | {c.get('Very complex',0)} |")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inventory", help="Inventory CSV")
    ap.add_argument("--out", help="Scored CSV output path")
    ap.add_argument("--waves", type=int, default=4, help="Number of business waves (excluding wave 0)")
    ap.add_argument("--wave1-share", type=float, default=0.15, help="Share of interfaces in wave 1 (0.10-0.20)")
    ap.add_argument("--validate", action="store_true", help="Validate only; exit 4 on problems")
    ap.add_argument("--summary", action="store_true", help="Print band and wave summary (Markdown)")
    args = ap.parse_args(argv)

    path = Path(args.inventory)
    if not path.is_file():
        print(f"error: inventory not found: {path}", file=sys.stderr)
        return 2
    with open(path, newline="", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        fieldnames = list(rdr.fieldnames or [])
        rows = [dict(r) for r in rdr]
    if not rows:
        print("error: inventory has no rows", file=sys.stderr)
        return 2
    problems = validate(rows, fieldnames)
    for p in problems:
        print(f"validation: {p}", file=sys.stderr)
    if args.validate:
        hard = [p for p in problems if p.startswith("missing required") or p.startswith("duplicate") or "blank interface_id" in p]
        print("validation: " + ("OK" if not hard else "FAILED"), file=sys.stderr)
        return 4 if hard else 0
    if any(p.startswith("missing required") for p in problems):
        return 2

    score_rows(rows)
    assign_waves(rows, args.waves, args.wave1_share)

    if args.out:
        extra = [f"{fid}_score" for _, fid, _, _ in FACTORS] + ["unknown_factors", "weighted_score", "band", "retire_candidate", "review_flag", "wave"]
        out_fields = fieldnames + [c for c in extra if c not in fieldnames]
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"wrote {args.out} ({len(rows)} rows)")
    if args.summary or not args.out:
        print(summary(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
