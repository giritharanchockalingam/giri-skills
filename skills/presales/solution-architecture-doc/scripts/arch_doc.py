#!/usr/bin/env python3
"""Architecture document from components.json: C4 context + container diagrams, integration map, NFR table.

    python3 -I scripts/arch_doc.py components.json --out architecture.md --nfr nfr.csv [--client "Acme"]

components.json:
  {"system": "Order Hub",
   "actors": ["Store associate", "Marketplace partner"]            (strings, or {"name", "external": true})
   "containers": [{"id": "gw", "name": "API gateway", "tech": "Apigee X", "responsibility": "..."}],
   "external_systems": [{"id": "erp", "name": "ERP"}]               (optional; also auto-created
                                                                     for integration endpoints not in containers)
   "integrations": [{"from": "gw", "to": "erp", "pattern": "sync REST", "protocol": "HTTPS",
                     "data": "orders", "wave": 1}],
   "nfrs": [{"category": "Availability", "requirement": "...", "target": "99.9%", "measure": "..."}]}

Diagrams are Mermaid `flowchart` blocks in C4 layout (context: actors, system, external systems;
container: containers inside the system boundary, with every integration as an edge), so they
render anywhere Mermaid does. The integration map groups by pattern and lists waves; an NFR with
no target or measure is `[TO BE BASELINED — owner: ___]`; the decision-log stub carries one ADR
row per pattern and per container technology. No number is invented.
Exit 1 on invalid JSON, missing keys, duplicate ids, or an integration endpoint that is not a
container, actor or external system. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: ___]"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def label(s: str) -> str:
    """Mermaid-safe label: no brackets/braces/parens/quotes/pipes."""
    return re.sub(r"[\[\]{}()\"|`]", "", str(s)).replace("\n", " ").strip() or "unnamed"


def nid(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(s))
    return s if re.match(r"[A-Za-z_]", s) else f"n_{s}"


def load(path: Path) -> dict:
    if not path.is_file():
        die(f"file not found: {path}")
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"invalid JSON: {e}")
    if not isinstance(d, dict) or not d.get("system"):
        die("components.json needs 'system'")
    conts = d.get("containers") or []
    if not isinstance(conts, list) or not conts:
        die("components.json needs a non-empty 'containers' list")
    ids = set()
    for c in conts:
        if not isinstance(c, dict) or not c.get("id") or not c.get("name"):
            die("every container needs 'id' and 'name'")
        if c["id"] in ids:
            die(f"duplicate container id {c['id']!r}")
        ids.add(c["id"])
    actors = []
    for a_ in d.get("actors") or []:
        a_ = {"name": a_} if isinstance(a_, str) else a_
        if not a_.get("name"):
            die("every actor needs 'name'")
        a_.setdefault("id", nid("actor_" + a_["name"]))
        actors.append(a_)
    ext = {}
    for e in d.get("external_systems") or []:
        if not isinstance(e, dict) or not e.get("id"):
            die("every external system needs 'id'")
        ext[e["id"]] = e.get("name") or e["id"]
    known = ids | set(ext) | {a_["id"] for a_ in actors}
    ints = d.get("integrations") or []
    for i, it in enumerate(ints, 1):
        for k in ("from", "to"):
            if not it.get(k):
                die(f"integration {i} lacks '{k}'")
            if it[k] not in known:
                die(f"integration {i}: endpoint {it[k]!r} is not a container, actor or external system id")
        it.setdefault("pattern", TBD); it.setdefault("protocol", TBD); it.setdefault("data", TBD)
        it["wave"] = str(it.get("wave", "") or TBD)
        it.setdefault("id", f"INT-{i:03d}")
    for n in d.get("nfrs") or []:
        if not isinstance(n, dict) or not n.get("category") or not n.get("requirement"):
            die("every NFR needs 'category' and 'requirement'")
    d["actors"], d["external_systems"], d["integrations"] = actors, ext, ints
    return d


def context_diagram(d: dict) -> list[str]:
    sysid = "SYS"
    L = ["```mermaid", "flowchart TB", f'  {sysid}["{label(d["system"])}"]']
    for a_ in d["actors"]:
        L.append(f'  {nid(a_["id"])}(["{label(a_["name"])}"])')
        L.append(f'  {nid(a_["id"])} -->|uses| {sysid}')
    cont_ids = {c["id"] for c in d["containers"]}
    seen = set()
    for it in d["integrations"]:
        src, dst = it["from"], it["to"]
        for end in (src, dst):
            if end in d["external_systems"] and end not in seen:
                L.append(f'  {nid(end)}[["{label(d["external_systems"][end])}"]]'); seen.add(end)
        if src in cont_ids and dst in d["external_systems"]:
            L.append(f'  {sysid} -->|{label(it["pattern"])}: {label(it["data"])}| {nid(dst)}')
        elif dst in cont_ids and src in d["external_systems"]:
            L.append(f'  {nid(src)} -->|{label(it["pattern"])}: {label(it["data"])}| {sysid}')
    for e in d["external_systems"]:
        if e not in seen:
            L.append(f'  {nid(e)}[["{label(d["external_systems"][e])}"]]')
            L.append(f'  {sysid} --- {nid(e)}')
    if not d["actors"] and not d["external_systems"]:
        L.append(f"  {sysid} --- {sysid}")
    L.append("```")
    return L


def container_diagram(d: dict) -> list[str]:
    L = ["```mermaid", "flowchart LR", f'  subgraph {nid(d["system"])}["{label(d["system"])}"]']
    for c in d["containers"]:
        L.append(f'    {nid(c["id"])}["{label(c["name"])}<br/><i>{label(c.get("tech") or "tech: " + TBD)}</i>"]')
    L.append("  end")
    for a_ in d["actors"]:
        L.append(f'  {nid(a_["id"])}(["{label(a_["name"])}"])')
    for e, name in d["external_systems"].items():
        L.append(f'  {nid(e)}[["{label(name)}"]]')
    edges = 0
    for it in d["integrations"]:
        L.append(f'  {nid(it["from"])} -->|{label(it["id"])} {label(it["pattern"])}| {nid(it["to"])}')
        edges += 1
    for a_ in d["actors"]:
        if not any(it["from"] == a_["id"] or it["to"] == a_["id"] for it in d["integrations"]):
            L.append(f'  {nid(a_["id"])} --> {nid(d["containers"][0]["id"])}')
            edges += 1
    if edges == 0:
        L.append(f'  {nid(d["containers"][0]["id"])} --- {nid(d["containers"][0]["id"])}')
    L.append("```")
    return L


def name_of(d: dict, ref: str) -> str:
    for c in d["containers"]:
        if c["id"] == ref:
            return c["name"]
    for a_ in d["actors"]:
        if a_["id"] == ref:
            return a_["name"]
    return d["external_systems"].get(ref, ref)


def main() -> int:
    ap = argparse.ArgumentParser(description="components.json -> architecture.md (Mermaid C4) + nfr.csv")
    ap.add_argument("components")
    ap.add_argument("--out", required=True)
    ap.add_argument("--nfr", required=True, help="nfr.csv")
    ap.add_argument("--client", default="<Client>")
    a = ap.parse_args()
    d = load(Path(a.components))
    nfrs = []
    for n in d.get("nfrs") or []:
        nfrs.append({"category": n["category"], "requirement": n["requirement"],
                     "target": str(n.get("target") or "").strip() or TBD,
                     "measure": str(n.get("measure") or "").strip() or TBD,
                     "source": str(n.get("source") or "").strip() or TBD})
    patterns: dict[str, list] = {}
    for it in d["integrations"]:
        patterns.setdefault(it["pattern"], []).append(it)
    waves = sorted({it["wave"] for it in d["integrations"]}, key=lambda w: (not w.isdigit(), w))

    L = [f"# Solution Architecture — {a.client} — {d['system']}", "",
         f"Generated from `{Path(a.components).name}`: {len(d['containers'])} containers, "
         f"{len(d['actors'])} actors, {len(d['external_systems'])} external systems, "
         f"{len(d['integrations'])} integrations, {len(nfrs)} NFRs.", "",
         "## Bottom line", f"{TBD} — target state in one sentence and the decision asked.", "",
         "## System context (C4 level 1)"] + context_diagram(d) + [
         f"*Figure 1 — System context for {d['system']}; sources: components.json*", "",
         "## Container view (C4 level 2)"] + container_diagram(d) + [
         f"*Figure 2 — Containers and integrations; sources: components.json*", "",
         "| Container | Technology | Responsibility |", "|---|---|---|"]
    for c in d["containers"]:
        L.append(f"| {c['name']} (`{c['id']}`) | {c.get('tech') or TBD} | {c.get('responsibility') or TBD} |")
    L += ["", "## Integration map (grouped by pattern)"]
    for pat, items in patterns.items():
        L += ["", f"### {pat}", "| ID | From | To | Protocol | Data | Wave |", "|---|---|---|---|---|---|"]
        L += [f"| {it['id']} | {name_of(d, it['from'])} | {name_of(d, it['to'])} | {it['protocol']} | {it['data']} | {it['wave']} |"
              for it in items]
    if not patterns:
        L += ["", "| ID | From | To | Protocol | Data | Wave |", "|---|---|---|---|---|---|", f"| — | none declared | | | | {TBD} |"]
    L += ["", "## Waves", "| Wave | Integrations | Patterns |", "|---|---|---|"]
    for w in waves:
        items = [it for it in d["integrations"] if it["wave"] == w]
        L.append(f"| {w} | {', '.join(it['id'] for it in items)} | {', '.join(sorted({it['pattern'] for it in items}))} |")
    if not waves:
        L.append(f"| {TBD} | | |")
    L += ["", "## Non-functional requirements", "| Category | Requirement | Target | Measure | Source |", "|---|---|---|---|---|"]
    L += [f"| {n['category']} | {n['requirement']} | {n['target']} | {n['measure']} | {n['source']} |" for n in nfrs] \
        or [f"| {TBD} | | | | |"]
    L += ["", "## Decision log (stub — one ADR per decision; complete on assets/adr-template.md)",
          "| ADR | Decision | Options considered | Status | Owner |", "|---|---|---|---|---|"]
    k = 1
    for pat in patterns:
        L.append(f"| ADR-{k:03d} | Integration pattern: {pat} | {TBD} | proposed | {TBD} |"); k += 1
    for c in d["containers"]:
        if c.get("tech"):
            L.append(f"| ADR-{k:03d} | {c['name']} on {c['tech']} | {TBD} | proposed | {TBD} |"); k += 1
    if k == 1:
        L.append(f"| ADR-001 | {TBD} | | proposed | |")
    L += ["", "## Open items", "| Item | Owner | By |", "|---|---|---|",
          *(f"| NFR target: {n['category']} — {n['requirement']} | {TBD} | |" for n in nfrs if n["target"] == TBD),
          *(f"| Wave for {it['id']} | {TBD} | |" for it in d["integrations"] if it["wave"] == TBD)]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    with Path(a.nfr).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["category", "requirement", "target", "measure", "source"])
        w.writeheader(); w.writerows(nfrs)
    n_tbd = sum(1 for n in nfrs if n["target"] == TBD)
    print(f"architecture: {len(d['containers'])} containers, {len(d['integrations'])} integrations in "
          f"{len(patterns)} patterns, {len(nfrs)} NFRs ({n_tbd} targets to baseline) -> {a.out}")
    return 0


if __name__ == "__main__":
    main()
