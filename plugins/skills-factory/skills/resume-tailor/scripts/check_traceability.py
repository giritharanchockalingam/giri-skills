#!/usr/bin/env python3
"""Prove every bullet of a tailored résumé traces to the master résumé — the TRUTH LOCK gate.

    python3 -I scripts/check_traceability.py --resume tailored-resume.md --master master-resume.md \
        --out traceability.csv

Units checked ("bullets"): every list item (`- `, `* `, `1. `) anywhere in the résumé, plus every prose
line under the `## Summary` heading. Headings, tables, blockquotes, HTML comments and blank lines are
not checked (role headers `### Employer — Title (dates)` are copied from the master's own headers).

For each bullet, traceability.csv records: bullet (first 80 chars), cited_ids, all_ids_exist (yes/no),
numbers_in_bullet_found_in_cited_lines (yes/no). Exit 1 — and the run halts — when any bullet
  * carries no `[MR-Lnn]` citation,
  * cites an id that is not a line of the master résumé, or
  * contains a number, percentage or dollar figure that none of its cited lines contains.
A file carrying `<!-- dry-run: template unfilled -->` (the runner's dry provider) has no bullets to
check: the CSV is written with its header only and the gate passes with evidence "dry-run template".
Exit 1 on a missing file or a master without MR-L ids. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

DRY_MARKER = "<!-- dry-run: template unfilled -->"
MR_LINE_RE = re.compile(r"^\s*(MR-L\d+)\s*\|\s*(.*)$")
CITE_RE = re.compile(r"\[(MR-L\d+(?:\s*,\s*MR-L\d+)*)\]")
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")
# a number not glued to a letter or slash on the left (so S/4HANA's 4 is not a number) — $, %, M/K suffixes allowed
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9/.])\$?(\d[\d,]*(?:\.\d+)?)")
FIELDS = ["bullet", "cited_ids", "all_ids_exist", "numbers_in_bullet_found_in_cited_lines"]


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


def load_master(path: str) -> dict[str, str]:
    lines = {}
    for raw in read(path).splitlines():
        m = MR_LINE_RE.match(raw)
        if m:
            lines[m.group(1)] = m.group(2)
    if not lines:
        die("master résumé has no `MR-Lnn | text` lines (see assets/master-resume.example.md)")
    return lines


def numbers(text: str) -> list[str]:
    return [n.replace(",", "") for n in NUMBER_RE.findall(text)]


def units(resume: str) -> list[str]:
    """Bullets anywhere + prose lines under '## Summary'."""
    out, in_summary = [], False
    for raw in resume.splitlines():
        line = raw.rstrip()
        if line.startswith("#"):
            in_summary = line.lstrip("#").strip().lower().startswith("summary")
            continue
        s = line.strip()
        if not s or s.startswith(("<!--", "|", ">", "_", "```")):
            continue
        m = BULLET_RE.match(line)
        if m:
            out.append(m.group(1).strip())
        elif in_summary:
            out.append(s)
    return out


def check(resume: str, master: dict[str, str]) -> tuple[list[dict], list[str]]:
    rows, problems = [], []
    for u in units(resume):
        ids = []
        for m in CITE_RE.finditer(u):
            ids += [i.strip() for i in m.group(1).split(",")]
        text = CITE_RE.sub("", u).strip()
        label = text[:80]
        if not ids:
            rows.append({"bullet": label, "cited_ids": "", "all_ids_exist": "no",
                         "numbers_in_bullet_found_in_cited_lines": "no"})
            problems.append(f"no citation: {label}")
            continue
        missing = [i for i in ids if i not in master]
        cited_text = " ".join(master.get(i, "") for i in ids)
        cited_nums = set(numbers(cited_text))
        untraced = sorted({n for n in numbers(text) if n not in cited_nums})
        rows.append({"bullet": label, "cited_ids": ";".join(ids), "all_ids_exist": "no" if missing else "yes",
                     "numbers_in_bullet_found_in_cited_lines": "no" if untraced else "yes"})
        if missing:
            problems.append(f"unknown id(s) {missing}: {label}")
        if untraced:
            problems.append(f"number(s) {untraced} not in cited lines {ids}: {label}")
    return rows, problems


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="TRUTH LOCK gate: every résumé bullet cites existing MR-L lines "
                                             "and introduces no number they do not contain")
    ap.add_argument("--resume", required=True, help="tailored résumé (Markdown)")
    ap.add_argument("--master", required=True, help="master résumé with MR-Lnn | line ids")
    ap.add_argument("--out", required=True, help="traceability.csv")
    a = ap.parse_args()
    resume = read(a.resume)
    master = load_master(a.master)
    out = Path(a.out)
    if DRY_MARKER in resume:
        write_csv([], out)
        print(f"0 bullets checked (dry-run template); wrote {out}")
        return 0
    rows, problems = check(resume, master)
    write_csv(rows, out)
    if not rows:
        print("TRUTH LOCK: the résumé has no bullets or summary lines to check", file=sys.stderr)
        return 1
    n_ok = sum(1 for r in rows if r["all_ids_exist"] == "yes" and r["numbers_in_bullet_found_in_cited_lines"] == "yes")
    if problems:
        for pr in problems:
            print(f"TRUTH LOCK: {pr}", file=sys.stderr)
        print(f"{len(rows)} bullets checked, {len(rows) - n_ok} fail the truth lock; wrote {out}", file=sys.stderr)
        return 1
    print(f"{len(rows)} bullets checked, all trace to the master résumé; wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
