#!/usr/bin/env python3
"""Fail when a Next.js repo holds the same route or module in two source extensions (e.g. route.js + route.ts).

    python3 -I scripts/check_siblings.py <repo>

Walks the repo (node_modules/.next/build output skipped) and reports every stem that exists with more
than one of .ts/.tsx/.js/.jsx/.mjs/.cjs — a Next.js route conflict, or an ambiguous `@/lib/x` import.
Exit 0 when none, 1 when any (each printed), 2 on bad input. Stdlib; used by the eval checks after install.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
SKIP_DIRS = {"node_modules", ".next", ".git", "dist", "build", "out", "coverage", ".vercel"}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_siblings.py <repo>", file=sys.stderr)
        return 2
    repo = Path(sys.argv[1])
    if not repo.is_dir():
        print(f"error: not a directory: {repo}", file=sys.stderr)
        return 2
    stems: dict[str, list[str]] = defaultdict(list)
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if p.is_file() and p.suffix in EXT and not any(part in SKIP_DIRS for part in rel.parts):
            stems[rel.with_suffix("").as_posix()].append(rel.as_posix())
    pairs = {k: v for k, v in stems.items() if len(v) > 1}
    for k, v in pairs.items():
        print(f"sibling conflict: {k} -> {', '.join(v)}")
    print(f"{len(pairs)} sibling conflict(s) in {repo}")
    return 1 if pairs else 0


if __name__ == "__main__":
    sys.exit(main())
