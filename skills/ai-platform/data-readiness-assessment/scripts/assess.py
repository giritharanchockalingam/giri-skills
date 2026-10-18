#!/usr/bin/env python3
"""Data readiness assessment: profile a sample CSV and score it against owner-set requirements.

Every threshold comes from the requirements CSV (key,value[,source,notes]). Nothing is
defaulted: a dimension whose threshold is absent is reported
`[TO BE BASELINED — owner: Data owner]`, never passed.

Usage:
  python3 -I assess.py --data sample.csv --requirements requirements.csv \
      [--as-of 2026-10-01] --out-dir OUT

Requirement keys (all optional; each one switches its dimension from TBD to scored):
  min_rows            integer   volume:       rows >= min_rows
  max_null_pct        number    completeness: every column's null % <= max_null_pct
  required_columns    a;b;c     schema:       every listed column present
  unique_key          a[;b]     uniqueness:   no duplicate and no null key values
  max_duplicate_rows  integer   duplicates:   fully duplicated rows <= max_duplicate_rows
  date_column         name      freshness:    newest date in date_column is at most
  max_age_days        number                  max_age_days before --as-of (all three needed)

Verdict: any fail -> "Not ready"; else any TBD -> "Ready-with-gaps"; else "Ready".
Outputs: OUT/readiness.json (profile + dimension results), OUT/readiness.md
  (Verdict, Dimensions, Column profile, Gaps and owners).
Exit codes: 0 Ready / Ready-with-gaps · 1 Not ready · 2 missing or invalid input.
Nulls: empty cells and the tokens NA, N/A, NULL, None, NaN, nil (case-insensitive).
Type inference: the narrowest of integer < float < boolean < date < datetime < string that
every non-null value satisfies; dates are ISO 8601 (YYYY-MM-DD[THH:MM[:SS]]).
Stdlib only; reads only the given files; writes only into --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

NULL_TOKENS = {"", "na", "n/a", "null", "none", "nan", "nil"}
KNOWN_KEYS = {"min_rows", "max_null_pct", "required_columns", "unique_key", "max_duplicate_rows",
              "date_column", "max_age_days"}
TBD_OWNER = "Data owner"
FAIL_OWNER = {"volume": "Data owner", "completeness": "Data steward", "schema": "Data engineer",
              "uniqueness": "Data steward", "duplicates": "Data steward", "freshness": "Data engineer"}
INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
BOOL_TOKENS = {"true", "false", "yes", "no", "y", "n", "t", "f"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")


class InputError(Exception):
    """A required input is missing or malformed (exit 2)."""


# ------------------------------------------------------------------ loading

def is_null(v: str | None) -> bool:
    return v is None or v.strip().lower() in NULL_TOKENS


def load_dataset(path: Path) -> tuple[list[str], list[list[str]]]:
    if not path.is_file():
        raise InputError(f"dataset not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows or not any(c.strip() for c in rows[0]):
        raise InputError(f"dataset has no header row: {path.name}")
    header = [c.strip() for c in rows[0]]
    if len(set(header)) != len(header):
        dupes = sorted({h for h in header if header.count(h) > 1})
        raise InputError(f"dataset header repeats column names: {dupes}")
    body = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue  # blank line
        r = (r + [""] * len(header))[: len(header)]
        body.append(r)
    return header, body


def load_requirements(path: Path) -> tuple[dict, list[str]]:
    """Return (typed requirements, notes). Unknown keys are reported, not used."""
    if not path.is_file():
        raise InputError(f"requirements file not found: {path}")
    reqs: dict = {}
    notes: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "key" not in reader.fieldnames or "value" not in reader.fieldnames:
            raise InputError("requirements CSV needs a header with columns key,value")
        for row in reader:
            k = (row.get("key") or "").strip()
            v = (row.get("value") or "").strip()
            if not k or k.startswith("#"):
                continue
            if k not in KNOWN_KEYS:
                notes.append(f"Ignored unknown requirement key '{k}'.")
                continue
            if v == "":
                continue  # blank value = not set by the owner -> dimension stays TBD
            try:
                if k in ("min_rows", "max_duplicate_rows"):
                    if not INT_RE.match(v) or int(v) < 0:
                        raise ValueError
                    reqs[k] = int(v)
                elif k in ("max_null_pct", "max_age_days"):
                    n = float(v)
                    if n < 0 or (k == "max_null_pct" and n > 100):
                        raise ValueError
                    reqs[k] = n
                elif k in ("required_columns", "unique_key"):
                    cols = [c.strip() for c in v.split(";") if c.strip()]
                    if not cols:
                        raise ValueError
                    reqs[k] = cols
                else:
                    reqs[k] = v
            except ValueError:
                raise InputError(f"invalid value for requirement '{k}': {v!r}") from None
    return reqs, notes


def parse_as_of(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        raise InputError(f"--as-of must be an ISO date (YYYY-MM-DD), got {s!r}") from None


def parse_date(v: str) -> date | None:
    v = v.strip()
    if DATE_RE.match(v):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    if DATETIME_RE.match(v):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00").replace(" ", "T", 1)).date()
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------ profiling

def infer_type(values: list[str]) -> str:
    if not values:
        return "empty"
    vs = [v.strip() for v in values]
    if all(INT_RE.match(v) for v in vs):
        return "integer"
    if all(FLOAT_RE.match(v) for v in vs):
        return "float"
    if all(v.lower() in BOOL_TOKENS for v in vs):
        return "boolean"
    if all(DATE_RE.match(v) and parse_date(v) for v in vs):
        return "date"
    if all((DATE_RE.match(v) or DATETIME_RE.match(v)) and parse_date(v) for v in vs):
        return "datetime"
    return "string"


def profile(header: list[str], body: list[list[str]]) -> dict:
    n = len(body)
    cols = []
    for i, name in enumerate(header):
        raw = [r[i] for r in body]
        non_null = [v for v in raw if not is_null(v)]
        nulls = n - len(non_null)
        cols.append({
            "column": name,
            "inferred_type": infer_type(non_null),
            "nulls": nulls,
            "null_pct": round(nulls / n * 100, 2) if n else 0.0,
            "distinct": len({v.strip() for v in non_null}),
        })
    distinct_rows = len({tuple(c.strip() for c in r) for r in body})
    return {"rows": n, "columns": len(header), "duplicate_rows": n - distinct_rows, "column_profile": cols}


# ------------------------------------------------------------------ dimensions

def _tbd(dim: str, missing: list[str], why: str = "") -> dict:
    keys = ", ".join(missing)
    return {"dimension": dim, "status": "TBD", "threshold": None, "observed": None,
            "detail": why or f"No threshold supplied ({keys}).",
            "owner": TBD_OWNER, "marker": f"[TO BE BASELINED — owner: {TBD_OWNER}]", "missing_keys": missing}


def _scored(dim: str, ok: bool, threshold, observed, detail: str) -> dict:
    return {"dimension": dim, "status": "pass" if ok else "fail", "threshold": threshold, "observed": observed,
            "detail": detail, "owner": None if ok else FAIL_OWNER[dim], "marker": None, "missing_keys": []}


def score(header, body, prof: dict, reqs: dict, as_of: date | None) -> list[dict]:
    n = prof["rows"]
    idx = {h: i for i, h in enumerate(header)}
    dims = []

    # volume
    if "min_rows" in reqs:
        dims.append(_scored("volume", n >= reqs["min_rows"], reqs["min_rows"], n,
                            f"{n} rows vs minimum {reqs['min_rows']}."))
    else:
        dims.append(_tbd("volume", ["min_rows"]))

    # completeness
    if "max_null_pct" in reqs:
        lim = reqs["max_null_pct"]
        over = [c for c in prof["column_profile"] if c["null_pct"] > lim]
        worst = max((c["null_pct"] for c in prof["column_profile"]), default=0.0)
        detail = ("All columns within limit." if not over else
                  "Over limit: " + ", ".join(f"{c['column']} ({c['null_pct']}%)" for c in over) + ".")
        d = _scored("completeness", not over, lim, worst, detail)
        d["columns_over"] = [c["column"] for c in over]
        dims.append(d)
    else:
        dims.append(_tbd("completeness", ["max_null_pct"]))

    # schema
    if "required_columns" in reqs:
        missing = [c for c in reqs["required_columns"] if c not in idx]
        d = _scored("schema", not missing, len(reqs["required_columns"]),
                    len(reqs["required_columns"]) - len(missing),
                    "All required columns present." if not missing else "Missing: " + ", ".join(missing) + ".")
        d["missing_columns"] = missing
        dims.append(d)
    else:
        dims.append(_tbd("schema", ["required_columns"]))

    # uniqueness
    if "unique_key" in reqs:
        key = reqs["unique_key"]
        absent = [c for c in key if c not in idx]
        if absent:
            d = _scored("uniqueness", False, 0, None, "Key column(s) not in dataset: " + ", ".join(absent) + ".")
        else:
            null_key = 0
            seen: dict[tuple, int] = {}
            for r in body:
                t = tuple(r[idx[c]].strip() for c in key)
                if any(is_null(v) for v in t):
                    null_key += 1
                    continue
                seen[t] = seen.get(t, 0) + 1
            dup = sum(v - 1 for v in seen.values())
            d = _scored("uniqueness", dup == 0 and null_key == 0, 0, dup,
                        f"{dup} duplicate key rows, {null_key} rows with a null key on ({'; '.join(key)}).")
            d["null_key_rows"] = null_key
        dims.append(d)
    else:
        dims.append(_tbd("uniqueness", ["unique_key"]))

    # duplicates
    if "max_duplicate_rows" in reqs:
        dims.append(_scored("duplicates", prof["duplicate_rows"] <= reqs["max_duplicate_rows"],
                            reqs["max_duplicate_rows"], prof["duplicate_rows"],
                            f"Fully duplicated rows: {prof['duplicate_rows']}."))
    else:
        dims.append(_tbd("duplicates", ["max_duplicate_rows"]))

    # freshness
    need = [k for k in ("date_column", "max_age_days") if k not in reqs]
    if need:
        dims.append(_tbd("freshness", need))
    elif as_of is None:
        dims.append(_tbd("freshness", ["as_of"], "No as_of date supplied; age cannot be computed without one."))
    else:
        col = reqs["date_column"]
        if col not in idx:
            dims.append(_scored("freshness", False, reqs["max_age_days"], None,
                                f"date_column '{col}' not in dataset."))
        else:
            vals = [r[idx[col]] for r in body if not is_null(r[idx[col]])]
            parsed = [d for d in (parse_date(v) for v in vals) if d]
            unparsed = len(vals) - len(parsed)
            if not parsed:
                d = _scored("freshness", False, reqs["max_age_days"], None,
                            f"No ISO dates parseable in '{col}'.")
            else:
                newest = max(parsed)
                age = (as_of - newest).days
                future = sum(1 for p in parsed if p > as_of)
                d = _scored("freshness", age <= reqs["max_age_days"], reqs["max_age_days"], age,
                            f"Newest {col} = {newest.isoformat()}, {age} days before as_of {as_of.isoformat()}.")
                d["newest_date"] = newest.isoformat()
                d["future_dated_rows"] = future
            d["unparseable_dates"] = unparsed
            dims.append(d)
    return dims


def verdict(dims: list[dict]) -> str:
    if any(d["status"] == "fail" for d in dims):
        return "Not ready"
    if any(d["status"] == "TBD" for d in dims):
        return "Ready-with-gaps"
    return "Ready"


# ------------------------------------------------------------------ rendering

def _cell(v) -> str:
    return "—" if v is None else str(v)


def render_md(res: dict) -> str:
    p = res["profile"]
    counts = res["summary"]
    lines = [
        "# Data readiness assessment",
        "",
        f"Dataset: `{res['source']['dataset']}` · requirements: `{res['source']['requirements']}` · "
        f"as_of: {res['source']['as_of'] or '[not supplied]'}",
        "",
        "## Verdict",
        "",
        f"**{res['verdict']}** — {counts['pass']} pass, {counts['fail']} fail, {counts['TBD']} TBD "
        f"of {counts['dimensions']} dimensions. {p['rows']} rows × {p['columns']} columns profiled.",
        "",
        "## Dimensions",
        "",
        "| Dimension | Status | Threshold | Observed | Detail |",
        "|---|---|---|---|---|",
    ]
    for d in res["dimensions"]:
        status = d["marker"] if d["status"] == "TBD" else d["status"]
        lines.append(f"| {d['dimension']} | {status} | {_cell(d['threshold'])} | {_cell(d['observed'])} | {d['detail']} |")
    lines += ["", "## Column profile", "",
              f"Duplicate rows: {p['duplicate_rows']}.", "",
              "| Column | Inferred type | Nulls | Null % | Distinct |", "|---|---|---|---|---|"]
    for c in p["column_profile"]:
        lines.append(f"| {c['column']} | {c['inferred_type']} | {c['nulls']} | {c['null_pct']} | {c['distinct']} |")
    lines += ["", "## Gaps and owners", ""]
    gaps = [d for d in res["dimensions"] if d["status"] != "pass"]
    if not gaps:
        lines.append("No gaps: every dimension passed its owner-set threshold.")
    else:
        lines += ["| Dimension | Gap | Owner | Action |", "|---|---|---|---|"]
        for d in gaps:
            if d["status"] == "TBD":
                lines.append(f"| {d['dimension']} | {d['marker']} | {d['owner']} | "
                             f"Set {', '.join(d['missing_keys'])} in the requirements file and re-run. |")
            else:
                lines.append(f"| {d['dimension']} | {d['detail']} | {d['owner']} | "
                             f"Remediate at source or agree a waiver, then re-run. |")
    if res["notes"]:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in res["notes"]]
    lines += ["", "_Thresholds are the owner's requirements file; this assessment invents none. "
              "Nulls = empty or NA/N/A/NULL/None/NaN/nil._", ""]
    return "\n".join(lines)


def assess(data: Path, requirements: Path, as_of_s: str | None) -> dict:
    header, body = load_dataset(data)
    reqs, notes = load_requirements(requirements)
    as_of = parse_as_of(as_of_s)
    prof = profile(header, body)
    dims = score(header, body, prof, reqs, as_of)
    counts = {s: sum(1 for d in dims if d["status"] == s) for s in ("pass", "fail", "TBD")}
    counts["dimensions"] = len(dims)
    return {
        "source": {"dataset": data.name, "requirements": requirements.name,
                   "as_of": as_of.isoformat() if as_of else None},
        "requirements": reqs,
        "verdict": verdict(dims),
        "summary": counts,
        "dimensions": dims,
        "profile": prof,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="sample dataset CSV with a header row")
    ap.add_argument("--requirements", type=Path, required=True, help="owner requirements CSV (key,value)")
    ap.add_argument("--as-of", help="ISO date the freshness age is measured from")
    ap.add_argument("--out-dir", type=Path, required=True, help="directory for readiness.json and readiness.md")
    args = ap.parse_args(argv)
    try:
        res = assess(args.data, args.requirements, args.as_of)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "readiness.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out_dir / "readiness.md").write_text(render_md(res), encoding="utf-8")
    print(f"verdict: {res['verdict']} ({res['summary']['pass']} pass, {res['summary']['fail']} fail, "
          f"{res['summary']['TBD']} TBD)")
    return 1 if res["verdict"] == "Not ready" else 0


if __name__ == "__main__":
    sys.exit(main())
