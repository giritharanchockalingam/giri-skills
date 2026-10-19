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

Brownfield (--existing golden-set.csv): extend the golden set you already have. Existing rows are kept
verbatim with their ids; new cases whose input (case- and whitespace-insensitive) is already in the set
are skipped as duplicates; new cases get the next free GS-nnnn ids; an explicit new id that collides with
an existing one is an error. If the existing CSV carries an `output` column (e.g. the release candidate's
answers), those outputs go to --outputs-out with the new cases' outputs. --merge-report writes the counts
and the ids added / skipped as JSON.

Usage:
    python3 -I build_golden.py cases.csv --out golden-set.csv [--outputs-out outputs.csv]
    python3 -I build_golden.py new-cases.csv --existing golden-set.csv --out golden-set.csv \
        [--outputs-out outputs.csv] [--merge-report golden-merge.json]
    python3 -I build_golden.py transcript.md --out golden-set.csv --category support

Exit codes: 0 ok; 1 bad input (missing file, no cases, no `input` column). Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
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


def _next_id(taken: set[str], start: int) -> tuple[str, int]:
    i = start
    while f"GS-{i:04d}" in taken:
        i += 1
    return f"GS-{i:04d}", i + 1


def normalize(cases: list[dict], default_category: str, default_source: str,
              taken: set[str] | None = None) -> list[dict]:
    """Golden rows from raw cases. Blank ids: GS-<position> by default; with `taken` (merging into an
    existing set), the next GS-nnnn id not already taken."""
    out = []
    nxt = 1
    for i, c in enumerate(cases, 1):
        cid = (c.get("id") or "").strip()
        if not cid:
            if taken is None:
                cid = f"GS-{i:04d}"
            else:
                cid, nxt = _next_id(taken, nxt)
        if taken is not None:
            taken.add(cid)
        row = {k: (c.get(k) or "").strip() for k in COLS}
        row["id"] = cid
        row["category"] = row["category"] or default_category
        row["difficulty"] = row["difficulty"] or "medium"
        row["expected_json_valid"] = (row["expected_json_valid"] or "false").lower()
        row["weight"] = row["weight"] or "1"
        row["source"] = row["source"] or default_source
        if (not row["must_contain"] and not row["must_not_contain"] and not row["expected_json_valid"] == "true"
                and TBD_NOTE not in row["notes"]):
            row["notes"] = (row["notes"] + "; " if row["notes"] else "") + TBD_NOTE
        row["_output"] = (c.get("output") or c.get("expected") or "").strip()
        out.append(row)
    return out


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def merge(existing: list[dict], new_cases: list[dict], default_category: str, default_source: str) -> tuple[list, dict]:
    """Existing golden rows (kept as-is) + new cases (deduped by input, ids continued)."""
    ids = [(r.get("id") or "").strip() for r in existing]
    if "" in ids:
        sys.exit("error: existing golden set has a row without an id")
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        sys.exit(f"error: existing golden set repeats id(s) {dupes}")
    kept = normalize(existing, default_category, "sme", taken=set())
    for r, orig in zip(kept, existing):  # an existing row's `expected` is never used as its output
        r["_output"] = (orig.get("output") or "").strip()
    seen = {_key(r["input"]): r["id"] for r in kept}
    fresh, skipped = [], []
    for c in new_cases:
        k = _key(c.get("input") or "")
        if k in seen:
            skipped.append({"input": (c.get("input") or "").strip()[:80], "existing_id": seen[k]})
            continue
        cid = (c.get("id") or "").strip()
        if cid and cid in {r["id"] for r in kept}:
            sys.exit(f"error: new case id {cid!r} already exists in the golden set")
        seen[k] = cid or "(new)"
        fresh.append(c)
    added = normalize(fresh, default_category, default_source, taken={r["id"] for r in kept})
    report = {"existing": len(kept), "added": len(added), "duplicates_skipped": len(skipped),
              "total": len(kept) + len(added), "added_ids": [r["id"] for r in added], "skipped": skipped}
    return kept + added, report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="cases CSV or transcript .txt/.md")
    ap.add_argument("--out", type=Path, required=True, help="golden-set CSV to write")
    ap.add_argument("--outputs-out", type=Path, help="also write id,output CSV for run_evals.py --outputs")
    ap.add_argument("--category", default="uncategorized", help="default category")
    ap.add_argument("--source", dest="src", default="", help="default source label (log|sme|synthetic)")
    ap.add_argument("--existing", type=Path, help="golden-set CSV to extend (brownfield); ids are kept")
    ap.add_argument("--merge-report", type=Path, help="with --existing: write merge counts and ids as JSON")
    a = ap.parse_args(argv)
    if not a.source.is_file():
        sys.exit(f"error: source not found: {a.source}")
    is_csv = a.source.suffix.lower() == ".csv"
    cases = from_csv(a.source) if is_csv else from_transcript(a.source)
    default_src = a.src or ("log" if not is_csv else "sme")
    report = None
    if a.existing:
        if not a.existing.is_file():
            sys.exit(f"error: existing golden set not found: {a.existing}")
        rows, report = merge(from_csv(a.existing), cases, a.category, default_src)
    else:
        rows = normalize(cases, a.category, default_src)
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
    if report is not None:
        print(f"merged: {report['existing']} existing kept, {report['added']} added, "
              f"{report['duplicates_skipped']} duplicate(s) skipped")
        if a.merge_report:
            a.merge_report.parent.mkdir(parents=True, exist_ok=True)
            a.merge_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
