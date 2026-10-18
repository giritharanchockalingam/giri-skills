#!/usr/bin/env python3
"""Check a cleaned eval JSONL: every line a JSON object, required keys non-empty, ids unique.

Usage: python3 -I check_jsonl.py FILE [--require KEY ...]
Exit 0 when valid, 1 on any violation, 2 when FILE is missing. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a JSONL eval file")
    ap.add_argument("file")
    ap.add_argument("--require", action="append", default=[], help="key that must be non-empty on every line")
    a = ap.parse_args(argv)
    p = Path(a.file)
    if not p.is_file():
        print(f"missing: {p}", file=sys.stderr)
        return 2
    bad: list[str] = []
    ids: set[str] = set()
    n = 0
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        n += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            bad.append(f"line {i}: not JSON ({e.msg})")
            continue
        if not isinstance(obj, dict):
            bad.append(f"line {i}: not an object")
            continue
        for k in a.require:
            if obj.get(k) in (None, "", []):
                bad.append(f"line {i}: '{k}' empty")
        rid = str(obj.get("id", ""))
        if rid and rid in ids:
            bad.append(f"line {i}: duplicate id {rid}")
        ids.add(rid)
    if n == 0:
        bad.append("no records")
    if bad:
        print(f"{p.name}: {len(bad)} problem(s): {bad[:5]}")
        return 1
    print(f"{p.name}: {n} records valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
