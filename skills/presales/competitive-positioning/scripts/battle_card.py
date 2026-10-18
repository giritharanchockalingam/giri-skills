#!/usr/bin/env python3
"""Battle card from evidence-rated capability, claim and concern CSVs.

    python3 -I scripts/battle_card.py our-capabilities.csv their-claims.csv concerns.csv \
        --out battle-card.md [--client "Acme"] [--alternative "Incumbent SI"]

our-capabilities.csv: capability, evidence, strength (1-5)
their-claims.csv:     claim, source, strength (1-5)      (their strength on that claim, as evidenced)
concerns.csv:         stakeholder, concern

Wedge = our capability with strength >= 4 that overlaps (shared keyword) a claim where their strength
<= 2 AND overlaps a stakeholder concern. Landmines = their claims rated >= 4 (do not attack) plus the
template's standing rules. Objection grid = one row per concern with acknowledge / reframe / proof /
ask-back: reframe and proof are pre-filled only from a matching capability's evidence, otherwise
`[TO BE BASELINED — owner: Bid manager]`. A blank evidence or source cell becomes the marker; nothing is
invented. Exit 1 on missing columns, strength outside 1-5 or non-numeric. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Bid manager]"
STOP = set("the a an and or of to in on for with our their we they your you is are be by at as from "
           "that this it its into over under than more less very can will not no any all has have had "
           "do does did but if then so such per via up out new old own same".split())


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_csv(path: str, cols: list[str]) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    if not rows:
        die(f"{p.name}: no data rows")
    missing = [c for c in cols if c not in rows[0]]
    if missing:
        die(f"{p.name}: missing columns {missing}")
    return rows


def strength(row: dict, where: str) -> int:
    raw = row.get("strength", "")
    if not re.fullmatch(r"[1-5]", raw):
        die(f"{where}: strength must be 1-5, got {raw!r}")
    return int(raw)


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in STOP}


def overlap(a: str, b: str) -> set[str]:
    return words(a) & words(b)


def main() -> int:
    ap = argparse.ArgumentParser(description="our-capabilities + their-claims + concerns -> battle-card.md")
    ap.add_argument("ours"); ap.add_argument("theirs"); ap.add_argument("concerns")
    ap.add_argument("--out", required=True)
    ap.add_argument("--client", default="<Client>")
    ap.add_argument("--alternative", default="<Alternative>")
    a = ap.parse_args()
    ours = read_csv(a.ours, ["capability", "evidence", "strength"])
    theirs = read_csv(a.theirs, ["claim", "source", "strength"])
    concerns = read_csv(a.concerns, ["stakeholder", "concern"])
    for i, r in enumerate(ours, 1):
        r["s"] = strength(r, f"our-capabilities row {i}"); r["evidence"] = r["evidence"] or TBD
    for i, r in enumerate(theirs, 1):
        r["s"] = strength(r, f"their-claims row {i}"); r["source"] = r["source"] or f"{TBD} (hypothesis)"

    wedges, near = [], []
    for o in ours:
        if o["s"] < 4:
            continue
        for t in theirs:
            if t["s"] > 2 or not overlap(o["capability"], t["claim"]):
                continue
            hits = [c for c in concerns if overlap(o["capability"] + " " + t["claim"], c["concern"])]
            (wedges if hits else near).append({"ours": o, "theirs": t, "concerns": hits})
    landmines = [t for t in theirs if t["s"] >= 4]
    grid = []
    for c in concerns:
        best = max(ours, key=lambda o: (len(overlap(o["capability"] + " " + o["evidence"], c["concern"])), o["s"]))
        hit = overlap(best["capability"] + " " + best["evidence"], c["concern"])
        grid.append({"concern": c, "cap": best if hit else None})

    L = [f"# Battle Card — {a.client} — vs {a.alternative}", "",
         "**INTERNAL — do not distribute.** Competitor claims are evidence-rated; unsourced claims are hypotheses.", "",
         "## Bottom line",
         (f"{len(wedges)} wedge(s) found where we are strong (≥4), they are weak (≤2) and a stakeholder cares; "
          f"{len(landmines)} landmine(s) where they are strong (≥4)." if wedges else
          f"No wedge found on the evidence supplied ({len(ours)} capabilities, {len(theirs)} claims, "
          f"{len(concerns)} concerns): reshape the pursuit or qualify out — {TBD}."), "",
         "## Our capabilities (as evidenced)", "| Capability | Strength | Evidence |", "|---|---|---|"]
    L += [f"| {o['capability']} | {o['s']} | {o['evidence']} |" for o in sorted(ours, key=lambda o: -o["s"])]
    L += ["", "## Their claims (evidence-rated)", "| Claim | Their strength | Source |", "|---|---|---|"]
    L += [f"| {t['claim']} | {t['s']} | {t['source']} |" for t in sorted(theirs, key=lambda t: -t["s"])]
    L += ["", "## Wedge", "| Wedge (our capability) | Their weak claim | Stakeholder concern it answers | Why we win (evidence) |",
          "|---|---|---|---|"]
    L += [f"| {w['ours']['capability']} | {w['theirs']['claim']} (them: {w['theirs']['s']}) | "
          f"{'; '.join(c['stakeholder'] + ': ' + c['concern'] for c in w['concerns'])} | {w['ours']['evidence']} |"
          for w in wedges] or [f"| none on current evidence | | | {TBD} |"]
    if near:
        L += ["", "Near-wedges (we are strong, they are weak, but no stated concern yet — ask in discovery):"]
        L += [f"- {w['ours']['capability']} vs \"{w['theirs']['claim']}\"" for w in near]
    L += ["", "## Landmines", "| Do not | Because | Instead |", "|---|---|---|",
          "| Name the alternative in any client document | it signals fear and invites comparison on their terms | ghost lines in the proposal |",
          "| Disparage the platform the client already owns | the sponsor chose it | position around the seams |"]
    L += [f"| Attack their claim \"{t['claim']}\" | rated {t['s']}/5 on {t['source']} | concede it; redirect to the wedge |" for t in landmines]
    L += ["", "## Objection handling", "| Objection (stakeholder) | Acknowledge | Reframe | Proof (cleared ref) | Ask-back |",
          "|---|---|---|---|---|"]
    for g in grid:
        c, cap = g["concern"], g["cap"]
        ack = f"\"{c['concern']}\" is a fair concern — {c['stakeholder']} owns the outcome."
        reframe = f"Position on: {cap['capability']}" if cap else TBD
        proof = cap["evidence"] if cap and cap["evidence"] != TBD else TBD
        ask = f"What would you need to see to be confident on \"{c['concern']}\"?"
        L.append(f"| {c['concern']} ({c['stakeholder']}) | {ack} | {reframe} | {proof} | {ask} |")
    L += ["", "## Ghost lines (for proposal-writer)", "| Risk stated generally | How we remove it | Where it goes |", "|---|---|---|"]
    L += [f"| {w['theirs']['claim']} — stated as a program risk, no name | {w['ours']['capability']} | approach / why-us |" for w in wedges] \
        or [f"| {TBD} | | |"]
    L += ["", "## Intelligence gaps", "| Gap | Why it matters | Owner | By |", "|---|---|---|---|"]
    L += [f"| Source for \"{t['claim']}\" | unsourced claim is a hypothesis | {TBD} | |" for t in theirs if t["source"].startswith(TBD)]
    L += [f"| Evidence for \"{o['capability']}\" | we rate it {o['s']} with no proof | {TBD} | |" for o in ours if o["evidence"] == TBD]
    L += [f"| Proof for objection \"{g['concern']['concern']}\" | no capability evidence matches | {TBD} | |" for g in grid if not g["cap"]]
    if L[-1].startswith("|---"):
        L.append("| none | | | |")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"battle card: {len(wedges)} wedges, {len(landmines)} landmines, {len(grid)} objections -> {a.out}")
    return 0


if __name__ == "__main__":
    main()
