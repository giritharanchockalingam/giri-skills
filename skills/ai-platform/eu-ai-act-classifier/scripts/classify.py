#!/usr/bin/env python3
"""EU AI Act classifier: one AI system's questionnaire -> risk tier + obligations with dates.

Classifies one AI system under Regulation (EU) 2024/1689 (the AI Act) as amended by
Regulation (EU) 2026/1744 (the "AI Omnibus", OJ 24 Jul 2026, in force 27 Jul 2026) into
prohibited | high-risk | limited-transparency | minimal, or `undetermined` when a blank
answer could change the tier. Lists the obligations that follow for the stated role, with
article and application date, from assets/obligations-catalogue.csv (dates verified against
the sources in references/sources.md). Not legal advice.

Usage:
  python3 -I classify.py --system system.csv [--evidence evidence.csv] [--as-of YYYY-MM-DD] --out-dir OUT
  python3 -I classify.py --verify OUT/classification.json      (re-checks a finished run)

Inputs:
  system    kv-csv key,value[,source,notes] (layout: assets/system-questionnaire.csv). Yes/no
            keys accept yes|no|true|false|y|n; blank or "unknown" = unanswered. '#' lines are comments.
  evidence  CSV obligation_id,status,evidence,owner; status done|in_progress|not_started|not_applicable.
  as-of     date used to mark obligations already in force (never defaulted to today).

Outputs (in --out-dir): classification.json, obligations.csv, ai-act-report.md.
Exit codes: 0 classified (incl. undetermined) · 1 prohibited practice (gate; outputs still
written) or --verify failure · 2 missing/invalid input. Stdlib only; no network.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CATALOGUE = SKILL_DIR / "assets" / "obligations-catalogue.csv"
TBD = "[TO BE BASELINED — owner: AI compliance lead]"
SOURCES_CHECKED = "2026-10-18"
LEGAL_BASIS = "Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744"
ROLES = ("provider", "deployer", "importer", "distributor")
EVIDENCE_STATUS = ("done", "in_progress", "not_started", "not_applicable")
OBL_COLS = ["obligation_id", "article", "obligation", "applies_from", "applies_to_role", "owner",
            "status", "in_force", "evidence", "date_basis"]

# key, group, article, question  (assets/system-questionnaire.csv carries the same keys)
QUESTIONS = [
    ("system_name", "context", "", "Name of the AI system"),
    ("role", "context", "Art. 3(3)-(7)", "Your role for this system: provider | deployer | importer | distributor"),
    ("intended_purpose", "context", "Art. 3(12)", "Intended purpose in one sentence"),
    ("placed_on_market", "context", "Art. 111, Art. 50(2) transition", "Date first placed on the market / put into service (YYYY-MM-DD)"),
    ("accountable_owner", "context", "", "Named owner for the obligations (role or person)"),
    ("p_subliminal_manipulation", "prohibited", "Art. 5(1)(a)", "Uses subliminal, manipulative or deceptive techniques that materially distort behaviour causing significant harm?"),
    ("p_exploit_vulnerabilities", "prohibited", "Art. 5(1)(b)", "Exploits vulnerabilities due to age, disability or social/economic situation causing significant harm?"),
    ("p_social_scoring", "prohibited", "Art. 5(1)(c)", "Evaluates or classifies people by social behaviour or personality leading to detrimental or unjustified treatment (social scoring)?"),
    ("p_crime_risk_profiling", "prohibited", "Art. 5(1)(d)", "Predicts a person's risk of committing a crime based solely on profiling or personality traits?"),
    ("p_untargeted_face_scraping", "prohibited", "Art. 5(1)(e)", "Builds or expands facial recognition databases by untargeted scraping of images from the internet or CCTV?"),
    ("p_emotion_recognition_work_education", "prohibited", "Art. 5(1)(f)", "Infers emotions of people in the workplace or in education (outside medical or safety reasons)?"),
    ("p_biometric_categorisation_sensitive", "prohibited", "Art. 5(1)(g)", "Categorises people by biometric data to infer race, political opinions, union membership, religion, sex life or orientation?"),
    ("p_realtime_rbi_law_enforcement", "prohibited", "Art. 5(1)(h)", "Real-time remote biometric identification in publicly accessible spaces for law enforcement (outside the Art. 5(1)(h) exceptions)?"),
    ("p_non_consensual_intimate_content", "prohibited", "Art. 5(1)(ba) (added by Reg. 2026/1744)", "Generates or manipulates realistic intimate or sexually explicit depictions of an identifiable person without consent?"),
    ("p_csam_generation", "prohibited", "Art. 5(1)(bb) (added by Reg. 2026/1744)", "Generates or manipulates child sexual abuse material?"),
    ("annex1_safety_component", "high-risk", "Art. 6(1), Annex I", "Is it a safety component of (or itself) a product under Annex I harmonisation law that needs third-party conformity assessment?"),
    ("a3_biometrics", "high-risk", "Annex III point 1", "Remote biometric identification, biometric categorisation or emotion recognition (where permitted)?"),
    ("a3_critical_infrastructure", "high-risk", "Annex III point 2", "Safety component in management/operation of critical digital infrastructure, road traffic, water, gas, heating or electricity?"),
    ("a3_education", "high-risk", "Annex III point 3", "Education/vocational training: admission, evaluating learning outcomes, assessing education level, or proctoring?"),
    ("a3_employment", "high-risk", "Annex III point 4", "Employment: recruitment/selection, or decisions on promotion, termination, task allocation or monitoring of workers?"),
    ("a3_essential_services", "high-risk", "Annex III point 5", "Essential services: public benefits eligibility, creditworthiness/credit scoring, life/health insurance pricing, or emergency call triage?"),
    ("a3_law_enforcement", "high-risk", "Annex III point 6", "Law enforcement uses listed in Annex III point 6?"),
    ("a3_migration", "high-risk", "Annex III point 7", "Migration, asylum or border control uses listed in Annex III point 7?"),
    ("a3_justice_democracy", "high-risk", "Annex III point 8", "Administration of justice or influencing elections/referendums or voting behaviour?"),
    ("d63_narrow_procedural", "derogation", "Art. 6(3)(a)", "Annex III only: intended to perform a narrow procedural task?"),
    ("d63_improves_prior_human", "derogation", "Art. 6(3)(b)", "Annex III only: intended to improve the result of a previously completed human activity?"),
    ("d63_detects_patterns", "derogation", "Art. 6(3)(c)", "Annex III only: detects decision patterns or deviations, without replacing or influencing the human assessment absent proper human review?"),
    ("d63_preparatory", "derogation", "Art. 6(3)(d)", "Annex III only: performs a preparatory task to an assessment relevant to an Annex III use case?"),
    ("d63_profiling", "derogation", "Art. 6(3) last subparagraph", "Annex III only: performs profiling of natural persons? (if yes, always high-risk)"),
    ("t_interacts_with_persons", "transparency", "Art. 50(1)", "Intended to interact directly with natural persons?"),
    ("t_synthetic_content", "transparency", "Art. 50(2)", "Generates synthetic audio, image, video or text content?"),
    ("t_emotion_recognition", "transparency", "Art. 50(3)", "Is an emotion recognition system (permitted use)?"),
    ("t_biometric_categorisation", "transparency", "Art. 50(3)", "Is a biometric categorisation system (permitted use)?"),
    ("t_deepfake", "transparency", "Art. 50(4)", "Generates or manipulates image, audio or video that constitutes a deep fake?"),
    ("t_public_interest_text", "transparency", "Art. 50(4)", "Generates or manipulates text published to inform the public on matters of public interest?"),
    ("is_gpai", "gpai", "Art. 3(63), Art. 53", "Are you the provider of a general-purpose AI model (not just a user of one)?"),
    ("gpai_systemic_risk", "gpai", "Art. 51, Art. 55", "Is that GPAI model classified as having systemic risk?"),
]
QMAP = {q[0]: q for q in QUESTIONS}
YES_NO_GROUPS = ("prohibited", "high-risk", "derogation", "transparency", "gpai")
P_KEYS = [q[0] for q in QUESTIONS if q[1] == "prohibited"]
A3_KEYS = [q[0] for q in QUESTIONS if q[0].startswith("a3_")]
D_COND = ["d63_narrow_procedural", "d63_improves_prior_human", "d63_detects_patterns", "d63_preparatory"]
T_KEYS = [q[0] for q in QUESTIONS if q[1] == "transparency"]
NEW_PROHIBITIONS = ("p_non_consensual_intimate_content", "p_csam_generation")


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"input file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise InputError(f"{path.name} is empty")
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None}
            for r in csv.DictReader(io.StringIO("\n".join(lines)))]


def parse_date(s: str, what: str) -> dt.date:
    try:
        return dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        raise InputError(f"{what} must be a date YYYY-MM-DD, got {s!r}") from None


def yes_no(key: str, v: str):
    t = v.strip().lower()
    if t in ("", "unknown", "tbd", "?"):
        return None
    if t in ("yes", "y", "true"):
        return True
    if t in ("no", "n", "false"):
        return False
    raise InputError(f"system key {key!r}: answer must be yes or no (or blank), got {v!r}")


def load_system(path: Path) -> tuple[dict, dict]:
    rows = read_csv(path)
    if "key" not in rows[0] or "value" not in rows[0]:
        raise InputError("system CSV needs columns key,value")
    raw: dict[str, str] = {}
    for r in rows:
        k = r.get("key", "")
        if not k:
            continue
        if k not in QMAP:
            raise InputError(f"system CSV: unknown key {k!r} (see assets/system-questionnaire.csv)")
        if k in raw:
            raise InputError(f"system CSV: duplicate key {k!r}")
        raw[k] = r.get("value", "")
    ans: dict = {}
    for k, (_, group, _, _) in QMAP.items():
        v = raw.get(k, "")
        ans[k] = yes_no(k, v) if group in YES_NO_GROUPS else (v or None)
    if ans["role"] is not None:
        ans["role"] = ans["role"].lower()
        if ans["role"] not in ROLES:
            raise InputError(f"role must be one of {ROLES}, got {raw['role']!r}")
    if ans["placed_on_market"] is not None:
        parse_date(ans["placed_on_market"], "placed_on_market")
    return ans, raw


def load_catalogue() -> list[dict]:
    rows = read_csv(CATALOGUE)
    for r in rows:
        r["roles"] = r["applies_to_role"].split(";")
    return rows


def load_evidence(path: Path | None, known: set[str]) -> dict[str, dict]:
    if path is None:
        return {}
    rows = read_csv(path)
    for col in ("obligation_id", "status", "evidence", "owner"):
        if col not in rows[0]:
            raise InputError(f"evidence CSV needs columns obligation_id,status,evidence,owner (missing {col})")
    out = {}
    for i, r in enumerate(rows, start=2):
        oid, st = r["obligation_id"], r["status"].lower()
        if oid not in known:
            raise InputError(f"evidence line {i}: unknown obligation_id {oid!r} (see assets/obligations-catalogue.csv)")
        if st not in EVIDENCE_STATUS:
            raise InputError(f"evidence line {i}: status must be one of {EVIDENCE_STATUS}, got {r['status']!r}")
        if oid in out:
            raise InputError(f"evidence line {i}: duplicate obligation_id {oid!r}")
        out[oid] = {"status": st, "evidence": r["evidence"], "owner": r["owner"]}
    return out


def classify(a: dict) -> dict:
    """Tier from answers. Blank answers that could change the tier make it undetermined."""
    p_yes = [k for k in P_KEYS if a[k] is True]
    p_open = [k for k in P_KEYS if a[k] is None]
    routes, basis, open_tier, derogation = [], [], [], False
    if p_yes:
        return {"tier": "prohibited", "provisional_tier": "prohibited", "basis": [QMAP[k][2] for k in p_yes],
                "high_risk_routes": [], "derogation_applied": False, "tier_open_keys": [], "prohibited_hits": p_yes}
    if a["annex1_safety_component"] is True:
        routes.append("annex1")
        basis.append("Art. 6(1), Annex I")
    a3_yes = [k for k in A3_KEYS if a[k] is True]
    a3_open = [k for k in A3_KEYS if a[k] is None]
    d_yes = [k for k in D_COND if a[k] is True]
    d_open = [k for k in D_COND if a[k] is None]
    deriv_open: list[str] = []
    if a3_yes:
        prof = a["d63_profiling"]
        if prof is True or (not d_yes and not d_open):
            routes.append("annex3")
            basis += ["Art. 6(2)"] + [QMAP[k][2] for k in a3_yes]
            if prof is True:
                basis.append("Art. 6(3) last subparagraph (profiling)")
        elif prof is False and d_yes:
            derogation = True
            basis += ["Art. 6(3) derogation"] + [QMAP[k][2] for k in d_yes]
        else:
            deriv_open = (["d63_profiling"] if prof is None else []) + (d_open if not d_yes else [])
    t_yes = [k for k in T_KEYS if a[k] is True]
    t_open = [k for k in T_KEYS if a[k] is None]
    if routes:
        cand = "high-risk"
        open_tier = p_open
    else:
        hr_open = (["annex1_safety_component"] if a["annex1_safety_component"] is None else []) + a3_open + deriv_open
        if t_yes:
            cand = "limited-transparency"
            basis += [QMAP[k][2] for k in t_yes]
        else:
            cand = "minimal"
        open_tier = p_open + hr_open + ([] if t_yes else t_open)
    if cand == "high-risk" and t_yes:
        basis += [QMAP[k][2] for k in t_yes]
    return {"tier": "undetermined" if open_tier else cand, "provisional_tier": cand, "basis": sorted(set(basis), key=basis.index),
            "high_risk_routes": routes, "derogation_applied": derogation, "tier_open_keys": open_tier, "prohibited_hits": []}


def triggered(trigger: str, a: dict, c: dict) -> bool:
    if trigger == "any":
        return True
    if trigger.startswith("p_"):
        return a.get(trigger) is True
    if trigger == "high-risk":
        return bool(c["high_risk_routes"])
    if trigger == "high-risk-annex3":
        return "annex3" in c["high_risk_routes"]
    if trigger == "derogation":
        return c["derogation_applied"]
    if trigger in T_KEYS or trigger == "is_gpai":
        return a.get(trigger) is True
    if trigger == "gpai_systemic":
        return a.get("is_gpai") is True and a.get("gpai_systemic_risk") is True
    raise InputError(f"catalogue: unknown trigger {trigger!r}")


def applies_from(row: dict, a: dict, c: dict) -> tuple[str, str]:
    """Resolve the catalogue date rule to an ISO date (or TBD text) plus its basis."""
    rule, pom = row["date_rule"], a.get("placed_on_market")
    if rule == "high-risk":
        dates = sorted(row["applies_from"].split("|")[0 if r == "annex3" else 1] for r in c["high_risk_routes"])
        return dates[0], row["date_basis"]
    if rule == "pom_before":  # applies_from = new|cutoff|legacy
        new, cutoff, legacy = row["applies_from"].split("|")
        if pom is None:
            return f"{new} or {legacy} {TBD}", row["date_basis"] + "; placed_on_market not given"
        return (legacy if pom < cutoff else new), row["date_basis"]
    return row["applies_from"], row["date_basis"]


def build(a: dict, evidence: dict, as_of: dt.date | None) -> tuple[dict, list[dict]]:
    c = classify(a)
    role = a["role"]
    owner_default = a["accountable_owner"] or TBD
    obligations = []
    for row in load_catalogue():
        if not triggered(row["trigger"], a, c):
            continue
        if role is not None and role not in row["roles"]:
            continue
        date, basis = applies_from(row, a, c)
        ev = evidence.get(row["obligation_id"], {})
        if as_of is None:
            in_force = "not assessed (no --as-of)"
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            in_force = "yes" if as_of >= dt.date.fromisoformat(date) else "no"
        else:
            in_force = TBD
        obligations.append({
            "obligation_id": row["obligation_id"], "article": row["article"], "obligation": row["obligation"],
            "applies_from": date, "applies_to_role": role or row["applies_to_role"],
            "owner": ev.get("owner") or owner_default, "status": ev.get("status", "open"),
            "in_force": in_force, "evidence": ev.get("evidence", ""), "date_basis": basis})
    obligations.sort(key=lambda o: (o["applies_from"], o["obligation_id"]))
    unanswered = []
    for k, (_, group, art, q) in QMAP.items():
        if a[k] is None:
            unanswered.append({"key": k, "article": art, "question": q, "could_change_tier": k in c["tier_open_keys"],
                               "answer": TBD})
    unanswered.sort(key=lambda u: (not u["could_change_tier"], list(QMAP).index(u["key"])))
    status_counts = {s: sum(1 for o in obligations if o["status"] == s) for s in ("open",) + EVIDENCE_STATUS}
    result = {
        "system_name": a["system_name"] or TBD,
        "role": role or TBD,
        "intended_purpose": a["intended_purpose"] or TBD,
        "tier": c["tier"],
        "provisional_tier": c["provisional_tier"],
        "basis_articles": c["basis"],
        "high_risk_routes": c["high_risk_routes"],
        "art_6_3_derogation_applied": c["derogation_applied"],
        "prohibited_hits": c["prohibited_hits"],
        "gpai": {"is_gpai_model_provider": a["is_gpai"], "systemic_risk": a["gpai_systemic_risk"]},
        "transparency_triggers": [k for k in T_KEYS if a[k] is True],
        "unanswered_keys": unanswered,
        "tier_open_keys": c["tier_open_keys"],
        "as_of": as_of.isoformat() if as_of else None,
        "obligations_count": len(obligations),
        "obligations_status": status_counts,
        "obligations_in_force": sum(1 for o in obligations if o["in_force"] == "yes"),
        "legal_basis": LEGAL_BASIS,
        "dates_verified_on": SOURCES_CHECKED,
        "gate": "fail" if c["tier"] == "prohibited" else "pass",
        "not_legal_advice": True,
    }
    return result, obligations


def md_cell(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def yn(v) -> str:
    return TBD if v is None else ("yes" if v else "no")


def render(res: dict, obl: list[dict]) -> str:
    tier = res["tier"]
    L = [f"# EU AI Act classification — {res['system_name']}", "",
         "Not legal advice: a structured screening against the Act's text; confirm with counsel before relying on it.", "",
         "## Summary", ""]
    head = {
        "prohibited": "**PROHIBITED** — the system matches an Art. 5 prohibited practice. Gate: FAIL (exit 1). Do not place on the market or use.",
        "high-risk": "**HIGH-RISK** — Chapter III requirements apply.",
        "limited-transparency": "**LIMITED (TRANSPARENCY)** — Art. 50 transparency obligations apply; not high-risk.",
        "minimal": "**MINIMAL** — no tier-specific obligations; AI literacy (Art. 4) still applies to providers and deployers.",
        "undetermined": f"**UNDETERMINED** — {len(res['tier_open_keys'])} unanswered question(s) could change the tier; "
                        f"answers so far point to **{res['provisional_tier']}**.",
    }[tier]
    L += [f"- Tier: {head}",
          f"- Role: {res['role']} · Intended purpose: {res['intended_purpose']}",
          f"- Obligations listed: {res['obligations_count']} (" + ", ".join(f"{k} {v}" for k, v in res["obligations_status"].items() if v) + ")"
          if res["obligations_count"] else "- Obligations listed: 0",
          f"- In force as of {res['as_of']}: {res['obligations_in_force']}" if res["as_of"] else "- In force: not assessed (no --as-of date given)",
          f"- Unanswered questions: {len(res['unanswered_keys'])} ({len(res['tier_open_keys'])} could change the tier)",
          f"- Legal basis: {res['legal_basis']}; dates verified {res['dates_verified_on']} (references/sources.md)", "",
          "## Classification", "", "| Item | Result |", "|---|---|",
          f"| Tier | {tier} |", f"| Provisional tier (answers so far) | {res['provisional_tier']} |",
          f"| Basis articles | {'; '.join(res['basis_articles']) or 'none triggered'} |",
          f"| High-risk route | {', '.join(res['high_risk_routes']) or 'none'} |",
          f"| Art. 6(3) derogation applied | {'yes' if res['art_6_3_derogation_applied'] else 'no'} |",
          f"| Transparency triggers | {', '.join(res['transparency_triggers']) or 'none'} |",
          f"| GPAI model provider | {yn(res['gpai']['is_gpai_model_provider'])} |",
          f"| GPAI systemic risk | {yn(res['gpai']['systemic_risk'])} |",
          ""]
    if res["art_6_3_derogation_applied"]:
        L += ["Art. 6(3) derogation: the provider must document the assessment before placing on the market and register "
              "the system (Art. 6(4), Art. 49(2)); the derogation never applies where the system profiles natural persons.", ""]
    L += ["## Obligations", ""]
    if obl:
        L += ["| ID | Article | Obligation | Applies from | Role | Owner | Status | In force |", "|---|---|---|---|---|---|---|---|"]
        for o in obl:
            L.append(f"| {o['obligation_id']} | {md_cell(o['article'])} | {md_cell(o['obligation'])} | {o['applies_from']} | "
                     f"{o['applies_to_role']} | {md_cell(o['owner'])} | {o['status']} | {o['in_force']} |")
    else:
        L.append("No obligations in the catalogue are triggered for this role and these answers.")
    if tier == "undetermined":
        L += ["", "Only obligations already triggered by the answers given are listed. Resolving the open questions may add "
              "obligations (for example the Chapter III high-risk set)."]
    L += ["", "## Open questions", ""]
    if res["unanswered_keys"]:
        L += ["| Key | Article | Question | Could change tier | Answer |", "|---|---|---|---|---|"]
        for u in res["unanswered_keys"]:
            L.append(f"| {u['key']} | {md_cell(u['article']) or '—'} | {md_cell(u['question'])} | "
                     f"{'yes' if u['could_change_tier'] else 'no'} | {u['answer']} |")
    else:
        L.append("None: every questionnaire key is answered.")
    L += ["", "## Limits", "",
          "- Not legal advice and not a legal determination. The questionnaire paraphrases Art. 5, Art. 6, Annex I, Annex III "
          "and Art. 50; edge cases (exceptions in Art. 5(1)(h), Annex III sub-points, sectoral Annex I law) need counsel.",
          f"- Dates follow {LEGAL_BASIS} (AI Omnibus, OJ 24 Jul 2026, in force 27 Jul 2026), checked {SOURCES_CHECKED}. "
          "The high-risk dates moved once already (Annex III 2 Aug 2026 -> 2 Dec 2027; Annex I 2 Aug 2027 -> 2 Aug 2028); "
          "re-check EUR-Lex before relying on any date.",
          "- Where the catalogue marks a date as the skill's reading (date_basis), the Act does not state that date for the "
          "article directly; confirm with counsel.",
          "- Obligations are a summary list, not the full article text; authorised-representative, notified-body and "
          "sector-specific duties are out of scope.",
          "- Answers are taken as given; the skill does not test the system."]
    return "\n".join(L) + "\n"


def write_outputs(out: Path, res: dict, obl: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "classification.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=OBL_COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(obl)
    (out / "obligations.csv").write_text(buf.getvalue(), encoding="utf-8")
    (out / "ai-act-report.md").write_text(render(res, obl), encoding="utf-8")


def verify(path: Path) -> list[str]:
    """Re-check a finished run directory for internal consistency."""
    d = path if path.is_dir() else path.parent
    errs = []
    try:
        res = json.loads((d / "classification.json").read_text(encoding="utf-8"))
        obl = list(csv.DictReader((d / "obligations.csv").open(encoding="utf-8")))
        rep = (d / "ai-act-report.md").read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        return [f"cannot read outputs: {e}"]
    if res.get("tier") not in ("prohibited", "high-risk", "limited-transparency", "minimal", "undetermined"):
        errs.append(f"invalid tier {res.get('tier')!r}")
    if res.get("obligations_count") != len(obl):
        errs.append(f"obligations_count {res.get('obligations_count')} != {len(obl)} rows")
    if res.get("tier") == "undetermined" and not res.get("tier_open_keys"):
        errs.append("undetermined tier without open keys")
    if res.get("tier") != "undetermined" and res.get("tier_open_keys"):
        errs.append("tier determined but open keys remain")
    if res.get("not_legal_advice") is not True or "Not legal advice" not in rep:
        errs.append("not-legal-advice statement missing")
    for o in obl:
        if o.get("obligation_id", "") not in rep:
            errs.append(f"obligation {o.get('obligation_id')} missing from report")
        if not o.get("owner"):
            errs.append(f"obligation {o.get('obligation_id')} has no owner")
    for u in res.get("unanswered_keys", []):
        if f"| {u['key']} |" not in rep:
            errs.append(f"open key {u['key']} missing from report")
    for text in (rep, (d / "obligations.csv").read_text(encoding="utf-8")):
        for m in re.finditer(r"\[TO BE BASELINED[^\]]*\]", text):
            if "owner:" not in m.group(0) or m.group(0).rstrip("]").endswith("owner:"):
                errs.append(f"unowned marker {m.group(0)}")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", type=Path, help="system questionnaire CSV (key,value,source,notes)")
    ap.add_argument("--evidence", type=Path, help="optional evidence CSV obligation_id,status,evidence,owner")
    ap.add_argument("--as-of", help="YYYY-MM-DD; marks obligations already in force")
    ap.add_argument("--out-dir", type=Path, help="directory for the three outputs")
    ap.add_argument("--verify", type=Path, help="re-check a finished run (any output file or the out dir)")
    args = ap.parse_args(argv)
    if args.verify:
        errs = verify(args.verify)
        for e in errs:
            print(f"verify: {e}")
        print("verify: ok" if not errs else f"verify: {len(errs)} problem(s)")
        return 1 if errs else 0
    try:
        if not args.system or not args.out_dir:
            raise InputError("--system and --out-dir are required")
        as_of = parse_date(args.as_of, "--as-of") if args.as_of else None
        answers, _ = load_system(args.system)
        known = {r["obligation_id"] for r in load_catalogue()}
        res, obl = build(answers, load_evidence(args.evidence, known), as_of)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write_outputs(args.out_dir, res, obl)
    if res["tier"] == "prohibited":
        print("PROHIBITED: " + ", ".join(res["prohibited_hits"]) + " — gate fails", file=sys.stderr)
        return 1
    print(f"tier: {res['tier']} · {len(obl)} obligations · {len(res['unanswered_keys'])} open questions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
