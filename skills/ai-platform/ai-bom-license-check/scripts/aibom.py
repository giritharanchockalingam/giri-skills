#!/usr/bin/env python3
"""AI bill of materials + licence check: models, datasets, libraries, services against a licence policy.

Every licence string is normalised to an SPDX identifier (SPDX License List 3.29.0) or a
LicenseRef- id through assets/license-catalog.csv. Strings the catalog does not know stay
`unknown` (never guessed) and go to review with Legal counsel. Decisions come only from the
organisation's policy CSV; without one every decision is `[TO BE BASELINED — owner: Legal counsel]`.

Rules (references/method.md):
  * a commercial or redistribution use of a licence flagged commercial_use_restricted=yes -> deny
  * commercial_use_restricted=conditional (e.g. Llama MAU threshold) + commercial/redistribution use:
    an `allow` becomes `review`
  * simple SPDX expressions: `A OR B` (best decision of the parts), `A AND B` (strictest); a mix,
    parentheses or WITH -> unknown
GATE: any `deny` -> exit 1 (outputs still written).

Usage:
  python3 -I aibom.py --bom bom.csv [--policy policy.csv] [--system NAME] --out-dir OUT
  python3 -I aibom.py --verify OUT/aibom.json     # re-check any output (whole out dir)

Inputs:
  bom     CSV component,type,version,license,source_url,use
          type model|dataset|library|service; use internal|commercial|redistribution
  policy  CSV license,decision[,notes]; decision allow|review|deny (layout: assets/license-policy.example.csv)
  system  optional name of the AI system the BOM describes (metadata.component)

Outputs (in --out-dir): aibom.csv, aibom.json (CycloneDX 1.6-shaped subset), license-report.md.
Exit codes: 0 no component denied · 1 GATE: at least one deny · 2 missing/invalid input.
--verify: 0 consistent, 1 mismatch, 2 target missing. Stdlib only; no network.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "assets" / "license-catalog.csv"
TBD_LEGAL = "[TO BE BASELINED — owner: Legal counsel]"
TBD_ENG = "[TO BE BASELINED — owner: Engineering lead]"
TYPES = {"model": "machine-learning-model", "dataset": "data", "library": "library", "service": None}
USES = ("internal", "commercial", "redistribution")
DECISIONS = ("allow", "review", "deny")
FLAG_NAMES = ("commercial_use_restricted", "copyleft", "attribution_required", "use_based_restrictions")
# CycloneDX 1.6 component.type enum (bom-1.6.schema.json)
CDX_TYPES = {"application", "framework", "library", "container", "platform", "operating-system", "device",
             "device-driver", "firmware", "file", "machine-learning-model", "data", "cryptographic-asset"}
CSV_COLS = ["component", "type", "version", "license_raw", "spdx_id", "decision", "reason", "flags", "use"]
SECTIONS = ["Summary", "Components", "Blocked", "Needs review", "Obligations", "Method"]


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"input file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8-sig").splitlines() if not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items() if k is not None} for r in rows]


def norm(s: str) -> str:
    s = s.lower().replace("licence", "license")
    return re.sub(r"[^a-z0-9.+]", "", s)


def load_catalog() -> tuple[dict, dict]:
    rows = read_csv(CATALOG)
    by_id, index = {}, {}
    for r in rows:
        by_id[r["spdx_id"]] = r
        for key in [r["spdx_id"], r["name"]] + [a for a in r["aliases"].split(";") if a.strip()]:
            index.setdefault(norm(key), r["spdx_id"])
    return by_id, index


def resolve(raw: str, index: dict) -> tuple[str, list[str], str]:
    """-> (spdx_id or 'unknown', parts, operator)."""
    if not raw or "(" in raw or ")" in raw or re.search(r"\sWITH\s", raw):
        return "unknown", [], ""
    has_or, has_and = bool(re.search(r"\sOR\s", raw)), bool(re.search(r"\sAND\s", raw))
    if has_or and has_and:
        return "unknown", [], ""
    op = "OR" if has_or else "AND" if has_and else ""
    parts = [p.strip() for p in re.split(r"\s(?:OR|AND)\s", raw)] if op else [raw.strip()]
    ids = [index.get(norm(p)) for p in parts]
    if any(i is None for i in ids):
        return "unknown", [], ""
    return (f" {op} ".join(ids) if op else ids[0]), ids, op


def load_bom(path: Path) -> list[dict]:
    rows = read_csv(path)
    need = ("component", "type", "version", "license", "source_url", "use")
    if not rows or any(c not in rows[0] for c in need):
        raise InputError("bom CSV needs columns " + ",".join(need) + " and at least one row")
    out, seen = [], set()
    for i, r in enumerate(rows, start=2):
        if not r["component"]:
            raise InputError(f"bom line {i}: component is blank")
        t, u = r["type"].lower(), r["use"].lower()
        if t not in TYPES:
            raise InputError(f"bom line {i}: type {r['type']!r} not in model|dataset|library|service")
        if u not in USES:
            raise InputError(f"bom line {i}: use {r['use']!r} not in internal|commercial|redistribution")
        key = (r["component"], r["version"])
        if key in seen:
            raise InputError(f"bom line {i}: duplicate component {r['component']} {r['version']}")
        seen.add(key)
        out.append({**r, "type": t, "use": u})
    return out


def load_policy(path: Path | None, index: dict) -> dict | None:
    if path is None:
        return None
    rows = read_csv(path)
    if not rows or "license" not in rows[0] or "decision" not in rows[0]:
        raise InputError("policy CSV needs columns license,decision and at least one row")
    pol = {}
    for i, r in enumerate(rows, start=2):
        d = r["decision"].lower()
        if d not in DECISIONS:
            raise InputError(f"policy line {i}: decision {r['decision']!r} not in allow|review|deny")
        lid = index.get(norm(r["license"]))
        if lid is None:
            raise InputError(f"policy line {i}: licence {r['license']!r} is not in the catalog; use an SPDX or LicenseRef id")
        pol[lid] = d
    return pol


RANK = {"allow": 0, TBD_LEGAL: 1, "review": 2, "deny": 3}


def evaluate(c: dict, catalog: dict, index: dict, policy: dict | None) -> dict:
    raw = c["license"]
    spdx, parts, op = resolve(raw, index)
    reasons: list[str] = []
    flags: dict[str, str] = {f: "no" for f in FLAG_NAMES}
    obligations: list[str] = []
    if spdx == "unknown":
        decision = "review" if policy is not None else TBD_LEGAL
        reasons.append(f"licence string not in catalog: {raw or 'blank'} — review by Legal counsel"
                       if raw else f"licence not stated: {TBD_ENG}")
    else:
        part_dec = []
        for pid in parts:
            if policy is None:
                part_dec.append(TBD_LEGAL)
            else:
                part_dec.append(policy.get(pid, "review"))
        if op == "OR":
            best = min(range(len(parts)), key=lambda k: (RANK[part_dec[k]], k))
            chosen = [parts[best]]
            decision = part_dec[best]
            if len(parts) > 1:
                reasons.append(f"OR expression: {parts[best]} chosen "
                               + ("(best policy decision)" if policy is not None else "(first listed; no policy)"))
        else:
            chosen = parts
            decision = max(part_dec, key=lambda d: RANK[d])
        for pid in chosen:
            entry = catalog[pid]
            for fl in FLAG_NAMES:
                v = entry[fl]
                if v == "yes" or (v == "conditional" and flags[fl] == "no"):
                    flags[fl] = v
            if entry["obligations"] and entry["obligations"] != "None":
                obligations.append(f"{pid}: {entry['obligations']}")
        if policy is None:
            reasons.append("no licence policy supplied")
        else:
            missing = [p for p in chosen if p not in policy]
            if missing:
                reasons.append("not in policy: " + ", ".join(missing) + " — review by Legal counsel")
            else:
                reasons.append("policy: " + "; ".join(f"{p} = {policy[p]}" for p in chosen))
    commercial = c["use"] in ("commercial", "redistribution")
    if commercial and flags["commercial_use_restricted"] == "yes":
        decision = "deny"
        reasons.append(f"use '{c['use']}' conflicts with a non-commercial licence")
    elif commercial and flags["commercial_use_restricted"] == "conditional":
        reasons.append("conditional commercial terms: confirm eligibility with Legal counsel")
        if decision == "allow":
            decision = "review"
    flag_list = [f if flags[f] == "yes" else f"{f}:conditional" for f in FLAG_NAMES if flags[f] != "no"]
    return {
        "component": c["component"], "type": c["type"], "version": c["version"] or TBD_ENG,
        "license_raw": raw or TBD_ENG, "spdx_id": spdx, "decision": decision, "reason": "; ".join(reasons),
        "flags": ";".join(flag_list) or "none", "use": c["use"], "source_url": c["source_url"],
        "obligations": obligations, "parts": parts if spdx != "unknown" else [], "op": op,
    }


def cdx_licenses(r: dict, catalog: dict) -> list:
    if r["spdx_id"] == "unknown":
        return [{"license": {"name": r["license_raw"], "acknowledgement": "declared"}}] if r["license_raw"] != TBD_ENG else []
    if len(r["parts"]) == 1 and not r["spdx_id"].startswith("LicenseRef-"):
        return [{"license": {"id": r["spdx_id"], "acknowledgement": "declared"}}]
    return [{"expression": r["spdx_id"], "acknowledgement": "declared"}]


def to_cyclonedx(rows: list[dict], catalog: dict, system: str | None, gate: str) -> dict:
    comps, svcs = [], []
    for n, r in enumerate(rows, start=1):
        item = {"bom-ref": f"aibom-{n}", "name": r["component"]}
        if r["version"] != TBD_ENG:
            item["version"] = r["version"]
        lic = cdx_licenses(r, catalog)
        if lic:
            item["licenses"] = lic
        if r["source_url"]:
            item["externalReferences"] = [{"type": "website", "url": r["source_url"]}]
        item["properties"] = [{"name": "giri-skills:decision", "value": r["decision"]},
                              {"name": "giri-skills:flags", "value": r["flags"]},
                              {"name": "giri-skills:reason", "value": r["reason"]},
                              {"name": "giri-skills:use", "value": r["use"]}]
        if r["type"] == "service":
            svcs.append(item)
        else:
            comps.append({"type": TYPES[r["type"]], **item})
    bom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1}
    if system:
        bom["metadata"] = {"component": {"type": "application", "bom-ref": "system", "name": system}}
    bom["components"] = comps
    bom["services"] = svcs
    counts = {d: sum(1 for r in rows if r["decision"] == d) for d in DECISIONS}
    counts["tbd"] = sum(1 for r in rows if r["decision"] == TBD_LEGAL)
    bom["properties"] = [{"name": "giri-skills:gate", "value": gate}] + \
        [{"name": f"giri-skills:count:{k}", "value": str(v)} for k, v in counts.items()]
    return bom


def cell(s: str) -> str:
    return s.replace("|", "\\|")


def render(rows: list[dict], system: str | None, policy_given: bool, gate: str) -> str:
    deny = [r for r in rows if r["decision"] == "deny"]
    review = [r for r in rows if r["decision"] in ("review", TBD_LEGAL)]
    allow = [r for r in rows if r["decision"] == "allow"]
    unknown = [r for r in rows if r["spdx_id"] == "unknown"]
    L = [f"# AI-BOM licence check — {system or TBD_ENG}", "",
         "## Summary", "",
         f"**Release gate: {'FAIL' if gate == 'fail' else 'PASS'}** — {len(deny)} blocked, {len(review)} need review, "
         f"{len(allow)} allowed, of {len(rows)} components ({len(unknown)} with an unrecognised licence).", ""]
    if not policy_given:
        L += [f"No licence policy supplied: every decision is {TBD_LEGAL}.", ""]
    L += ["| Type | Components |", "|---|---|"]
    for t in TYPES:
        L.append(f"| {t} | {sum(1 for r in rows if r['type'] == t)} |")
    L += ["", "Not legal advice: decisions apply the organisation's policy; Legal counsel owns every review.", "",
          "## Components", "", "| Component | Type | Version | Use | Licence (raw) | SPDX id | Decision | Flags |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {cell(r['component'])} | {r['type']} | {cell(r['version'])} | {r['use']} | {cell(r['license_raw'])} | "
                 f"{r['spdx_id']} | {r['decision']} | {r['flags']} |")
    L += ["", "## Blocked", ""]
    if deny:
        L += ["| Component | Licence | Reason |", "|---|---|---|"]
        L += [f"| {cell(r['component'])} | {r['spdx_id']} | {cell(r['reason'])} |" for r in deny]
    else:
        L.append("None: no component is denied.")
    L += ["", "## Needs review", ""]
    if review:
        L += ["| Component | Licence | Decision | Reason | Owner |", "|---|---|---|---|---|"]
        L += [f"| {cell(r['component'])} | {r['spdx_id']} | {r['decision']} | {cell(r['reason'])} | Legal counsel |"
              for r in review]
    else:
        L.append("None.")
    L += ["", "## Obligations", "", "Obligations that apply if the component ships (from the licence catalog):", ""]
    obs = [(r["component"], o) for r in rows if r["decision"] != "deny" for o in r["obligations"]]
    if obs:
        L += ["| Component | Obligation |", "|---|---|"]
        L += [f"| {cell(c)} | {cell(o)} |" for c, o in obs]
    else:
        L.append("None recorded.")
    if unknown:
        L += ["", f"Obligations for unrecognised licences: {TBD_LEGAL}."]
    L += ["", "## Method", "",
          "- Licence strings normalised through `assets/license-catalog.csv` (SPDX License List 3.29.0 ids; "
          "LicenseRef- ids for AI licences SPDX does not list). Unknown strings stay `unknown` and go to review.",
          "- Decision = the policy's decision for the normalised id; ids missing from the policy go to review; "
          "no policy means every decision is TBD for Legal counsel.",
          "- Commercial or redistribution use of a non-commercial licence is denied; conditional commercial terms "
          "(Llama 700M MAU clause) turn an allow into a review.",
          "- `aibom.json` is a CycloneDX-shaped subset (bomFormat, specVersion 1.6, components with type "
          "machine-learning-model/data/library, services, licenses, externalReferences, properties); it is not "
          "schema-validated here.",
          "- Limits: catalog flags summarise licence terms; they do not replace reading the licence. Not legal advice."]
    return "\n".join(L) + "\n"


def build(bom_path: Path, policy_path: Path | None, system: str | None) -> tuple[list[dict], dict, str]:
    catalog, index = load_catalog()
    bom = load_bom(bom_path)
    policy = load_policy(policy_path, index)
    rows = [evaluate(c, catalog, index, policy) for c in bom]
    gate = "fail" if any(r["decision"] == "deny" for r in rows) else "pass"
    return rows, to_cyclonedx(rows, catalog, system, gate), render(rows, system, policy is not None, gate)


def write(rows, bom, md, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLS)
    for r in rows:
        w.writerow([r[c] for c in CSV_COLS])
    (out / "aibom.csv").write_text(buf.getvalue(), encoding="utf-8")
    (out / "aibom.json").write_text(json.dumps(bom, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "license-report.md").write_text(md, encoding="utf-8")


def verify(target: Path) -> list[str]:
    out = target if target.is_dir() else target.parent
    probs = [f"{n} missing" for n in ("aibom.csv", "aibom.json", "license-report.md") if not (out / n).is_file()]
    if probs:
        return probs
    catalog, _ = load_catalog()
    rows = list(csv.DictReader((out / "aibom.csv").open(encoding="utf-8")))
    bom = json.loads((out / "aibom.json").read_text(encoding="utf-8"))
    md = (out / "license-report.md").read_text(encoding="utf-8")
    if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != "1.6":
        probs.append("bomFormat/specVersion not CycloneDX 1.6")
    comps, svcs = bom.get("components", []), bom.get("services", [])
    for c in comps:
        if c.get("type") not in CDX_TYPES:
            probs.append(f"component {c.get('name')}: type {c.get('type')!r} not in CycloneDX 1.6 enum")
    if len(comps) + len(svcs) != len(rows):
        probs.append("components + services != rows in aibom.csv")
    names = {(x["name"], x.get("version", TBD_ENG)) for x in comps + svcs}
    for i, r in enumerate(rows, start=2):
        if (r["component"], r["version"]) not in names:
            probs.append(f"line {i}: {r['component']} missing from aibom.json")
        if r["decision"] not in DECISIONS and r["decision"] != TBD_LEGAL:
            probs.append(f"line {i}: decision {r['decision']!r} invalid")
        ids = [p for p in re.split(r"\s(?:OR|AND)\s", r["spdx_id"])]
        if r["spdx_id"] != "unknown" and any(p not in catalog for p in ids):
            probs.append(f"line {i}: spdx_id {r['spdx_id']!r} not in catalog")
        if r["use"] in ("commercial", "redistribution") and "commercial_use_restricted" in r["flags"].split(";") \
                and r["decision"] != "deny":
            probs.append(f"line {i}: commercial use of a non-commercial licence not denied")
    gate = "fail" if any(r["decision"] == "deny" for r in rows) else "pass"
    props = {p["name"]: p["value"] for p in bom.get("properties", [])}
    if props.get("giri-skills:gate") != gate:
        probs.append("gate property does not match decisions")
    if f"**Release gate: {gate.upper()}**" not in md:
        probs.append("license-report.md gate line does not match")
    for s in SECTIONS:
        if f"## {s}" not in md:
            probs.append(f"license-report.md missing section {s}")
    return probs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bom", type=Path, help="BOM CSV component,type,version,license,source_url,use")
    ap.add_argument("--policy", type=Path, help="licence policy CSV license,decision,notes")
    ap.add_argument("--system", help="name of the AI system the BOM describes")
    ap.add_argument("--out-dir", type=Path, help="directory for aibom.csv, aibom.json, license-report.md")
    ap.add_argument("--verify", type=Path, metavar="OUTPUT", help="re-check an AI-BOM output (any file in the out dir)")
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
    if a.bom is None or a.out_dir is None:
        print("error: --bom and --out-dir are required", file=sys.stderr)
        return 2
    try:
        rows, bom, md = build(a.bom, a.policy, a.system or None)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write(rows, bom, md, a.out_dir)
    deny = [r["component"] for r in rows if r["decision"] == "deny"]
    print(f"AI-BOM written: {len(rows)} components, {len(deny)} denied, "
          f"{sum(1 for r in rows if r['decision'] in ('review', TBD_LEGAL))} need review")
    if deny:
        print("GATE: denied component(s): " + ", ".join(deny), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
