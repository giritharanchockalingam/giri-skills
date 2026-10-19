#!/usr/bin/env python3
"""Map JD competencies to story-bank stories and build the prep pack — the TRUTH LOCK made executable.

    python3 -I scripts/prep.py --jd jd.txt --stories story-bank.md --round panel \
        --competencies references/competency-map.md --questions references/question-bank.md \
        --ask references/questions-to-ask.md --plan-template assets/90-day-plan.md --out-dir ./out

story-bank.md: `## SB-nn — Title (C4 Transformation, C1 Strategy)` headers with S/T/A/R/R+ lines
(layout: assets/story-bank.example.md). Competency codes C1..C10 come from the competency map.

Writes, deterministically:
  * competency-map.csv — competency, status (mapped|GAP), name, in_jd, jd_hits, jd_evidence, story_ids.
    A competency with no story in the bank is GAP. Nothing is invented to fill it;
  * prep-pack.md — per competency (JD emphasis first): the stories by id, quoted from the bank; the
    likely questions for the round type, each paired with story ids or GAP; the gaps and how to
    handle them honestly;
  * questions-to-ask.md — the question sets for the interviewers of this round type;
  * 90-day-plan.md — the plan skeleton with JD-derived focus headings; every unknown is
    `[TO BE BASELINED — owner: …]` with a named owner.
Next round (--previous-round debrief.md: your notes from the earlier round): the SB ids you told and the
questions they asked (lines ending in `?`) are read; prep-pack.md gains "Since the last round" — stories
already told (do not retell them to the same people), competencies where every story was told (bring
a fresh story or new depth), competencies not shown yet, and the questions already asked (expect
follow-ups) — and each told story is marked in "Stories by competency".
Exit 1 on a missing/empty file, a story bank without SB ids, or a competency map without C-codes.
Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROUNDS = {
    "recruiter": {"section": "Round 1", "ask": ["Recruiter"], "plan": False},
    "hiring-manager": {"section": "Round 2", "ask": ["Hiring manager"], "plan": True},
    "panel": {"section": "Round 3", "ask": ["Panel — peers", "Panel — direct reports / architects"], "plan": False},
    "executive": {"section": "Round 4", "ask": ["CIO / CTO", "CEO / business executive"], "plan": True},
    "case": {"section": "Round 5", "ask": ["CIO / CTO", "CEO / business executive"], "plan": True},
}
STORY_HEAD_RE = re.compile(r"^##\s+(SB-\d+)\s*[—–-]\s*(.*?)\s*(?:\(([^)]*)\))?\s*$")
CODE_RE = re.compile(r"\bC\d+\b")
COMP_ROW_RE = re.compile(r"^\|\s*(C\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")
TBD = "[TO BE BASELINED — owner: {owner}]"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    text = p.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        die(f"file is empty: {p}")
    return text


# ------------------------------------------------------------------ parsing

def load_competencies(text: str) -> list[dict]:
    comps = []
    for line in text.splitlines():
        m = COMP_ROW_RE.match(line)
        if not m:
            continue
        code, name, _probe, phrases_cell = m.groups()
        phrases = []
        for q in re.findall(r'"([^"]+)"', phrases_cell):
            phrases += [p.strip() for p in q.split("/") if p.strip()]
        comps.append({"code": code, "name": name.strip(), "phrases": phrases})
    if not comps:
        die("competency map has no `| Cn | name | ... |` rows")
    return comps


def load_stories(text: str) -> list[dict]:
    stories, cur = [], None
    for raw in text.splitlines():
        m = STORY_HEAD_RE.match(raw.strip())
        if m:
            cur = {"id": m.group(1), "title": m.group(2).strip(), "codes": CODE_RE.findall(m.group(3) or ""),
                   "lines": []}
            stories.append(cur)
            continue
        if cur is not None and raw.strip().startswith("- "):
            cur["lines"].append(raw.strip()[2:])
    if not stories:
        die("story bank has no `## SB-nn — Title (C-codes)` headers (see assets/story-bank.example.md)")
    return stories


def jd_hits(jd: str, phrases: list[str]) -> list[tuple[str, str]]:
    """(phrase, JD line) for every phrase found on a JD line, word-bounded, case-insensitive."""
    hits, seen = [], set()
    lines = [re.sub(r"^[-*•\d.)]+\s+", "", ln.strip()) for ln in jd.splitlines() if ln.strip()]
    for ph in phrases:
        rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(ph) + r"(?![A-Za-z0-9])", re.I)
        for ln in lines:
            if rx.search(ln) and (ph.lower(), ln) not in seen:
                seen.add((ph.lower(), ln))
                hits.append((ph, ln))
    return hits


def evidence(hits: list[tuple[str, str]]) -> str:
    """One entry per JD line: `phrase1, phrase2: "line"`."""
    by_line: dict[str, list[str]] = {}
    for ph, ln in hits:
        by_line.setdefault(ln, []).append(ph)
    return " | ".join(f'{", ".join(phs)}: "{ln[:90]}"' for ln, phs in list(by_line.items())[:3])


def sections(text: str, level: str = "## ") -> dict[str, list[str]]:
    out, cur = {}, None
    for ln in text.splitlines():
        if ln.startswith(level) and not ln.startswith(level + "#"):
            cur = ln[len(level):].strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(ln)
    return out


def table_rows(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    header, rows = [], []
    for ln in lines:
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not header:
            header = cells
        elif all(set(c) <= {"-", ":"} for c in cells):
            continue
        else:
            rows.append(cells)
    return header, rows


# ------------------------------------------------------------------ build

def build_map(comps, stories, jd) -> list[dict]:
    rows = []
    for c in comps:
        hits = jd_hits(jd, c["phrases"])
        ids = [s["id"] for s in stories if c["code"] in s["codes"]]
        rows.append({"competency": c["code"], "status": "mapped" if ids else "GAP", "name": c["name"],
                     "in_jd": "yes" if hits else "no", "jd_hits": len(hits),
                     "jd_evidence": evidence(hits),
                     "story_ids": ";".join(ids)})
    rows.sort(key=lambda r: (-r["jd_hits"], int(r["competency"][1:])))
    return rows


def write_map(rows, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["competency", "status", "name", "in_jd", "jd_hits", "jd_evidence", "story_ids"])
        w.writeheader()
        w.writerows(rows)


def round_questions(qbank: str, round_key: str) -> tuple[list[str], list[list[str]], list[str]]:
    key = ROUNDS[round_key]["section"]
    sec = next((v for k, v in sections(qbank).items() if k.startswith(key)), None)
    if sec is None:
        die(f"question bank has no '## {key}' section")
    header, rows = table_rows(sec)
    extra = [ln.strip() for ln in sec if ln.strip() and not ln.strip().startswith("|")]
    return header, rows, extra


def write_pack(rows, stories, jd, round_key, qbank, path: Path, jd_title: str, debrief: str = "") -> None:
    by_code = {r["competency"]: r for r in rows}
    story_by_id = {s["id"]: s for s in stories}
    gaps = [r for r in rows if r["status"] == "GAP"]
    since, told = since_last_round(debrief, rows, stories) if debrief else ([], set())
    L = [f"# Prep pack — {jd_title} — {round_key} round", "",
         "TRUTH LOCK: every story below is quoted from the story bank by id. A competency marked GAP has no "
         "story; prepare an honest 'closest experience and how I would approach it' answer or add a true "
         "story to the bank. Nothing here is invented.", "",
         "## Competency → story map (JD emphasis first)", "",
         "| Competency | Status | In JD | JD evidence | Stories |", "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['competency']} {r['name']} | {r['status']} | {r['in_jd']} ({r['jd_hits']}) | "
                 f"{r['jd_evidence'] or '—'} | {r['story_ids'].replace(';', ', ') or 'GAP'} |")
    L += ["", "## Stories by competency", ""]
    for r in rows:
        L.append(f"### {r['competency']} {r['name']} — {r['status']}")
        L.append("")
        if r["status"] == "GAP":
            L += [f"**GAP — no story in the bank for {r['competency']}.** Do not invent one. Options: (a) interview "
                  "the user for a true example and add it to the bank; (b) prepare the closest-experience answer.", ""]
            continue
        for sid in r["story_ids"].split(";"):
            s = story_by_id[sid]
            L.append(f"**[{sid}] {s['title']}** (tagged {', '.join(s['codes'])})"
                     + (" — told in the last round" if sid in told else ""))
            L.append("")
            L += [f"- {ln}" for ln in s["lines"]]
            L.append("")
    header, qrows, extra = round_questions(qbank, round_key)
    L += [f"## Likely questions — {round_key} ({ROUNDS[round_key]['section']})", "",
          "| " + " | ".join(header) + " | Story ids |", "|" + "---|" * (len(header) + 1)]
    for q in qrows:
        codes = CODE_RE.findall(" ".join(q))
        if codes:
            ids = []
            for code in codes:
                ids += (by_code.get(code, {}).get("story_ids", "") or "").split(";")
            ids = [i for i in ids if i]
            link = ", ".join(dict.fromkeys(ids)) if ids else f"GAP ({', '.join(codes)})"
        else:
            link = "— (facts from master résumé / JD)"
        L.append("| " + " | ".join(q) + f" | {link} |")
    if extra:
        L += [""] + extra
    L += since
    L += ["", "## Gaps and how to handle them honestly", ""]
    if not gaps:
        L.append("None — every competency has at least one story in the bank.")
    for g in gaps:
        where = "emphasised in the JD" if g["in_jd"] == "yes" else "not emphasised in the JD"
        L.append(f"- **{g['competency']} {g['name']}** ({where}): say so if asked; offer the closest true "
                 f"experience and how you would approach it. Owner: user (add a true story or accept the gap).")
    L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


SB_RE = re.compile(r"\bSB-\d+\b")


def since_last_round(debrief: str, rows, stories) -> tuple[list[str], set[str]]:
    known = {s_["id"] for s_ in stories}
    told = [x for x in dict.fromkeys(SB_RE.findall(debrief))]
    unknown = [x for x in told if x not in known]
    told_set = {x for x in told if x in known}
    asked = [re.sub(r"^[-*•\s]*(?:asked:\s*)?", "", ln.strip(), flags=re.I) for ln in debrief.splitlines()
             if ln.strip().endswith("?")]
    L = ["", "## Since the last round", "",
         f"Stories already told: {', '.join(sorted(told_set)) or 'none recorded'} — do not retell them to the same "
         "interviewers; reference them in one line and go deeper or use another story."]
    if unknown:
        L.append(f"Not in the story bank (check the id): {', '.join(unknown)}.")
    spent = [r for r in rows if r["status"] == "mapped" and set(r["story_ids"].split(";")) <= told_set]
    fresh = [r for r in rows if r["status"] == "mapped" and r["in_jd"] == "yes"
             and not set(r["story_ids"].split(";")) & told_set]
    L += ["", "| Competency | Situation | Stories |", "|---|---|---|"]
    L += [f"| {r['competency']} {r['name']} | every story already told — bring new depth | {r['story_ids'].replace(';', ', ')} |"
          for r in spent]
    L += [f"| {r['competency']} {r['name']} | in the JD, not shown yet — lead with it | {r['story_ids'].replace(';', ', ')} |"
          for r in fresh]
    if not spent and not fresh:
        L.append("| — | nothing spent, nothing outstanding | |")
    L += ["", "Questions already asked (expect follow-ups, keep answers consistent):", ""]
    L += [f"- {q}" for q in asked] or ["- none recorded"]
    return L, told_set


def write_ask(ask_text: str, round_key: str, path: Path) -> None:
    secs = sections(ask_text)
    L = [f"# Questions to ask — {round_key} round", "",
         "Pick 6–8. Ask the ones whose answers change your decision; never ask what the website answers.", ""]
    for name in ROUNDS[round_key]["ask"]:
        body = secs.get(name)
        if body is None:
            die(f"questions-to-ask has no '## {name}' section")
        L += [f"## {name}", ""] + [ln for ln in body if ln.strip()] + [""]
    if "Questions not to ask" in secs:
        L += ["## Questions not to ask", ""] + [ln for ln in secs["Questions not to ask"] if ln.strip()] + [""]
    path.write_text("\n".join(L), encoding="utf-8")


def write_plan(template: str, rows, jd_title: str, jd: str, path: Path) -> None:
    text = template.replace("<Role>, <Company>", jd_title).replace("<Role>", jd_title).replace("<Company>", jd_title)
    text = text.replace("[TO BE BASELINED]", TBD.format(owner="Me"))
    # JD lines that look like mandate statements feed the Mandate table; the rest is TBD with an owner
    sentences = []
    for ln in jd.splitlines():
        ln = re.sub(r"^[-*•\d.)]+\s+", "", ln.strip())
        sentences += [s_.strip() for s_ in re.split(r"(?<=[.;])\s+", ln) if s_.strip()]
    outcome = next((s_ for s_ in sentences if re.search(r"\b(owns?|leads?|accountable|responsible for|deliver)\b", s_, re.I)), "")
    scope = next((s_ for s_ in sentences if re.search(r"\$\d|team of \d|\d+\s*(?:people|engineers|staff)|budget", s_, re.I)), "")
    fills = {"Primary outcome": outcome, "Scope (teams, budget, platforms)": scope}
    out = []
    for ln in text.splitlines():
        if ln.startswith("|") and not set(ln.strip("| ")) <= {"-", "|", " "}:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            label = cells[0]
            if label in fills and len(cells) >= 2 and not cells[1]:
                cells[1] = f"{fills[label][:120]} (JD)" if fills[label] else TBD.format(owner="Hiring manager")
                if len(cells) >= 3 and not cells[2]:
                    cells[2] = "Hiring manager"
            elif label in ("Top 3 stakeholders", "Known constraints") and len(cells) >= 2 and not cells[1]:
                cells[1] = TBD.format(owner="Hiring manager")
                if len(cells) >= 3 and not cells[2]:
                    cells[2] = "Hiring manager"
            elif label == "" and any(c for c in cells):
                pass
            elif not any(cells):
                cells = [TBD.format(owner="Me")] + [""] * (len(cells) - 1)
            ln = "| " + " | ".join(cells) + " |"
        ln = re.sub(r":\s*___\s*$", f": {TBD.format(owner='Hiring manager')}", ln)
        out.append(ln)
    text = "\n".join(out).replace("owner: Candidate]", "owner: Me]")
    # JD-derived focus headings: top competencies by JD emphasis
    focus = ["", "## Focus areas from the JD", ""]
    top = [r for r in rows if r["in_jd"] == "yes"][:4]
    if not top:
        focus.append(f"No competency phrases found in the JD — {TBD.format(owner='Me')}")
    for r in top:
        focus += [f"### {r['competency']} {r['name']}", ""]
        for part in r["jd_evidence"].split(" | "):
            focus.append(f"- {part}")
        focus.append(f"- Stories: {r['story_ids'].replace(';', ', ') or 'GAP — no story in the bank'}")
        focus.append("")
    text = text.rstrip("\n") + "\n" + "\n".join(focus) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="JD competencies → story-bank map, prep pack, questions, 90-day plan")
    ap.add_argument("--jd", required=True)
    ap.add_argument("--stories", required=True, help="story bank with SB-nn ids and competency tags")
    ap.add_argument("--round", required=True, choices=sorted(ROUNDS))
    ap.add_argument("--competencies", default="references/competency-map.md")
    ap.add_argument("--questions", default="references/question-bank.md")
    ap.add_argument("--ask", default="references/questions-to-ask.md")
    ap.add_argument("--plan-template", default="assets/90-day-plan.md")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--previous-round", default="", help="your debrief notes from the earlier round")
    a = ap.parse_args()
    jd = read(a.jd)
    stories = load_stories(read(a.stories))
    comps = load_competencies(read(a.competencies))
    qbank, ask, plan = read(a.questions), read(a.ask), read(a.plan_template)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jd_title = next((ln.strip() for ln in jd.splitlines() if ln.strip()), "role")[:100]
    rows = build_map(comps, stories, jd)
    write_map(rows, out / "competency-map.csv")
    write_pack(rows, stories, jd, a.round, qbank, out / "prep-pack.md", jd_title,
               read(a.previous_round) if a.previous_round else "")
    write_ask(ask, a.round, out / "questions-to-ask.md")
    write_plan(plan, rows, jd_title, jd, out / "90-day-plan.md")
    n_gap = sum(r["status"] == "GAP" for r in rows)
    print(f"{len(rows)} competencies: {len(rows) - n_gap} mapped, {n_gap} GAP; {len(stories)} stories; "
          f"round={a.round}; wrote 4 files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
