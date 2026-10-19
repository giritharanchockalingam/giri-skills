#!/usr/bin/env python3
"""Map an AI system's evidence to NIST AI RMF 1.0 subcategories; report coverage and gaps.

Reads the 72-subcategory catalogue in assets/nist-ai-rmf-1.0.csv (NIST AI 100-1) and an
evidence CSV, writes every subcategory with its status, evidence and owner, computes coverage
per function as (implemented + 0.5 x partial) / applicable (applicable = all - not_applicable;
unlisted subcategories count as missing), and optionally gates on a minimum overall coverage.
With --obligations (obligations.csv from eu-ai-act-classifier) it lists open AI Act
obligations and whether their mapped subcategories (assets/aiact-nist-crosswalk.csv, the
skill's own mapping) are fully, partly or not at all supported by evidence.

Usage:
  python3 -I map_controls.py --evidence evidence.csv [--min-coverage 0.6] [--obligations obligations.csv] --out-dir OUT
  python3 -I map_controls.py --verify OUT/coverage.json     (re-checks a finished run)

Inputs:
  evidence     CSV subcategory_id,status,evidence,owner; status implemented|partial|planned|not_applicable.
               Ids as in NIST AI 100-1 ("GOVERN 1.1", case and spacing normalised). '#' lines are comments.
  min-coverage fraction 0-1; overall coverage below it fails the run (exit 1).
  obligations  CSV with obligation_id,article,status (eu-ai-act-classifier output).

Outputs (in --out-dir): controls.csv, coverage.json, controls-report.md.
Exit codes: 0 written (and gate met if given) · 1 coverage below --min-coverage, or unknown
subcategory ids in the evidence (outputs still written), or --verify failure · 2 invalid input.
Stdlib only; no network.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CATALOGUE = SKILL_DIR / "assets" / "nist-ai-rmf-1.0.csv"
CROSSWALK = SKILL_DIR / "assets" / "aiact-nist-crosswalk.csv"
TBD = "[TO BE BASELINED — owner: AI risk lead]"
FUNCTIONS = ("GOVERN", "MAP", "MEASURE", "MANAGE")
STATUSES = ("implemented", "partial", "planned", "not_applicable")
GAP_STATUSES = ("partial", "planned", "missing")
CLOSED_OBLIGATION = ("done", "not_applicable")
CTRL_COLS = ["subcategory_id", "function", "category", "status", "evidence", "owner", "gap", "note"]


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")


def csv_safe(v) -> str:
    """OWASP CSV-injection guard: prefix a formula-leading text cell with a single quote (numbers untouched)."""
    s = "" if v is None else str(v)
    if s.startswith(_FORMULA_LEAD) and not _NUMBER.fullmatch(s):
        return "'" + s
    return s


def read_csv(path: Path, what: str) -> list[dict]:
    if not path.is_file():
        raise InputError(f"{what} file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        raise InputError(f"{what} file {path.name} is not a UTF-8 text CSV ({e.reason} at byte {e.start}); "
                         "save it as CSV UTF-8") from None
    if "\x00" in text:
        raise InputError(f"{what} file {path.name} is not a text CSV (contains NUL bytes)")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise InputError(f"{what} CSV is empty (needs a header row)")
    try:
        return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None}
                for r in csv.DictReader(io.StringIO("\n".join(lines)))], lines[0]
    except csv.Error as e:
        raise InputError(f"{what} file {path.name}: malformed CSV ({e})") from None


def norm_id(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().upper())


def load_catalogue() -> list[dict]:
    rows, _ = read_csv(CATALOGUE, "catalogue")
    return rows


def load_evidence(path: Path, known: set[str]) -> tuple[dict, list[dict]]:
    rows, header = read_csv(path, "evidence")
    cols = [c.strip() for c in next(csv.reader([header]))]
    for col in ("subcategory_id", "status", "evidence", "owner"):
        if col not in cols:
            raise InputError(f"evidence CSV needs columns subcategory_id,status,evidence,owner (missing {col})")
    ev, errors, seen = {}, [], set()
    for i, r in enumerate(rows, start=2):
        sid, st = norm_id(r["subcategory_id"]), r["status"].lower()
        if not sid:
            raise InputError(f"evidence line {i}: blank subcategory_id")
        if st == "" and not r["evidence"] and sid in known:
            continue  # unfilled template row: counted as missing
        if st not in STATUSES:
            raise InputError(f"evidence line {i}: status must be one of {STATUSES}, got {r['status']!r}")
        if sid in seen:
            raise InputError(f"evidence line {i}: duplicate subcategory_id {sid!r}")
        seen.add(sid)
        rec = {"status": st, "evidence": r["evidence"], "owner": r["owner"]}
        if sid in known:
            ev[sid] = rec
        else:
            errors.append({"subcategory_id": r["subcategory_id"], "line": i, **rec})
    return ev, errors


def parse_fraction(s: str | None):
    if s is None or s == "":
        return None
    try:
        v = float(s)
    except ValueError:
        raise InputError(f"--min-coverage must be a fraction between 0 and 1, got {s!r}") from None
    if not 0 <= v <= 1:
        raise InputError(f"--min-coverage must be between 0 and 1, got {s!r}")
    return v


def coverage(counts: dict):
    applicable = sum(counts[k] for k in ("implemented", "partial", "planned", "missing"))
    if applicable == 0:
        return None
    return round((counts["implemented"] + 0.5 * counts["partial"]) / applicable, 3)


def uncited(r: dict) -> bool:
    return r["status"] in ("implemented", "partial") and not r["evidence"]


def coverage_evidenced(sel: list[dict]):
    """Gate basis: implemented/partial claims with no evidence cited get no credit."""
    counts = {k: sum(1 for r in sel if r["status"] == k and not (k in ("implemented", "partial") and not r["evidence"]))
              for k in ("implemented", "partial")}
    counts["planned"] = sum(1 for r in sel if r["status"] == "planned")
    counts["missing"] = sum(1 for r in sel if r["status"] == "missing" or uncited(r))
    return coverage(counts)


def crosswalk_for(oid: str, xw: list[dict]):
    for r in xw:
        key = r["obligation_id"]
        if key == oid or (key.endswith("*") and oid.startswith(key[:-1])):
            return r
    return None


def map_obligations(path: Path, controls: dict) -> list[dict]:
    rows, header = read_csv(path, "obligations")
    cols = [c.strip() for c in next(csv.reader([header]))]
    for col in ("obligation_id", "article", "status"):
        if col not in cols:
            raise InputError(f"obligations CSV needs columns obligation_id,article,status (missing {col})")
    xw, _ = read_csv(CROSSWALK, "crosswalk")
    out = []
    for r in rows:
        if r["status"].lower() in CLOSED_OBLIGATION:
            continue
        x = crosswalk_for(r["obligation_id"], xw)
        subs = x["subcategory_ids"].split(";") if x else []
        st = {s: controls[s]["status"] for s in subs if s in controls}
        if not x:
            support = "no crosswalk entry"
        elif all(st.get(s) in ("implemented", "not_applicable") for s in subs) and any(v == "implemented" for v in st.values()):
            support = "supported"
        elif any(v in ("implemented", "partial") for v in st.values()):
            support = "partial"
        else:
            support = "none"
        out.append({"obligation_id": r["obligation_id"], "article": r["article"], "status": r["status"],
                    "applies_from": r.get("applies_from", ""), "subcategories": subs,
                    "subcategory_status": [f"{s}: {st.get(s, 'missing')}" for s in subs], "support": support})
    return out


def build(cat: list[dict], ev: dict, errors: list[dict], min_cov, obligations_path: Path | None) -> tuple[dict, list[dict]]:
    controls, rows = {}, []
    for c in cat:
        sid = c["subcategory_id"]
        e = ev.get(sid, {"status": "missing", "evidence": "", "owner": ""})
        notes = []
        if e["status"] in ("implemented", "partial") and not e["evidence"]:
            notes.append("no evidence cited")
        if e["status"] == "not_applicable" and not e["evidence"]:
            notes.append("no justification for not_applicable")
        if e["status"] == "missing":
            notes.append("not in evidence input")
        row = {"subcategory_id": sid, "function": c["function"], "category": c["category"], "status": e["status"],
               "evidence": e["evidence"], "owner": e["owner"] or TBD,
               "gap": "yes" if e["status"] in GAP_STATUSES else "no", "note": "; ".join(notes)}
        rows.append(row)
        controls[sid] = row
    for er in errors:
        rows.append({"subcategory_id": er["subcategory_id"], "function": "ERROR", "category": "", "status": "error",
                     "evidence": f"unknown subcategory id (not in NIST AI RMF 1.0), evidence line {er['line']}",
                     "owner": er["owner"] or TBD, "gap": "n/a", "note": f"input status was {er['status']}"})
    per_fn = {}
    for fn in FUNCTIONS + ("ALL",):
        sel = [r for r in rows if r["function"] != "ERROR" and (fn == "ALL" or r["function"] == fn)]
        counts = {k: sum(1 for r in sel if r["status"] == k) for k in ("implemented", "partial", "planned", "not_applicable", "missing")}
        counts["total"] = len(sel)
        counts["applicable"] = counts["total"] - counts["not_applicable"]
        counts["coverage"] = coverage(counts)
        counts["uncited_claims"] = sum(1 for r in sel if uncited(r))
        counts["coverage_evidenced"] = coverage_evidenced(sel)
        per_fn[fn] = counts
    overall = per_fn["ALL"]["coverage_evidenced"]
    gate = None
    if min_cov is not None:
        gate = "pass" if overall is not None and overall >= min_cov else "fail"
    obl = map_obligations(obligations_path, controls) if obligations_path else None
    result = {
        "framework": "NIST AI RMF 1.0 (NIST AI 100-1)",
        "subcategories_in_catalogue": len(cat),
        "formula": "coverage = (implemented + 0.5 * partial) / (total - not_applicable); unlisted = missing",
        "gate_basis": "coverage_evidenced: as coverage, but implemented/partial claims with no evidence cited get no credit",
        "functions": {fn: per_fn[fn] for fn in FUNCTIONS},
        "overall": per_fn["ALL"],
        "min_coverage": min_cov,
        "gate": gate if gate else "not set",
        "gaps": sum(1 for r in rows if r["gap"] == "yes"),
        "gaps_without_owner": sum(1 for r in rows if r["gap"] == "yes" and r["owner"] == TBD),
        "claims_without_evidence": sorted(r["subcategory_id"] for r in rows if "no evidence cited" in r["note"]),
        "na_without_justification": sorted(r["subcategory_id"] for r in rows if "no justification" in r["note"]),
        "input_errors": [{"subcategory_id": e["subcategory_id"], "line": e["line"], "error": "unknown subcategory id"} for e in errors],
        "aiact_obligations": obl,
        "aiact_open_without_evidence": None if obl is None else sum(1 for o in obl if o["support"] in ("none", "no crosswalk entry")),
    }
    return result, rows


def f3(v) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def cell(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ") if s else "—"


def render(res: dict, rows: list[dict], cat: list[dict]) -> str:
    para = {c["subcategory_id"]: c["paraphrase"] for c in cat}
    ov = res["overall"]
    L = ["# NIST AI RMF controls coverage", "",
         "Evidence mapped to NIST AI RMF 1.0 subcategories. A self-assessment of the evidence supplied, not an audit or certification.", "",
         "## Summary", "",
         f"- Overall coverage: **{f3(ov['coverage'])}** ({ov['implemented']} implemented, {ov['partial']} partial, {ov['planned']} planned, "
         f"{ov['missing']} missing, {ov['not_applicable']} not applicable of {ov['total']} subcategories)"]
    L.append(f"- Evidence-backed coverage (gate basis): **{f3(ov['coverage_evidenced'])}** — {ov['uncited_claims']} "
             "implemented/partial claim(s) with no evidence cited get no credit")
    if res["min_coverage"] is not None:
        verdict = "PASS" if res["gate"] == "pass" else "FAIL (exit 1)"
        L.append(f"- Gate: minimum coverage {res['min_coverage']:.3f} — **{verdict}** (evidence-backed coverage "
                 f"{f3(ov['coverage_evidenced'])})")
    else:
        L.append("- Gate: no minimum coverage given")
    L += [f"- Gaps (partial, planned or missing): {res['gaps']}; without a named owner: {res['gaps_without_owner']}",
          f"- Input errors (unknown subcategory ids): {len(res['input_errors'])}" + (" — the run fails (exit 1) until they are fixed" if res["input_errors"] else "")]
    if res["aiact_obligations"] is not None:
        L.append(f"- Open AI Act obligations with no supporting NIST evidence: {res['aiact_open_without_evidence']} of {len(res['aiact_obligations'])}")
    L += ["", "## Coverage by function", "",
          "| Function | Implemented | Partial | Planned | Not applicable | Missing | Applicable | Coverage |", "|---|---|---|---|---|---|---|---|"]
    for fn, c in list(res["functions"].items()) + [("ALL", ov)]:
        L.append(f"| {fn} | {c['implemented']} | {c['partial']} | {c['planned']} | {c['not_applicable']} | {c['missing']} | {c['applicable']} | {f3(c['coverage'])} |")
    L += ["", "## Gaps", ""]
    gaps = [r for r in rows if r["gap"] == "yes"]
    if gaps:
        L += ["| Subcategory | Status | Owner | Outcome expected (paraphrase) |", "|---|---|---|---|"]
        for r in gaps:
            L.append(f"| {r['subcategory_id']} | {r['status']} | {cell(r['owner'])} | {cell(para[r['subcategory_id']])} |")
    else:
        L.append("None: every applicable subcategory is implemented.")
    if res["claims_without_evidence"] or res["na_without_justification"]:
        L += ["", "Claims to check: " +
              "; ".join(filter(None, [
                  ("implemented/partial with no evidence cited: " + ", ".join(res["claims_without_evidence"])) if res["claims_without_evidence"] else "",
                  ("not_applicable with no justification: " + ", ".join(res["na_without_justification"])) if res["na_without_justification"] else ""])) + "."]
    if res["input_errors"]:
        L += ["", "Input errors: " + ", ".join(f"`{e['subcategory_id']}` (line {e['line']})" for e in res["input_errors"]) +
              " are not NIST AI RMF 1.0 subcategory ids; they are excluded from coverage."]
    if res["aiact_obligations"] is not None:
        L += ["", "### AI Act obligations and NIST evidence", "",
              "Support: supported = every mapped subcategory implemented (or not applicable); partial = some implemented or partial; "
              "none = only planned or missing. Crosswalk: the skill's own mapping (assets/aiact-nist-crosswalk.csv), not an official NIST or EU crosswalk.", ""]
        if res["aiact_obligations"]:
            L += ["| Obligation | Article | Status | Applies from | Mapped subcategories | Support |", "|---|---|---|---|---|---|"]
            for o in res["aiact_obligations"]:
                L.append(f"| {o['obligation_id']} | {cell(o['article'])} | {o['status']} | {cell(o['applies_from'])} | "
                         f"{cell('; '.join(o['subcategory_status']))} | {o['support']} |")
        else:
            L.append("None: every AI Act obligation in the input is done or not applicable.")
    L += ["", "## Evidence register", "", "| Subcategory | Function | Status | Evidence | Owner | Note |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['subcategory_id']} | {r['function']} | {r['status']} | {cell(r['evidence'])} | {cell(r['owner'])} | {cell(r['note'])} |")
    L += ["", "## Method", "",
          f"- Catalogue: {res['framework']}, {res['subcategories_in_catalogue']} subcategories (GOVERN 19, MAP 18, MEASURE 22, MANAGE 13), "
          "paraphrased in assets/nist-ai-rmf-1.0.csv; verified against NIST AI 100-1 on 2026-10-18 (references/sources.md).",
          f"- Formula: {res['formula']}. Coverage is rounded to 3 decimals; the gate compares the rounded overall value.",
          "- Statuses are taken as supplied. The skill does not inspect the evidence; claims without evidence are flagged and "
          "get no credit in the evidence-backed coverage the gate uses.",
          "- Gaps with no owner are assigned to the AI risk lead as a placeholder owner.",
          "- Limits: NIST AI RMF is voluntary; coverage is not compliance with any law. The AI RMF 1.0 is being revised (NIST, 2026); "
          "re-check the catalogue when a new version is published."]
    return "\n".join(L) + "\n"


def write_outputs(out: Path, res: dict, rows: list[dict], cat: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CTRL_COLS, lineterminator="\n")
    w.writeheader()
    w.writerows([{k: csv_safe(v) for k, v in r.items()} for r in rows])
    (out / "controls.csv").write_text(buf.getvalue(), encoding="utf-8")
    (out / "coverage.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "controls-report.md").write_text(render(res, rows, cat), encoding="utf-8")


def verify(path: Path) -> list[str]:
    d = path if path.is_dir() else path.parent
    errs = []
    try:
        res = json.loads((d / "coverage.json").read_text(encoding="utf-8"))
        rows = list(csv.DictReader((d / "controls.csv").open(encoding="utf-8")))
        rep = (d / "controls-report.md").read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        return [f"cannot read outputs: {e}"]
    cat_ids = [c["subcategory_id"] for c in load_catalogue()]
    got = [r["subcategory_id"] for r in rows if r["function"] != "ERROR"]
    if got != cat_ids:
        errs.append(f"controls.csv lists {len(got)} subcategories, catalogue has {len(cat_ids)}")
    for fn in FUNCTIONS:
        sel = [r for r in rows if r["function"] == fn]
        counts = {k: sum(1 for r in sel if r["status"] == k) for k in ("implemented", "partial", "planned", "not_applicable", "missing")}
        cov = coverage(counts)
        j = res["functions"][fn]
        if any(j[k] != v for k, v in counts.items()) or j["coverage"] != cov \
                or j.get("coverage_evidenced") != coverage_evidenced(sel):
            errs.append(f"{fn}: coverage.json does not match controls.csv")
        if f"| {fn} | {counts['implemented']} | {counts['partial']} |" not in rep:
            errs.append(f"{fn}: report row does not match controls.csv")
    for r in rows:
        if r["gap"] == "yes" and not r["owner"]:
            errs.append(f"{r['subcategory_id']}: gap without owner")
    if res.get("min_coverage") is not None:
        ov = res["overall"].get("coverage_evidenced")
        exp = "pass" if ov is not None and ov >= res["min_coverage"] else "fail"
        if res.get("gate") != exp:
            errs.append(f"gate {res.get('gate')} inconsistent with coverage {ov} vs {res['min_coverage']}")
    for text in (rep, (d / "controls.csv").read_text(encoding="utf-8")):
        for m in re.finditer(r"\[TO BE BASELINED[^\]]*\]", text):
            if "owner:" not in m.group(0) or m.group(0).rstrip("]").strip().endswith("owner:"):
                errs.append(f"unowned marker {m.group(0)}")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evidence", type=Path, help="evidence CSV subcategory_id,status,evidence,owner")
    ap.add_argument("--min-coverage", help="fraction 0-1; overall coverage below it fails the run")
    ap.add_argument("--obligations", type=Path, help="obligations.csv from eu-ai-act-classifier")
    ap.add_argument("--out-dir", type=Path, help="directory for controls.csv, coverage.json, controls-report.md")
    ap.add_argument("--verify", type=Path, help="re-check a finished run (any output file or the out dir)")
    args = ap.parse_args(argv)
    if args.verify:
        errs = verify(args.verify)
        for e in errs:
            print(f"verify: {e}")
        print("verify: ok" if not errs else f"verify: {len(errs)} problem(s)")
        return 1 if errs else 0
    try:
        if not args.evidence or not args.out_dir:
            raise InputError("--evidence and --out-dir are required")
        min_cov = parse_fraction(args.min_coverage)
        cat = load_catalogue()
        ev, errors = load_evidence(args.evidence, {c["subcategory_id"] for c in cat})
        res, rows = build(cat, ev, errors, min_cov, args.obligations)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write_outputs(args.out_dir, res, rows, cat)
    rc = 0
    if res["input_errors"]:
        print("unknown subcategory id(s): " + ", ".join(e["subcategory_id"] for e in res["input_errors"]), file=sys.stderr)
        rc = 1
    if res["gate"] == "fail":
        print(f"evidence-backed coverage {f3(res['overall']['coverage_evidenced'])} below minimum "
              f"{res['min_coverage']:.3f}", file=sys.stderr)
        rc = 1
    print(f"coverage {f3(res['overall']['coverage'])} (evidence-backed {f3(res['overall']['coverage_evidenced'])}) · gaps {res['gaps']} · gate {res['gate']}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
