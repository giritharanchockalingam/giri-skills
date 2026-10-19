#!/usr/bin/env python3
"""Build a client-brief skeleton from a notes/links file. No network access.

Reads a plain-text or Markdown notes file containing URLs, pasted excerpts,
and free-form notes. Classifies each line into a brief section using keyword
and URL-pattern heuristics, writes a Markdown skeleton in the layout of
assets/brief-template.md, and reports which sections received no material.

The script never fetches anything. It organizes what the user already has so
the brief can be completed by reading the cited sources. Every classified item
is listed with its origin line number so it can be traced back.

Usage:
    python3 -I brief_skeleton.py --notes notes.md --company "Acme Corp" --out brief.md
    python3 -I brief_skeleton.py --notes notes.txt --company "Acme" --purpose proposal
    ... --previous last-brief.md                       # refresh: what is new since the last brief
    ... --final brief.md --draft-only                  # no model step: a cited brief from the notes

--previous: the brief written last time for this client. Each note line already in it is carried, the
rest is marked NEW in the To-do column, and "Changes since the last brief" lists the new items and the
previous brief's sources that the notes no longer carry (not re-confirmed: re-check or drop them).
--draft-only --final: writes the brief on the template's sections with every item cited by its [Sn]
source id (items without a URL cite "notes Ln"); the bottom line is the first three cited items, verbatim,
with the "so what" left as an owned marker — labelled as a draft (the model step was not run).

Exit codes: 0 success; 2 input file not found or empty.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import OrderedDict
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)

# Section -> (URL host/path patterns, keyword patterns). Order matters: first match wins.
RULES: "OrderedDict[str, tuple[list[str], list[str]]]" = OrderedDict(
    [
        (
            "Financial signals",
            [
                r"sec\.gov", r"edgar", r"10-k", r"10-q", r"20-f", r"annual[- ]report",
                r"investor", r"earnings", r"proxy", r"bond", r"audited",
            ],
        ),
        (
            "Technology signals",
            [
                r"careers", r"jobs?\.", r"greenhouse", r"lever\.co", r"workday\.com",
                r"github\.com", r"developer\.", r"/api", r"status\.", r"engineering",
                r"job posting", r"posting", r"tech stack", r"platform", r"migrat",
                r"mulesoft", r"apigee", r"boomi", r"informatica", r"kafka", r"salesforce",
                r"sap", r"oracle", r"workday", r"aws", r"azure", r"gcp", r"snowflake",
                r"databricks", r"kubernetes",
            ],
        ),
        (
            "Leadership",
            [
                r"linkedin\.com/in/", r"\bcio\b", r"\bcto\b", r"\bcdo\b", r"\bcfo\b",
                r"\bciso\b", r"chief", r"appointed", r"joins? as", r"named .* officer",
                r"vice president", r"\bvp\b", r"provost",
            ],
        ),
        (
            "Recent news",
            [
                r"prnewswire", r"businesswire", r"reuters", r"bloomberg", r"wsj\.com",
                r"ft\.com", r"techcrunch", r"news", r"press[- ]release", r"announce",
                r"acqui", r"partnership", r"outage", r"breach", r"lawsuit",
            ],
        ),
        (
            "Snapshot",
            [
                r"wikipedia", r"about[- ]us", r"/about", r"headquarter", r"founded",
                r"employees", r"revenue", r"locations", r"stores", r"plants", r"campuses",
            ],
        ),
        (
            "Likely initiatives (hypotheses)",
            [
                r"initiative", r"program", r"roadmap", r"transformation", r"modern",
                r"strategy", r"priority", r"hypothes",
            ],
        ),
        (
            "Risks and landmines",
            [r"risk", r"landmine", r"incumbent", r"competitor", r"avoid", r"sensitive"],
        ),
        (
            "Questions for the call",
            [r"\?$", r"^q[:\d]", r"ask them", r"question"],
        ),
    ]
)

SECTION_ORDER = [
    "Bottom line",
    "Snapshot",
    "Financial signals",
    "Technology signals",
    "Leadership",
    "Recent news",
    "Likely initiatives (hypotheses)",
    "Risks and landmines",
    "Questions for the call",
    "Sources",
]

TBD = "[TO BE BASELINED — owner: Account owner]"


def classify(line: str) -> str:
    """Return the section name for a line, or 'Unclassified'."""
    low = line.lower()
    for section, patterns in RULES.items():
        for pat in patterns:
            if re.search(pat, low):
                return section
    return "Unclassified"


def parse_notes(text: str) -> tuple[dict[str, list[tuple[int, str]]], list[tuple[int, str]]]:
    """Split notes into classified items and a list of (line_no, url) sources."""
    buckets: dict[str, list[tuple[int, str]]] = {s: [] for s in SECTION_ORDER}
    buckets["Unclassified"] = []
    sources: list[tuple[int, str]] = []
    current_heading: str | None = None

    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        # Explicit user headings override heuristics: "## Leadership" or "[leadership]"
        m = re.match(r"^(?:#+\s*|\[)([A-Za-z /()]+?)\]?\s*$", line)
        if m:
            name = m.group(1).strip().lower()
            matched = next((s for s in SECTION_ORDER if s.lower().startswith(name[:8])), None)
            current_heading = matched
            continue
        for url in URL_RE.findall(line):
            sources.append((n, url))
        section = current_heading or classify(line)
        buckets.setdefault(section, []).append((n, line))
    return buckets, sources


def norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lstrip("-*#> ").strip()).lower()


def compare_previous(prev_text: str, buckets: dict, sources: list) -> dict:
    """Which note lines are new since the previous brief, and which previous sources the notes dropped."""
    prev_norm = norm_line(prev_text.replace("\\|", "|"))
    prev_urls = list(OrderedDict.fromkeys(URL_RE.findall(prev_text)))
    new_lines = set()
    for items in buckets.values():
        for n, line in items:
            urls = URL_RE.findall(line)
            text_seen = norm_line(URL_RE.sub("", line)) and norm_line(URL_RE.sub("", line)) in prev_norm
            if not (text_seen or (urls and all(u in prev_urls for u in urls))):
                new_lines.add(n)
    now_urls = {u for _, u in sources}
    return {"new_lines": new_lines, "dropped_sources": [u for u in prev_urls if u not in now_urls]}


def changes_section(delta: dict, buckets: dict) -> list[str]:
    out = ["## Changes since the last brief", ""]
    new = [(n, line, sec) for sec, items in buckets.items() for n, line in items
           if n in delta["new_lines"] and not line.startswith("#")]
    out += [f"- NEW (L{n}, {sec}): {line.replace('|', chr(92) + '|')}" for n, line, sec in sorted(new)] or \
           ["- No new material since the last brief."]
    out += [f"- Not re-confirmed: {u} was cited last time and is not in the notes — re-check or drop it ({TBD})"
            for u in delta["dropped_sources"]]
    return out + [""]


def render(company: str, purpose: str, buckets: dict, sources: list, today: str, delta: dict | None = None) -> str:
    out: list[str] = []
    out.append(f"# Client Brief — {company} — for {purpose} on {TBD}")
    out.append("")
    out.append(f"Prepared: {today} · Angle: {TBD} · Network used: no (skeleton from notes)")
    out.append("")
    out.append("## Bottom line")
    out.append(f"1. {TBD}")
    out.append(f"2. {TBD}")
    out.append(f"3. {TBD}")
    out.append("")

    for section in SECTION_ORDER[1:-1]:
        out.append(f"## {section}")
        items = buckets.get(section, [])
        if items:
            out.append("| # | Material from notes (line) | Source | Confidence | To do |")
            out.append("|---|---|---|---|---|")
            for i, (n, line) in enumerate(items, start=1):
                urls = URL_RE.findall(line)
                src = urls[0] if urls else "notes"
                cell = line.replace("|", "\\|")
                todo = "NEW since last brief — verify and cite" if delta and n in delta["new_lines"] else "verify and cite"
                out.append(f"| {i} | {cell} (L{n}) | {src} | {TBD} | {todo} |")
        else:
            out.append(f"_No material in notes._ {TBD}")
        out.append("")

    if delta is not None:
        out += changes_section(delta, buckets)
    out.append("## Sources")
    out.append("| # | Source | Section / page | Date accessed | Tier |")
    out.append("|---|---|---|---|---|")
    if sources:
        for i, (n, url) in enumerate(sources, start=1):
            out.append(f"| S{i} | {url} | (notes L{n}) | {TBD} | {TBD} |")
    else:
        out.append(f"| S1 | {TBD} | | | |")
    out.append("")

    unclassified = buckets.get("Unclassified", [])
    if unclassified:
        out.append("## Unclassified notes (place manually)")
        out.append("| Line | Text |")
        out.append("|---|---|")
        for n, line in unclassified:
            out.append(f"| L{n} | {line.replace('|', '\\|')} |")
        out.append("")
    return "\n".join(out)


def render_final(company: str, purpose: str, buckets: dict, sources: list, today: str, delta: dict | None = None) -> str:
    """The brief on the template's sections, every item cited by source id; no model step."""
    sid = {}
    for i, (_, url) in enumerate(sources, start=1):
        sid.setdefault(url, f"S{i}")

    def cite(n: int, line: str) -> str:
        ids = [sid[u] for u in URL_RE.findall(line) if u in sid]
        return " ".join(f"[{x}]" for x in dict.fromkeys(ids)) or f"notes L{n}"

    def text(line: str) -> str:
        return URL_RE.sub("", line).strip(" —-:").replace("|", "\\|") or line.replace("|", "\\|")

    out = [f"# Client Brief — {company} — for {purpose} on {TBD}", "",
           f"Prepared: {today} · Angle: {TBD} · Network used: no (brief from the user's notes)", "",
           "> Script draft — the model step was not run (draft only): items are the user's notes, verbatim and cited; "
           "inferences and the so-what are owned markers.", "", "## Bottom line"]
    cited = [(n, line) for sec in ("Financial signals", "Technology signals", "Leadership", "Recent news", "Snapshot")
             for n, line in buckets.get(sec, []) if URL_RE.search(line)]
    for i, (n, line) in enumerate(cited[:3], start=1):
        out.append(f"{i}. {text(line)} {cite(n, line)} — so what: {TBD}")
    if not cited:
        out.append(f"1. {TBD} (no cited material in the notes)")
    out.append("")
    for section in SECTION_ORDER[1:-1]:
        out += [f"## {section}", ""]
        items = buckets.get(section, [])
        if items:
            out += ["| # | Item (verbatim from notes) | Source | Confidence |", "|---|---|---|---|"]
            out += [f"| {i} | {text(line)} | {cite(n, line)} | {TBD} |" for i, (n, line) in enumerate(items, start=1)]
        else:
            out.append(f"_No material in notes._ {TBD}")
        out.append("")
    if delta is not None:
        out += changes_section(delta, buckets)
    out += ["## Sources", "", "| # | Source | Section / page | Date accessed | Tier |", "|---|---|---|---|---|"]
    listed = set()
    for n, u in sources:
        if u not in listed:
            listed.add(u)
            out.append(f"| {sid[u]} | {u} | (notes L{n}) | {TBD} | {TBD} |")
    if not sources:
        out.append(f"| — | {TBD} | | | |")
    return "\n".join(out) + "\n"


