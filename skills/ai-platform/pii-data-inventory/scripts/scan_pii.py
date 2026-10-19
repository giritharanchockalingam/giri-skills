#!/usr/bin/env python3
"""PII data inventory: scan every column of a sample CSV with deterministic detectors.

Raw matched values are NEVER written to any output: reports carry counts, rates and
masked examples only (e.g. j***@e***.com, ***-**-6789, **** 1111).

Usage:
  python3 -I scan_pii.py --data sample.csv [--policy policy.csv] [--previous last-inventory.csv] [--strict] --out-dir OUT
  python3 -I scan_pii.py --leak-check REPORT --data sample.csv   # exit 1 if REPORT holds a raw match

Value detectors (per non-empty cell, trimmed):
  email         local@domain.tld
  phone         E.164 (+ and 8-15 digits) or NANP 10-digit (optional +1/1, separators . - space ())
  ssn           US SSN pattern ddd-dd-dddd, structurally valid (area not 000/666/9xx,
                group not 00, serial not 0000)
  payment_card  13-19 digits (spaces/dashes allowed) passing the Luhn checksum
  ipv4 / ipv6   parsed by the stdlib ipaddress module
  dob           ISO YYYY-MM-DD or MM/DD/YYYY date in a column whose name contains dob/birth
  Email and SSN are also found embedded in free text; the others match the whole cell.
Column-name hints (heuristic, need human confirmation): name, address, ssn, email, phone.

Policy CSV (optional): pii_type,handling with handling in mask|tokenize|drop|allow.
A column's handling is the strictest of its types' handlings (drop > tokenize > mask > allow).
If any of its types has no policy row, handling is `[TO BE BASELINED — owner: Privacy officer]`.

Outputs: OUT/pii-inventory.csv (column,pii_types,match_rate,rows_scanned,handling,matches,basis)
         OUT/pii-report.md (Summary, Column inventory, Handling gaps, Method)
Brownfield (--previous): pass the pii-inventory.csv of the last scan of this table. Each column is then
classed new | removed | pii-added | pii-removed | handling-changed | unchanged against it; the inventory
gains a change_vs_previous column and the report a "Changes since last inventory" section.
match_rate = cells matched by any value detector / non-empty cells in the column (3 dp).
Exit codes: 0 ok · 1 --strict and a PII column lacks a policy handling (or a leak-check hit)
            · 2 missing or invalid input.
Stdlib only; reads only the given files; writes only into --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import ipaddress
import re
import sys
from datetime import date, datetime
from pathlib import Path

HANDLINGS = ("drop", "tokenize", "mask", "allow")  # strictest first
TBD = "[TO BE BASELINED — owner: Privacy officer]"
VALUE_TYPES = ("email", "phone", "ssn", "payment_card", "ipv4", "ipv6", "dob")
HINT_TYPES = ("name", "address", "ssn", "email", "phone")
KNOWN_TYPES = set(VALUE_TYPES) | set(HINT_TYPES)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$")
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
NANP_RE = re.compile(r"^(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-]?([2-9]\d{2})[\s.-]?(\d{4})$")
SSN_RE = re.compile(r"^(\d{3})-(\d{2})-(\d{4})$")
EMAIL_IN_TEXT_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![\w-])")
SSN_IN_TEXT_RE = re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])")
CARD_CHARS_RE = re.compile(r"^[\d -]+$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
US_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
NAME_EXCLUDE = {"product", "file", "host", "hostname", "company", "org", "organization", "item", "sku",
                "table", "column", "brand", "store", "app", "service", "domain", "server", "project", "field"}
ADDRESS_EXCLUDE = {"ip", "email", "mac", "web", "url", "memory"}


class InputError(Exception):
    """A required input is missing or malformed (exit 2)."""


# ------------------------------------------------------------------ detectors

def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def is_email(v: str) -> bool:
    return bool(EMAIL_RE.match(v))


def is_phone(v: str) -> bool:
    compact = re.sub(r"[\s().-]", "", v)
    return bool(E164_RE.match(compact)) or bool(NANP_RE.match(v))


def is_ssn(v: str) -> bool:
    m = SSN_RE.match(v)
    if not m:
        return False
    area, group, serial = m.groups()
    return area not in ("000", "666") and not area.startswith("9") and group != "00" and serial != "0000"


def is_card(v: str) -> bool:
    if not CARD_CHARS_RE.match(v):
        return False
    digits = re.sub(r"\D", "", v)
    return 13 <= len(digits) <= 19 and luhn_ok(digits)


def ip_version(v: str) -> int | None:
    try:
        return ipaddress.ip_address(v).version
    except ValueError:
        return None


def is_date(v: str) -> bool:
    try:
        if ISO_DATE_RE.match(v):
            date.fromisoformat(v)
            return True
        if US_DATE_RE.match(v):
            datetime.strptime(v, "%m/%d/%Y")
            return True
    except ValueError:
        return False
    return False


def tokens(col: str) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", col)
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def is_dob_column(col: str) -> bool:
    low = col.lower()
    return "dob" in tokens(col) or "birth" in low


def name_hints(col: str) -> list[str]:
    t = set(tokens(col))
    joined = "".join(tokens(col))
    hints = []
    if ("name" in t or joined in ("firstname", "lastname", "fullname", "surname", "givenname")) \
            and not (t & NAME_EXCLUDE) and "username" not in t:
        hints.append("name")
    if ("address" in t or "street" in t) and not (t & ADDRESS_EXCLUDE):
        hints.append("address")
    if "ssn" in t or "socialsecurity" in joined:
        hints.append("ssn")
    if "email" in t or "mail" in t:
        hints.append("email")
    if "phone" in t or "mobile" in t or "tel" in t:
        hints.append("phone")
    return hints


def detect(v: str, dob_col: bool) -> list[tuple[str, str]]:
    """(pii_type, matched raw text) pairs for one trimmed cell. Email and SSN are also found
    embedded in free text; the other detectors match the whole cell."""
    found: list[tuple[str, str]] = []
    if is_email(v):
        found.append(("email", v))
    else:
        found += [("email", m.group(0)) for m in EMAIL_IN_TEXT_RE.finditer(v)][:1]
    if is_ssn(v):
        found.append(("ssn", v))
    else:
        emb = [m.group(0) for m in SSN_IN_TEXT_RE.finditer(v) if is_ssn(m.group(0))]
        if emb:
            found.append(("ssn", emb[0]))
        elif is_card(v):
            found.append(("payment_card", v))
        elif is_phone(v):
            found.append(("phone", v))
    ver = ip_version(v)
    if ver == 4:
        found.append(("ipv4", v))
    elif ver == 6:
        found.append(("ipv6", v))
    if dob_col and is_date(v):
        found.append(("dob", v))
    return found


# ------------------------------------------------------------------ masking (never emit raw values)

def _first_star(s: str) -> str:
    return (s[:1] + "***") if s else "***"


def mask(v: str, kind: str) -> str:
    if kind == "email":
        local, _, domain = v.partition("@")
        labels = domain.split(".")
        return f"{_first_star(local)}@{_first_star(labels[0])}.{labels[-1]}"
    digits = re.sub(r"\D", "", v)
    if kind == "ssn":
        return f"***-**-{digits[-4:]}"
    if kind == "payment_card":
        return f"**** {digits[-4:]}"
    if kind == "phone":
        return f"***-***-{digits[-4:]}"
    if kind == "ipv4":
        return v.split(".")[0] + ".***.***.***"
    if kind == "ipv6":
        return v.split(":")[0] + ":****:…"
    if kind == "dob":
        return "****-**-**"
    return "[redacted]"


# ------------------------------------------------------------------ scan

def load_dataset(path: Path) -> tuple[list[str], list[list[str]]]:
    if not path.is_file():
        raise InputError(f"dataset not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows or not any(c.strip() for c in rows[0]):
        raise InputError(f"dataset has no header row: {path.name}")
    header = [c.strip() for c in rows[0]]
    body = [(r + [""] * len(header))[: len(header)] for r in rows[1:] if any(c.strip() for c in r)]
    return header, body


def load_policy(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    if not path.is_file():
        raise InputError(f"policy file not found: {path}")
    pol: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not {"pii_type", "handling"} <= set(reader.fieldnames):
            raise InputError("policy CSV needs a header with columns pii_type,handling")
        for row in reader:
            t = (row.get("pii_type") or "").strip().lower()
            h = (row.get("handling") or "").strip().lower()
            if not t or t.startswith("#"):
                continue
            if t not in KNOWN_TYPES:
                raise InputError(f"unknown pii_type in policy: {t!r} (known: {sorted(KNOWN_TYPES)})")
            if h == "":
                continue  # blank = not decided -> stays TBD
            if h not in HANDLINGS:
                raise InputError(f"invalid handling for {t!r}: {h!r} (allowed: {', '.join(HANDLINGS)})")
            pol[t] = h
    return pol


def column_handling(types: list[str], policy: dict[str, str] | None) -> tuple[str, list[str]]:
    """(handling, types lacking a policy row)."""
    if not types:
        return "n/a", []
    if policy is None:
        return TBD, list(types)
    missing = [t for t in types if t not in policy]
    if missing:
        return TBD, missing
    return min((policy[t] for t in types), key=HANDLINGS.index), []


def scan(header: list[str], body: list[list[str]], policy: dict[str, str] | None) -> list[dict]:
    out = []
    for i, col in enumerate(header):
        dob_col = is_dob_column(col)
        counts = {t: 0 for t in VALUE_TYPES}
        examples: dict[str, list[str]] = {}
        non_empty = matched = 0
        for r in body:
            v = r[i].strip()
            if not v:
                continue
            non_empty += 1
            found = detect(v, dob_col)
            if found:
                matched += 1
            for t, raw in found:
                counts[t] += 1
                ex = examples.setdefault(t, [])
                m = mask(raw, t)
                if len(ex) < 2 and m not in ex:
                    ex.append(m)
        value_types = [t for t in VALUE_TYPES if counts[t] > 0]
        hints = [h for h in name_hints(col) if h not in value_types]
        types = value_types + hints
        handling, missing = column_handling(types, policy)
        basis = "+".join(x for x in (("values" if value_types else ""), ("name-hint" if hints else "")) if x) or "none"
        out.append({
            "column": col, "pii_types": types, "value_types": value_types, "hint_types": hints,
            "match_rate": round(matched / non_empty, 3) if non_empty else 0.0,
            "rows_scanned": len(body), "non_empty": non_empty, "matches": matched,
            "counts": {t: counts[t] for t in value_types}, "examples": examples,
            "handling": handling, "policy_missing": missing, "basis": basis,
        })
    return out


def load_previous(path: Path) -> dict[str, dict]:
    """A pii-inventory.csv from an earlier run: column -> {types, handling}."""
    if not path.is_file():
        raise InputError(f"previous inventory not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        need = {"column", "pii_types", "handling"}
        if not need <= set(reader.fieldnames or []):
            raise InputError(f"previous inventory needs columns {sorted(need)}; header is {reader.fieldnames}")
        prev = {}
        for row in reader:
            col = (row.get("column") or "").strip()
            if not col:
                continue
            types = [t for t in (row.get("pii_types") or "").split(";") if t and t != "none"]
            prev[col] = {"types": types, "handling": (row.get("handling") or "").strip()}
    return prev


def compare_previous(cols: list[dict], prev: dict[str, dict]) -> list[dict]:
    """Per-column change vs the last inventory; also sets c['change'] on each current column."""
    changes = []
    for c in cols:
        p = prev.get(c["column"])
        if p is None:
            kind, detail = "new", ("PII: " + ", ".join(c["pii_types"])) if c["pii_types"] else "no PII"
        else:
            added = [t for t in c["pii_types"] if t not in p["types"]]
            gone = [t for t in p["types"] if t not in c["pii_types"]]
            if added:
                kind, detail = "pii-added", "now also " + ", ".join(added)
            elif gone:
                kind, detail = "pii-removed", "no longer " + ", ".join(gone)
            elif p["handling"] != c["handling"]:
                kind, detail = "handling-changed", f"{p['handling']} -> {c['handling']}"
            else:
                kind, detail = "unchanged", ""
        c["change"] = kind
        if kind != "unchanged":
            changes.append({"column": c["column"], "change": kind, "detail": detail,
                            "handling": c["handling"], "has_pii": bool(c["pii_types"])})
    for col, p in prev.items():
        if col not in {c["column"] for c in cols}:
            changes.append({"column": col, "change": "removed",
                            "detail": ("was " + ", ".join(p["types"])) if p["types"] else "had no PII",
                            "handling": p["handling"] or "n/a", "has_pii": bool(p["types"])})
    return changes


# ------------------------------------------------------------------ outputs

CSV_COLS = ["column", "pii_types", "match_rate", "rows_scanned", "handling", "matches", "basis"]


def write_csv(path: Path, cols: list[dict], with_change: bool = False) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS + (["change_vs_previous"] if with_change else []))
        for c in cols:
            w.writerow([c["column"], ";".join(c["pii_types"]) or "none", f"{c['match_rate']:.3f}",
                        c["rows_scanned"], c["handling"], c["matches"], c["basis"]]
                       + ([c.get("change", "")] if with_change else []))


def render_changes(changes: list[dict], prev_name: str) -> list[str]:
    lines = ["", "## Changes since last inventory", "",
             f"Compared with `{prev_name}`: {len(changes)} column change(s)."]
    if changes:
        lines += ["", "| Column | Change | Detail | Handling now |", "|---|---|---|---|"]
        for ch in changes:
            lines.append(f"| {ch['column']} | {ch['change']} | {ch['detail'] or '—'} | {ch['handling']} |")
        urgent = [ch["column"] for ch in changes if ch["change"] in ("new", "pii-added") and ch["has_pii"]]
        if urgent:
            lines += ["", "PII that was not in the last inventory: " + ", ".join(urgent)
                      + ". Update the record of processing and confirm downstream copies apply the handling"
                        " — owner: Privacy officer."]
    return lines


def render_md(src: str, policy_name: str | None, cols: list[dict], strict: bool,
              changes: list[dict] | None = None, prev_name: str = "") -> str:
    pii = [c for c in cols if c["pii_types"]]
    gaps = [c for c in pii if c["policy_missing"]]
    rows = cols[0]["rows_scanned"] if cols else 0
    lines = [
        "# PII data inventory", "",
        f"Dataset: `{src}` · policy: `{policy_name}`" if policy_name else
        f"Dataset: `{src}` · policy: not supplied — every PII column's handling is {TBD}", "",
        "## Summary", "",
        f"- Columns scanned: {len(cols)}; rows scanned: {rows}.",
        f"- Columns with PII (values or name hints): {len(pii)}.",
        f"- Columns with a handling gap: {len(gaps)}." + (" `--strict` was set: the run fails (exit 1)."
                                                          if strict and gaps else ""),
        "- Raw values are never written: examples below are masked.", "",
        "## Column inventory", "",
        "| Column | PII types | Basis | Match rate | Matches / non-empty | Masked examples | Handling |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in cols:
        ex = "; ".join(e for t in c["value_types"] for e in c["examples"].get(t, [])) or \
             ("hint only — no value pattern" if c["hint_types"] else "—")
        lines.append(f"| {c['column']} | {', '.join(c['pii_types']) or 'none'} | {c['basis']} | "
                     f"{c['match_rate']:.3f} | {c['matches']} / {c['non_empty']} | {ex} | {c['handling']} |")
    lines += ["", "## Handling gaps", ""]
    if not gaps:
        lines.append("None: every PII column has a policy handling.")
    else:
        lines += ["| Column | PII types without policy | Owner | Action |", "|---|---|---|---|"]
        for c in gaps:
            lines.append(f"| {c['column']} | {', '.join(c['policy_missing'])} | Privacy officer | "
                         f"Add a pii_type,handling row (mask, tokenize, drop or allow) and re-run. |")
    allowed = [c for c in pii if c["handling"] == "allow"]
    if allowed:
        lines += ["", "Columns the policy allows in clear: " + ", ".join(c["column"] for c in allowed)
                  + ". Confirm a lawful basis is recorded for each."]
    if changes is not None:
        lines += render_changes(changes, prev_name)
    lines += ["", "## Method", "",
              "- Deterministic detectors: email; phone (E.164 or NANP 10-digit); US SSN pattern (structurally valid);"
              " payment card (13–19 digits, Luhn); IPv4/IPv6; date of birth (dates in dob/birth columns)."
              " Email and SSN are also found inside free text; the others must fill the cell.",
              "- Column-name hints (name, address, ssn, email, phone) are heuristics: confirm or dismiss each.",
              "- Match rate = cells matched by a value detector ÷ non-empty cells. A sample can miss PII that"
              " is rare in the full table; free-text columns need human review regardless of the rate.",
              "- Not detected: names and addresses inside free text, national IDs other than the US SSN pattern,"
              " health or biometric data, quasi-identifier combinations. This is not a legal determination.", ""]
    return "\n".join(lines)


def leak_check(report: Path, data: Path) -> int:
    """Exit 1 if any raw value a detector matches in `data` appears verbatim in `report`."""
    header, body = load_dataset(data)
    text = report.read_text(encoding="utf-8", errors="replace")
    leaks = 0
    for i, col in enumerate(header):
        dob_col = is_dob_column(col)
        for r in body:
            v = r[i].strip()
            if not v:
                continue
            leaks += sum(1 for _, raw in detect(v, dob_col) if raw in text)
    print(f"leak-check: {leaks} raw matched value(s) found in {report.name}")
    return 1 if leaks else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="sample CSV with a header row")
    ap.add_argument("--policy", type=Path, help="policy CSV pii_type,handling (mask|tokenize|drop|allow)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when a PII column has no policy handling")
    ap.add_argument("--previous", type=Path, help="pii-inventory.csv of the last scan, to report what changed")
    ap.add_argument("--out-dir", type=Path, help="directory for pii-inventory.csv and pii-report.md")
    ap.add_argument("--leak-check", type=Path, metavar="REPORT", help="verify REPORT holds no raw matched value")
    args = ap.parse_args(argv)
    try:
        if args.leak_check:
            return leak_check(args.leak_check, args.data)
        if not args.out_dir:
            ap.error("--out-dir is required")
        header, body = load_dataset(args.data)
        policy = load_policy(args.policy)
        prev = load_previous(args.previous) if args.previous else None
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    cols = scan(header, body, policy)
    changes = compare_previous(cols, prev) if prev is not None else None
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "pii-inventory.csv", cols, with_change=prev is not None)
    (args.out_dir / "pii-report.md").write_text(
        render_md(args.data.name, args.policy.name if args.policy else None, cols, args.strict,
                  changes, args.previous.name if args.previous else ""), encoding="utf-8")
    pii = [c for c in cols if c["pii_types"]]
    gaps = [c for c in pii if c["policy_missing"]]
    print(f"pii columns: {len(pii)} of {len(cols)}; handling gaps: {len(gaps)}")
    if changes is not None:
        print(f"vs previous inventory: {len(changes)} column change(s)")
    if args.strict and gaps:
        print("strict: PII without policy handling in " + ", ".join(c["column"] for c in gaps), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
