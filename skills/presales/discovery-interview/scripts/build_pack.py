#!/usr/bin/env python3
"""Build a discovery prep pack: vertical question bank filtered by persona, timed, with the five closes.

    python3 -I scripts/build_pack.py --vertical retail --personas "CIO,VP Digital" --minutes 45 \
        --banks references/question-banks --out discovery-pack.md [--client "Acme"]

Reads references/question-banks/<vertical>.md (tables under "### <Stage>" headings:
| # | Question | Persona | Listen for |) and keeps the questions whose Persona cell names one of
the requested personas (case-insensitive token match; "CIO / SVP SC" matches "CIO"). Time budget:
20% reserved for the client's questions, 10 minutes for the five closes, 3 minutes opening, the
rest at 3 minutes per question, drawn round-robin across the funnel stages in order so every stage
is represented. Also copies the bank's branch table and pre-reads.
Exit 1 on an unknown vertical, a bank with no question tables, or no question matching the personas
(the error lists the personas the bank knows). Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VERTICALS = ("edtech", "retail", "manufacturing", "travel")
MIN_PER_QUESTION = 3
CLOSES_MIN = 10
OPENING_MIN = 3
CLIENT_SHARE = 0.20
CLOSES = [("Decision owner", "Who signs this off, and who else has to agree?"),
          ("Budget state", "Is this funded, being funded, or pre-budget — capex or opex?"),
          ("Timeline driver", "What date or event makes this matter now?"),
          ("Incumbents / alternatives", "Who else is helping you with this today, and who else are you talking to?"),
          ("Success measure", "Twelve months from now, what number tells you this worked?")]


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def parse_bank(text: str):
    """Return (questions, branches, prereads). questions: [{id, question, persona, listen, stage}]."""
    questions, branches, prereads = [], [], []
    stage, in_q, in_branch, in_pre = None, False, False, False
    for ln in text.splitlines():
        if ln.startswith("## "):
            h = ln[3:].lower()
            in_q, in_branch, in_pre = h.startswith("questions"), h.startswith("branch"), h.startswith("pre-reads")
            stage = None
            continue
        if ln.startswith("### "):
            stage = ln[4:].strip()
            continue
        if not ln.startswith("|"):
            if in_pre and ln.strip():
                prereads += [[d.strip(" ."), "[TO BE BASELINED — owner: ___]", "pre-read"]
                             for d in ln.split(",") if d.strip(" .")]
            continue
        c = cells(ln)
        if set("".join(c)) <= set("-: ") or not c:
            continue
        if in_q and stage and len(c) >= 4 and re.fullmatch(r"[A-Z]{1,2}\d{1,3}", c[0]):
            questions.append({"id": c[0], "question": c[1], "persona": c[2], "listen": c[3], "stage": stage})
        elif in_branch and len(c) >= 2 and c[0].lower() not in ("if they say",):
            branches.append((c[0], c[1]))
        elif in_pre and len(c) >= 2 and c[0].lower() not in ("document", "pre-read"):
            prereads.append(c)
    return questions, branches, prereads


def persona_tokens(cell: str) -> list[str]:
    return [t.strip().lower() for t in re.split(r"/|,|;", cell) if t.strip()]


def matches(cell: str, wanted: list[str]) -> bool:
    toks = persona_tokens(cell)
    for w in wanted:
        wl = w.lower()
        if any(wl == t or wl in t or t in wl for t in toks):
            return True
    return False


def select(questions, wanted, n: int):
    by_stage: dict[str, list] = {}
    for q in questions:
        if matches(q["persona"], wanted):
            by_stage.setdefault(q["stage"], []).append(q)
    stages = [s for s in dict.fromkeys(q["stage"] for q in questions) if s in by_stage]
    picked = []
    while len(picked) < n and any(by_stage[s] for s in stages):
        for s in stages:
            if by_stage[s] and len(picked) < n:
                picked.append(by_stage[s].pop(0))
    order = {s: i for i, s in enumerate(dict.fromkeys(q["stage"] for q in questions))}
    picked.sort(key=lambda q: (order[q["stage"]], questions.index(q)))
    return picked, sum(len(v) for v in by_stage.values()) + len(picked)


def main() -> int:
    ap = argparse.ArgumentParser(description="Discovery prep pack from a vertical question bank")
    ap.add_argument("--vertical", required=True, choices=VERTICALS)
    ap.add_argument("--personas", required=True, help="comma list, e.g. 'CIO,VP Digital'")
    ap.add_argument("--minutes", type=int, required=True)
    ap.add_argument("--banks", default="references/question-banks", help="dir with <vertical>.md")
    ap.add_argument("--client", default="<Client>")
    ap.add_argument("--initiative", default="<Initiative>")
    ap.add_argument("--out", required=True)
    ap.add_argument("--five-closes", default="", help="also write a prep-mode five-closes.md (all closes open)")
    ap.add_argument("--pain-matrix", default="", help="also write an empty pain-matrix.csv (header only) for prep mode")
    a = ap.parse_args()
    if a.minutes < 20 or a.minutes > 240:
        die("--minutes must be 20..240")
    wanted = [p.strip() for p in a.personas.split(",") if p.strip()]
    if not wanted:
        die("--personas is empty")
    bank = Path(a.banks) / f"{a.vertical}.md"
    if not bank.is_file():
        die(f"question bank not found: {bank}")
    questions, branches, prereads = parse_bank(bank.read_text(encoding="utf-8"))
    if not questions:
        die(f"{bank.name}: no question tables found")

    client_min = round(a.minutes * CLIENT_SHARE)
    q_min = a.minutes - client_min - CLOSES_MIN - OPENING_MIN
    n = max(q_min // MIN_PER_QUESTION, 0)
    picked, n_match = select(questions, wanted, n)
    if not picked:
        known = sorted({t for q in questions for t in persona_tokens(q["persona"])})
        die(f"no question in {bank.name} is tagged for {wanted}; bank personas: {known}")
    used = len(picked) * MIN_PER_QUESTION
    slack = q_min - used

    L = [f"# Discovery Pack — {a.client} — {a.initiative} — prep", "",
         f"Vertical: {a.vertical} · Personas: {', '.join(wanted)} · Call length: {a.minutes} min · "
         f"Bank: `{bank.as_posix()}` ({len(questions)} questions, {n_match} match the personas, {len(picked)} selected)", "",
         "## Bottom line", "[TO BE BASELINED — owner: ___] — what we must learn on this call to decide whether to propose, and what shape.", "",
         "## Hypotheses", "| ID | Hypothesis | If true, we propose | Confirms | Kills | Tested by |", "|---|---|---|---|---|---|",
         "| H1 | [TO BE BASELINED — owner: ___] | | | | |", "",
         f"## Time budget ({a.minutes} min; {int(CLIENT_SHARE * 100)}% reserved for their questions)",
         "| Block | Minutes | Note |", "|---|---|---|",
         f"| Opening and agenda | {OPENING_MIN} | why we are here, what we will ask |",
         f"| Questions ({len(picked)} × {MIN_PER_QUESTION} min) | {used} | funnel order below |",
         f"| Five closes | {CLOSES_MIN} | last ten minutes before their questions |",
         f"| Their questions (reserved) | {client_min} | never cut this block |",
         f"| Slack | {slack} | absorbs long answers |",
         f"| **Total** | **{OPENING_MIN + used + CLOSES_MIN + client_min + slack}** | |", "",
         "## Question plan", "| # | Bank id | Question | Persona | Stage | Listen for | Hypothesis | Min |",
         "|---|---|---|---|---|---|---|---|"]
    for i, q in enumerate(picked, 1):
        L.append(f"| {i} | {q['id']} | {q['question']} | {q['persona']} | {q['stage']} | {q['listen']} | H? | {MIN_PER_QUESTION} |")
    L += ["", "## Branches", "| If they say | Go to |", "|---|---|"]
    L += [f"| {a_} | {b} |" for a_, b in branches] or ["| [TO BE BASELINED — owner: ___] | |"]
    L += ["", "## Five closes (last 10 minutes)", "| Close | Ask | Asked by | Answer captured |", "|---|---|---|---|"]
    L += [f"| {name} | {ask} | | |" for name, ask in CLOSES]
    L += ["", "## Pre-reads to request", "| Document | From (client role) | Why |", "|---|---|---|"]
    L += [f"| {' | '.join(p[:3])} |" for p in prereads] or ["| [TO BE BASELINED — owner: ___] | | |"]
    L += ["", "## Questions not selected (same personas, if time allows)", "| Bank id | Question | Persona | Stage |", "|---|---|---|---|"]
    rest = [q for q in questions if matches(q["persona"], wanted) and q not in picked]
    L += [f"| {q['id']} | {q['question']} | {q['persona']} | {q['stage']} |" for q in rest] or ["| — | none | | |"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    if a.five_closes:
        F = [f"# Five closes — {a.client}", "", "Prep mode: no notes synthesized yet; every close is open and must be asked on the call.", "",
             "## Five closes", "| Close | Answer captured (verbatim) | Status |", "|---|---|---|"]
        F += [f"| {name} | TBD — owner: ___ | open — ask: {ask} |" for name, ask in CLOSES]
        Path(a.five_closes).write_text("\n".join(F) + "\n", encoding="utf-8")
    if a.pain_matrix:
        Path(a.pain_matrix).write_text("pain,impact,urgency,evidence,owner\n", encoding="utf-8")
    print(f"discovery pack: {len(picked)} questions for {wanted} in {a.minutes} min -> {a.out}")
    return 0


if __name__ == "__main__":
    main()
