#!/usr/bin/env python3
"""Build a golden-set CSV (run_evals.py layout) from a transcript or a raw cases CSV.

Input (one of):
  * CSV with at least an `input` column. Optional columns are carried over:
      id, category, difficulty, expected, must_contain, must_not_contain,
      expected_json_valid, weight, source, notes, output
  * Transcript .txt/.md with `User:` / `Assistant:` turns (also `Q:`/`A:`, `Human:`/`AI:`).
    Each user turn becomes a case; the following assistant turn becomes `expected` and,
    with --outputs-out, also the pre-recorded `output` for offline scoring.

Output columns (assets/golden-set.csv):
  id, category, difficulty, input, expected, must_contain, must_not_contain,
  expected_json_valid, weight, source, notes
Rules: ids are GS-0001…; missing category -> `uncategorized`; missing difficulty -> `medium`;
missing source -> `log` for transcripts, `synthetic` when --source says so; `must_contain`
is never invented — when absent, notes say `must_contain [TO BE BASELINED — owner: SME]`.

Usage:
    python3 -I build_golden.py cases.csv --out golden-set.csv [--outputs-out outputs.csv]
    python3 -I build_golden.py transcript.md --out golden-set.csv --category support

Exit codes: 0 ok; 1 bad input (missing file, no cases, no `input` column). Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

COLS = ["id", "category", "difficulty", "input", "expected", "must_contain", "must_not_contain",
        "expected_json_valid", "weight", "source", "notes"]
TURN_RE = re.compile(r"^\s*(user|human|q|assistant|ai|a|bot)\s*:\s*(.*)$", re.I)
USER = {"user", "human", "q"}
TBD_NOTE = "must_contain [TO BE BASELINED — owner: SME]"


def from_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("error: no rows in CSV")
    if "input" not in rows[0]:
        sys.exit("error: CSV needs an `input` column")
    return [r for r in rows if (r.get("input") or "").strip()]


def from_transcript(path: Path) -> list[dict]:
    cases, cur_user, cur_asst, in_user = [], [], [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = TURN_RE.match(line)
        if m:
            role = m.group(1).lower()
            if role in USER:
                if cur_user:
                    cases.append({"input": "\n".join(cur_user).strip(), "expected": "\n".join(cur_asst).strip()})
                cur_user, cur_asst, in_user = [m.group(2)], [], True
            else:
                cur_asst.append(m.group(2))
                in_user = False
        elif in_user is True:
            cur_user.append(line)
        elif in_user is False:
            cur_asst.append(line)
    if cur_user:
        cases.append({"input": "\n".join(cur_user).strip(), "expected": "\n".join(cur_asst).strip()})
    if not cases:
        sys.exit("error: no User:/Assistant: turns found in transcript")
    return cases


def normalize(cases: list[dict], default_category: str, default_source: str) -> list[dict]:
    out = []
    for i, c in enumerate(cases, 1):
        cid = (c.get("id") or "").strip() or f"GS-{i:04d}"
        row = {k: (c.get(k) or "").strip() for k in COLS}
        row["id"] = cid
        row["category"] = row["category"] or default_category
        row["difficulty"] = row["difficulty"] or "medium"
        row["expected_json_valid"] = (row["expected_json_valid"] or "false").lower()
        row["weight"] = row["weight"] or "1"
        row["source"] = row["source"] or default_source
        if not row["must_contain"] and not row["must_not_contain"] and not row["expected_json_valid"] == "true":
            row["notes"] = (row["notes"] + "; " if row["notes"] else "") + TBD_NOTE
        row["_output"] = (c.get("output") or c.get("expected") or "").strip()
        out.append(row)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="cases CSV or transcript .txt/.md")
    ap.add_argument("--out", type=Path, required=True, help="golden-set CSV to write")
    ap.add_argument("--outputs-out", type=Path, help="also write id,output CSV for run_evals.py --outputs")
    ap.add_argument("--category", default="uncategorized", help="default category")
    ap.add_argument("--source", dest="src", default="", help="default source label (log|sme|synthetic)")
    a = ap.parse_args(argv)
    if not a.source.is_file():
        sys.exit(f"error: source not found: {a.source}")
    is_csv = a.source.suffix.lower() == ".csv"
    cases = from_csv(a.source) if is_csv else from_transcript(a.source)
    rows = normalize(cases, a.category, a.src or ("log" if not is_csv else "sme"))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    if a.outputs_out:
        with a.outputs_out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "output"])
            w.writerows([r["id"], r["_output"]] for r in rows if r["_output"])
    tbd = sum(TBD_NOTE in r["notes"] for r in rows)
    print(f"{len(rows)} cases -> {a.out} ({tbd} need must_contain from an SME)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
