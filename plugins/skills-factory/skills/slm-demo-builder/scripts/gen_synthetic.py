#!/usr/bin/env python3
"""Seeded synthetic demo data from a demo spec's entity field tables (assets/demo-spec.md §7).

    python3 -I scripts/gen_synthetic.py demo-spec.md --out-dir runs/x [--rows 200] [--seed 42]
    python3 -I scripts/gen_synthetic.py demo-spec-v2.md --existing demo/ --out-dir runs/y   # extend a demo

Spec layout: under "## 7. Synthetic data plan", one `### <entity>` heading per entity followed by a
`| Field | Type | Example | Constraints |` table. The §7 volume table (`| Entity | Volume | ... |`)
overrides --rows per entity when its Volume cell is a number. Constraints are `key=value` pairs
separated by `;`.

Types and constraints:
  id      prefix=C; width=5            sequential ids C00001.. (never random, never real)
  name    —                            fictional full name from the curated list in this script
  email   —                            <first>.<last><n>@example.com from the row's name field if any — always example.com
  date    within_days=90               ISO date within N days before the fixed demo date 2026-01-15
  int     min=1; max=100
  float   min=0; max=1; decimals=2
  enum    values=a|b|c; weights=1|3|6
  bool    —
  text    words=12                     lorem-ish sentence from a fixed vocabulary
  ref     entity=customers; field=customer_id   value drawn from an already generated entity (declare it after)
PII guard: a field typed ssn, credit_card, phone, phone_real, passport or iban, or a field name
containing ssn / social_security / credit_card / card_number / passport / iban, is refused (exit 1):
demos must not carry real-looking identifiers. Emails are only ever @example.com.

Brownfield (--existing DIR): DIR holds the demo's current data-manifest.json and data/*.csv. The demo is
extended without moving what the walkthrough relies on: existing rows keep every value of every column
the spec still has (so planted cases stay put); new columns, new rows and new entities are generated with
RNG streams derived from the seed and the entity/field name; rows beyond a lowered volume are trimmed;
dropped columns are removed; a column whose type changed (manifest column_types) is regenerated; a kept
ref value whose target row no longer exists is redrawn. The manifest gains "extended_from" with the
per-entity changes.

Writes {out}/data/<entity>.csv and {out}/data-manifest.json (demo, seed, demo_date, pii_guard,
entities: [{entity, rows, columns, file}]). Deterministic for a given seed. Exit 1 on a missing spec,
no entity tables, an unknown type, a bad constraint or a PII field. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import re
import sys
from pathlib import Path

DEMO_DATE = dt.date(2026, 1, 15)
FIRST = ["Avery", "Jordan", "Priya", "Mateo", "Lena", "Tomas", "Ngozi", "Hana", "Luca", "Imani",
         "Soren", "Amara", "Kenji", "Elif", "Rafael", "Maren", "Dev", "Saoirse", "Yusuf", "Noor"]
LAST = ["Okafor", "Lindqvist", "Nakamura", "Castillo", "Byrne", "Haddad", "Varga", "Mbeki", "Petrov",
        "Delacroix", "Oyelaran", "Svensson", "Tanaka", "Moreau", "Kowalski", "Achebe", "Ferreira", "Nilsen"]
VOCAB = ("ticket order policy renewal invoice request status update review approve pending shipment "
         "warranty account contact summary clause customer region quarter note follow-up escalate").split()
TYPES = {"id", "name", "email", "date", "int", "float", "enum", "bool", "text", "ref"}
PII_TYPES = {"ssn", "credit_card", "phone", "phone_real", "passport", "iban"}
PII_NAMES = ("ssn", "social_security", "credit_card", "card_number", "passport", "iban")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_constraints(text: str) -> dict:
    out = {}
    for part in text.split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip().lower()] = v.strip()
    return out


def parse_spec(path: Path) -> tuple[dict[str, list[dict]], dict[str, int]]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## 7\..*$", text, re.M)
    section = text[m.start():] if m else text
    nxt = re.search(r"^## (?!7\.)\d+\.", section, re.M)
    if nxt:
        section = section[: nxt.start()]
    entities: dict[str, list[dict]] = {}
    volumes: dict[str, int] = {}
    current = None
    for ln in section.splitlines():
        h = re.match(r"^###\s+(.+?)\s*$", ln)
        if h:
            current = h.group(1).strip().lower().replace(" ", "_")
            entities.setdefault(current, [])
            continue
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= set("-: "):
            continue
        if current is None:
            if len(cells) >= 2 and cells[0].lower() != "entity" and cells[1].isdigit():
                volumes[cells[0].lower().replace(" ", "_")] = int(cells[1])
            continue
        if cells[0].lower() == "field" or len(cells) < 2:
            continue
        entities[current].append({"field": cells[0], "type": cells[1].lower(),
                                  "example": cells[2] if len(cells) > 2 else "",
                                  "constraints": parse_constraints(cells[3] if len(cells) > 3 else "")})
    entities = {k: v for k, v in entities.items() if v}
    if not entities:
        die(f"{path.name}: no entity field tables found under '## 7. Synthetic data plan' "
            "(expected '### <entity>' + '| Field | Type | Example | Constraints |')")
    return entities, volumes


def pii_check(entities: dict[str, list[dict]]) -> None:
    for ent, fields in entities.items():
        for f in fields:
            fname = f["field"].lower()
            if f["type"] in PII_TYPES or any(p in fname for p in PII_NAMES):
                die(f"PII guard: {ent}.{f['field']} (type {f['type']}) refused — demos never carry real-looking "
                    "identifiers; drop the field or use type id/text")
            if f["type"] not in TYPES:
                die(f"{ent}.{f['field']}: unknown type {f['type']!r}; allowed: {sorted(TYPES)}")


def make_value(f: dict, i: int, rng: random.Random, generated: dict[str, list[dict]], ent: str, row: dict) -> str:
    t, c = f["type"], f["constraints"]
    try:
        if t == "id":
            return f"{c.get('prefix', f['field'][:1].upper())}{i:0{int(c.get('width', 5))}d}"
        if t == "name":
            return f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if t == "email":
            prior = next((v for v in row.values() if isinstance(v, str) and v.split(" ")[0] in FIRST), "")
            first, last = prior.split(" ")[:2] if prior else (rng.choice(FIRST), rng.choice(LAST))
            return f"{first.lower()}.{last.lower()}{i}@example.com"
        if t == "date":
            return (DEMO_DATE - dt.timedelta(days=rng.randint(0, int(c.get("within_days", 90))))).isoformat()
        if t == "int":
            return str(rng.randint(int(c.get("min", 1)), int(c.get("max", 100))))
        if t == "float":
            return f"{rng.uniform(float(c.get('min', 0)), float(c.get('max', 1))):.{int(c.get('decimals', 2))}f}"
        if t == "enum":
            values = [v.strip() for v in c.get("values", "").split("|") if v.strip()]
            if not values:
                die(f"{ent}.{f['field']}: enum needs values=a|b|c")
            weights = [float(w) for w in c["weights"].split("|")] if c.get("weights") else None
            if weights and len(weights) != len(values):
                die(f"{ent}.{f['field']}: weights count must match values")
            return rng.choices(values, weights=weights)[0]
        if t == "bool":
            return str(rng.random() < float(c.get("p_true", 0.5))).lower()
        if t == "text":
            n = int(c.get("words", 12))
            words = [rng.choice(VOCAB) for _ in range(n)]
            return (" ".join(words)).capitalize() + "."
        if t == "ref":
            src, fld = c.get("entity", "").lower().replace(" ", "_"), c.get("field", "")
            if src not in generated:
                die(f"{ent}.{f['field']}: ref entity {src!r} must be declared before {ent}")
            pool = [r[fld] for r in generated[src] if fld in r]
            if not pool:
                die(f"{ent}.{f['field']}: ref field {src}.{fld} not found")
            return rng.choice(pool)
    except ValueError as e:
        die(f"{ent}.{f['field']}: bad constraint ({e})")
    return ""


def load_existing(d: Path) -> tuple[dict, dict[str, list[dict]]]:
    mf = d / "data-manifest.json"
    if not mf.is_file():
        die(f"--existing {d}: no data-manifest.json")
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{mf}: invalid JSON: {e}")
    rows: dict[str, list[dict]] = {}
    for e in manifest.get("entities", []):
        fp = d / e.get("file", "")
        if not fp.is_file():
            die(f"--existing {d}: {e.get('file')} listed in the manifest is missing")
        with fp.open(newline="", encoding="utf-8") as fh:
            rows[e["entity"]] = list(csv.DictReader(fh))
    return manifest, rows


def _stream(seed: int, *parts: str) -> random.Random:
    return random.Random(f"{seed}:" + ":".join(parts))


def extend_entity(ent: str, fields: list[dict], n: int, seed: int, old_rows: list[dict] | None,
                  old_types: dict[str, str], generated: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    """Rows for one entity, keeping existing values where the spec still allows them."""
    if old_rows is None:
        rng = _stream(seed, ent)
        rows = []
        for i in range(1, n + 1):
            row: dict = {}
            for f in fields:
                row[f["field"]] = make_value(f, i, rng, generated, ent, row)
            rows.append(row)
        return rows, {"entity": ent, "change": "added", "rows": n}
    old_cols = list(old_rows[0].keys()) if old_rows else []
    names = [f["field"] for f in fields]
    retyped = [f["field"] for f in fields if f["field"] in old_types and old_types[f["field"]] != f["type"]]
    keep = [c for c in names if c in old_cols and c not in retyped]
    new_cols = [c for c in names if c not in old_cols]
    col_rng = {f["field"]: _stream(seed, ent, f["field"]) for f in fields}
    tail_rng = _stream(seed, ent, "append")
    rows, repaired = [], 0
    for i in range(1, n + 1):
        row: dict = {}
        old = old_rows[i - 1] if i <= len(old_rows) else None
        for f in fields:
            k = f["field"]
            if old is not None and k in keep:
                v = old[k]
                if f["type"] == "ref":
                    src, fld = f["constraints"].get("entity", "").lower().replace(" ", "_"), f["constraints"].get("field", "")
                    if src in generated and v not in {r.get(fld) for r in generated[src]}:
                        v = make_value(f, i, col_rng[k], generated, ent, row)
                        repaired += 1
                row[k] = v
            else:
                row[k] = make_value(f, i, col_rng[k] if old is not None else tail_rng, generated, ent, row)
        rows.append(row)
    change = {"entity": ent, "change": "extended", "rows_kept": min(n, len(old_rows)),
              "rows_added": max(0, n - len(old_rows)), "rows_trimmed": max(0, len(old_rows) - n),
              "columns_added": new_cols, "columns_removed": [c for c in old_cols if c not in names],
              "columns_regenerated": retyped, "refs_redrawn": repaired}
    return rows, change


def main() -> int:
    ap = argparse.ArgumentParser(description="demo-spec.md entity tables -> seeded synthetic CSVs + manifest")
    ap.add_argument("spec")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--rows", type=int, default=200, help="rows per entity unless the spec's volume table says otherwise")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--existing", help="demo folder with data-manifest.json + data/ to extend (planted rows kept)")
    a = ap.parse_args()
    sp = Path(a.spec)
    if not sp.is_file():
        die(f"spec not found: {sp}")
    if a.rows < 1:
        die("--rows must be >= 1")
    entities, volumes = parse_spec(sp)
    pii_check(entities)
    old_manifest, old_rows = load_existing(Path(a.existing)) if a.existing else (None, {})
    old_types = {e["entity"]: e.get("column_types", {}) for e in (old_manifest or {}).get("entities", [])}
    changes = []
    title = re.search(r"^#\s+Demo Spec\s+[—-]\s+(.+?)\s+[—-]", sp.read_text(encoding="utf-8"), re.M)
    out = Path(a.out_dir)
    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)
    generated: dict[str, list[dict]] = {}
    manifest = []
    for ent, fields in entities.items():
        n = volumes.get(ent, a.rows)
        if old_manifest is not None:
            rows, ch = extend_entity(ent, fields, n, a.seed, old_rows.get(ent), old_types.get(ent, {}), generated)
            changes.append(ch)
        else:
            rows = []
            for i in range(1, n + 1):
                row: dict = {}
                for f in fields:
                    row[f["field"]] = make_value(f, i, rng, generated, ent, row)
                rows.append(row)
        generated[ent] = rows
        path = data / f"{ent}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=[f["field"] for f in fields])
            w.writeheader()
            w.writerows(rows)
        manifest.append({"entity": ent, "rows": n, "columns": [f["field"] for f in fields], "file": f"data/{ent}.csv",
                         "column_types": {f["field"]: f["type"] for f in fields}})
    doc = {"demo": title.group(1).strip() if title else sp.stem, "spec": sp.name, "seed": a.seed,
           "demo_date": DEMO_DATE.isoformat(), "pii_guard": "passed", "email_domain": "example.com",
           "label": "Sample data — generated for demonstration", "entities": manifest}
    if old_manifest is not None:
        gone = [e for e in old_rows if e not in entities]
        changes += [{"entity": e, "change": "removed", "rows": len(old_rows[e])} for e in gone]
        for e in gone:
            stale = data / f"{e}.csv"
            if stale.is_file() and out.resolve() == Path(a.existing).resolve():
                stale.unlink()
        doc["extended_from"] = {"spec": old_manifest.get("spec"), "seed": old_manifest.get("seed"), "changes": changes}
    (out / "data-manifest.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"synthetic data: {len(manifest)} entities, {sum(m['rows'] for m in manifest)} rows, seed {a.seed} -> {data}")
    if old_manifest is not None:
        print("extended: " + "; ".join(f"{c['entity']} {c['change']}" for c in changes))
    return 0


if __name__ == "__main__":
    main()
