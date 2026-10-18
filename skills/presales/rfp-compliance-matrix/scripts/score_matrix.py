#!/usr/bin/env python3
"""Score an extracted requirements CSV against a capability inventory -> compliance matrix.

Inputs
  requirements CSV (from extract_requirements.py; columns used):
    req_id, client_id, section, page, text, mdo_hint [, keyword, source_file]
  capabilities CSV (our inventory; one row per capability):
    capability_id, keywords, status, evidence, owner [, gap_condition, mitigation, category]
      keywords  : `||`-separated words/phrases matched against the requirement text
      status    : C (comply) or P (partial). A `C` with empty evidence is downgraded to P
                  (references/compliance-scoring.md §1). N is never produced by this script:
                  an unmatched requirement is Q (clarify) with a CQ id, so a human decides.
      owner     : named person who answers for this capability

Outputs
  --out matrix.csv   17 columns per assets/compliance-matrix-columns.md
  --gaps gaps.md     bottom line, mandatory gaps, clarification questions, bid gate
  --summary x.json   counts, mandatory C share, bid gate verdict and the open gate tests

Bid gate (references/compliance-scoring.md §3), computed only for the tests this script can
see: mandatory N count (always 0 here), mandatory C share, Q count. The other gate tests
(hidden mandatories, deadline feasibility, weighting, incumbent, strategic fit) are reported
as `[TO BE BASELINED — owner: bid manager]`; the verdict is therefore "provisional".

Usage:
    python3 -I score_matrix.py requirements.csv --capabilities caps.csv \
        --out matrix.csv --gaps gaps.md --summary bid-score.json [--min-overlap 0.5]

Exit codes: 0 ok; 1 bad input (missing file, missing columns, no rows). Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

MATRIX_COLS = ["req_id", "client_id", "section", "page", "text", "category", "mdo", "weight",
               "flags", "compliance", "evidence", "gap_condition", "mitigation", "owner",
               "response_section", "status", "clarification_id"]
REQ_COLS = {"req_id", "text"}
CAP_COLS = {"capability_id", "keywords", "status", "owner"}
TBD = "[TO BE BASELINED — owner: bid manager]"
WORD_RE = re.compile(r"[a-z0-9][a-z0-9+\-/.]*")


def read_csv(path: Path, required: set[str], label: str) -> list[dict]:
    if not path.is_file():
        sys.exit(f"error: {label} not found: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"error: {label} has no rows: {path}")
    missing = required - set(rows[0].keys())
    if missing:
        sys.exit(f"error: {label} missing columns: {sorted(missing)}")
    return rows


def tokens(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


def match(req_text: str, caps: list[dict], min_overlap: float):
    """Best capability by share of its keyword phrases found in the requirement."""
    rt = req_text.lower()
    rtoks = tokens(req_text)
    best, best_score = None, 0.0
    for cap in caps:
        kws = [k.strip().lower() for k in cap.get("keywords", "").split("||") if k.strip()]
        if not kws:
            continue
        hits = 0
        for kw in kws:
            if " " in kw:
                hits += kw in rt
            else:
                hits += kw in rtoks
        score = hits / len(kws)
        if score > best_score:
            best, best_score = cap, score
    if best is not None and best_score >= min_overlap:
        return best, best_score
    return None, best_score


def mdo_of(row: dict) -> str:
    v = (row.get("mdo_hint") or row.get("mdo") or "").strip().upper()[:1]
    return v if v in ("M", "D", "O") else "D"


def score(reqs: list[dict], caps: list[dict], min_overlap: float):
    matrix, cq_n = [], 0
    for r in reqs:
        cap, s = match(r.get("text", ""), caps, min_overlap)
        row = {c: "" for c in MATRIX_COLS}
        row.update({k: r.get(k, "") for k in ("req_id", "client_id", "section", "page", "text")})
        row["mdo"] = mdo_of(r)
        row["weight"] = r.get("weight") or TBD
        row["status"] = "drafted"
        if cap is None:
            cq_n += 1
            row["compliance"] = "Q"
            row["clarification_id"] = f"CQ-{cq_n:03d}"
            row["gap_condition"] = "no matching capability in inventory — confirm scope and intent"
            row["owner"] = TBD
            row["flags"] = "UNQ" if not re.search(r"\d", r.get("text", "")) else ""
        else:
            status = (cap.get("status") or "P").strip().upper()[:1]
            evidence = (cap.get("evidence") or "").strip()
            if status == "C" and not evidence:
                status = "P"
                row["gap_condition"] = "evidence not cited — C downgraded to P (scoring §1)"
            if status not in ("C", "P"):
                status = "P"
            row["compliance"] = status
            row["evidence"] = evidence
            row["owner"] = cap.get("owner") or TBD
            row["category"] = cap.get("category", "")
            if status == "P":
                row["gap_condition"] = row["gap_condition"] or cap.get("gap_condition") or TBD
                row["mitigation"] = cap.get("mitigation") or TBD
            row["flags"] = f"match={s:.2f}"
        matrix.append(row)
    return matrix


def gate(matrix: list[dict]) -> dict:
    mand = [r for r in matrix if r["mdo"] == "M"]
    m_c = sum(r["compliance"] == "C" for r in mand)
    m_n = sum(r["compliance"] == "N" for r in mand)
    m_q = sum(r["compliance"] == "Q" for r in mand)
    share = (m_c / len(mand)) if mand else None
    if m_n >= 1:
        verdict = "NO-BID"
    elif share is None:
        verdict = "BID-WITH-CONDITIONS"
    elif share >= 0.8 and m_q == 0:
        verdict = "BID"
    elif share >= 0.6:
        verdict = "BID-WITH-CONDITIONS"
    else:
        verdict = "NO-BID"
    return {
        "verdict": verdict + " (provisional)",
        "mandatory_total": len(mand), "mandatory_C": m_c, "mandatory_N": m_n, "mandatory_Q": m_q,
        "mandatory_C_share": round(share, 3) if share is not None else None,
        "open_gate_tests": {k: TBD for k in ("hidden_mandatories", "deadline_feasibility",
                                              "evaluation_weighting", "incumbent_signal",
                                              "strategic_fit")},
    }


def render_gaps(matrix: list[dict], g: dict) -> str:
    counts = {k: sum(r["compliance"] == k for r in matrix) for k in "CPNQ"}
    L = ["# Compliance gaps and bid gate", "",
         "## Bottom line",
         f"**{g['verdict']}** — {len(matrix)} requirements: C {counts['C']} · P {counts['P']} · "
         f"N {counts['N']} · Q {counts['Q']}. Mandatory C share: "
         f"{g['mandatory_C_share'] if g['mandatory_C_share'] is not None else 'n/a (no M rows)'} "
         f"({g['mandatory_C']}/{g['mandatory_total']}).",
         "", "Open gate tests (not computable from the matrix):",
         "| Test | Status |", "|---|---|"]
    L += [f"| {k.replace('_', ' ')} | {v} |" for k, v in g["open_gate_tests"].items()]
    L += ["", "## Mandatory gaps", "| req_id | client_id | compliance | gap | mitigation | owner |",
          "|---|---|---|---|---|---|"]
    gaps = [r for r in matrix if r["mdo"] == "M" and r["compliance"] in ("P", "N", "Q")]
    L += [f"| {r['req_id']} | {r['client_id']} | {r['compliance']} | {r['gap_condition']} | "
          f"{r['mitigation']} | {r['owner']} |" for r in gaps] or ["| — | | | none | | |"]
    L += ["", "## Clarification questions",
          "| CQ | Clause | Requirement (verbatim) | Why it matters (internal) |", "|---|---|---|---|"]
    qs = [r for r in matrix if r["compliance"] == "Q"]
    L += [f"| {r['clarification_id']} | {r['client_id'] or r['req_id']} | "
          f"{r['text'][:120].replace('|', '/')} | {r['gap_condition']} |" for r in qs] or ["| — | | none | |"]
    L += ["", "## Partials (all)", "| req_id | mdo | evidence | gap | owner |", "|---|---|---|---|---|"]
    L += [f"| {r['req_id']} | {r['mdo']} | {r['evidence']} | {r['gap_condition']} | {r['owner']} |"
          for r in matrix if r["compliance"] == "P"] or ["| — | | | none | |"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("requirements", type=Path, help="requirements CSV from extract_requirements.py")
    ap.add_argument("--capabilities", type=Path, required=True, help="capability inventory CSV")
    ap.add_argument("--out", type=Path, required=True, help="matrix CSV path")
    ap.add_argument("--gaps", type=Path, help="gaps/bid-gate Markdown path")
    ap.add_argument("--summary", type=Path, help="bid score JSON path")
    ap.add_argument("--min-overlap", type=float, default=0.5,
                    help="share of a capability's keywords that must hit (default 0.5)")
    a = ap.parse_args(argv)
    reqs = read_csv(a.requirements, REQ_COLS, "requirements CSV")
    caps = read_csv(a.capabilities, CAP_COLS, "capabilities CSV")
    matrix = score(reqs, caps, a.min_overlap)
    g = gate(matrix)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MATRIX_COLS)
        w.writeheader()
        w.writerows(matrix)
    if a.gaps:
        a.gaps.write_text(render_gaps(matrix, g), encoding="utf-8")
    if a.summary:
        counts = {k: sum(r["compliance"] == k for r in matrix) for k in "CPNQ"}
        a.summary.write_text(json.dumps({"requirements": len(matrix), "counts": counts, "gate": g},
                                        indent=2), encoding="utf-8")
    print(f"{len(matrix)} requirements scored -> {a.out}; gate: {g['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
