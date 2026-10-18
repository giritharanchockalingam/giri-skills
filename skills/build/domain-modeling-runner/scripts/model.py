#!/usr/bin/env python3
"""Validate a domain model (entities + relationships [+ glossary]) and render it.

    python3 -I scripts/model.py --entities entities.csv --relationships relationships.csv \
        [--glossary glossary.csv] [--title "Ordering"] --md model.md --json model.json
    python3 -I scripts/model.py --check model.json      # contract check on a written model.json

Inputs
  entities.csv       entity, attribute, type, required, notes   (one row per attribute)
  relationships.csv  from, to, cardinality (1:1 | 1:N | N:M), name [, notes]
  glossary.csv       term, definition [, avoid]                  (optional; avoid = ;-separated synonyms)

Validation — errors (exit 1, outputs still written so the gaps are visible):
  E1 relationship endpoint not defined in entities.csv
  E2 entity without an identifier: an attribute named `id` or `<entity>_id`, or a note with PK / identifier
  E3 cardinality not in 1:1 | 1:N | N:M
  E4 N:M relationship without a join note (relationship notes must name the join, e.g. "join: Enrollment")
  E5 duplicate attribute within an entity; E6 `required` not yes/no/true/false/y/n/1/0
Warnings (Open questions): orphan entities (in no relationship), glossary terms with no definition
(rendered `[TO BE BASELINED — owner: Domain expert]`), glossary terms that are not entities.

Outputs: model.md (Diagram with a ```mermaid erDiagram, Entities, Relationships, Invariants, Glossary,
Open questions) and model.json. The glossary follows the vendored domain-modeling GLOSSARY format
(**Term**: definition, _Avoid_: synonyms). Mermaid cardinality uses the text aliases (1, 0+) so the
diagram carries no unbalanced brace markers; the title block uses Mermaid front matter.

Exit codes: 0 valid · 1 validation errors or --check failed · 2 missing/unreadable input or missing
columns. Stdlib only; writes only --md / --json.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

TBD_DEF = "[TO BE BASELINED — owner: Domain expert]"
ENTITY_COLS = ("entity", "attribute", "type", "required", "notes")
REL_COLS = ("from", "to", "cardinality", "name")
GLOSS_COLS = ("term", "definition")
CARDINALITIES = {"1:1": ("1", "1"), "1:N": ("1", "0+"), "N:M": ("0+", "0+")}
TRUE = {"yes", "true", "y", "1"}
FALSE = {"no", "false", "n", "0", ""}


class InputError(Exception):
    """Unusable input (missing file/columns) -> exit 2."""


def read_csv(path: Path, need: tuple, label: str) -> list[dict]:
    if not path.is_file():
        raise InputError(f"{label} file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        row["_line"] = str(reader.line_num)
        rows.append(row)
    header = {h.strip().lower() for h in next(csv.reader(io.StringIO(text)), []) if h}
    missing = [c for c in need if c not in header]
    if missing:
        raise InputError(f"{label} is missing column(s) {missing}; expected {list(need)}")
    out = []
    for r in rows:
        if r.get(None):
            raise InputError(f"{label}: a row has more fields than the header ({r[None]!r}); quote values containing commas")
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k is not None and k != "_line"} | \
            {"_line": r["_line"]}
        if not any(v for k, v in r.items() if k != "_line") or r.get(need[0], "").startswith("#"):
            continue
        out.append(r)
    return out


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def mm_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    return s if s and not s[0].isdigit() else f"E_{s}"


def mm_text(s: str) -> str:
    return re.sub(r"[\"\[\]{}()<>|]", "", s).strip()


# ------------------------------------------------------------------ build

def build(ent_rows, rel_rows, gloss_rows, title: str, sources: dict) -> dict:
    errors, warnings = [], []
    entities: dict[str, dict] = {}
    for r in ent_rows:
        i = r["_line"]
        name = r["entity"]
        if not name:
            errors.append(f"E0 entities line {i}: empty entity name")
            continue
        e = entities.setdefault(norm(name), {"name": name, "attributes": [], "identifier": None})
        attr = r["attribute"]
        if not attr:
            continue                                   # an entity row with no attribute just declares it
        if any(a["name"].lower() == attr.lower() for a in e["attributes"]):
            errors.append(f"E5 {name}: duplicate attribute '{attr}'")
            continue
        req = r["required"].lower()
        if req not in TRUE | FALSE:
            errors.append(f"E6 {name}.{attr}: required '{r['required']}' is not yes/no")
        notes = r.get("notes", "")
        is_id = (attr.lower() in ("id", f"{norm(name)}_id", f"{name.lower()}_id")
                 or re.search(r"\b(?:PK|identifier|primary key)\b", notes, re.I) is not None)
        is_fk = re.search(r"\bFK\b|foreign key|references\s+\w+", notes, re.I) is not None
        a = {"name": attr, "type": r["type"] or "string", "required": req in TRUE or is_id,
             "identifier": is_id, "foreign_key": is_fk, "notes": notes}
        e["attributes"].append(a)
        if is_id and not e["identifier"]:
            e["identifier"] = attr
    for e in entities.values():
        if not e["identifier"]:
            errors.append(f"E2 {e['name']}: no identifier (add an `id` / `{norm(e['name'])}_id` attribute or mark one PK)")

    rels = []
    for r in rel_rows:
        i = r["_line"]
        frm, to, card, name = r["from"], r["to"], r["cardinality"].upper().replace(" ", ""), r["name"]
        notes = r.get("notes", "")
        ok = True
        for end in (frm, to):
            if norm(end) not in entities:
                errors.append(f"E1 relationship line {i} ({frm} -> {to}): entity '{end}' is not defined in entities")
                ok = False
        if card not in CARDINALITIES:
            errors.append(f"E3 relationship line {i} ({frm} -> {to}): cardinality '{r['cardinality']}' "
                          f"not in {sorted(CARDINALITIES)}")
            ok = False
        join = None
        if card == "N:M":
            m = re.search(r"join\s*[:=]?\s*([A-Za-z][\w-]*)", notes, re.I)
            named = [e["name"] for k, e in entities.items() if e["name"] in notes and k not in (norm(frm), norm(to))]
            join = (m.group(1) if m else None) or (named[0] if named else None)
            if not join:
                errors.append(f"E4 relationship line {i} ({frm} -> {to}): N:M needs a join note "
                              f"(e.g. notes 'join: {mm_name(frm)}{mm_name(to)}')")
                ok = False
        rels.append({"from": entities.get(norm(frm), {}).get("name", frm), "to": entities.get(norm(to), {}).get("name", to),
                     "cardinality": card, "name": name or "relates to", "notes": notes, "join": join, "valid": ok})

    linked = ({norm(r["from"]) for r in rels} | {norm(r["to"]) for r in rels}
              | {norm(r["join"]) for r in rels if r["join"]})
    for k, e in entities.items():
        if k not in linked:
            warnings.append(f"W1 orphan entity {e['name']}: in no relationship — is it part of this context?")

    glossary, seen = [], set()
    for g in gloss_rows:
        term = g["term"]
        if not term or norm(term) in seen:
            continue
        seen.add(norm(term))
        d = g.get("definition", "")
        avoid = [x.strip() for x in g.get("avoid", "").split(";") if x.strip()]
        glossary.append({"term": term, "definition": d or TBD_DEF, "avoid": avoid, "defined": bool(d)})
        if not d:
            warnings.append(f"W2 glossary term {term}: no definition")
        if norm(term) not in entities:
            warnings.append(f"W3 glossary term {term} is not an entity — attribute, state or a missing entity?")
    for k, e in entities.items():
        if k not in seen:
            glossary.append({"term": e["name"], "definition": TBD_DEF, "avoid": [], "defined": False})
            warnings.append(f"W2 glossary term {e['name']}: entity has no glossary definition")

    invariants = []
    for e in entities.values():
        if e["identifier"]:
            invariants.append(f"Every {e['name']} has a unique {e['identifier']}.")
        for a in e["attributes"]:
            if a["required"] and not a["identifier"]:
                invariants.append(f"Every {e['name']} has {a['name']} set.")
    for r in rels:
        if not r["valid"]:
            continue
        if r["cardinality"] == "1:N":
            invariants.append(f"Every {r['to']} belongs to exactly one {r['from']} ({r['name']}).")
        elif r["cardinality"] == "1:1":
            invariants.append(f"A {r['from']} has at most one {r['to']} and each {r['to']} has exactly one {r['from']} ({r['name']}).")
        else:
            invariants.append(f"A {r['from']}–{r['to']} pair appears at most once in {r['join']} ({r['name']}).")

    return {"skill": "domain-modeling-runner", "title": title, "sources": sources,
            "valid": not errors, "errors": errors, "warnings": warnings,
            "entities": list(entities.values()), "relationships": rels,
            "glossary": glossary, "invariants": invariants}


# ------------------------------------------------------------------ render

def mermaid(m: dict) -> str:
    title = re.sub(r"[:#'\"`]", "", mm_text(m["title"])) or "Domain model"
    lines = ["---", f"title: {title}", "---", "erDiagram"]
    for e in m["entities"]:
        lines.append(f"    {mm_name(e['name'])} {{")
        for a in e["attributes"]:
            key = " PK" if a["identifier"] else (" FK" if a["foreign_key"] else "")
            typ = re.sub(r"[^A-Za-z0-9_]", "_", a["type"]) or "string"
            if typ[0].isdigit():
                typ = f"t_{typ}"
            comment = re.sub(r"\s+", " ", re.sub(r"\b(?:PK|FK)\b", "", mm_text(a["notes"]))).strip()[:60]
            lines.append(f"        {typ} {mm_name(a['name'])}{key}" + (f' "{comment}"' if comment else ""))
        lines.append("    }")
    for r in m["relationships"]:
        if not r["valid"]:
            continue
        left, right = CARDINALITIES[r["cardinality"]]
        lines.append(f'    {mm_name(r["from"])} {left} to {right} {mm_name(r["to"])} : "{mm_text(r["name"]) or "relates"}"')
    return "\n".join(lines)


def _cell(s) -> str:
    return str(s if s not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def render_md(m: dict) -> str:
    src = ", ".join(v for v in m["sources"].values() if v)
    out = [f"# Domain model — {m['title']}", "",
           f"_Generated by domain-modeling-runner from {src}. Validation: "
           f"{'PASS' if m['valid'] else 'FAIL — ' + str(len(m['errors'])) + ' error(s)'}, "
           f"{len(m['warnings'])} warning(s)._", "",
           "## Diagram", "", "```mermaid", mermaid(m), "```", ""]
    if any(not r["valid"] for r in m["relationships"]):
        out += ["Invalid relationships are left out of the diagram; see Open questions.", ""]
    out += ["## Entities", ""]
    for e in m["entities"]:
        out += [f"### {e['name']}", "", f"Identifier: `{e['identifier']}`" if e["identifier"]
                else "Identifier: **missing**", "",
                "| Attribute | Type | Required | Key | Notes |", "|---|---|---|---|---|"]
        for a in e["attributes"]:
            key = "PK" if a["identifier"] else ("FK" if a["foreign_key"] else "")
            out.append(f"| {_cell(a['name'])} | {_cell(a['type'])} | {'yes' if a['required'] else 'no'} | "
                       f"{_cell(key)} | {_cell(a['notes'])} |")
        out.append("")
    out += ["## Relationships", "", "| From | To | Cardinality | Name | Join | Notes |", "|---|---|---|---|---|---|"]
    for r in m["relationships"]:
        out.append(f"| {_cell(r['from'])} | {_cell(r['to'])} | {r['cardinality']}{'' if r['valid'] else ' (invalid)'} | "
                   f"{_cell(r['name'])} | {_cell(r['join'])} | {_cell(r['notes'])} |")
    if not m["relationships"]:
        out.append("| — | — | — | none defined | — | — |")
    out += ["", "## Invariants", "", "Checklist derived from identifiers, required attributes and cardinalities; "
            "confirm each with the domain expert and enforce it in code or schema.", ""]
    out += [f"- [ ] {x}" for x in m["invariants"]] or ["- none derived"]
    out += ["", "## Glossary", "", f"### {m['title']}", ""]
    for g in m["glossary"]:
        out += [f"**{g['term']}**:", g["definition"]]
        if g["avoid"]:
            out.append(f"_Avoid_: {', '.join(g['avoid'])}")
        out.append("")
    out += ["## Open questions", ""]
    if m["errors"]:
        out += ["Errors (must be fixed; the run fails until they are):", ""] + [f"- {e}" for e in m["errors"]] + [""]
    if m["warnings"]:
        out += ["Warnings (owner: Domain expert):", ""] + [f"- {w}" for w in m["warnings"]] + [""]
    if not m["errors"] and not m["warnings"]:
        out += ["None.", ""]
    return "\n".join(out)


def check(path: Path) -> list[str]:
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"cannot read {path}: {e}"]
    problems = []
    if m.get("errors"):
        problems.append(f"{len(m['errors'])} validation error(s): {m['errors'][0]}")
    names = {norm(e["name"]) for e in m.get("entities", [])}
    for r in m.get("relationships", []):
        for end in (r.get("from", ""), r.get("to", "")):
            if norm(end) not in names:
                problems.append(f"relationship endpoint {end!r} undefined")
    for e in m.get("entities", []):
        if not e.get("identifier"):
            problems.append(f"{e.get('name')} has no identifier")
    for g in m.get("glossary", []):
        if not g.get("definition"):
            problems.append(f"glossary term {g.get('term')} has an empty definition (needs text or an owned TBD)")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Entities + relationships CSV -> validated domain model (Mermaid ER, glossary)")
    ap.add_argument("--entities", help="entities CSV: entity,attribute,type,required,notes")
    ap.add_argument("--relationships", help="relationships CSV: from,to,cardinality,name[,notes]")
    ap.add_argument("--glossary", help="optional glossary CSV: term,definition[,avoid]")
    ap.add_argument("--title", default="Domain model", help="context name for the diagram and glossary heading")
    ap.add_argument("--md", dest="md_out", help="write model.md here")
    ap.add_argument("--json", dest="json_out", help="write model.json here")
    ap.add_argument("--check", metavar="MODEL_JSON", help="exit 1 unless a written model.json is valid")
    a = ap.parse_args()
    if a.check:
        problems = check(Path(a.check))
        for p in problems:
            print(f"FAIL: {p}", file=sys.stderr)
        print("model.json: " + ("FAIL" if problems else "OK"))
        return 1 if problems else 0
    if not a.entities or not a.relationships:
        print("error: --entities and --relationships are required", file=sys.stderr)
        return 2
    if not a.md_out and not a.json_out:
        print("error: give --md and/or --json", file=sys.stderr)
        return 2
    try:
        ents = read_csv(Path(a.entities), ENTITY_COLS[:4], "entities")
        rels = read_csv(Path(a.relationships), REL_COLS, "relationships")
        gloss = read_csv(Path(a.glossary), GLOSS_COLS[:1], "glossary") if a.glossary else []
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not ents:
        print("error: entities CSV has no rows", file=sys.stderr)
        return 2
    sources = {"entities": Path(a.entities).name, "relationships": Path(a.relationships).name,
               "glossary": Path(a.glossary).name if a.glossary else ""}
    m = build(ents, rels, gloss, a.title.strip() or "Domain model", sources)
    if a.md_out:
        Path(a.md_out).write_text(render_md(m), encoding="utf-8")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    for e in m["errors"]:
        print(f"invalid: {e}", file=sys.stderr)
    print(f"model: {len(m['entities'])} entities, {len(m['relationships'])} relationships, "
          f"{len(m['errors'])} errors, {len(m['warnings'])} warnings")
    return 0 if m["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
