#!/usr/bin/env python3
"""Copy an existing repo layout to the run's target before the skill acts on it (evals/demos only).

    python3 -I scripts/seed_repo.py --from evals/fixtures/repo-existing --target <out>/repo

Lets a demo run the brownfield ("existing") path against a copy, so the fixture in the skill folder is
never written to. Every file under --from (dotfiles included) is copied to the same relative path under
--target, and a `.seeded-copy` marker is written. A target this script seeded earlier is wiped and
re-seeded (re-runs into the same out dir); any other non-empty target is refused, so a real repo is
never overwritten. Exit 1 on bad input. Stdlib.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

MARKER = ".seeded-copy"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy an existing repo layout to a fresh target (demos only)")
    ap.add_argument("--from", dest="src", required=True, help="directory to copy (the existing repo layout)")
    ap.add_argument("--target", required=True, help="directory to create")
    a = ap.parse_args()
    src, target = Path(a.src).resolve(), Path(a.target).resolve()
    if not src.is_dir():
        die(f"source layout not found: {src}")
    if target == src or src in target.parents:
        die("target must be outside the source layout")
    if target.exists():
        if not target.is_dir():
            die(f"target is not a directory: {target}")
        if any(target.iterdir()):
            if not (target / MARKER).is_file():
                die(f"target is not empty and was not seeded by this script: {target}")
            shutil.rmtree(target)
    files = sorted(p for p in src.rglob("*") if p.is_file())
    if not files:
        die(f"source layout is empty: {src}")
    target.mkdir(parents=True, exist_ok=True)
    for p in files:
        dest = target / p.relative_to(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, dest)
    (target / MARKER).write_text("copied by seed_repo.py from an example layout — safe to delete\n", encoding="utf-8")
    print(f"seeded {target} with {len(files)} file(s) from {src.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
