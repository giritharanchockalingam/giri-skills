#!/usr/bin/env python3
"""AI threat model: STRIDE per DFD element + OWASP Top 10 for LLM Applications (2025) per component.

Usage:
  python3 -I threat_model.py --components C.csv --flows F.csv [--controls K.csv]
                             [--max-open-high N] --out-dir OUT
  python3 -I threat_model.py --verify OUT/threats.csv      # structural re-check of a threats.csv

Inputs ('#' lines are comments):
  components  id,name,kind,trust_zone,handles_pii,write_actions,internet_facing
              kind in user|app|llm|retriever|vector_store|tool|data_store|external_api|agent
  flows       from,to,data,crosses_trust_boundary      (yes/no; zones that differ force yes)
  controls    threat_id,mitigation_id,status,evidence,owner   (status in_place|planned;
              each row names a threat_id OR a mitigation_id)

Rules (full text in references/method.md):
  Element type: user/external_api -> external_entity (S,R); app/llm/retriever/tool/agent ->
  process (S,T,R,I,D,E); vector_store/data_store -> data_store (T,I,D); every flow ->
  data_flow (T,I,D)  [Microsoft STRIDE-per-element, MSDN Magazine Nov 2006, Figure 5].
  OWASP LLM items by component kind and flags (assets/owasp-llm-top10-2025.csv).
  Likelihood 1-3 = 1 + exposed (internet_facing; for a flow, either end internet_facing)
                    + boundary (component touches a boundary-crossing flow; flow crosses).
  Impact 1-3     = 1 + handles_pii (if category in PII_CATS) + write_actions (if in WRITE_CATS);
                   D and LLM10 are fixed at 2.
  Severity: L x I >= 6 high, 3-4 medium, <= 2 low.
  Status: mitigated if a threat_id control is in_place or every listed mitigation is in_place;
          planned if any matching control exists; else open.
Outputs: OUT/threats.csv, OUT/dfd.md, OUT/threat-report.md.
Exit: 0 ok · 1 open high threats > --max-open-high (outputs still written) · 2 bad/missing input.
Stdlib only; deterministic (input order, no timestamps).
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
OWNER_TBD = "[TO BE BASELINED — owner: Security architect]"

KINDS = ("user", "app", "llm", "retriever", "vector_store", "tool", "data_store", "external_api", "agent")
ELEMENT_TYPE = {"user": "external_entity", "external_api": "external_entity",
                "app": "process", "llm": "process", "retriever": "process", "tool": "process", "agent": "process",
                "vector_store": "data_store", "data_store": "data_store"}
STRIDE = ("S", "T", "R", "I", "D", "E")
STRIDE_NAME = {"S": "Spoofing", "T": "Tampering", "R": "Repudiation", "I": "Information disclosure",
               "D": "Denial of service", "E": "Elevation of privilege"}
STRIDE_PER_ELEMENT = {"external_entity": "SR", "process": "STRIDE", "data_store": "TID", "data_flow": "TID"}
PII_CATS = {"S", "T", "I", "E", "LLM01", "LLM02", "LLM03", "LLM04", "LLM07", "LLM08"}
WRITE_CATS = {"S", "T", "R", "E", "LLM01", "LLM03", "LLM05", "LLM06", "LLM09"}
FIXED_IMPACT = {"D": 2, "LLM10": 2}
UNTRUSTED_KINDS = {"user", "external_api", "retriever", "vector_store"}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
THREAT_COLS = ["threat_id", "element", "element_type", "category", "threat", "likelihood", "impact",
               "severity", "mitigation", "status", "owner", "evidence"]

STRIDE_TEXT = {
    ("external_entity", "S"): "Someone impersonates {name} to the system (stolen session, forged identity or key).",
    ("external_entity", "R"): "{name} denies having sent a request or approved an action, and no record proves it.",
    ("process", "S"): "An attacker impersonates {name} or its caller to obtain its privileges.",
    ("process", "T"): "Code, configuration or in-memory state of {name} is altered to change its behaviour.",
    ("process", "R"): "Actions taken by {name} cannot be attributed to a user or request afterwards.",
    ("process", "I"): "{name} exposes data it processes through responses, errors or logs.",
    ("process", "D"): "{name} is overloaded or crashed so the service becomes unavailable.",
    ("process", "E"): "A caller of {name} gains rights it was not granted (for example by abusing its service identity).",
    ("data_store", "T"): "Records in {name} are modified or deleted without authorisation.",
    ("data_store", "I"): "Data in {name} is read by a party that should not see it.",
    ("data_store", "D"): "{name} is filled, locked or corrupted so dependants cannot use it.",
    ("data_flow", "T"): "The {name} message is altered in transit.",
    ("data_flow", "I"): "The {name} message is intercepted or observed in transit.",
    ("data_flow", "D"): "The {name} flow is blocked, flooded or dropped.",
}
OWASP_TEXT = {
    "LLM01": "Direct or indirect prompt injection reaching {name} (from {src}) overrides its instructions.",
    "LLM02": "{name} discloses personal or confidential data in its output.",
    "LLM03": "A compromised or vulnerable third-party model, library or tool in {name} is used.",
    "LLM04": "Data feeding {name} (training, fine-tuning or embeddings) is poisoned.",
    "LLM05": "{name} acts on model output from {src} without validation or encoding.",
    "LLM06": "{name} performs write actions beyond what the task needs when the model is manipulated or wrong.",
    "LLM07": "The system prompt of {name} leaks, exposing instructions or secrets placed in it.",
    "LLM08": "{name} returns or leaks embeddings or chunks across users or tenants, or serves poisoned content.",
    "LLM09": "{name} produces false or misleading content that users or downstream steps rely on.",
    "LLM10": "Unbounded requests to {name} exhaust capacity or budget, or enable model extraction.",
}


class InputError(Exception):
    pass


def read_csv(path: Path, label: str, required_cols: list[str]) -> list[dict]:
    if not path.is_file():
        raise InputError(f"{label}: file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise InputError(f"{label}: file is empty")
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    header = [h.strip() for h in (csv.DictReader(io.StringIO(lines[0])).fieldnames or [])]
    missing = [c for c in required_cols if c not in header]
    if missing:
        raise InputError(f"{label}: missing column(s) {', '.join(missing)}; header is {', '.join(header)}")
    out = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rows]
    if not out:
        raise InputError(f"{label}: no data rows")
    return out


def yes_no(v: str, label: str) -> bool:
    v = v.strip().lower()
    if v not in ("yes", "no"):
        raise InputError(f"{label}: expected yes or no, got {v!r}")
    return v == "yes"


def load_components(path: Path) -> list[dict]:
    rows = read_csv(path, "components", ["id", "name", "kind", "trust_zone", "handles_pii",
                                         "write_actions", "internet_facing"])
    seen, out = set(), []
    for n, r in enumerate(rows, 2):
        cid, kind = r["id"], r["kind"].lower()
        if not ID_RE.match(cid):
            raise InputError(f"components row {n}: id {cid!r} must be letters, digits or _ (start with a letter)")
        if cid in seen:
            raise InputError(f"components row {n}: duplicate id {cid!r}")
        if kind not in KINDS:
            raise InputError(f"components row {n}: kind {kind!r} not in {'|'.join(KINDS)}")
        if not r["trust_zone"]:
            raise InputError(f"components row {n}: trust_zone is blank")
        seen.add(cid)
        out.append({"id": cid, "name": r["name"] or cid, "kind": kind, "zone": r["trust_zone"],
                    "pii": yes_no(r["handles_pii"], f"components row {n} handles_pii"),
                    "write": yes_no(r["write_actions"], f"components row {n} write_actions"),
                    "internet": yes_no(r["internet_facing"], f"components row {n} internet_facing"),
                    "etype": ELEMENT_TYPE[kind]})
    return out


def load_flows(path: Path, comps: dict) -> list[dict]:
    rows = read_csv(path, "flows", ["from", "to", "data", "crosses_trust_boundary"])
    seen, out = set(), []
    for n, r in enumerate(rows, 2):
        a, b = r["from"], r["to"]
        for end in (a, b):
            if end not in comps:
                raise InputError(f"flows row {n}: unknown component {end!r}")
        if a == b:
            raise InputError(f"flows row {n}: a flow needs two different components")
        if (a, b) in seen:
            raise InputError(f"flows row {n}: duplicate flow {a}>{b} (merge the data into one row)")
        seen.add((a, b))
        declared = yes_no(r["crosses_trust_boundary"], f"flows row {n} crosses_trust_boundary")
        zones_differ = comps[a]["zone"] != comps[b]["zone"]
        out.append({"id": f"{a}>{b}", "from": a, "to": b, "data": r["data"] or "data",
                    "crosses": declared or zones_differ, "corrected": zones_differ and not declared})
    return out


def load_mitigations() -> tuple[dict, list[dict]]:
    rows = read_csv(ASSETS / "mitigations.csv", "mitigations", ["id", "mitigation", "maps_to", "applies_to"])
    return {r["id"]: r for r in rows}, rows


def load_owasp() -> list[dict]:
    return read_csv(ASSETS / "owasp-llm-top10-2025.csv", "owasp", ["id", "name", "applies_to", "mitigation_ids"])


def load_controls(path: Path | None) -> list[dict]:
    if path is None:
        return []
    rows = read_csv(path, "controls", ["status"])
    for n, r in enumerate(rows, 2):
        if r.get("status", "").lower() not in ("in_place", "planned"):
            raise InputError(f"controls row {n}: status {r.get('status')!r} not in in_place|planned")
        if not r.get("threat_id") and not r.get("mitigation_id"):
            raise InputError(f"controls row {n}: give a threat_id or a mitigation_id")
        r["status"] = r["status"].lower()
    return rows


def reach_sources(comps: list[dict], flows: list[dict]) -> dict[str, list[str]]:
    """For each component: the untrusted origins (sorted ids) that reach it via flows."""
    adj: dict[str, list[str]] = {}
    for f in flows:
        adj.setdefault(f["from"], []).append(f["to"])
    origins = [c["id"] for c in comps if c["kind"] in UNTRUSTED_KINDS or c["internet"]]
    reached: dict[str, set] = {c["id"]: set() for c in comps}
    for o in origins:
        q, seen = deque(adj.get(o, [])), set()
        while q:
            x = q.popleft()
            if x in seen or x == o:
                continue
            seen.add(x)
            reached[x].add(o)
            q.extend(adj.get(x, []))
    return {k: sorted(v) for k, v in reached.items()}


def score(likelihood: int, impact: int) -> str:
    s = likelihood * impact
    return "high" if s >= 6 else "medium" if s >= 3 else "low"


def impact_for(cat: str, pii: bool, write: bool) -> int:
    if cat in FIXED_IMPACT:
        return FIXED_IMPACT[cat]
    return min(3, 1 + (pii and cat in PII_CATS) + (write and cat in WRITE_CATS))


def build_threats(comps: list[dict], flows: list[dict], mit_rows: list[dict], owasp: list[dict]) -> list[dict]:
    byid = {c["id"]: c for c in comps}
    touches = {c["id"]: False for c in comps}
    incoming: dict[str, list[str]] = {c["id"]: [] for c in comps}
    for f in flows:
        if f["crosses"]:
            touches[f["from"]] = touches[f["to"]] = True
        incoming[f["to"]].append(f["from"])
    sources = reach_sources(comps, flows)

    def stride_mits(cat: str, etype: str) -> list[str]:
        ids = [m["id"] for m in mit_rows if cat in m["maps_to"].split(";") and etype in m["applies_to"].split(";")]
        if not ids:
            raise InputError(f"mitigations.csv has no mitigation for {cat} on {etype}")
        return ids

    threats = []
    for c in comps:
        lik = 1 + c["internet"] + touches[c["id"]]
        for cat in STRIDE_PER_ELEMENT[c["etype"]]:
            threats.append({"threat_id": f"{c['id']}:{cat}", "element": c["id"], "element_type": c["etype"],
                            "category": cat, "threat": STRIDE_TEXT[(c["etype"], cat)].format(name=c["name"]),
                            "likelihood": lik, "impact": impact_for(cat, c["pii"], c["write"]),
                            "mits": stride_mits(cat, c["etype"])})
        for item in owasp:
            oid = item["id"]
            if c["kind"] not in item["applies_to"].split(";"):
                continue
            src = ""
            if oid == "LLM01":
                if not sources[c["id"]]:
                    continue
                src = ", ".join(sources[c["id"]])
            elif oid == "LLM02" and not c["pii"]:
                continue
            elif oid == "LLM05":
                feeders = sorted(x for x in incoming[c["id"]] if byid[x]["kind"] in ("llm", "agent"))
                if not feeders:
                    continue
                src = ", ".join(feeders)
            elif oid == "LLM06" and not c["write"]:
                continue
            threats.append({"threat_id": f"{c['id']}:{oid}", "element": c["id"], "element_type": c["etype"],
                            "category": oid, "threat": OWASP_TEXT[oid].format(name=c["name"], src=src),
                            "likelihood": lik, "impact": impact_for(oid, c["pii"], c["write"]),
                            "mits": item["mitigation_ids"].split(";")})
    for f in flows:
        a, b = byid[f["from"]], byid[f["to"]]
        lik = 1 + (a["internet"] or b["internet"]) + f["crosses"]
        pii, write = a["pii"] or b["pii"], b["write"]
        name = f"{a['name']} → {b['name']} ({f['data']})"
        for cat in STRIDE_PER_ELEMENT["data_flow"]:
            threats.append({"threat_id": f"{f['id']}:{cat}", "element": f["id"], "element_type": "data_flow",
                            "category": cat, "threat": STRIDE_TEXT[("data_flow", cat)].format(name=name),
                            "likelihood": lik, "impact": impact_for(cat, pii, write),
                            "mits": stride_mits(cat, "data_flow")})
    for t in threats:
        t["severity"] = score(t["likelihood"], t["impact"])
    return threats


def apply_controls(threats: list[dict], controls: list[dict]) -> list[dict]:
    """Set status/owner/evidence; return control rows that matched nothing."""
    tids = {t["threat_id"] for t in threats}
    mids = {m for t in threats for m in t["mits"]}
    unmatched = [r for r in controls
                 if (r.get("threat_id") and r["threat_id"] not in tids)
                 or (not r.get("threat_id") and r.get("mitigation_id") not in mids)]
    for t in threats:
        direct = [r for r in controls if r.get("threat_id") == t["threat_id"]]
        via = [r for r in controls if not r.get("threat_id") and r.get("mitigation_id") in t["mits"]]
        in_place_m = {r["mitigation_id"] for r in via if r["status"] == "in_place"}
        if any(r["status"] == "in_place" for r in direct) or set(t["mits"]) <= in_place_m:
            t["status"] = "mitigated"
        elif direct or via:
            t["status"] = "planned"
        else:
            t["status"] = "open"
        matched = direct + via
        owners = sorted({r.get("owner", "") for r in matched if r.get("owner", "")})
        t["owner"] = ";".join(owners) if owners else OWNER_TBD
        t["evidence"] = " | ".join(sorted({r.get("evidence", "") for r in matched if r.get("evidence", "")}))
    return unmatched


def write_threats(path: Path, threats: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(THREAT_COLS)
        for t in threats:
            w.writerow([t["threat_id"], t["element"], t["element_type"], t["category"], t["threat"],
                        t["likelihood"], t["impact"], t["severity"], ";".join(t["mits"]), t["status"],
                        t["owner"], t["evidence"]])


def label(s: str) -> str:
    return re.sub(r'[\[\]{}()"|<>#;]', " ", s).strip() or "x"


def render_dfd(comps: list[dict], flows: list[dict]) -> str:
    zones: dict[str, list[dict]] = {}
    for c in comps:
        zones.setdefault(c["zone"], []).append(c)
    shape = {"external_entity": ('["', '"]'), "process": ('("', '")'), "data_store": ('[("', '")]')}
    out = ["```mermaid", "flowchart LR"]
    for i, (z, cs) in enumerate(zones.items()):
        out.append(f'  subgraph Z{i}["Trust zone: {label(z)}"]')
        for c in cs:
            o, cl = shape[c["etype"]]
            out.append(f"    {c['id']}{o}{label(c['name'])}{cl}")
        out.append("  end")
    crossing = []
    for i, f in enumerate(flows):
        mark = "crosses boundary: " if f["crosses"] else ""
        out.append(f'  {f["from"]} -->|"{mark}{label(f["data"])}"| {f["to"]}')
        if f["crosses"]:
            crossing.append(str(i))
    if crossing:
        out.append(f"  linkStyle {','.join(crossing)} stroke:#c62828,stroke-width:2px,stroke-dasharray:5 3")
    out.append("```")
    n_cross = len(crossing)
    lines = ["# Data flow diagram", "",
             f"Components: {len(comps)} in {len(zones)} trust zones. Flows: {len(flows)}, "
             f"of which {n_cross} cross a trust boundary (dashed red).", "",
             "Each subgraph is a trust zone; its edge is a trust boundary. Shapes: rectangle = external entity, "
             "rounded = process, cylinder = data store.", "", *out, ""]
    corrected = [f["id"] for f in flows if f["corrected"]]
    if corrected:
        lines += ["Flows marked `crosses_trust_boundary=no` whose ends sit in different zones were treated as "
                  "crossing: " + ", ".join(corrected) + ".", ""]
    return "\n".join(lines)


def md_cell(s: str) -> str:
    return s.replace("|", "\\|")


def render_report(comps, flows, threats, unmatched, mit_by_id, owasp, max_open_high, controls_name) -> str:
    def count(**kw):
        return sum(1 for t in threats if all(t[k] == v for k, v in kw.items()))
    open_high = [t for t in threats if t["severity"] == "high" and t["status"] == "open"]
    gate = ("no gate set (`max_open_high` not given)" if max_open_high is None else
            f"{'FAIL' if len(open_high) > max_open_high else 'PASS'}: {len(open_high)} open high "
            f"vs limit {max_open_high}")
    owasp_hit = sorted({t["category"] for t in threats if t["category"].startswith("LLM")})
    lines = ["# AI threat model", "", "## Summary", "",
             f"- Threats: {len(threats)} ({count(severity='high')} high, {count(severity='medium')} medium, "
             f"{count(severity='low')} low) across {len(comps)} components and {len(flows)} flows.",
             f"- Status: {count(status='open')} open, {count(status='planned')} planned, "
             f"{count(status='mitigated')} mitigated.",
             f"- Open high threats: {len(open_high)}. Gate: {gate}.",
             f"- OWASP LLM Top 10 (2025) items in scope: {', '.join(owasp_hit) or 'none'}.",
             f"- Controls file: {controls_name or 'none supplied — every threat is open and owned by the Security architect until baselined'}.",
             "", "## Data flow", "",
             "See `dfd.md` for the diagram. Boundary-crossing flows:", ""]
    crossing = [f for f in flows if f["crosses"]]
    if crossing:
        lines += ["| Flow | Data | From zone | To zone |", "|---|---|---|---|"]
        byid = {c["id"]: c for c in comps}
        for f in crossing:
            lines.append(f"| {f['id']} | {md_cell(f['data'])} | {byid[f['from']]['zone']} | {byid[f['to']]['zone']} |")
    else:
        lines.append("None: every flow stays inside one trust zone.")
    lines += ["", "## Threats by severity", ""]
    for sev in ("high", "medium", "low"):
        ts = [t for t in threats if t["severity"] == sev]
        lines += [f"### {sev.capitalize()} ({len(ts)})", ""]
        if not ts:
            lines += ["None.", ""]
            continue
        lines += ["| Threat id | Category | Threat | L×I | Status | Owner |", "|---|---|---|---|---|---|"]
        for t in ts:
            cat = t["category"] if t["category"].startswith("LLM") else f"{t['category']} {STRIDE_NAME[t['category']]}"
            lines.append(f"| {t['threat_id']} | {cat} | {md_cell(t['threat'])} | {t['likelihood']}×{t['impact']} "
                         f"| {t['status']} | {t['owner']} |")
        lines.append("")
    lines += ["## Open high threats", ""]
    if not open_high:
        lines.append("None.")
    else:
        lines += ["| Threat id | Mitigations to apply | Owner |", "|---|---|---|"]
        for t in open_high:
            ms = "; ".join(f"{m} {mit_by_id[m]['mitigation']}" for m in t["mits"])
            lines.append(f"| {t['threat_id']} | {md_cell(ms)} | {t['owner']} |")
    if max_open_high is not None and len(open_high) > max_open_high:
        lines += ["", f"Gate failed: {len(open_high)} open high threats exceed `max_open_high` = {max_open_high}; "
                  "the run exits 1."]
    if unmatched:
        lines += ["", "Control rows that matched no threat or mitigation (check the ids against `threats.csv`):", ""]
        lines += [f"- {r.get('threat_id') or r.get('mitigation_id')} ({r['status']})" for r in unmatched]
    used = sorted({m for t in threats for m in t["mits"]}, key=lambda x: int(x[1:]))
    lines += ["", "## Method & limits", "",
              "- STRIDE per element (Microsoft, MSDN Magazine Nov 2006): external entities S,R; processes S,T,R,I,D,E; "
              "data stores T,I,D; data flows T,I,D. Kinds map to element types as in `references/method.md`.",
              "- OWASP Top 10 for LLM Applications 2025 items are applied by component kind and flags "
              "(`assets/owasp-llm-top10-2025.csv`); names verified against genai.owasp.org (see `references/sources.md`).",
              "- Likelihood = 1 + exposed + boundary; impact = 1 + PII + write flags for the categories they affect "
              "(D and LLM10 fixed at 2); severity high if L×I ≥ 6, medium 3–4, low ≤ 2.",
              "- Status comes only from the controls file: mitigated needs a threat-level `in_place` control or every "
              "listed mitigation `in_place`; anything else matched is planned; unmatched threats are open.",
              "- Limits: rule-based enumeration from the declared DFD, not a penetration test or a security sign-off. "
              "Components or flows missing from the inputs are not analysed; business-logic abuse and "
              "multi-step attack chains need a human review session.", "",
              "Mitigation catalogue used:", "", "| Id | Mitigation |", "|---|---|"]
    lines += [f"| {m} | {md_cell(mit_by_id[m]['mitigation'])} |" for m in used]
    lines.append("")
    return "\n".join(lines)


def verify(path: Path) -> int:
    errors = []
    try:
        rows = read_csv(path, "threats", THREAT_COLS)
    except InputError as e:
        print(f"verify: {e}")
        return 1
    mit_by_id, _ = load_mitigations()
    seen = set()
    for r in rows:
        tid = r["threat_id"]
        if tid in seen:
            errors.append(f"duplicate threat_id {tid}")
        seen.add(tid)
        if r["severity"] not in SEV_ORDER:
            errors.append(f"{tid}: severity {r['severity']!r}")
        if r["status"] not in ("open", "planned", "mitigated"):
            errors.append(f"{tid}: status {r['status']!r}")
        if not r["owner"]:
            errors.append(f"{tid}: blank owner")
        if not r["mitigation"] or any(m not in mit_by_id for m in r["mitigation"].split(";")):
            errors.append(f"{tid}: unknown mitigation {r['mitigation']!r}")
        try:
            if score(int(r["likelihood"]), int(r["impact"])) != r["severity"]:
                errors.append(f"{tid}: severity does not match likelihood × impact")
        except ValueError:
            errors.append(f"{tid}: likelihood/impact not integers")
    for e in errors[:20]:
        print(f"verify: {e}")
    print(f"verify: {len(rows)} threats, {len(errors)} problem(s)")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--components", type=Path)
    ap.add_argument("--flows", type=Path)
    ap.add_argument("--controls", type=Path)
    ap.add_argument("--max-open-high", type=str)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--verify", type=Path, metavar="THREATS_CSV")
    args = ap.parse_args(argv)
    if args.verify:
        return verify(args.verify)
    try:
        if not (args.components and args.flows and args.out_dir):
            raise InputError("--components, --flows and --out-dir are required")
        max_open_high = None
        if args.max_open_high not in (None, ""):
            if not re.fullmatch(r"\d+", args.max_open_high.strip()):
                raise InputError(f"--max-open-high must be a non-negative integer, got {args.max_open_high!r}")
            max_open_high = int(args.max_open_high)
        comps = load_components(args.components)
        flows = load_flows(args.flows, {c["id"]: c for c in comps})
        mit_by_id, mit_rows = load_mitigations()
        owasp = load_owasp()
        controls = load_controls(args.controls)
        threats = build_threats(comps, flows, mit_rows, owasp)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    unmatched = apply_controls(threats, controls)
    threats.sort(key=lambda t: (SEV_ORDER[t["severity"]], t["threat_id"]))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_threats(args.out_dir / "threats.csv", threats)
    (args.out_dir / "dfd.md").write_text(render_dfd(comps, flows), encoding="utf-8")
    (args.out_dir / "threat-report.md").write_text(
        render_report(comps, flows, threats, unmatched, mit_by_id, owasp, max_open_high,
                      args.controls.name if args.controls else None), encoding="utf-8")
    open_high = sum(1 for t in threats if t["severity"] == "high" and t["status"] == "open")
    print(f"threats: {len(threats)}; open high: {open_high}")
    if max_open_high is not None and open_high > max_open_high:
        print(f"gate: {open_high} open high threats > max_open_high {max_open_high}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
