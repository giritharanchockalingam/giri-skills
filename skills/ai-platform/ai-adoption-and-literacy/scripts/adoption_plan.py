#!/usr/bin/env python3
"""AI adoption and literacy plan: population x module catalog -> curriculum, training load, KPIs.

Rules (references/method.md):
  * A role needs a module when the module's `audience` includes the role's exposure AND the
    module's `level` is above the role's current proficiency (0-3).
  * A module whose `mandatory_for` includes the role's exposure is always required, whatever the
    proficiency (the default catalog makes the human-oversight module mandatory for overseers).
  * hours per person = sum of the role's module hours; role hours = headcount x hours per person;
    seats per module = sum of headcount of the roles that need it.
  * Training load is summed per business unit and mapped to rollout waves; a business unit with
    no wave is `[TO BE BASELINED — owner: Change lead]`.
  * Adoption KPI targets come only from --targets; every missing target is
    `[TO BE BASELINED — owner: Change lead]`.

Usage:
  python3 -I adoption_plan.py --population population.csv [--catalog modules.csv]
      [--waves waves.csv] [--targets targets.csv] [--strict] --out-dir OUT
  python3 -I adoption_plan.py --verify OUT/adoption.json     (any file in OUT works)

Inputs:
  population  CSV role,headcount,exposure,proficiency,business_unit
              exposure in none|user|operator|builder|overseer; proficiency integer 0-3.
  catalog     CSV module_id,title,hours,audience,level,format[,mandatory_for]
              audience / mandatory_for are '|'-separated exposure levels; level integer 1-3.
              Default: ../assets/literacy-modules.csv (the skill's own curriculum design).
  waves       CSV wave,business_unit,start_date (YYYY-MM-DD).
  targets     CSV key,value[,source] for adoption KPIs.
  Lines starting with '#' are comments.

Outputs (in --out-dir): curriculum.csv, training-load.csv, adoption-plan.md, adoption.json.
Exit codes: 0 written · 1 --strict and an overseer/operator role has no module (outputs still
written) · 2 missing or invalid input. Stdlib only; no network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = SKILL_DIR / "assets" / "literacy-modules.csv"
EXPOSURES = ("none", "user", "operator", "builder", "overseer")
GATED = ("operator", "overseer")
TBD = "[TO BE BASELINED — owner: Change lead]"
TBD_LD = "[TO BE BASELINED — owner: L&D lead]"
# Adoption KPIs the plan always shows (the skill's own measurement design; targets are never defaulted).
KPIS = [
    ("training_completion_rate", "Share of in-scope people who completed every required module", "LMS completion records"),
    ("weekly_active_rate", "Share of licensed users who used the AI system in the last 7 days", "product telemetry"),
    ("task_success_rate", "Share of AI-assisted tasks accepted without rework", "workflow / QA sampling"),
    ("satisfaction", "Average user rating of the AI system (scale stated in the target source)", "in-product or pulse survey"),
    ("time_saved_hours_per_user_week", "Self-reported or measured hours saved per active user per week", "time study or survey"),
]


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


def fmt(x: float) -> str:
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def read_csv(path: Path, label: str, required_cols: tuple[str, ...]) -> list[dict]:
    if not path.is_file():
        raise InputError(f"{label} file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8-sig").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    header = [h.strip() for h in (csv.reader(io.StringIO(lines[0])).__next__() if lines else [])]
    missing = [c for c in required_cols if c not in header]
    if missing:
        raise InputError(f"{label} CSV needs columns {','.join(required_cols)} (missing {','.join(missing)})")
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rows]


def to_int(v: str, label: str, lo: int, hi: int | None = None) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise InputError(f"{label}: expected an integer, got {v!r}") from None
    if n < lo or (hi is not None and n > hi):
        raise InputError(f"{label}: {n} out of range {lo}-{hi if hi is not None else 'inf'}")
    return n


def levels(v: str, label: str) -> list[str]:
    out = [x.strip().lower() for x in v.split("|") if x.strip()]
    bad = [x for x in out if x not in EXPOSURES]
    if bad:
        raise InputError(f"{label}: unknown exposure level(s) {bad}; allowed {EXPOSURES}")
    return out


def load_population(path: Path) -> list[dict]:
    rows = read_csv(path, "population", ("role", "headcount", "exposure", "proficiency", "business_unit"))
    if not rows:
        raise InputError("population CSV has no rows")
    seen, out = set(), []
    for i, r in enumerate(rows, start=2):
        if not r["role"] or not r["business_unit"]:
            raise InputError(f"population row {i}: role and business_unit are required")
        key = (r["role"], r["business_unit"])
        if key in seen:
            raise InputError(f"population row {i}: duplicate role {r['role']!r} in {r['business_unit']!r}")
        seen.add(key)
        exp = r["exposure"].lower()
        if exp not in EXPOSURES:
            raise InputError(f"population row {i}: exposure {r['exposure']!r} not in {EXPOSURES}")
        out.append({"role": r["role"], "business_unit": r["business_unit"], "exposure": exp,
                    "headcount": to_int(r["headcount"], f"population row {i} headcount", 0),
                    "proficiency": to_int(r["proficiency"], f"population row {i} proficiency", 0, 3)})
    return out


def load_catalog(path: Path) -> list[dict]:
    rows = read_csv(path, "catalog", ("module_id", "title", "hours", "audience", "level", "format"))
    if not rows:
        raise InputError("catalog CSV has no modules")
    out, ids = [], set()
    for i, r in enumerate(rows, start=2):
        if not r["module_id"] or r["module_id"] in ids:
            raise InputError(f"catalog row {i}: module_id missing or duplicated")
        ids.add(r["module_id"])
        try:
            hours = float(r["hours"])
        except ValueError:
            raise InputError(f"catalog row {i}: hours must be a number, got {r['hours']!r}") from None
        if hours <= 0:
            raise InputError(f"catalog row {i}: hours must be > 0")
        out.append({"module_id": r["module_id"], "title": r["title"], "hours": hours, "format": r["format"],
                    "audience": levels(r["audience"], f"catalog row {i} audience"),
                    "level": to_int(r["level"], f"catalog row {i} level", 1, 3),
                    "mandatory_for": levels(r.get("mandatory_for", ""), f"catalog row {i} mandatory_for")})
    return sorted(out, key=lambda m: m["module_id"])


def load_waves(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    out = {}
    for i, r in enumerate(read_csv(path, "waves", ("wave", "business_unit", "start_date")), start=2):
        try:
            dt.date.fromisoformat(r["start_date"])
        except ValueError:
            raise InputError(f"waves row {i}: start_date must be YYYY-MM-DD, got {r['start_date']!r}") from None
        if r["business_unit"] in out:
            raise InputError(f"waves row {i}: business_unit {r['business_unit']!r} appears in two waves")
        out[r["business_unit"]] = {"wave": r["wave"], "start_date": r["start_date"]}
    return out


def load_targets(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    return {r["key"]: {"value": r["value"], "source": r.get("source", "")}
            for r in read_csv(path, "targets", ("key", "value")) if r["key"] and r["value"]}


def build(pop, catalog, waves, targets, catalog_label: str) -> dict:
    roles, curriculum = [], []
    seats = {m["module_id"]: 0 for m in catalog}
    for p in sorted(pop, key=lambda r: (r["business_unit"], r["role"])):
        mods = []
        for m in catalog:
            if p["exposure"] in m["mandatory_for"]:
                reason = f"mandatory for {p['exposure']} (rule), regardless of proficiency"
            elif p["exposure"] in m["audience"] and m["level"] > p["proficiency"]:
                reason = f"exposure {p['exposure']}; module level {m['level']} > proficiency {p['proficiency']}"
            else:
                continue
            mods.append(m)
            seats[m["module_id"]] += p["headcount"]
            curriculum.append({"business_unit": p["business_unit"], "role": p["role"], "module_id": m["module_id"],
                               "title": m["title"], "hours": fmt(m["hours"]), "reason": reason})
        hpp = sum(m["hours"] for m in mods)
        roles.append({**p, "modules": [m["module_id"] for m in mods], "hours_per_person": round(hpp, 2),
                      "total_hours": round(hpp * p["headcount"], 2)})
    gaps = [r for r in roles if r["exposure"] in GATED and not r["modules"]]
    has_oversight = any("overseer" in m["mandatory_for"] for m in catalog)
    overseer_rule_gap = (not has_oversight) and any(r["exposure"] == "overseer" for r in roles)
    load: dict[str, dict] = {}
    for r in roles:
        bu = r["business_unit"]
        w = waves.get(bu, {"wave": TBD, "start_date": TBD})
        e = load.setdefault(bu, {"wave": w["wave"], "business_unit": bu, "start_date": w["start_date"],
                                 "people": 0, "learners": 0, "hours": 0.0})
        e["people"] += r["headcount"]
        e["learners"] += r["headcount"] if r["modules"] else 0
        e["hours"] = round(e["hours"] + r["total_hours"], 2)
    load_rows = sorted(load.values(), key=lambda e: (e["wave"] == TBD, e["start_date"], e["wave"], e["business_unit"]))
    kpis = []
    for key, definition, source in KPIS:
        t = targets.get(key)
        kpis.append({"kpi": key, "definition": definition, "measured_from": source,
                     "target": t["value"] if t else TBD, "target_source": (t["source"] or "targets input") if t else ""})
    for key in sorted(set(targets) - {k for k, _, _ in KPIS}):
        kpis.append({"kpi": key, "definition": "owner-supplied KPI", "measured_from": TBD,
                     "target": targets[key]["value"], "target_source": targets[key]["source"] or "targets input"})
    total_people = sum(r["headcount"] for r in roles)
    return {
        "catalog": catalog_label,
        "totals": {"roles": len(roles), "people": total_people,
                   "learners": sum(r["headcount"] for r in roles if r["modules"]),
                   "training_hours": round(sum(r["total_hours"] for r in roles), 2),
                   "modules_in_catalog": len(catalog),
                   "modules_used": sum(1 for v in seats.values() if v > 0)},
        "roles": roles,
        "modules": [{"module_id": m["module_id"], "title": m["title"], "hours": m["hours"], "level": m["level"],
                     "format": m["format"], "audience": m["audience"], "mandatory_for": m["mandatory_for"],
                     "seats": seats[m["module_id"]], "seat_hours": round(seats[m["module_id"]] * m["hours"], 2)}
                    for m in catalog],
        "curriculum": curriculum,
        "training_load": load_rows,
        "kpis": kpis,
        "gaps": {"unmapped_operator_overseer_roles": [f"{r['role']} ({r['business_unit']})" for r in gaps],
                 "overseer_rule_unmet": overseer_rule_gap,
                 "business_units_without_wave": [e["business_unit"] for e in load_rows if e["wave"] == TBD]},
    }


def render(plan: dict, strict: bool) -> str:
    t, g = plan["totals"], plan["gaps"]
    L = ["# AI adoption and literacy plan", "",
         "## Summary", "",
         f"- {t['people']} people in {t['roles']} roles; {t['learners']} need at least one module.",
         f"- Total training load: {fmt(t['training_hours'])} hours across {t['modules_used']} of "
         f"{t['modules_in_catalog']} catalog modules.",
         f"- Catalog: {plan['catalog']}."]
    if g["unmapped_operator_overseer_roles"]:
        L.append(f"- Gap: operator/overseer roles with no module: {', '.join(g['unmapped_operator_overseer_roles'])} "
                 f"— {TBD_LD}.")
    else:
        L.append("- Every operator and overseer role has at least one module mapped.")
    if g["overseer_rule_unmet"]:
        L.append(f"- Gap: the catalog has no module mandatory for overseers (human-oversight rule) — {TBD_LD}.")
    if strict:
        failed = bool(g["unmapped_operator_overseer_roles"]) or g["overseer_rule_unmet"]
        L.append(f"- `--strict` was set: {'the run fails (exit 1).' if failed else 'gate passed.'}")
    L += ["", "## Who needs what", "",
          "| Business unit | Role | Exposure | Proficiency | Headcount | Modules | Hours / person | Total hours |",
          "|---|---|---|---|---|---|---|---|"]
    for r in plan["roles"]:
        L.append(f"| {r['business_unit']} | {r['role']} | {r['exposure']} | {r['proficiency']} | {r['headcount']} | "
                 f"{', '.join(r['modules']) or 'none'} | {fmt(r['hours_per_person'])} | {fmt(r['total_hours'])} |")
    L += ["", "## Curriculum", "",
          "| Module | Title | Level | Hours | Format | Audience | Mandatory for | Seats | Seat-hours |",
          "|---|---|---|---|---|---|---|---|---|"]
    for m in plan["modules"]:
        L.append(f"| {m['module_id']} | {m['title']} | {m['level']} | {fmt(m['hours'])} | {m['format']} | "
                 f"{'/'.join(m['audience'])} | {'/'.join(m['mandatory_for']) or '—'} | {m['seats']} | {fmt(m['seat_hours'])} |")
    L += ["", "## Rollout", "",
          "| Wave | Business unit | Start date | People | Learners | Training hours |", "|---|---|---|---|---|---|"]
    for e in plan["training_load"]:
        L.append(f"| {e['wave']} | {e['business_unit']} | {e['start_date']} | {e['people']} | {e['learners']} | {fmt(e['hours'])} |")
    L += ["", "Sequence: train the wave before its go-live; overseers and operators complete their modules before "
          "they take on oversight or operation duties.",
          "", "## Adoption KPIs", "",
          "| KPI | Definition | Measured from | Target | Target source |", "|---|---|---|---|---|"]
    for k in plan["kpis"]:
        L.append(f"| {k['kpi']} | {k['definition']} | {k['measured_from']} | {k['target']} | {k['target_source'] or '—'} |")
    L += ["", "Targets come only from the targets input; none is defaulted.",
          "", "## Art. 4 note", "",
          "EU AI Act (Regulation (EU) 2024/1689) Article 4 has applied since 2 February 2025 (Art. 113(a)). As amended by "
          "the Digital Omnibus on AI (Regulation (EU) 2026/1744, in force since July 2026), providers and deployers "
          "\"shall take measures to support the development of AI literacy of their staff and other persons dealing "
          "with the operation and use of AI systems on their behalf\", taking into account their technical knowledge, "
          "experience, education and training and the context of use; the obligation \"does not require providers or "
          "deployers to guarantee any specific level of AI literacy of any individual.\" Deployers of high-risk systems "
          "must still assign human oversight to people with the necessary competence, training and authority "
          "(Art. 26(2)). This plan is evidence of measures taken; keep completion records. Not a legal determination — "
          "confirm scope with counsel. Sources: `references/sources.md`.",
          "", "## Method", "",
          "- A role needs a module when the module's audience includes the role's exposure and the module level "
          "is above the role's proficiency; modules marked mandatory for an exposure are always required.",
          "- Hours per person = sum of module hours; total = headcount × hours per person; seats = sum of headcount.",
          "- Business units without a wave are " + TBD + ".",
          "- Limits: proficiency is self- or manager-assessed; hours exclude travel and backfill; the default catalog "
          "is this skill's own design, not a regulatory syllabus."]
    return "\n".join(L) + "\n"


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    path.write_text(buf.getvalue(), encoding="utf-8")


def verify(path: Path) -> int:
    """Recompute every total in adoption.json and cross-check curriculum.csv / training-load.csv."""
    d = path if path.name == "adoption.json" else path.parent / "adoption.json"
    errs = []
    try:
        plan = json.loads(d.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"verify: cannot read {d}: {e}", file=sys.stderr)
        return 1
    mods = {m["module_id"]: m for m in plan["modules"]}
    seats = {k: 0 for k in mods}
    for r in plan["roles"]:
        hpp = round(sum(mods[m]["hours"] for m in r["modules"]), 2)
        if abs(hpp - r["hours_per_person"]) > 1e-6 or abs(round(hpp * r["headcount"], 2) - r["total_hours"]) > 1e-6:
            errs.append(f"role {r['role']}: hours do not recompute")
        for m in r["modules"]:
            seats[m] += r["headcount"]
            if r["exposure"] not in mods[m]["mandatory_for"] and not (
                    r["exposure"] in mods[m]["audience"] and mods[m]["level"] > r["proficiency"]):
                errs.append(f"role {r['role']}: module {m} not justified by the rule")
    for k, m in mods.items():
        if seats[k] != m["seats"]:
            errs.append(f"module {k}: seats {m['seats']} != {seats[k]}")
    total = round(sum(r["total_hours"] for r in plan["roles"]), 2)
    if abs(total - plan["totals"]["training_hours"]) > 1e-6:
        errs.append("total training hours do not recompute")
    if abs(round(sum(e["hours"] for e in plan["training_load"]), 2) - total) > 1e-6:
        errs.append("training load does not sum to total hours")
    cur = d.parent / "curriculum.csv"
    if cur.exists():
        n = sum(1 for _ in csv.DictReader(cur.open(encoding="utf-8")))
        if n != sum(len(r["modules"]) for r in plan["roles"]):
            errs.append("curriculum.csv row count does not match role modules")
    tl = d.parent / "training-load.csv"
    if tl.exists():
        h = round(sum(float(r["hours"]) for r in csv.DictReader(tl.open(encoding="utf-8"))), 2)
        if abs(h - total) > 1e-6:
            errs.append("training-load.csv hours do not sum to total")
    for e in errs:
        print(f"verify: {e}", file=sys.stderr)
    if not errs:
        print(f"verify: ok ({len(plan['roles'])} roles, {fmt(total)} hours)")
    return 1 if errs else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--population", type=Path)
    ap.add_argument("--catalog", type=Path)
    ap.add_argument("--waves", type=Path)
    ap.add_argument("--targets", type=Path)
    ap.add_argument("--strict", action="store_true", help="exit 1 if an operator/overseer role has no module")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--verify", type=Path, help="re-verify an output directory's adoption.json and exit")
    args = ap.parse_args(argv)
    if args.verify:
        return verify(args.verify)
    if not args.population or not args.out_dir:
        print("error: --population and --out-dir are required", file=sys.stderr)
        return 2
    try:
        catalog_path = args.catalog or DEFAULT_CATALOG
        label = (f"supplied catalog `{catalog_path.name}`" if args.catalog else
                 "default `assets/literacy-modules.csv` (this skill's own curriculum design)")
        plan = build(load_population(args.population), load_catalog(catalog_path),
                     load_waves(args.waves), load_targets(args.targets), label)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "curriculum.csv", ["business_unit", "role", "module_id", "title", "hours", "reason"], plan["curriculum"])
    write_csv(out / "training-load.csv", ["wave", "business_unit", "start_date", "people", "learners", "hours"],
              [{**e, "hours": fmt(e["hours"])} for e in plan["training_load"]])
    plan["strict"] = bool(args.strict)
    failed = bool(plan["gaps"]["unmapped_operator_overseer_roles"]) or plan["gaps"]["overseer_rule_unmet"]
    plan["gate"] = "fail" if (args.strict and failed) else ("pass" if args.strict else "not run")
    (out / "adoption.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (out / "adoption-plan.md").write_text(render(plan, args.strict), encoding="utf-8")
    if args.strict and failed:
        print("strict gate failed: " + (", ".join(plan["gaps"]["unmapped_operator_overseer_roles"])
                                        or "no human-oversight module for overseers"), file=sys.stderr)
        return 1
    t = plan["totals"]
    print(f"adoption plan written: {t['people']} people, {fmt(t['training_hours'])} training hours")
    return 0


if __name__ == "__main__":
    sys.exit(main())
