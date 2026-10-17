#!/usr/bin/env python3
"""Retrieval evaluation: recall@k, precision@k, MRR, coverage from a CSV.

CSV columns (header required):
  query_id, query, expected_doc_ids, retrieved_doc_ids [, query_type, notes]
  - expected_doc_ids: pipe-separated ids; empty means out-of-scope (expect abstention)
  - retrieved_doc_ids: pipe-separated ids in ranked order (best first)

Usage:
  python3 -I eval_retrieval.py --csv retrieval-eval-set.csv --k 1,5,10 [--json out.json] [--min-recall 0.8 --at 5]

Exit code 1 when --min-recall is set and recall@<at> is below it. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def split_ids(cell: str) -> list[str]:
    return [x.strip() for x in (cell or "").split("|") if x.strip()]


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"query_id", "expected_doc_ids", "retrieved_doc_ids"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"CSV missing columns: {sorted(missing)}")
        return list(reader)


def recall_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    """Fraction of expected ids present in top-k (1.0/0.0 when single expected)."""
    if not expected:
        return float("nan")
    top = set(retrieved[:k])
    return sum(1 for e in expected if e in top) / len(expected)


def hit_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    if not expected:
        return float("nan")
    return 1.0 if any(e in retrieved[:k] for e in expected) else 0.0


def precision_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    if not expected or k == 0:
        return float("nan")
    top = retrieved[:k]
    return sum(1 for r in top if r in set(expected)) / k


def reciprocal_rank(expected: list[str], retrieved: list[str]) -> float:
    if not expected:
        return float("nan")
    exp = set(expected)
    for i, r in enumerate(retrieved, start=1):
        if r in exp:
            return 1.0 / i
    return 0.0


def mean(values: list[float]) -> float:
    vals = [v for v in values if v == v]  # drop NaN
    return sum(vals) / len(vals) if vals else float("nan")


def evaluate(rows: list[dict], ks: list[int]) -> dict:
    per_type: dict[str, list[dict]] = defaultdict(list)
    in_scope, out_scope = [], []
    for r in rows:
        exp, ret = split_ids(r["expected_doc_ids"]), split_ids(r["retrieved_doc_ids"])
        rec = {
            "query_id": r["query_id"],
            "query_type": (r.get("query_type") or "unspecified").strip(),
            "expected": exp,
            "retrieved": ret,
        }
        if exp:
            in_scope.append(rec)
            per_type[rec["query_type"]].append(rec)
        else:
            out_scope.append(rec)

    def summarize(group: list[dict]) -> dict:
        out = {"n": len(group)}
        for k in ks:
            out[f"recall@{k}"] = round(mean([recall_at_k(g["expected"], g["retrieved"], k) for g in group]), 4)
            out[f"hit@{k}"] = round(mean([hit_at_k(g["expected"], g["retrieved"], k) for g in group]), 4)
            out[f"precision@{k}"] = round(mean([precision_at_k(g["expected"], g["retrieved"], k) for g in group]), 4)
        out["mrr"] = round(mean([reciprocal_rank(g["expected"], g["retrieved"]) for g in group]), 4)
        out["coverage"] = round(mean([hit_at_k(g["expected"], g["retrieved"], 10**9) for g in group]), 4)
        return out

    result = {"overall": summarize(in_scope), "by_type": {t: summarize(g) for t, g in sorted(per_type.items())}}
    if out_scope:
        # Abstention proxy: out-of-scope queries should retrieve nothing (or the caller's abstain logic handles it).
        empty = sum(1 for g in out_scope if not g["retrieved"])
        result["out_of_scope"] = {"n": len(out_scope), "retrieved_nothing_rate": round(empty / len(out_scope), 4)}
    misses = [g["query_id"] for g in in_scope if hit_at_k(g["expected"], g["retrieved"], max(ks)) == 0.0]
    result["misses_at_max_k"] = misses
    return result


def print_scorecard(res: dict, ks: list[int]) -> None:
    cols = ["n"] + [f"recall@{k}" for k in ks] + [f"hit@{k}" for k in ks] + ["mrr", "coverage"]
    print("group".ljust(18) + "".join(c.rjust(12) for c in cols))
    rows = [("overall", res["overall"])] + list(res["by_type"].items())
    for name, s in rows:
        print(name[:17].ljust(18) + "".join(str(s[c]).rjust(12) for c in cols))
    if "out_of_scope" in res:
        o = res["out_of_scope"]
        print(f"out_of_scope n={o['n']} retrieved_nothing_rate={o['retrieved_nothing_rate']}")
    if res["misses_at_max_k"]:
        print(f"misses@{max(ks)}: {', '.join(res['misses_at_max_k'])}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--k", default="1,5,10", help="comma-separated k values")
    ap.add_argument("--json", type=Path, help="write full results to this file")
    ap.add_argument("--min-recall", type=float, help="gate: fail if recall@<at> below this")
    ap.add_argument("--at", type=int, default=5, help="k used for the --min-recall gate")
    args = ap.parse_args()

    ks = sorted({int(x) for x in args.k.split(",") if x.strip()})
    rows = load_rows(args.csv)
    if not rows:
        sys.exit("CSV has no rows")
    res = evaluate(rows, ks)
    print_scorecard(res, ks)
    if args.json:
        args.json.write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    if args.min_recall is not None:
        key = f"recall@{args.at}"
        got = res["overall"].get(key)
        if got is None:
            sys.exit(f"gate k={args.at} not in --k list")
        if got != got or got < args.min_recall:
            print(f"GATE FAILED: {key}={got} < {args.min_recall}")
            return 1
        print(f"GATE PASSED: {key}={got} >= {args.min_recall}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
