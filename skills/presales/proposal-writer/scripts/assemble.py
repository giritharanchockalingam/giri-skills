#!/usr/bin/env python3
"""Assemble a proposal draft from the section library, win themes and upstream files.

    python3 -I scripts/assemble.py win-themes.json --library assets/section-library.md \
        [--discovery discovery-pack.md] [--estimate estimate-memo.md] [--value-case value-case.md] \
        --out proposal.md --placeholders placeholders.csv --sources sources.md

win-themes.json: {"client": "...", "initiative": "...", "themes": [{"theme", "proof", "so_what"}, ...]}

What it does, deterministically:
  * walks the section library in order (section 13, the internal checklist, is not shipped);
  * threads the win themes into the executive summary (T1..Tn) and the why-us table;
  * quotes the "Bottom line" of the estimate memo (pricing basis) and the value case (objectives),
    and the pain matrix rows of the discovery pack (understanding of needs) when supplied;
  * replaces every unfilled <placeholder> with `[TO BE BASELINED — owner: ___]` and records it in
    placeholders.csv (placeholder, section, owner) so nothing silent remains;
  * writes sources.md = the concatenation of every supplied input, the trace target for numbers.
Nothing is invented: no number, date, role or reference appears that is not in an input file.
Exit 1 on a missing/invalid win-themes file or a library without sections. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: ___]"
PLACEHOLDER_RE = re.compile(r"<([^<>\n`]{1,120})>")
SECTION_RE = re.compile(r"^## (\d+)\. (.+)$")
SKIP_SECTIONS = {"13"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


def load_themes(path: str) -> dict:
    try:
        data = json.loads(read(path))
    except json.JSONDecodeError as e:
        die(f"win-themes is not valid JSON: {e}")
    if not isinstance(data, dict) or not data.get("client") or not data.get("initiative"):
        die("win-themes.json needs 'client' and 'initiative'")
    themes = data.get("themes") or []
    if not isinstance(themes, list) or not themes:
        die("win-themes.json needs a non-empty 'themes' list")
    for i, t in enumerate(themes, 1):
        if not isinstance(t, dict) or not t.get("theme"):
            die(f"theme {i} lacks 'theme'")
        t.setdefault("proof", "")
        t.setdefault("so_what", "")
    return data


def split_library(text: str) -> list[tuple[str, str, list[str]]]:
    """[(number, title, body_lines)] in library order; guidance lines (> ...) dropped."""
    sections, cur = [], None
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m:
            cur = (m.group(1), m.group(2).strip(), [])
            sections.append(cur)
            continue
        if cur is None or line.startswith("> ") or line.strip() == "---":
            continue
        cur[2].append(line)
    if not sections:
        die("section library has no '## N. Title' sections")
    return sections


def section_of(md: str, heading: str) -> list[str]:
    """Lines under the first heading containing `heading` (case-insensitive), up to the next heading of same or higher level."""
    lines = md.splitlines()
    out, level = [], None
    for ln in lines:
        if ln.startswith("#"):
            lvl = len(ln) - len(ln.lstrip("#"))
            if level is None:
                if heading.lower() in ln.lower():
                    level = lvl
                continue
            if lvl <= level:
                break
        elif level is not None:
            out.append(ln)
    return [ln for ln in out if ln.strip()]


def table_rows(lines: list[str]) -> list[str]:
    return [ln for ln in lines if ln.startswith("|") and not set(ln.replace("|", "").strip()) <= set("-: ")]


def thread_exec_summary(body: list[str], themes: list[dict]) -> list[str]:
    out, done = [], False
    for ln in body:
        if ln.startswith("- **T1 ") or ln.startswith("- **T2") or ln.startswith("- **T3"):
            if not done:
                for i, t in enumerate(themes, 1):
                    proof = t["proof"] or TBD
                    out.append(f"- **T{i} {t['theme']}** — {t['so_what'] or TBD} (proof: {proof})")
                done = True
            continue
        out.append(ln)
    return out


def thread_why_us(body: list[str], themes: list[dict]) -> list[str]:
    out = []
    for ln in body:
        out.append(ln)
        if ln.startswith("| Theme | Your need |"):
            continue
        if ln.startswith("|---|---|---|---|") and out[-2].startswith("| Theme | Your need |"):
            for t in themes:
                out.append(f"| {t['theme']} | {t['so_what'] or TBD} | {t['theme']} | {t['proof'] or TBD} |")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble proposal.md from the section library + win themes")
    ap.add_argument("win_themes", help="win-themes.json")
    ap.add_argument("--library", required=True, help="assets/section-library.md")
    ap.add_argument("--discovery", default="", help="discovery pack .md (optional)")
    ap.add_argument("--estimate", default="", help="estimate memo .md (optional)")
    ap.add_argument("--value-case", default="", help="value-case.md (optional)")
    ap.add_argument("--out", required=True, help="proposal.md")
    ap.add_argument("--placeholders", required=True, help="placeholders.csv")
    ap.add_argument("--sources", default="", help="sources.md (concatenated inputs for number tracing)")
    a = ap.parse_args()

    wt = load_themes(a.win_themes)
    client, initiative, themes = str(wt["client"]), str(wt["initiative"]), wt["themes"]
    library = split_library(read(a.library))
    discovery, estimate, value = read(a.discovery), read(a.estimate), read(a.value_case)

    doc = [f"# {client} — {initiative} — Proposal", "",
           f"_Draft assembled from the section library; win themes: {len(themes)}; "
           f"upstream files: {', '.join(n for n, f in (('discovery', discovery), ('estimate', estimate), ('value-case', value)) if f) or 'none'}_", ""]
    registry = []
    for num, title, body in library:
        if num in SKIP_SECTIONS:
            continue
        body = [ln.replace("<Client>", client).replace("<Initiative>", initiative)
                  .replace("<our firm>", TBD) for ln in body]
        title = title.replace("<our firm>", "us")
        if num == "1":
            body = thread_exec_summary(body, themes)
        if num == "11":
            body = thread_why_us(body, themes)
        if num == "2" and discovery:
            rows = table_rows(section_of(discovery, "Pain / Impact / Urgency"))
            if rows:
                body += ["", "Evidence from discovery (verbatim pain matrix):"] + rows
        if num == "3" and value:
            bl = section_of(value, "Bottom line")
            if bl:
                body += ["", "Value case bottom line (from value-case.md):"] + bl
        if num == "10" and estimate:
            bl = section_of(estimate, "Bottom line")
            if bl:
                body += ["", "Basis: estimate memo bottom line (from estimate-memo.md):"] + bl
        filled = []
        for ln in body:
            def rep(m, _title=title):
                registry.append({"placeholder": m.group(1), "section": f"{num}. {_title}", "owner": ""})
                return TBD
            filled.append(PLACEHOLDER_RE.sub(rep, ln))
        doc += [f"## {num}. {title}", ""] + filled + [""]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(doc).rstrip("\n") + "\n", encoding="utf-8")
    with Path(a.placeholders).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["placeholder", "section", "owner"])
        w.writeheader()
        w.writerows(registry)
    if a.sources:
        parts = [f"# Sources for {client} — {initiative}", "", "## win-themes.json", "",
                 json.dumps(wt, indent=2)]
        for name, text in (("discovery pack", discovery), ("estimate memo", estimate), ("value case", value),
                           ("section library (structural guidance; its numbers are layout rules, not client facts)",
                            read(a.library))):
            if text:
                parts += ["", f"## {name}", "", text]
        Path(a.sources).write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"proposal: {len(library) - len(SKIP_SECTIONS)} sections, {len(themes)} themes threaded, "
          f"{len(registry)} placeholders registered -> {out}")
    return 0


if __name__ == "__main__":
    main()
