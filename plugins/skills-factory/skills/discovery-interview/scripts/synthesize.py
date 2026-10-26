#!/usr/bin/env python3
"""Synthesize discovery notes into a pain matrix and the five closes.

    python3 -I scripts/synthesize.py notes.md --pain-matrix pain-matrix.csv --five-closes five-closes.md

notes.md: one statement per bullet or line. Supported, all optional:
  * speaker prefix     "Name (Title): text"  or  "Title: text"   -> owner column
  * explicit tags      "PAIN:", "DECISION:", "BUDGET:", "TIMELINE:", "INCUMBENT:", "SUCCESS:"
  * untagged lines     classified by keyword (see PAIN_WORDS / CLOSE_WORDS); lines matching
                       nothing go to the "parked" list in five-closes.md, never into the matrix
Pain rows carry impact / urgency = H when the line holds a figure ($, %, hours, days, cost) or a
date / freeze / renewal word, else "TBD" — never guessed. Evidence is the verbatim line, so it is
never empty. Each close is quoted verbatim or `TBD — owner: Engagement lead`.
Exit 1 when notes.md is missing or holds no usable line. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

TBD = "TBD — owner: Engagement lead"
PAIN_WORDS = ("manual", "slow", "broke", "brittle", "fail", "outage", "incident", "cost", "cannot", "can't",
              "late", "error", "re-key", "rekey", "complain", "war room", "cancel", "wrong", "risk",
              "expensive", "stuck", "delay", "backlog", "pain", "problem", "issue", "overtime", "miss",
              "takes", "only one", "single point", "key person", "dropped")
IMPACT_RE = re.compile(r"[$€£]\s?\d|\d+(\.\d+)?\s?%|\b\d[\d,]*\s*(hours?|days?|weeks?|fte|orders?|incidents?|k|m)\b|\bcost|\bmargin|\brevenue|\blost\b", re.I)
URGENCY_RE = re.compile(r"\b(by|before|deadline|freeze|peak|renewal|renew|end[- ]of[- ]life|eol|expires?|this year|next (quarter|peak|term)|q[1-4]\b|20\d\d)\b", re.I)
CLOSE_WORDS = {
    "decision_owner": ("decision", "sign off", "signs off", "approve", "approver", "owns the decision", "decides"),
    "budget_state": ("budget", "funded", "funding", "capex", "opex", "unfunded"),
    "timeline_driver": ("deadline", "freeze", "renewal", "expires", "go-live", "by q", "must be live", "before peak", "end of life"),
    "incumbents": ("incumbent", "currently use", "today we use", "vendor", "existing partner", "already working with", "talking to"),
    "success_measure": ("success", "kpi", "measure", "target", "looks like", "we will know"),
}
CLOSE_LABELS = {"decision_owner": "Decision owner", "budget_state": "Budget state",
                "timeline_driver": "Timeline driver", "incumbents": "Incumbents / alternatives",
                "success_measure": "Success measure"}
TAG_RE = re.compile(r"^(PAIN|DECISION|BUDGET|TIMELINE|INCUMBENT|SUCCESS)\s*:\s*(.+)$", re.I)
TAG_TO_CLOSE = {"DECISION": "decision_owner", "BUDGET": "budget_state", "TIMELINE": "timeline_driver",
                "INCUMBENT": "incumbents", "SUCCESS": "success_measure"}
SPEAKER_RE = re.compile(r"^([A-Z][\w .'-]{1,40}?(?:\s*\([^)]{1,40}\))?)\s*:\s+(.+)$")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def lines_of(text: str):
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        ln = re.sub(r"^[-*•]\s+|^\d+[.)]\s+", "", ln)
        if ln:
            yield ln


def split_speaker(ln: str):
    m = SPEAKER_RE.match(ln)
    if m and not TAG_RE.match(ln):
        who = m.group(1).strip()
        title = re.search(r"\(([^)]+)\)", who)
        return (title.group(1).strip() if title else who), m.group(2).strip()
    return "", ln


def classify(text: str):
    low = text.lower()
    m = TAG_RE.match(text)
    if m:
        tag, body = m.group(1).upper(), m.group(2).strip()
        return ("pain", body) if tag == "PAIN" else (TAG_TO_CLOSE[tag], body)
    for key, words in CLOSE_WORDS.items():
        if any(w in low for w in words):
            return key, text
    if any(w in low for w in PAIN_WORDS):
        return "pain", text
    return "parked", text


def main() -> int:
    ap = argparse.ArgumentParser(description="notes.md -> pain-matrix.csv + five-closes.md")
    ap.add_argument("notes")
    ap.add_argument("--pain-matrix", required=True)
    ap.add_argument("--five-closes", required=True)
    ap.add_argument("--client", default="<Client>")
    a = ap.parse_args()
    p = Path(a.notes)
    if not p.is_file():
        die(f"file not found: {p}")
    rows = list(lines_of(p.read_text(encoding="utf-8", errors="replace")))
    if not rows:
        die(f"{p.name}: no usable lines")

    pains, closes, parked = [], {k: [] for k in CLOSE_LABELS}, []
    for ln in rows:
        owner, body = split_speaker(ln)
        kind, text = classify(body)
        if kind == "pain":
            pains.append({"pain": text, "impact": "H" if IMPACT_RE.search(text) else "TBD",
                          "urgency": "H" if URGENCY_RE.search(text) else "TBD",
                          "evidence": f"{owner + ': ' if owner else ''}\"{text}\"", "owner": owner or TBD})
        elif kind == "parked":
            parked.append(ln)
        else:
            closes[kind].append(f"{owner + ': ' if owner else ''}\"{text}\"")
            if any(w in text.lower() for w in PAIN_WORDS):
                pains.append({"pain": text, "impact": "H" if IMPACT_RE.search(text) else "TBD",
                              "urgency": "H" if URGENCY_RE.search(text) else "TBD",
                              "evidence": f"{owner + ': ' if owner else ''}\"{text}\"", "owner": owner or TBD})
    with Path(a.pain_matrix).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pain", "impact", "urgency", "evidence", "owner"])
        w.writeheader(); w.writerows(pains)
    n_known = sum(1 for v in closes.values() if v)
    L = [f"# Five closes — {a.client}", "",
         f"Captured {n_known} of 5 closes from `{p.name}`; {len(pains)} pain rows; {len(parked)} lines parked.", "",
         "## Five closes", "| Close | Answer captured (verbatim) | Status |", "|---|---|---|"]
    for key, label in CLOSE_LABELS.items():
        ans = closes[key]
        L.append(f"| {label} | {' / '.join(ans) if ans else TBD} | {'captured' if ans else 'open — ask on the next call'} |")
    L += ["", "## Pain / Impact / Urgency matrix", "| # | Pain | Impact | Urgency | Evidence | Owner |", "|---|---|---|---|---|---|"]
    L += [f"| {i} | {r['pain']} | {r['impact']} | {r['urgency']} | {r['evidence']} | {r['owner']} |" for i, r in enumerate(pains, 1)] \
        or ["| — | no pain statements found | | | | |"]
    L += ["", "## Parked (not classified; review by hand)"] + [f"- {x}" for x in parked] or []
    if not parked:
        L.append("- none")
    Path(a.five_closes).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"synthesis: {len(pains)} pains, {n_known}/5 closes, {len(parked)} parked -> {a.pain_matrix}, {a.five_closes}")
    return 0


if __name__ == "__main__":
    main()