def coverage_report(buckets: dict) -> str:
    rows = []
    for section in SECTION_ORDER[1:-1]:
        count = len(buckets.get(section, []))
        status = "EMPTY — needs research" if count == 0 else f"{count} item(s)"
        rows.append(f"  {section:<34} {status}")
    rows.append(f"  {'Unclassified':<34} {len(buckets.get('Unclassified', []))} item(s)")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--notes", required=True, help="Path to notes/links file (.md or .txt)")
    p.add_argument("--company", required=True, help="Company name for the brief title")
    p.add_argument("--purpose", default="discovery", help="discovery | proposal | exec-meeting | pitch")
    p.add_argument("--out", default=None, help="Output Markdown path (default: stdout)")
    p.add_argument("--previous", default=None, help="the last brief for this client (refresh: new vs carried)")
    p.add_argument("--final", default=None, help="final brief path (written with --draft-only)")
    p.add_argument("--draft-only", action="store_true", help="no model step: write --final from the notes")
    args = p.parse_args(argv)

    path = Path(args.notes)
    if not path.is_file():
        print(f"error: notes file not found: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print(f"error: notes file is empty: {path}", file=sys.stderr)
        return 2

    buckets, sources = parse_notes(text)
    today = dt.date.today().isoformat()
    delta = None
    if args.previous:
        pp = Path(args.previous)
        if not pp.is_file():
            print(f"error: previous brief not found: {pp}", file=sys.stderr)
            return 2
        delta = compare_previous(pp.read_text(encoding="utf-8", errors="replace"), buckets, sources)
    md = render(args.company, args.purpose, buckets, sources, today, delta)
    if args.draft_only and args.final:
        Path(args.final).write_text(render_final(args.company, args.purpose, buckets, sources, today, delta), encoding="utf-8")

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)
    print("\nCoverage:", file=sys.stderr)
    print(coverage_report(buckets), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
