#!/usr/bin/env python3
"""Write HANDOFF.md from git facts, not memory.

    python3 -I scripts/handoff.py --target <repo> --state "green — invoices export shipped" \
        [--since <ref|YYYY-MM-DD>] [--project <name>] [--template assets/HANDOFF.md] \
        --out HANDOFF.md [--write-to-repo]

Range: --since <ref> (`<ref>..HEAD`) or --since <date>; otherwise commits after the last commit that
touched docs/HANDOFF.md in the target; otherwise the whole history. Fills the template:
  State                    --state verbatim
  Done this thread         commit subjects in the range (+ "uncommitted changes present" if any)
  Changed files            `git diff --name-status` over the range, each with the subject of the
                           last commit that touched it; uncommitted files from `git status`
  Open items               bullets carried from the previous docs/HANDOFF.md "Open items" section
  Decisions                left for the author (TBD marker)
  Next thread starts with  prompt skeleton naming the files to read; first action is a TBD marker
Keeps the file <= 80 lines (older history lives in git). --write-to-repo also copies the result to
<target>/docs/HANDOFF.md. Exit 1 when the target is not a git repository root or git fails. Stdlib, offline.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "assets" / "HANDOFF.md"
TBD = "[TO BE BASELINED — owner: ___]"
MAX_LINES = 80
STATUS_WORD = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed", "C": "copied", "T": "type changed"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def git(target: Path, *args: str, ok_codes=(0,)) -> str:
    r = subprocess.run(["git", *args], cwd=str(target), capture_output=True, text=True)
    if r.returncode not in ok_codes:
        die(f"git {' '.join(args)}: {r.stderr.strip() or 'failed'}")
    return r.stdout


def previous_handoff_commit(target: Path, rel: str) -> str:
    out = git(target, "log", "-1", "--format=%H", "--", rel).strip()
    return out


def section_bullets(text: str, heading: str) -> list[str]:
    lines, out, inside = text.splitlines(), [], False
    for ln in lines:
        if ln.startswith("#"):
            if inside:
                break
            inside = heading.lower() in ln.lower()
            continue
        if inside and ln.strip().startswith("- ") and ln.strip() not in ("- …", "- ..."):
            out.append(ln.strip())
    return out


def replace_section(md: str, heading_startswith: str, body_lines: list[str]) -> str:
    """Replace the body of the first `## <heading…>` section with body_lines (heading kept)."""
    lines, out, i = md.splitlines(), [], 0
    while i < len(lines):
        ln = lines[i]
        out.append(ln)
        i += 1
        if ln.startswith("## ") and ln[3:].lower().startswith(heading_startswith.lower()):
            out += body_lines
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            if i < len(lines):
                out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate HANDOFF.md from git history")
    ap.add_argument("--target", required=True, help="git repo")
    ap.add_argument("--state", required=True, help='one honest line, e.g. "green — export shipped, e2e pending"')
    ap.add_argument("--since", default="", help="ref or YYYY-MM-DD; default: last commit touching docs/HANDOFF.md")
    ap.add_argument("--project", default="", help="project name (default: repo dir name)")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--handoff-path", default="docs/HANDOFF.md", help="where the previous handoff lives in the repo")
    ap.add_argument("--out", default="HANDOFF.md")
    ap.add_argument("--write-to-repo", action="store_true", help="also copy the result to <target>/<handoff-path>")
    a = ap.parse_args()
    target = Path(a.target)
    if not target.is_dir():
        die(f"target is not a directory: {target}")
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(target), capture_output=True, text=True)
    if top.returncode != 0:
        die(f"not a git repository: {target}")
    if Path(top.stdout.strip()).resolve() != target.resolve():
        die(f"{target} is not a repository root (git root is {top.stdout.strip()}); pass the root directory")
    tmpl_path = Path(a.template)
    if not tmpl_path.is_file():
        die(f"template not found: {tmpl_path}")
    head = git(target, "rev-parse", "--verify", "-q", "HEAD", ok_codes=(0, 1)).strip()
    if not head:
        die("repository has no commits")

    # ---- range
    prev_text = ""
    prev_file = target / a.handoff_path
    if prev_file.is_file():
        prev_text = prev_file.read_text(encoding="utf-8", errors="replace")
    if a.since:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.since):
            log_args, diff_base, basis = [f"--since={a.since}"], "", f"since {a.since}"
            first = git(target, "log", "--reverse", "--format=%H", f"--since={a.since}").split()
            diff_base = f"{first[0]}~1" if first else ""
        else:
            git(target, "rev-parse", "--verify", "-q", a.since + "^{commit}")
            log_args, diff_base, basis = [f"{a.since}..HEAD"], a.since, f"since {a.since}"
    else:
        base = previous_handoff_commit(target, a.handoff_path)
        if base and base != head:
            log_args, diff_base, basis = [f"{base}..HEAD"], base, f"since last HANDOFF commit {base[:7]}"
        elif base == head:
            log_args, diff_base, basis = [f"{base}..HEAD"], base, f"since last HANDOFF commit {base[:7]} (no new commits)"
        else:
            log_args, diff_base, basis = ["HEAD"], "", "whole history (no previous HANDOFF commit)"

    commits = []
    for ln in git(target, "log", "--format=%h%x1f%s", *log_args).splitlines():
        h, _, s = ln.partition("\x1f")
        commits.append((h, s))

    # ---- changed files with why
    why: dict[str, str] = {}
    for h, s in reversed(commits):  # oldest first so the latest subject wins
        for f in git(target, "show", "--name-only", "--format=", h).split():
            why[f] = s
    changed = []
    if diff_base:
        root = git(target, "rev-parse", "--verify", "-q", diff_base + "^{commit}", ok_codes=(0, 1)).strip()
        name_status = git(target, "diff", "--name-status", root, "HEAD") if root else ""
    else:
        name_status = git(target, "show", "--name-status", "--format=", *[h for h, _ in commits]) if commits else ""
    seen = set()
    for ln in name_status.splitlines():
        parts = ln.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0][0], parts[-1]
        if path in seen:
            continue
        seen.add(path)
        changed.append(f"- `{path}` — {STATUS_WORD.get(status, status)}: {why.get(path, TBD)}")
    uncommitted = [ln[3:].strip() for ln in git(target, "status", "--porcelain").splitlines() if ln.strip()]
    for path in uncommitted:
        if path not in seen:
            changed.append(f"- `{path}` — uncommitted: {TBD}")

    done = [f"- {s} (`{h}`)" for h, s in commits] or [f"- no commits {basis}"]
    if uncommitted:
        done.append(f"- uncommitted changes present ({len(uncommitted)} file(s)) — commit or stash before closing")
    open_items = section_bullets(prev_text, "Open items") or [f"- none carried (no previous {a.handoff_path} open items)"]
    open_items.append(f"- {TBD} new open items from this thread")

    project = a.project or target.resolve().name
    today = dt.date.today().isoformat()
    md = tmpl_path.read_text(encoding="utf-8")
    md = md.replace("{{PROJECT}}", project).replace("{{DATE}}", today)
    md = re.sub(r"^## State:.*$", f"## State: {a.state}", md, count=1, flags=re.M)
    md = replace_section(md, "Done this thread", done)
    md = replace_section(md, "Changed files", changed or ["- none in range"])
    md = replace_section(md, "Open items", open_items)
    md = replace_section(md, "Decisions", [f"- {TBD} (link ADRs if any)"])
    md = replace_section(md, "Tried and rejected", ["- none recorded"])
    files_to_read = ["docs/HANDOFF.md"] + [f for f in ("CLAUDE.md", "docs/SPEC.md") if (target / f).exists()]
    md = replace_section(md, "Next thread starts with", [
        "```", f"Read {', '.join(files_to_read)}.",
        f"Use <skill>. {TBD} first action. Gate: plan→approve before any code.", "```"])
    md = md.replace("- …\n", "")
    lines = md.rstrip("\n").splitlines()
    if len(lines) > MAX_LINES:
        # trim the changed-files list first; older history lives in git
        keep = []
        in_changed, n = False, 0
        for ln in lines:
            if ln.startswith("## "):
                in_changed = ln.startswith("## Changed files")
                n = 0
            if in_changed and ln.startswith("- "):
                n += 1
                if n > 25:
                    if n == 26:
                        keep.append(f"- … {len(changed) - 25} more — see `git diff --name-status {diff_base or 'HEAD'}`")
                    continue
            keep.append(ln)
        lines = keep
    out_text = "\n".join(lines) + "\n"
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_text, encoding="utf-8")
    if a.write_to_repo:
        prev_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(out, prev_file)
    print(f"HANDOFF: {len(commits)} commit(s) {basis}, {len(changed)} changed file(s), "
          f"{len(open_items) - 1} open item(s) carried, {len(lines)} lines -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
