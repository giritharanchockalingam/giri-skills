#!/usr/bin/env python3
"""Assessment readout without a model step: the scoring and TCO summaries, assembled on the readout layout.

    python3 -I scripts/readout_draft.py --scoring scoring-summary.md --tco tco-summary.md \
        --client Acme --out readout.md

Used when the LLM readout step is skipped (draft only). Every figure is copied verbatim from the two
summaries this skill's scripts wrote (so `numbers_trace_to` holds by construction); nothing is
computed here. Sections (assets/assessment-readout-template.md): Bottom line (the summaries' own
headline lines), Scoring results (band table, unknown-factor and retirement lines), Wave plan (wave
table), TCO (the TCO summary, headings demoted), Risks and Next steps (owned to-be-baselined markers,
plus a risk line when interfaces carry unknown factors or payback is outside the horizon). Labelled
as a draft. Exit 1 when a summary is missing or lacks its tables. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Migration lead]"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def tables(text: str) -> list[list[str]]:
    """Consecutive `|` lines, as blocks."""
    out, cur = [], []
    for ln in text.splitlines():
        if ln.startswith("|"):
            cur.append(ln)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def line_starting(text: str, prefix: str) -> str:
    return next((ln.strip() for ln in text.splitlines() if ln.strip().startswith(prefix)), "")


def main() -> int:
    ap = argparse.ArgumentParser(description="scoring + TCO summaries -> readout.md (no model step)")
    ap.add_argument("--scoring", required=True, help="scoring-summary.md (score_inventory.py --summary)")
    ap.add_argument("--tco", required=True, help="tco-summary.md (tco.py --summary)")
    ap.add_argument("--client", default="<Client>")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sp, tp = Path(a.scoring), Path(a.tco)
    for p in (sp, tp):
        if not p.is_file():
            die(f"summary not found: {p}")
    scoring, tco = sp.read_text(encoding="utf-8"), tp.read_text(encoding="utf-8")
    blocks = tables(scoring)
    bands = next((b for b in blocks if b[0].startswith("| Band")), None)
    waves = next((b for b in blocks if b[0].startswith("| Wave")), None)
    if not bands or not waves:
        die(f"{sp.name} lacks the band and wave tables (expected score_inventory.py --summary output)")
    unknown = line_starting(scoring, "Interfaces with >=1 unknown factor")
    retire = line_starting(scoring, "Retirement candidates")
    payback = line_starting(tco, "Payback:")
    if not payback:
        die(f"{tp.name} lacks the 'Payback:' line (expected tco.py --summary output)")
    tco_body = [re.sub(r"^(#+) ", lambda m: "#" * (len(m.group(1)) + 1) + " ", ln)
                for ln in tco.splitlines() if not ln.startswith("# ")]
    risks = []
    m = re.search(r"unknown factor: (\d+)", unknown)
    if m and int(m.group(1)) > 0:
        risks.append(f"| {unknown} | scores and waves may move once the unknowns are baselined | {TBD} |")
    if "not within horizon" in payback:
        risks.append(f"| {payback} | the business case does not pay back inside the TCO horizon | {TBD} |")
    risks.append(f"| Delivery and cutover risks for the wave plan | {TBD} | {TBD} |")
    out = [f"# Migration Assessment — {a.client} — draft", "",
           "> Script draft — the model step was not run (draft only): figures are copied from the scoring and TCO "
           "summaries; recommendations are owned markers.", "",
           "## Bottom line", f"- {payback}", f"- {retire}" if retire else "", f"- {unknown}" if unknown else "",
           f"- Recommendation: {TBD}", "",
           "## Scoring results"] + bands + ["", unknown, retire, "", "## Wave plan"] + waves + \
          ["", "## TCO"] + tco_body + ["", "## Risks", "| Risk | Effect | Owner |", "|---|---|---|"] + risks + \
          ["", "## Next steps", "| Action | Owner | Date |", "|---|---|---|",
           f"| Validate band and wave assignments with the client architects | {TBD} | {TBD} |",
           f"| Confirm rate inputs and sources | {TBD} | {TBD} |"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(x for x in out if x is not None) + "\n", encoding="utf-8")
    print(f"readout draft -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
