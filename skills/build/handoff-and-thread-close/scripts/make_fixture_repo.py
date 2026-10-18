#!/usr/bin/env python3
"""Build a throwaway git repo from a layout of commit folders (evals/demos only).

    python3 -I scripts/make_fixture_repo.py --from evals/fixtures/repo-files --target <dir>

`--from` holds numbered folders (`01-init/`, `02-feature/`, …), each a file tree that is copied over
the target and committed; the subject comes from a `COMMIT_MSG` file in the folder (not copied) or
the folder name. A folder named `uncommitted/` is copied last without committing, to simulate work
in progress. A target this script built earlier is wiped and rebuilt; any other git repo is refused. Exit 1 on bad input. Stdlib.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

MARKER = ".fixture-repo"
GIT_ID = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.com", "-c", "commit.gpgsign=false"]


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def git(target: Path, *args: str) -> str:
    r = subprocess.run(["git", *GIT_ID, *args], cwd=str(target), capture_output=True, text=True)
    if r.returncode != 0:
        die(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def copy_tree(src: Path, dst: Path) -> None:
    for p in sorted(src.rglob("*")):
        if p.name == "COMMIT_MSG" or not p.is_file():
            continue
        rel = p.relative_to(src)
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, dst / rel)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a tiny git repo from commit folders")
    ap.add_argument("--from", dest="src", required=True, help="directory of commit folders")
    ap.add_argument("--target", required=True, help="repo directory to create")
    a = ap.parse_args()
    src, target = Path(a.src), Path(a.target)
    if not src.is_dir():
        die(f"source layout not found: {src}")
    folders = sorted(p for p in src.iterdir() if p.is_dir() and p.name != "uncommitted")
    if not folders:
        die(f"no commit folders under {src}")
    if (target / ".git").exists():
        if not (target / MARKER).exists():
            die(f"target already is a git repo (not one this script built): {target}")
        shutil.rmtree(target)  # rebuild a repo this script made earlier (re-runs into the same out dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / MARKER).write_text("built by make_fixture_repo.py — safe to delete\n", encoding="utf-8")
    git(target, "init", "-q", "-b", "main")
    for f in folders:
        copy_tree(f, target)
        msg_file = f / "COMMIT_MSG"
        subject = msg_file.read_text(encoding="utf-8").strip() if msg_file.is_file() else f.name.split("-", 1)[-1]
        git(target, "add", "-A")
        git(target, "commit", "-q", "-m", subject)
        print(f"committed: {subject}")
    unc = src / "uncommitted"
    if unc.is_dir():
        copy_tree(unc, target)
        print("copied uncommitted changes")
    print(f"fixture repo at {target}: {len(folders)} commit(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
