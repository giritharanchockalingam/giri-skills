#!/usr/bin/env python3
"""Orals prep from a proposal: timed script skeleton, number registry, likely questions.

    python3 -I scripts/orals.py proposal.md --minutes 60 --speakers "Giri,Priya,Alex" \
        --question-bank references/question-bank-and-red-team.md \
        --script orals-script.md --registry number-registry.csv --questions likely-questions.md

Timing: 70% presentation / 30% Q&A; a fixed opening (1.5 min) and close (1 min) bracket the
sections, which get presentation time proportional to their word count in proposal.md (minimum
one minute each). Speakers are assigned round-robin in proposal order; the opening goes to the
first speaker and the close to the last. number-registry.csv lists every number in the proposal
(>= 3 significant digits or carrying $ / %) with its section and context, plus the computed timing
and airtime numbers (section "orals timing"), so every number in orals-script.md traces to it.
likely-questions.md = the standard evaluator questions from the question bank, one question per
`[TO BE BASELINED` marker in the proposal ("what is the number?"), and one per assumption row.
No proof line is written for a section that holds no number; it reads `[TO BE BASELINED — owner: Bid manager]`.
Existing talk track (--talk-track track.md --check out.md): the team's current script, one line per
speaker turn (`Name: …` or `**Name:** …`), is checked against the proposal and the timing: every figure
it says that the proposal does not contain is flagged (cut it or source it in the proposal first),
each speaker's spoken minutes (at 150 words per minute) are compared with the allocated airtime, and
lines from people not in --speakers are listed. Written to --check; the generated script is unchanged.
Exit 1 when proposal.md is missing / has no sections, --minutes < 10, or --speakers is empty.
Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Bid manager]"
NUMBER_RE = re.compile(r"(?<![\w.])([$€£]?)(-?\d[\d,]*(?:\.\d+)?)(%?)(?![\w])")
DATE_RE = re.compile(r"\b\d{4}-\d{2}(-\d{2})?\b")
OPEN_MIN, CLOSE_MIN, QA_SHARE = 1.5, 1.0, 0.30


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def sig(num: str) -> int:
    return len(num.replace(",", "").replace("-", "").replace(".", "").lstrip("0"))


def numbers_in(text: str):
    """Numbers worth tracing (>= 3 significant digits or $ / %); ISO dates are not numbers."""
    for m in NUMBER_RE.finditer(DATE_RE.sub(" ", text)):
        sym, num, pct = m.groups()
        if sym or pct or sig(num) >= 3:
            yield f"{sym}{num}{pct}"


def sections_of(md: str) -> list[tuple[str, list[str]]]:
    out, cur = [], None
    for ln in md.splitlines():
        if ln.startswith("## "):
            cur = (re.sub(r"^\d+\.\s*", "", ln[3:].strip()), [])
            out.append(cur)
        elif cur is not None:
            cur[1].append(ln)
    return out


def mmss(minutes: float) -> str:
    total = int(round(minutes * 60))
    return f"{total // 60}:{total % 60:02d}"


def bank_questions(path: str) -> list[tuple[str, str, str]]:
    """(theme, question, answer pattern) rows from the '### <theme>' tables of the question bank."""
    p = Path(path)
    if not p.is_file():
        return []
    rows, theme = [], ""
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith("## "):
            theme = ""
            continue
        if ln.startswith("### "):
            theme = ln[4:].strip()
            continue
        if theme and ln.startswith("| \""):
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if len(c) >= 2:
                rows.append((theme, c[0].strip('"'), c[1]))
    return rows


WPM = 150
SPOKEN_NUM_RE = re.compile(r"(?<![\w.])[$€£]?\d[\d,]*(?:\.\d+)?(?:%|[kKmMbB]\b)?")


def spoken_figures(text: str) -> list[str]:
    """Figures as said, suffix kept ('$2.1M', '6.2%'); same threshold as numbers_in plus k/M/B amounts."""
    out = []
    for m in SPOKEN_NUM_RE.finditer(DATE_RE.sub(" ", text)):
        tok = m.group(0)
        core = tok.lstrip("$€£").rstrip("%kKmMbB")
        if tok[0] in "$€£" or tok[-1] in "%kKmMbB" or sig(core) >= 3:
            out.append(tok)
    return out


TURN_RE = re.compile(r"^\s*(?:[-*]\s*)?\**([A-Z][\w .'-]{0,40}?)\**\s*:\**\s*(.+)$")


def check_talk_track(track: str, registry: list[dict], airtime: dict, speakers: list[str]) -> list[str]:
    known = {r["number"] for r in registry if r["section"] != "orals timing"}
    words: dict[str, int] = {}
    untraced, strangers = [], []
    for n, ln in enumerate(track.splitlines(), 1):
        m = TURN_RE.match(ln)
        if not m or ln.lstrip().startswith("#"):
            continue
        who, said = m.group(1).strip(), m.group(2)
        words[who] = words.get(who, 0) + len(said.split())
        if who not in speakers and who not in strangers:
            strangers.append(who)
        untraced += [(n, who, x) for x in spoken_figures(said) if x not in known]
    L = ["# Talk track check", "", f"Checked against the proposal's number registry and the timed script ({WPM} words per minute).", "",
         "## Figures not in the proposal", "| Line | Speaker | Figure | Action |", "|---|---|---|---|"]
    L += [f"| {n} | {who} | {x} | cut it, or source it in the proposal first ({TBD}) |" for n, who, x in untraced] or \
         ["| — | — | — | every figure traces to the proposal |"]
    L += ["", "## Airtime vs spoken length", "| Speaker | Allocated min | Spoken min | Verdict |", "|---|---|---|---|"]
    for s_ in speakers:
        spoken = words.get(s_, 0) / WPM
        alloc = airtime.get(s_, 0.0)
        verdict = "no lines in the track" if not words.get(s_) else \
            ("over — cut" if spoken > alloc * 1.1 else "under — room to add proof" if spoken < alloc * 0.5 else "fits")
        L.append(f"| {s_} | {round(alloc, 1)} | {round(spoken, 1)} | {verdict} |")
    L += ["", "## Speakers not in the line-up", ""]
    L += [f"- {w}: has lines in the track but is not in --speakers — add them or reassign the lines" for w in strangers] or ["- none"]
    return L


def main() -> int:
    ap = argparse.ArgumentParser(description="proposal.md -> orals-script.md + number-registry.csv + likely-questions.md")
    ap.add_argument("proposal")
    ap.add_argument("--minutes", type=int, required=True)
    ap.add_argument("--speakers", required=True, help="comma list in speaking order")
    ap.add_argument("--question-bank", default="references/question-bank-and-red-team.md")
    ap.add_argument("--script", required=True); ap.add_argument("--registry", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--talk-track", default="", help="the team's existing talk track to check")
    ap.add_argument("--check", default="", help="with --talk-track: write the check here")
    a = ap.parse_args()
    if a.talk_track and not Path(a.talk_track).is_file():
        die(f"talk track not found: {a.talk_track}")
    if a.minutes < 10 or a.minutes > 240:
        die("--minutes must be 10..240")
    speakers = [s.strip() for s in a.speakers.split(",") if s.strip()]
    if not speakers:
        die("--speakers is empty")
    p = Path(a.proposal)
    if not p.is_file():
        die(f"file not found: {p}")
    md = p.read_text(encoding="utf-8", errors="replace")
    secs = sections_of(md)
    if not secs:
        die("proposal has no '## ' sections")
    title = next((ln[2:].strip() for ln in md.splitlines() if ln.startswith("# ")), p.stem)

    registry = []
    for name, lines in secs:
        for ln in lines:
            for n in numbers_in(ln):
                ctx = re.sub(r"\s*\|\s*", " / ", ln.strip().strip("|")).strip(" /")
                registry.append({"number": n, "section": name, "context": ctx[:140]})
    present = a.minutes * (1 - QA_SHARE)
    qa = a.minutes - present
    body_min = max(present - OPEN_MIN - CLOSE_MIN, len(secs) * 1.0)
    weights = [max(len(" ".join(lines).split()), 1) for _, lines in secs]
    tot_w = sum(weights)
    alloc = [max(1.0, round(body_min * w / tot_w * 2) / 2) for w in weights]
    scale = body_min / sum(alloc)
    alloc = [round(x * scale * 2) / 2 for x in alloc]
    alloc = [max(0.5, x) for x in alloc]

    rows, t = [], 0.0
    rows.append((t, t + OPEN_MIN, "Opening", speakers[0], "1–2", "Their situation in their words; the outcome we commit to", TBD))
    t += OPEN_MIN
    airtime = {s: 0.0 for s in speakers}
    airtime[speakers[0]] += OPEN_MIN
    for i, ((name, lines), m) in enumerate(zip(secs, alloc)):
        spk = speakers[i % len(speakers)]
        nums = [r["number"] for r in registry if r["section"] == name]
        proof = ", ".join(dict.fromkeys(nums)) if nums else TBD
        rows.append((t, t + m, name, spk, TBD, TBD, proof))
        airtime[spk] += m
        t += m
    rows.append((t, t + CLOSE_MIN, "Close", speakers[-1], "last", "The ask; next step with date; one memorable sentence", TBD))
    airtime[speakers[-1]] += CLOSE_MIN
    t += CLOSE_MIN
    rows.append((t, t + qa, "Q&A", "all (per likely-questions.md)", "—", "", ""))
    t_end = t + qa
    for lab, val in (("total minutes", a.minutes), ("presentation minutes", round(present, 1)), ("Q&A minutes", round(qa, 1)),
                     ("body minutes", round(body_min, 1))):
        registry.append({"number": str(val), "section": "orals timing", "context": lab})
    for s, m in airtime.items():
        share = round(100 * m / present)
        registry.append({"number": f"{share}%", "section": "orals timing", "context": f"airtime share {s}"})
        registry.append({"number": str(round(m, 1)), "section": "orals timing", "context": f"airtime minutes {s}"})
    registry.append({"number": mmss(t_end).replace(":", ""), "section": "orals timing", "context": "end of slot"})

    L = [f"# Orals Script — {title}", "",
         f"Format: {a.minutes} min total · {mmss(present)} presentation · {mmss(qa)} Q&A · Speakers: {', '.join(speakers)} · "
         f"Attendees: {TBD} · Evaluation criteria: {TBD}", "",
         "## Timed script", "| Start | End | Segment | Speaker | Slide | The point (one sentence) | Proof (numbers from proposal; see number-registry.csv) |",
         "|---|---|---|---|---|---|---|"]
    L += [f"| {mmss(s)} | {mmss(e)} | {seg} | {spk} | {slide} | {point} | {proof} |" for s, e, seg, spk, slide, point, proof in rows]
    L += ["", "## Airtime check", "| Speaker | Minutes | Share of presentation |", "|---|---|---|"]
    L += [f"| {s} | {round(m, 1)} | {round(100 * m / present)}% |" for s, m in airtime.items()]
    L += ["", "## Opening (verbatim, ≤90 s)", TBD, "", "## Close (verbatim, ≤60 s)", TBD, "",
          "## Number sheet (in front of every presenter)", "| Number | Context | Section |", "|---|---|---|"]
    seen = set()
    for r in registry:
        if r["section"] != "orals timing" and (r["number"], r["section"]) not in seen:
            seen.add((r["number"], r["section"]))
            L.append(f"| {r['number']} | {r['context']} | {r['section']} |")
    if not seen:
        L.append(f"| none in proposal | every claim needs a number — {TBD} | |")
    L += ["", "## Handoffs", "| From | To | Line |", "|---|---|---|"]
    L += [f"| {rows[i][3]} | {rows[i + 1][3]} | {TBD} |" for i in range(len(rows) - 2) if rows[i][3] != rows[i + 1][3]]
    L += ["", "## Logistics", "| Item | Status | Owner |", "|---|---|---|",
          f"| PDF + offline deck | | {TBD} |", f"| Attendee names/pronunciation | | {TBD} |",
          f"| Timekeeper and signals (−5, −2) | | {TBD} |", f"| Backup presenter per segment | | {TBD} |"]
    Path(a.script).parent.mkdir(parents=True, exist_ok=True)
    Path(a.script).write_text("\n".join(L) + "\n", encoding="utf-8")
    with Path(a.registry).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["number", "section", "context"]); w.writeheader(); w.writerows(registry)

    Q = [f"# Likely questions — {title}", "", "| # | Question | Theme | Answerer | Answer (≤75 words) | Evidence | Confidence |",
         "|---|---|---|---|---|---|---|"]
    k = 0
    for theme, q, pattern in bank_questions(a.question_bank):
        k += 1
        Q.append(f"| {k} | {q} | {theme} | {TBD} | pattern: {pattern} | {TBD} | |")
    for name, lines in secs:
        for ln in lines:
            if "[TO BE BASELINED" in ln:
                k += 1
                Q.append(f"| {k} | What is the number for: {re.sub(r'[|`*]', '', ln).strip()[:100]}? | Unbaselined ({name}) | {TBD} | how and when it will be baselined | {name} | |")
            if re.match(r"\|\s*A-\d+\s*\|", ln):
                k += 1
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                Q.append(f"| {k} | What if \"{cells[1] if len(cells) > 1 else ln}\" is wrong? | Assumptions | {TBD} | impact and change-control trigger | {name} | |")
    if k == 0:
        Q.append(f"| 1 | {TBD} | | | | | |")
    Path(a.questions).write_text("\n".join(Q) + "\n", encoding="utf-8")
    if a.talk_track and a.check:
        C = check_talk_track(Path(a.talk_track).read_text(encoding="utf-8", errors="replace"), registry, airtime, speakers)
        Path(a.check).write_text("\n".join(C) + "\n", encoding="utf-8")
    print(f"orals: {len(secs)} sections in {a.minutes} min, {len(speakers)} speakers, "
          f"{len(seen)} proposal numbers registered, {k} likely questions -> {a.script}")
    return 0


if __name__ == "__main__":
    main()
