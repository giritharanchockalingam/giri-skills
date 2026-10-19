#!/usr/bin/env python3
"""Data Protection Impact Assessment (GDPR Art. 35) for an AI system: screening + DPIA + risk register.

Screening applies the nine WP29/EDPB criteria (WP248 rev.01, endorsed by the EDPB on 25 May 2018):
a DPIA is required when two or more criteria are met, or when an Art. 35(3) case applies; where
unanswered criteria could tip the result, the skill follows WP248 and recommends a DPIA anyway.
The DPIA follows the Art. 35(7) minimum contents (description, necessity and proportionality,
risks to rights and freedoms, measures). Every blank fact becomes
`[TO BE BASELINED — owner: Data protection officer]`; nothing is invented.

Usage:
  python3 -I dpia.py --processing processing.csv [--pii-inventory pii-inventory.csv]
                     [--risks risks.csv] --out-dir OUT
  python3 -I dpia.py --verify OUT/dpia-risks.csv     # re-check any of the three outputs (whole dir)

Inputs:
  processing     kv-csv key,value[,source,notes] (layout: assets/processing-template.csv).
                 Screening keys take yes|no (blank = not answered).
  pii-inventory  pii-inventory.csv from ai-platform/pii-data-inventory
                 (column,pii_types,match_rate,rows_scanned,handling,matches,basis). PII columns whose
                 handling is blank or TBD become risks automatically.
  risks          CSV risk,likelihood,severity,measure,owner,residual; likelihood/severity 1-3,
                 residual low|medium|high (blank = not assessed).

Risk method (references/risk-method.md): score = likelihood x severity; 1-2 low, 3-4 medium,
6-9 high. With no measure and no stated residual, residual = inherent level.

Outputs (in --out-dir): dpia.md, dpia-risks.csv, screening.json.
Exit codes: 0 written · 1 GATE: a high residual risk has no measure (cannot sign off) — outputs
are still written · 2 missing/invalid input (or --verify target missing). --verify: 0 ok, 1 mismatch.
Stdlib only; no network; writes only inside --out-dir. Not legal advice.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Data protection officer]"
YES = {"yes", "y", "true", "1"}
NO = {"no", "n", "false", "0"}

# WP248 rev.01 section III.B.a — nine criteria; key = processing fact that answers it.
CRITERIA = [
    ("C1", "Evaluation or scoring", "evaluation_scoring"),
    ("C2", "Automated decision-making with legal or similar significant effect (Art. 22)", "automated_decision_making"),
    ("C3", "Systematic monitoring", "systematic_monitoring"),
    ("C4", "Sensitive data or data of a highly personal nature", None),  # special_categories | criminal_data | highly_personal_data
    ("C5", "Data processed on a large scale", "large_scale"),
    ("C6", "Matching or combining datasets", "combining_datasets"),
    ("C7", "Data concerning vulnerable data subjects", "vulnerable_subjects"),
    ("C8", "Innovative use or new technological or organisational solutions", "new_technology"),
    ("C9", "Processing that prevents data subjects from exercising a right or using a service or contract",
     "prevents_rights_or_service"),
]
C4_KEYS = ("special_categories", "criminal_data", "highly_personal_data")
YESNO_KEYS = {k for _, _, k in CRITERIA if k} | set(C4_KEYS) | {"publicly_accessible_area", "international_transfers"}

DESCRIPTION_KEYS = [
    ("system_name", "AI system"), ("controller", "Controller"), ("dpo", "Data protection officer"),
    ("purpose", "Purpose of processing"), ("data_subjects", "Data subjects"),
    ("data_categories", "Personal data categories"), ("data_sources", "Data sources"),
    ("recipients", "Recipients"), ("processors", "Processors"), ("retention", "Retention"),
    ("international_transfers", "International transfers (yes/no)"), ("transfer_mechanism", "Transfer mechanism"),
    ("assessment_date", "Assessment date"),
]
NECESSITY_KEYS = [
    ("lawful_basis", "Lawful basis (Art. 6; Art. 9 condition if special categories)"),
    ("necessity_justification", "Why the processing is necessary for the purpose"),
    ("data_minimisation", "Data minimisation"), ("accuracy_measures", "Accuracy"),
    ("retention", "Storage limitation (retention)"), ("transparency", "Information to data subjects"),
    ("data_subject_rights", "Data subject rights (access, rectification, objection, Art. 22 safeguards)"),
    ("processors", "Processor safeguards (Art. 28)"), ("transfer_mechanism", "International transfer safeguards"),
]
SIGNOFF_KEYS = [
    ("signoff_measures_approved_by", "Measures approved by"),
    ("signoff_residual_risk_accepted_by", "Residual risks accepted by"),
    ("signoff_dpo_advice", "DPO advice provided (summary)"),
    ("signoff_dpo_advice_accepted", "DPO advice accepted or overruled (with reasons)"),
    ("next_review", "Next review date"),
]
KNOWN_KEYS = YESNO_KEYS | {k for k, _ in DESCRIPTION_KEYS + NECESSITY_KEYS + SIGNOFF_KEYS}
RISK_COLS = ["risk", "source", "likelihood", "severity", "score", "level", "measure", "owner", "residual"]
LEVELS = ("low", "medium", "high")
SECTIONS = ["Screening", "Description of processing", "Necessity and proportionality",
            "Risks to rights and freedoms", "Measures", "Residual risk and consultation", "Sign-off"]


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


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"input file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        raise InputError(f"{path} is not a UTF-8 text CSV ({e.reason} at byte {e.start}); save it as CSV UTF-8")
    if "\x00" in text:
        raise InputError(f"{path} is not a text CSV (contains NUL bytes)")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    try:
        rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    except csv.Error as e:
        raise InputError(f"{path}: malformed CSV ({e})")
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None} for r in rows]


def cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def load_processing(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    if not rows or "key" not in rows[0] or "value" not in rows[0]:
        raise InputError("processing CSV needs columns key,value and at least one row")
    facts: dict[str, str] = {}
    for r in rows:
        k = r.get("key", "").strip().lower()
        if not k:
            continue
        v = r.get("value", "")
        if k in YESNO_KEYS and v and v.lower() not in YES | NO:
            raise InputError(f"processing key {k!r} takes yes|no, got {v!r}")
        facts[k] = v
    return facts


def yn(facts: dict, key: str):
    v = facts.get(key, "").lower()
    return True if v in YES else False if v in NO else None


def load_inventory(path: Path | None) -> list[dict]:
    if path is None:
        return []
    rows = read_csv(path)
    need = ("column", "pii_types", "handling")
    if rows and any(c not in rows[0] for c in need):
        raise InputError("pii inventory needs columns column,pii_types,handling (pii-data-inventory output)")
    return [r for r in rows if r.get("pii_types", "none") not in ("", "none")]


def handling_tbd(h: str) -> bool:
    return not h or "TO BE BASELINED" in h


def load_risks(path: Path | None) -> list[dict]:
    if path is None:
        return []
    rows = read_csv(path)
    if rows and "risk" not in rows[0]:
        raise InputError("risks CSV needs columns risk,likelihood,severity,measure,owner,residual")
    out = []
    for i, r in enumerate(rows, start=2):
        if not r.get("risk"):
            continue
        vals = {}
        for col in ("likelihood", "severity"):
            v = r.get(col, "")
            if v and v not in ("1", "2", "3"):
                raise InputError(f"risks line {i}: {col} must be 1, 2 or 3 (got {v!r})")
            vals[col] = int(v) if v else None
        res = r.get("residual", "").lower()
        if res and res not in LEVELS:
            raise InputError(f"risks line {i}: residual must be low|medium|high (got {r.get('residual')!r})")
        out.append({"risk": r["risk"], "source": "risks input", "likelihood": vals["likelihood"],
                    "severity": vals["severity"], "measure": r.get("measure", ""), "owner": r.get("owner", ""),
                    "residual": res})
    return out


def level_of(score: int) -> str:
    return "low" if score <= 2 else "medium" if score <= 4 else "high"


def score_risk(r: dict) -> dict:
    l, s = r["likelihood"], r["severity"]
    score = l * s if l and s else None
    level = level_of(score) if score is not None else "unscored"
    residual, basis = r["residual"], "stated"
    overridden = False
    if residual and not r["measure"] and score is not None and LEVELS.index(residual) < LEVELS.index(level):
        # A residual below the inherent level with no measure is not credible: nothing reduces the risk.
        basis = (f"no measure: stated residual '{residual}' is not credible; residual = inherent level ({level})")
        residual, overridden = level, True
    elif not residual:
        if not r["measure"] and score is not None:
            residual, basis = level, "no measure: residual = inherent level"
        else:
            residual, basis = TBD, "not assessed"
    return {
        "risk": r["risk"], "source": r["source"],
        "likelihood": str(l) if l else TBD, "severity": str(s) if s else TBD,
        "score": str(score) if score is not None else TBD, "level": level,
        "measure": r["measure"] or TBD, "owner": r["owner"] or TBD, "residual": residual,
        "residual_basis": basis, "has_measure": bool(r["measure"]), "residual_overridden": overridden,
    }


def screen(facts: dict, inventory: list[dict]) -> dict:
    crit = []
    inv_types = sorted({t for r in inventory for t in r["pii_types"].split(";")})
    for cid, name, key in CRITERIA:
        if cid == "C4":
            vals = {k: yn(facts, k) for k in C4_KEYS}
            if any(v is True for v in vals.values()):
                met = True
                basis = "processing: " + ", ".join(k for k in C4_KEYS if vals[k]) + " = yes"
            elif "payment_card" in inv_types and vals["highly_personal_data"] is None:
                met, basis = True, "pii_inventory: payment_card column (WP248: financial data usable for payment fraud)"
            elif all(v is False for v in vals.values()):
                met, basis = False, "processing: " + ", ".join(C4_KEYS) + " = no"
            else:
                met, basis = None, "not answered: " + ", ".join(k for k in C4_KEYS if vals[k] is None)
        else:
            v = yn(facts, key)
            met = v
            basis = f"processing: {key} = {'yes' if v else 'no'}" if v is not None else f"not answered: {key}"
        crit.append({"id": cid, "name": name, "met": met, "basis": basis})
    n_met = sum(1 for c in crit if c["met"] is True)
    n_unknown = sum(1 for c in crit if c["met"] is None)
    art = []
    if yn(facts, "evaluation_scoring") and yn(facts, "automated_decision_making"):
        art.append("Art. 35(3)(a): systematic and extensive evaluation based on automated processing with decisions producing legal or similarly significant effects")
    if yn(facts, "large_scale") and (yn(facts, "special_categories") or yn(facts, "criminal_data")):
        art.append("Art. 35(3)(b): large-scale processing of special categories (Art. 9(1)) or criminal-offence data (Art. 10)")
    if yn(facts, "systematic_monitoring") and yn(facts, "publicly_accessible_area") and yn(facts, "large_scale"):
        art.append("Art. 35(3)(c): systematic monitoring of a publicly accessible area on a large scale")
    if art:
        required, basis = True, f"Art. 35(3) case applies ({len(art)}); {n_met} of 9 WP248 criteria met"
    elif n_met >= 2:
        required, basis = True, f"{n_met} of 9 WP248 criteria met (two or more: DPIA required)"
    elif n_met + n_unknown >= 2:
        required, basis = True, (f"{n_met} of 9 WP248 criteria met and {n_unknown} not answered; unanswered criteria "
                                 f"could reach two, so a DPIA is carried out (WP248: where unclear, carry out a DPIA)")
    else:
        required, basis = False, (f"{n_met} of 9 WP248 criteria met and {n_unknown} not answered; no Art. 35(3) case. "
                                  "Not required on the WP248 two-criteria rule only: WP248 notes that a single "
                                  "criterion can suffice in some cases, and the supervisory authority's Art. 35(4) "
                                  f"list must be checked: {TBD}")
    return {"criteria": crit, "criteria_met": n_met, "criteria_unanswered": n_unknown,
            "art35_3_cases": art, "required": required, "basis": basis}


def build(facts: dict, inventory: list[dict], risks_in: list[dict]) -> dict:
    risks = [score_risk(r) for r in risks_in]
    for r in inventory:
        if handling_tbd(r.get("handling", "")):
            risks.append(score_risk({
                "risk": f"Personal data in column '{r['column']}' ({r['pii_types']}) has no decided handling",
                "source": f"pii_inventory:{r['column']}", "likelihood": None, "severity": None,
                "measure": "", "owner": "", "residual": ""}))
    if not risks:
        risks.append(score_risk({"risk": "Risks to rights and freedoms not yet identified", "source": "none supplied",
                                 "likelihood": None, "severity": None, "measure": "", "owner": "", "residual": ""}))
    gate = [r["risk"] for r in risks if r["residual"] == "high" and not r["has_measure"]]
    consult = [r["risk"] for r in risks if r["residual"] == "high"]
    overrides = [r["risk"] for r in risks if r["residual_overridden"]]
    incomplete = sum(1 for r in risks if TBD in (r["score"], r["residual"], r["measure"], r["owner"]))
    status = "blocked" if gate else "incomplete" if incomplete else "ready"
    return {"facts": facts, "inventory": inventory, "screening": screen(facts, inventory), "risks": risks,
            "gate_blockers": gate, "prior_consultation_required": bool(consult), "consultation_risks": consult,
            "residual_overrides": overrides, "incomplete_risks": incomplete, "signoff_status": status}


def f(facts: dict, key: str) -> str:
    return cell(facts.get(key) or TBD)


def render(d: dict) -> str:
    facts, scr = d["facts"], d["screening"]
    name = facts.get("system_name") or TBD
    L = [f"# DPIA — {name}", "",
         "Data Protection Impact Assessment under GDPR Art. 35. Not legal advice: the controller, advised by the "
         "Data protection officer, makes the determination.", "",
         f"**Bottom line:** DPIA {'required' if scr['required'] else 'not required on the WP248 two-criteria rule (current facts)'} — "
         f"{scr['basis']}. Sign-off status: **{d['signoff_status']}**. Prior consultation (Art. 36): "
         f"**{'required' if d['prior_consultation_required'] else 'not indicated'}**.", "",
         "## Screening", "",
         "WP248 rev.01 criteria (EDPB-endorsed). Two or more met: DPIA required; Art. 35(3) cases always require one.", "",
         "| # | Criterion | Met | Basis |", "|---|---|---|---|"]
    for c in scr["criteria"]:
        met = "yes" if c["met"] else "no" if c["met"] is False else TBD
        L.append(f"| {c['id']} | {c['name']} | {met} | {cell(c['basis'])} |")
    L += ["", f"Criteria met: {scr['criteria_met']} of 9 · not answered: {scr['criteria_unanswered']}.", ""]
    L += [f"- {a}" for a in scr["art35_3_cases"]] or ["- No Art. 35(3) case applies on the facts supplied."]
    L += ["", f"Result: **DPIA {'required' if scr['required'] else 'not required on the WP248 two-criteria rule'}** — {scr['basis']}.", "",
          "## Description of processing", "", "Art. 35(7)(a): systematic description of the processing and its purposes.", "",
          "| Item | Value |", "|---|---|"]
    L += [f"| {label} | {f(facts, k)} |" for k, label in DESCRIPTION_KEYS]
    other = sorted(k for k in facts if k not in KNOWN_KEYS and facts[k])
    if other:
        L += ["", "Other facts supplied:", "", "| Key | Value |", "|---|---|"]
        L += [f"| {k} | {cell(facts[k])} |" for k in other]
    L += ["", "Personal data found by the PII inventory:", ""]
    if d["inventory"]:
        L += ["| Column | PII types | Match rate | Handling |", "|---|---|---|---|"]
        for r in d["inventory"]:
            L.append(f"| {cell(r['column'])} | {r['pii_types']} | {r.get('match_rate', '') or '—'} | "
                     f"{cell(r.get('handling') or TBD) if not handling_tbd(r.get('handling', '')) else TBD} |")
    else:
        L.append(f"No PII inventory supplied: {TBD} (run ai-platform/pii-data-inventory on a sample).")
    L += ["", "## Necessity and proportionality", "", "Art. 35(7)(b).", "", "| Test | Position |", "|---|---|"]
    L += [f"| {label} | {f(facts, k)} |" for k, label in NECESSITY_KEYS]
    notes = []
    if yn(facts, "automated_decision_making"):
        notes.append("Automated decision-making is in scope: record Art. 22 safeguards (human intervention, "
                     "right to contest) under data subject rights.")
    if yn(facts, "international_transfers") and not facts.get("transfer_mechanism"):
        notes.append(f"International transfers are stated but no transfer mechanism: {TBD}.")
    allowed = [r["column"] for r in d["inventory"] if r.get("handling", "").lower() == "allow"]
    if allowed:
        notes.append("Columns the policy keeps in clear (justify necessity): " + ", ".join(sorted(allowed)) + ".")
    if notes:
        L += [""] + [f"- {n}" for n in notes]
    L += ["", "## Risks to rights and freedoms", "",
          "Art. 35(7)(c). Score = likelihood (1-3) × severity (1-3); 1-2 low, 3-4 medium, 6-9 high.", "",
          "| # | Risk | Source | Likelihood | Severity | Score | Level |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(d["risks"], start=1):
        L.append(f"| R{i} | {cell(r['risk'])} | {cell(r['source'])} | {r['likelihood']} | {r['severity']} | "
                 f"{r['score']} | {r['level']} |")
    L += ["", "## Measures", "", "Art. 35(7)(d): measures, safeguards and security mechanisms.", "",
          "| # | Risk | Measure | Owner |", "|---|---|---|---|"]
    for i, r in enumerate(d["risks"], start=1):
        L.append(f"| R{i} | {cell(r['risk'])} | {cell(r['measure'])} | {cell(r['owner'])} |")
    handled = [r for r in d["inventory"] if not handling_tbd(r.get("handling", "")) and r["handling"].lower() != "allow"]
    if handled:
        L += ["", "Data handling already set by the privacy policy (from the PII inventory):", ""]
        L += [f"- `{r['column']}` ({r['pii_types']}): {r['handling']}" for r in handled]
    L += ["", "## Residual risk and consultation", "", "| # | Risk | Residual | Basis |", "|---|---|---|---|"]
    for i, r in enumerate(d["risks"], start=1):
        L.append(f"| R{i} | {cell(r['risk'])} | {r['residual']} | {r['residual_basis']} |")
    L.append("")
    if d["residual_overrides"]:
        L.append(f"**Stated residual not accepted:** {len(d['residual_overrides'])} risk(s) state a residual below the "
                 "inherent level but have no measure; the residual is set to the inherent level: "
                 + "; ".join(cell(x) for x in d["residual_overrides"]) + ".")
        L.append("")
    if d["gate_blockers"]:
        L.append(f"**GATE — cannot sign off:** {len(d['gate_blockers'])} high residual risk(s) have no measure: "
                 + "; ".join(d["gate_blockers"]) + ".")
        L.append("")
    if d["prior_consultation_required"]:
        L.append(f"**Prior consultation required (Art. 36(1)):** {len(d['consultation_risks'])} residual risk(s) remain "
                 "high. Consult the supervisory authority before processing starts.")
    else:
        L.append("Prior consultation (Art. 36(1)) is not indicated: no residual risk is assessed as high.")
    if d["incomplete_risks"]:
        L += ["", f"{d['incomplete_risks']} risk(s) still carry TBD fields; the residual-risk conclusion is provisional "
              f"until they are scored: {TBD}."]
    L += ["", "## Sign-off", "", f"Status: **{d['signoff_status']}**.", "", "| Item | Name / decision |", "|---|---|"]
    L += [f"| {label} | {f(facts, k)} |" for k, label in SIGNOFF_KEYS]
    L += ["", "Limits: built only from the facts supplied; screening and risk levels follow WP248 and the skill's 3×3 "
          "method; not a legal determination."]
    return "\n".join(L) + "\n"


def write_outputs(d: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(RISK_COLS)
    for r in d["risks"]:
        w.writerow([csv_safe(r[c]) for c in RISK_COLS])
    (out / "dpia-risks.csv").write_text(buf.getvalue(), encoding="utf-8")
    scr = dict(d["screening"])
    scr.update({"prior_consultation_required": d["prior_consultation_required"],
                "signoff_status": d["signoff_status"], "gate_blockers": d["gate_blockers"],
                "residual_overrides": d["residual_overrides"],
                "risks_total": len(d["risks"])})
    (out / "screening.json").write_text(json.dumps(scr, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                                        encoding="utf-8")
    (out / "dpia.md").write_text(render(d), encoding="utf-8")


# ------------------------------------------------------------------ verify

def verify(target: Path) -> list[str]:
    out = target if target.is_dir() else target.parent
    probs: list[str] = []
    for name in ("dpia.md", "dpia-risks.csv", "screening.json"):
        if not (out / name).is_file():
            probs.append(f"{name} missing")
    if probs:
        return probs
    rows = list(csv.DictReader((out / "dpia-risks.csv").open(encoding="utf-8")))
    scr = json.loads((out / "screening.json").read_text(encoding="utf-8"))
    md = (out / "dpia.md").read_text(encoding="utf-8")
    if not rows:
        probs.append("dpia-risks.csv has no rows")
    for i, r in enumerate(rows, start=2):
        l, s = r["likelihood"], r["severity"]
        if l.isdigit() and s.isdigit():
            if r["score"] != str(int(l) * int(s)):
                probs.append(f"line {i}: score {r['score']} != {l}x{s}")
            elif r["level"] != level_of(int(r["score"])):
                probs.append(f"line {i}: level {r['level']} wrong for score {r['score']}")
        elif r["level"] != "unscored" or r["score"] != TBD:
            probs.append(f"line {i}: unscored risk must have score TBD and level unscored")
        if r["residual"] not in LEVELS and r["residual"] != TBD:
            probs.append(f"line {i}: residual {r['residual']!r} invalid")
        for c in RISK_COLS:
            if not r.get(c):
                probs.append(f"line {i}: blank {c}")
        if r["measure"] == TBD and r["level"] in LEVELS and r["residual"] in LEVELS \
                and LEVELS.index(r["residual"]) < LEVELS.index(r["level"]):
            probs.append(f"line {i}: residual {r['residual']} below inherent {r['level']} with no measure")
    met = sum(1 for c in scr["criteria"] if c["met"] is True)
    if len(scr["criteria"]) != 9 or met != scr["criteria_met"]:
        probs.append("screening criteria count mismatch")
    unknown = sum(1 for c in scr["criteria"] if c["met"] is None)
    expect_req = bool(scr["art35_3_cases"]) or met + unknown >= 2
    if scr["required"] != expect_req:
        probs.append(f"required={scr['required']} inconsistent with criteria/Art. 35(3)")
    gate = [r["risk"] for r in rows if r["residual"] == "high" and r["measure"] == TBD]
    if sorted(gate) != sorted(csv_safe(x) for x in scr["gate_blockers"]):
        probs.append("gate_blockers do not match dpia-risks.csv")
    consult = any(r["residual"] == "high" for r in rows)
    if consult != scr["prior_consultation_required"]:
        probs.append("prior_consultation_required does not match residual risks")
    if scr["risks_total"] != len(rows):
        probs.append("risks_total != rows in dpia-risks.csv")
    for sec in SECTIONS:
        if f"## {sec}" not in md:
            probs.append(f"dpia.md missing section {sec}")
    if consult and "Prior consultation required (Art. 36(1))" not in md:
        probs.append("dpia.md does not flag Art. 36 prior consultation")
    return probs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--processing", type=Path, help="processing description kv-csv")
    ap.add_argument("--pii-inventory", type=Path, help="pii-inventory.csv from pii-data-inventory")
    ap.add_argument("--risks", type=Path, help="risks CSV risk,likelihood,severity,measure,owner,residual")
    ap.add_argument("--out-dir", type=Path, help="directory for dpia.md, dpia-risks.csv, screening.json")
    ap.add_argument("--verify", type=Path, metavar="OUTPUT", help="re-check a DPIA output (any file in the out dir)")
    a = ap.parse_args(argv)
    if a.verify:
        if not a.verify.exists():
            print(f"error: {a.verify} not found", file=sys.stderr)
            return 2
        probs = verify(a.verify)
        for p in probs:
            print(f"FAIL: {p}", file=sys.stderr)
        print(f"verify: {'OK' if not probs else f'{len(probs)} problem(s)'}")
        return 1 if probs else 0
    if a.processing is None or a.out_dir is None:
        print("error: --processing and --out-dir are required", file=sys.stderr)
        return 2
    try:
        d = build(load_processing(a.processing), load_inventory(a.pii_inventory), load_risks(a.risks))
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write_outputs(d, a.out_dir)
    scr = d["screening"]
    print(f"DPIA written: required={scr['required']} ({scr['criteria_met']}/9 criteria), {len(d['risks'])} risks, "
          f"status={d['signoff_status']}, Art. 36={'yes' if d['prior_consultation_required'] else 'no'}")
    if d["gate_blockers"]:
        print("GATE: high residual risk without a measure: " + "; ".join(d["gate_blockers"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
