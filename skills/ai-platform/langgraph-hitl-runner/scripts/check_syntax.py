#!/usr/bin/env python3
"""Syntax-check a generated Python file without executing or importing it.

Usage: python3 -I check_syntax.py FILE [--require NAME ...]
  --require NAME   a top-level function or class NAME must be defined
Exit 0 when compile()/ast.parse() succeed and every required name exists, 1 otherwise,
2 when FILE is missing. Stdlib only; the file's imports are never resolved.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="compile()/ast.parse() a generated file (never executed)")
    ap.add_argument("file")
    ap.add_argument("--require", action="append", default=[], help="top-level def/class that must exist")
    a = ap.parse_args(argv)
    p = Path(a.file)
    if not p.is_file():
        print(f"missing: {p}", file=sys.stderr)
        return 2
    src = p.read_text(encoding="utf-8")
    try:
        compile(src, str(p), "exec")
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"SyntaxError {p.name}:{e.lineno}: {e.msg}")
        return 1
    defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))}
    missing = [r for r in a.require if r not in defined]
    if missing:
        print(f"{p.name}: missing top-level definitions {missing}")
        return 1
    print(f"{p.name}: syntax OK ({len(defined)} top-level defs); not executed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
