#!/usr/bin/env python3
"""Risk register + model card from a filled use-case canvas and the controls catalog.

    python3 -I scripts/risk_register.py use-case-canvas.md --out-dir runs/x \
        [--controls references/controls-catalog.md] [--template assets/model-card.md] [--name "Ticket triage"] \
        [--existing last-quarter/risk-register.csv]

Canvas (ai-use-case-canvas assets/use-case-canvas.md layout): the nine-box table
`| # | Box | Content |` is parsed by box name; `key: value;` pairs inside a box are read
(Tier, autonomy, sensitivity, owner, Sources, top risks ...). Headings and the Verdict line are
read when present.

Register rules (references/risk-taxonomy.md): one row per taxonomy category. Impact comes from
the canvas tier (low=2, medium=3, high=5 per the taxonomy's impact scale; basis cited) and likelihood is 3 only when the canvas
names that category among its top risks — anything the canvas does not support stays
`[TO BE BASELINED — owner: AI risk lead]`, and the rating is TBD until both scores exist.
Rating = L x I: >= 15 High, 8-14 Medium, < 8 Low. Controls are mapped per category from the
catalog's `| ID | Control | Addresses | ... |` table ("All" matches every category).

Existing register (--existing, e.g. last quarter's risk-register.csv; this script's columns, or the
assets/risk-register.csv layout with likelihood_1_5 / impact_1_5 / control_ids / control_owner): rows
are matched by category. The canvas still wins wherever it supports a value; where it gives none, a
reviewed 1-5 score and a named owner are carried forward (basis says so, to be re-confirmed), the
previous risk_id is kept so IDs stay stable, and previously accepted control ids that are still in
the catalog stay mapped. Every carry-forward and every change is listed in register-diff.csv;
existing rows whose category is not in the taxonomy are listed there, never dropped silently.

Writes risk-register.csv (risk_id, category, description, likelihood, impact, rating, control_id,
control, owner, basis), register-diff.csv (risk_id, category, field, previous, current, change;
header only when no existing register is given) and model-card.md (assets/model-card.md with the canvas facts filled; the
tier's minimum control set listed in §7). Exit 1 when any High-rated risk has no mapped control,
or on a missing/unparseable canvas or catalog. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
TBD = "[TO BE BASELINED — owner: AI risk lead]"
CATEGORIES = [("bias", "Bias / fairness"), ("privacy", "Privacy"), ("hallucination", "Hallucination / accuracy"),
              ("ip", "IP / copyright"), ("security", "Security"), ("misuse", "Misuse"),
              ("operational", "Operational"), ("transparency", "Transparency / accountability"),
              ("safety", "Safety (physical / wellbeing)")]
SYNONYMS = {"bias": ["bias", "fairness"], "privacy": ["privacy", "pii", "personal data"],
            "hallucination": ["hallucination", "accuracy", "fabricat"], "ip": ["ip ", "ip)", "ip,", "copyright", "licen"],
            "security": ["security", "injection", "exfiltrat"], "misuse": ["misuse", "out-of-scope use", "out of scope use"],
            "operational": ["operational", "drift", "vendor", "outage"], "transparency": ["transparency", "disclos", "contest", "appeal"],
            "safety": ["safety", "wellbeing", "harm"]}
TIER_IMPACT = {"low": 2, "medium": 3, "high": 5}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_canvas(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    boxes: dict[str, str] = {}
    for ln in text.splitlines():
        m = re.match(r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$", ln)
        if m:
            boxes[m.group(1).lower()] = m.group(2)
    if not boxes:
        die(f"{path.name}: no canvas box table found (expected `| # | Box | Content |` rows)")
    fields: dict[str, str] = {}
    for content in boxes.values():
        for part in content.split(";"):
            if ":" in part:
                k, _, v = part.partition(":")
                k, v = k.strip().lower(), v.strip()
                if k and v and not v.startswith("<") and k not in fields:
                    fields[k] = v
    m = re.search(r"^\*\*Verdict:\*\*\s*(.+)$", text, re.M)
    title = re.search(r"^#\s+AI Use-Case Canvas\s+[—-]\s+(.+?)\s+[—-]", text, re.M)
    return {"boxes": boxes, "fields": fields, "verdict": (m.group(1).strip() if m else ""),
            "name": (title.group(1).strip() if title else "")}


def box(c: dict, key: str) -> str:
    for k, v in c["boxes"].items():
        if key in k:
            return v.strip()
    return ""


def is_filled(v: str) -> bool:
    return bool(v) and not v.startswith("<") and "[TO BE BASELINED" not in v


def parse_catalog(path: Path) -> tuple[list[dict], dict[str, list[str]]]:
    if not path.is_file():
        die(f"controls catalog not found: {path}")
    controls, tiers = [], {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        cells = [x.strip() for x in ln.strip().strip("|").split("|")] if ln.startswith("|") else []
        if len(cells) >= 3 and re.fullmatch(r"C\d+", cells[0]):
            controls.append({"id": cells[0], "control": cells[1], "addresses": cells[2].lower()})
        elif len(cells) == 2 and cells[0].lower() in TIER_IMPACT:
            tiers[cells[0].lower()] = re.findall(r"C\d+", cells[1]) + (["(see lower tiers)"] if "+" in cells[1] else [])
    if not controls:
        die(f"{path.name}: no controls table found (`| C01 | ... | Addresses | ... |`)")
    return controls, tiers


def controls_for(cat: str, controls: list[dict]) -> list[dict]:
    label = dict(CATEGORIES)[cat].split(" ")[0].lower()
    return [c for c in controls if c["addresses"] == "all" or label in c["addresses"]]


def tier_controls(tier: str, tiers: dict) -> list[str]:
    order = ["low", "medium", "high"]
    if tier not in order:
        return []
    ids = []
    for t in order[: order.index(tier) + 1]:
        ids += [i for i in tiers.get(t, []) if i.startswith("C") and i not in ids]
    return ids


DIFF_COLS = ["risk_id", "category", "field", "previous", "current", "change"]
EXISTING_ALIASES = {"likelihood": ("likelihood", "likelihood_1_5"), "impact": ("impact", "impact_1_5"),
                    "owner": ("owner", "control_owner"), "control_id": ("control_id", "control_ids")}


def unset(v) -> bool:
    s = str(v if v is not None else "").strip()
    return not s or s.upper() == "TBD" or s.startswith("[TO BE BASELINED") or s.startswith("<")


def score(v) -> int | None:
    s = str(v or "").strip()
    return int(s) if s.isdigit() and 1 <= int(s) <= 5 else None


def load_existing(path: Path) -> list[dict]:
    if not path.is_file():
        die(f"existing register not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8-sig").splitlines() if not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(lines))
    if not rows or "category" not in rows[0]:
        die(f"{path.name}: existing register needs a category column and at least one row")
    out = []
    for r in rows:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items() if k is not None}
        rec = {"risk_id": r.get("risk_id", ""), "category": r.get("category", "").lower()}
        for field, names in EXISTING_ALIASES.items():
            rec[field] = next((r[n] for n in names if r.get(n)), "")
        out.append(rec)
    return out


def rating_of(likelihood, impact) -> str:
    if isinstance(likelihood, int) and isinstance(impact, int):
        s = likelihood * impact
        return "High" if s >= 15 else "Medium" if s >= 8 else "Low"
    return "TBD"


def merge_existing(rows: list[dict], existing: list[dict], controls: list[dict], src: str) -> list[dict]:
    """Carry reviewed values forward from an existing register; return the diff rows."""
    byid = {c["id"]: c for c in controls}
    known = {cat for cat, _ in CATEGORIES}
    prev = {}
    diff = []
    for e in existing:
        if e["category"] in known and e["category"] not in prev:
            prev[e["category"]] = e
        else:
            why = "category not in the taxonomy" if e["category"] not in known else "duplicate category"
            diff.append({"risk_id": e["risk_id"], "category": e["category"], "field": "row", "previous": e["risk_id"],
                         "current": "", "change": f"not carried: {why} — review with {TBD}"})
    used = {e["risk_id"] for e in existing if e["risk_id"]}
    nums = [int(m.group(1)) for i in used if (m := re.fullmatch(r"R-(\d+)", i))]
    nxt = max(nums, default=0) + 1
    for r in rows:
        e = prev.get(r["category"])
        if e is not None and e["risk_id"]:
            r["risk_id"] = e["risk_id"]  # IDs stay stable across reviews
        elif r["risk_id"] in used:
            r["risk_id"] = f"R-{nxt:03d}"
            nxt += 1
        if e is None:
            diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": "row", "previous": "",
                         "current": r["risk_id"], "change": "new: category not in the existing register"})
            continue
        basis = [r["basis"]] if r["basis"] != "canvas gives no basis for scores" else []
        for field in ("likelihood", "impact"):
            old = score(e[field])
            cur = r[field] if isinstance(r[field], int) else None
            if cur is None and old is not None:
                r[field] = old
                basis.append(f"{field} {old} carried forward from {src} {e['risk_id'] or r['category']} (re-confirm)")
                diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": field, "previous": str(old),
                             "current": str(old), "change": "carried forward: canvas gives no basis"})
            elif cur is not None and old is not None and cur != old:
                diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": field, "previous": str(old),
                             "current": str(cur), "change": "updated from the canvas"})
            elif cur is not None and old is None:
                diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": field,
                             "previous": e[field] or "blank", "current": str(cur), "change": "newly scored from the canvas"})
        if unset(r["owner"]) and not unset(e["owner"]):
            r["owner"] = e["owner"]
            diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": "owner", "previous": e["owner"],
                         "current": e["owner"], "change": "carried forward: canvas names no owner"})
        elif not unset(r["owner"]) and not unset(e["owner"]) and r["owner"] != e["owner"]:
            diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": "owner", "previous": e["owner"],
                         "current": r["owner"], "change": "updated from the canvas"})
        ids = [i for i in r["control_id"].split("; ") if i]
        old_ids = re.findall(r"C\d+", e["control_id"])
        kept = [i for i in old_ids if i in byid and i not in ids]
        gone = [i for i in old_ids if i not in byid]
        if kept:
            ids += kept
            r["control_id"] = "; ".join(ids)
            r["control"] = "; ".join(byid[i]["control"] for i in ids)
            diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": "control_id",
                         "previous": "; ".join(old_ids), "current": r["control_id"],
                         "change": "carried forward: previously accepted controls still in the catalog"})
        if gone:
            diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": "control_id",
                         "previous": "; ".join(gone), "current": "", "change": f"not carried: not in the controls catalog — review with {TBD}"})
        old_rating = rating_of(score(e["likelihood"]), score(e["impact"]))
        r["rating"] = rating_of(r["likelihood"] if isinstance(r["likelihood"], int) else None,
                                r["impact"] if isinstance(r["impact"], int) else None)
        if old_rating != r["rating"]:
            diff.append({"risk_id": r["risk_id"], "category": r["category"], "field": "rating", "previous": old_rating,
                         "current": r["rating"], "change": "re-rated"})
        r["basis"] = "; ".join(basis) or "canvas gives no basis for scores"
    return diff


def main() -> int:
    ap = argparse.ArgumentParser(description="use-case canvas + controls catalog -> risk-register.csv + model-card.md")
    ap.add_argument("canvas")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--controls", default=str(SKILL / "references" / "controls-catalog.md"))
    ap.add_argument("--template", default=str(SKILL / "assets" / "model-card.md"))
    ap.add_argument("--name", default="")
    ap.add_argument("--existing", default="", help="existing risk register CSV (e.g. last quarter's) to carry forward")
    a = ap.parse_args()
    cp = Path(a.canvas)
    if not cp.is_file():
        die(f"canvas not found: {cp}")
    c = parse_canvas(cp)
    controls, tiers = parse_catalog(Path(a.controls))
    name = a.name or c["name"] or "<system name>"
    f = c["fields"]
    tier = next((t for t in TIER_IMPACT if t in f.get("tier", "").lower()), "")
    top_risks = box(c, "risks and tier").lower()
    autonomy = f.get("autonomy", "")
    sensitivity = f.get("sensitivity", "")
    data_owner = f.get("owner", "")
    users = box(c, "problem and user")
    decision = box(c, "decision or task")

    rows, unmapped_high = [], []
    for i, (cat, label) in enumerate(CATEGORIES, 1):
        basis = []
        impact = TIER_IMPACT.get(tier)
        if impact:
            basis.append(f"impact from tier={tier} (canvas box 8)")
        named = any(s in top_risks for s in SYNONYMS[cat]) and is_filled(top_risks)
        likelihood = 3 if named else None
        if named:
            basis.append("likelihood 3: named as a top risk in canvas box 8")
        if likelihood and impact:
            score = likelihood * impact
            rating = "High" if score >= 15 else "Medium" if score >= 8 else "Low"
        else:
            rating = "TBD"
        desc = {
            "bias": f"Outputs systematically disadvantage a group in: {decision or TBD}",
            "privacy": f"Personal data exposed or retained beyond purpose; sensitivity: {sensitivity or TBD}",
            "hallucination": f"Confident false output acted on by: {users or TBD}",
            "ip": "Protected content leaks into or out of the system (training/retrieval provenance)",
            "security": f"Prompt injection or tool abuse; autonomy: {autonomy or TBD}",
            "misuse": "System used outside the canvas's intended decision or task",
            "operational": "Model/vendor change, drift, cost or outage breaks the workflow",
            "transparency": "Users unaware of AI involvement or unable to contest the outcome",
            "safety": "Advice or action harms people (vulnerable users, action-taking)",
        }[cat]
        mapped = controls_for(cat, controls)
        if rating == "High" and not mapped:
            unmapped_high.append(cat)
        rows.append({"risk_id": f"R-{i:03d}", "category": cat, "description": desc,
                     "likelihood": likelihood if likelihood else TBD, "impact": impact if impact else TBD,
                     "rating": rating, "control_id": "; ".join(m["id"] for m in mapped),
                     "control": "; ".join(m["control"] for m in mapped),
                     "owner": data_owner if (cat == "privacy" and data_owner) else TBD,
                     "basis": "; ".join(basis) or "canvas gives no basis for scores"})

    diff = []
    if a.existing:
        ep = Path(a.existing)
        diff = merge_existing(rows, load_existing(ep), controls, f"existing register `{ep.name}`")
        unmapped_high = [r["category"] for r in rows if r["rating"] == "High" and not r["control_id"]]

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "register-diff.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=DIFF_COLS)
        w.writeheader()
        w.writerows(diff)
    with (out / "risk-register.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["risk_id", "category", "description", "likelihood", "impact", "rating",
                                           "control_id", "control", "owner", "basis"])
        w.writeheader()
        w.writerows(rows)

    tpl_path = Path(a.template)
    if not tpl_path.is_file():
        die(f"template not found: {tpl_path}")
    t = tpl_path.read_text(encoding="utf-8")
    t = t.replace("<system name>", name).replace("<version>", "0.1").replace("<date>", TBD)
    t = t.replace("| Risk tier (internal / EU AI Act summary) | |",
                  f"| Risk tier (internal / EU AI Act summary) | {tier or TBD} / {TBD} |")
    t = t.replace("| Owner (business) | |", f"| Owner (business) | {f.get('baseline signed by', '') or TBD} |")
    t = t.replace("| Owner (technical) | |", f"| Owner (technical) | {TBD} |")
    t = t.replace("- Purpose:", f"- Purpose: {users or TBD}")
    t = t.replace("- Users:", f"- Users: {f.get('users', '') or TBD}")
    t = t.replace("- Decisions or actions influenced:", f"- Decisions or actions influenced: {decision or TBD}")
    t = t.replace("- Autonomy level and human oversight:", f"- Autonomy level and human oversight: {autonomy or TBD}")
    t = t.replace("## 2. Out-of-scope uses (explicit)\n- \n- ", f"## 2. Out-of-scope uses (explicit)\n- {TBD}\n- {TBD}")
    t = t.replace("| Retrieval sources | |", f"| Retrieval sources | {f.get('sources', '') or TBD} |")
    t = t.replace("| Tools and side effects | |", f"| Tools and side effects | {('autonomy: ' + autonomy) if autonomy else TBD} |")
    t = t.replace("| Data entering prompts (categories; PII handling) | |",
                  f"| Data entering prompts (categories; PII handling) | sensitivity: {sensitivity or TBD}; owner: {data_owner or TBD} |")
    t = t.replace("| Retrieval corpus (owner, ACL, refresh) | |",
                  f"| Retrieval corpus (owner, ACL, refresh) | {f.get('sources', '') or TBD}; access: {f.get('access', '') or TBD}; freshness: {f.get('freshness', '') or TBD} |")
    t = t.replace("## 6. Limitations and known failure modes\n- \n- ",
                  "## 6. Limitations and known failure modes\n- " + "\n- ".join(
                      f"{r['category']}: {r['description']} (rating {r['rating']})" for r in rows if r["rating"] in ("High", "Medium"))
                  + (f"\n- {TBD}" if not any(r["rating"] in ("High", "Medium") for r in rows) else ""))
    req = tier_controls(tier, tiers)
    byid = {x["id"]: x for x in controls}
    ctl_rows = [f"| {i} — {byid[i]['control'] if i in byid else ''} | planned — {TBD} | {TBD} |" for i in req] \
        or [f"| {TBD} (tier not stated in canvas) | | |"]
    t = t.replace("| Control (ID) | Status | Evidence |\n|---|---|---|",
                  "| Control (ID) | Status | Evidence |\n|---|---|---|\n" + "\n".join(ctl_rows))
    t = re.sub(r"^(\| [^|]+ \|) \|$", lambda m: f"{m.group(1)} {TBD} |", t, flags=re.M)
    t = re.sub(r"^(- [^:\n]+:)\s*$", lambda m: f"{m.group(1)} {TBD}", t, flags=re.M)
    t += ("\nSummary mapping for planning; legal review required for obligations. "
          f"Facts above come from the canvas `{cp.name}`; everything else is marked {TBD}.\n")
    (out / "model-card.md").write_text(t, encoding="utf-8")

    n_tbd = sum(r["rating"] == "TBD" for r in rows)
    print(f"risk register: {len(rows)} risks ({n_tbd} unscored), tier={tier or 'TBD'}, {len(req)} required controls -> {out}"
          + (f"; {len(diff)} change(s) against `{Path(a.existing).name}` in register-diff.csv" if a.existing else ""))
    if unmapped_high:
        print(f"error: High-rated risk(s) without a mapped control: {unmapped_high}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
