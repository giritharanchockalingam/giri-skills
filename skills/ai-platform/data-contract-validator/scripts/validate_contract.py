#!/usr/bin/env python3
"""Data contract validator: check a CSV dataset against its data contract before AI use.

Usage:
  python3 -I validate_contract.py --contract contract.csv --data data.csv --out-dir OUT
        [--freshness-column COL --as-of YYYY-MM-DD --max-age-days N]
  python3 -I validate_contract.py --verify OUTPUT_FILE --contract C --data D [same freshness args]
        # exit 0 when OUTPUT_FILE is byte-identical to what this script produces for the inputs
  python3 -I validate_contract.py --data data.csv --draft-contract OUT/contract-draft.csv --out-dir OUT
        # no contract yet: draft one from the extract, then validate the extract against the draft

Draft (--draft-contract D, used only when --contract is not given): if D does not exist it is written
  from the data — type from the values; required when the extract has no nulls; unique only for an
  all-distinct, null-free column named like a key (id, *_id, key, *_key, code, *_code); enum for text
  with at most 10 distinct values each seen at least twice on average; max_null_rate = the observed null
  rate rounded up to 3 dp when there are nulls; min/max, regex and owner left blank (the observed range
  goes in `notes`); severity warn for every rule. Its first line marks it as a DRAFT; while that line is
  present the report says the contract is a draft and that a pass is by construction. If D exists (a
  draft under review), it is used as the contract as it stands.

Contract (CSV, layout assets/contract-template.csv), one row per expected column:
  column, type, required, unique, min, max, allowed, regex, max_null_rate, severity, owner
  type      string|integer|number|boolean|date|datetime|email|enum
  required  yes|no (blank = no)        unique   yes|no (blank = no)
  min/max   number for integer/number; YYYY-MM-DD / ISO datetime for date/datetime;
            character length for string/email/enum
  allowed   pipe-separated exact values (required for enum)
  regex     full-match Python regex     max_null_rate  0..1 (blank = not checked)
  severity  error|warn (blank = error)  owner  role accountable (blank = TBD, owner: Data owner)
Contract (YAML): an ODCS v3 subset parsed with the repo's YAML subset parser
  (scripts/skillmeta.py) — see references/odcs-subset.md for the mapping and limits.

Rules (violations.csv `rule`): missing_column, extra_column, ragged_row, type, required,
  null_rate, unique, min, max, allowed, regex, freshness.
Null = empty after trimming, or the literal `null` (any case). Value rules (type, unique,
  min, max, allowed, regex) apply to non-null values; failing_rate = failing ÷ non-null values.
  required / null_rate: failing_rate = null rows ÷ rows. missing_column / freshness: all rows.
Examples: at most 3 distinct failing values per violation, each truncated to 40 characters.
Text columns' values never appear in profile.csv (min/max are reported for numeric and
  date-like columns only).

Outputs: OUT/violations.csv, OUT/profile.csv, OUT/contract-report.md (+ the drafted contract, if any)
Exit codes: 0 no error-severity violation · 1 at least one error-severity violation (outputs
  still written) or --verify mismatch · 2 missing or invalid input.
Stdlib only; reads only the given files; writes only into --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

TYPES = ("string", "integer", "number", "boolean", "date", "datetime", "email", "enum")
NUMERIC = ("integer", "number")
DATELIKE = ("date", "datetime")
LENGTH_TYPES = ("string", "email", "enum")
SEVERITIES = ("error", "warn")
TBD_OWNER = "[TO BE BASELINED — owner: Data owner]"
RULE_ORDER = ("missing_column", "ragged_row", "freshness", "type", "required", "null_rate", "unique",
              "min", "max", "allowed", "regex", "extra_column")
CONTRACT_COLS = ("column", "type", "required", "unique", "min", "max", "allowed", "regex",
                 "max_null_rate", "severity", "owner")
MAX_EXAMPLES = 3
EXAMPLE_LEN = 40

INT_RE = re.compile(r"^[+-]?\d+$")
NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$")
BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "t", "f", "1", "0"}


class InputError(Exception):
    """A required input is missing or malformed (exit 2)."""


_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(v) -> str:
    """OWASP CSV-injection guard: prefix a formula-leading text cell with a single quote (numbers untouched)."""
    s = "" if v is None else str(v)
    if s.startswith(_FORMULA_LEAD) and not NUM_RE.match(s):
        return "'" + s
    return s


def read_text_strict(path: Path, what: str) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        raise InputError(f"{what} file {Path(path).name} is not UTF-8 text ({e.reason} at byte {e.start}); "
                         "re-save it as CSV UTF-8 — bytes are never silently replaced") from None
    if "\x00" in text:
        raise InputError(f"{what} file {Path(path).name} is not a text file (contains NUL bytes)")
    return text


# ------------------------------------------------------------------ parsing helpers

def is_null(v: str) -> bool:
    s = v.strip()
    return s == "" or s.lower() == "null"


def parse_value(typ: str, v: str):
    """Parsed value or None when `v` does not parse as `typ`."""
    s = v.strip()
    if typ in ("string", "enum"):
        return s
    if typ == "integer":
        return int(s) if INT_RE.match(s) else None
    if typ == "number":
        if not NUM_RE.match(s):
            return None
        f = float(s)
        return f if math.isfinite(f) else None
    if typ == "boolean":
        return s.lower() if s.lower() in BOOL_VALUES else None
    if typ == "date":
        if not DATE_RE.match(s):
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    if typ == "datetime":
        if not DT_RE.match(s):
            return None
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        return d.replace(tzinfo=None) - (d.utcoffset() or timedelta(0)) if d.tzinfo else d
    if typ == "email":
        return s if EMAIL_RE.match(s) else None
    return None


def parse_bound(typ: str, raw: str, what: str, col: str):
    s = (raw or "").strip()
    if s == "":
        return None
    if typ in LENGTH_TYPES:
        if not INT_RE.match(s) or int(s) < 0:
            raise InputError(f"contract column '{col}': {what} must be a non-negative length for type {typ}, got {s!r}")
        return int(s)
    if typ == "boolean":
        raise InputError(f"contract column '{col}': {what} is not meaningful for boolean")
    if typ == "datetime" and DATE_RE.match(s):
        # A date-only bound on a datetime column covers the whole day: min = start, max = end of that day.
        s = s + ("T23:59:59.999999" if what == "max" else "T00:00:00")
    p = parse_value(typ if typ != "integer" else "number", s)
    if p is None:
        raise InputError(f"contract column '{col}': {what} {s!r} does not parse as {typ}")
    return p


def fmt_bound(v) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, datetime):
        if (v.hour, v.minute, v.second, v.microsecond) == (23, 59, 59, 999999):
            return f"{v.date().isoformat()} (whole day, to 23:59:59.999999)"
        return v.isoformat()
    return str(v)


def yes_no(raw: str, what: str, col: str) -> bool:
    s = (raw or "").strip().lower()
    if s in ("", "no", "n", "false"):
        return False
    if s in ("yes", "y", "true"):
        return True
    raise InputError(f"contract column '{col}': {what} must be yes or no, got {raw!r}")


def read_csv_text(path: Path, what: str) -> list[list[str]]:
    if not path or not Path(path).is_file():
        raise InputError(f"{what} file not found: {path}")
    text = read_text_strict(path, what)
    lines = text.splitlines()
    while lines and lines[0].lstrip().startswith("#"):  # leading comment lines (e.g. "fictional fixture")
        lines.pop(0)
    try:
        rows = list(csv.reader(io.StringIO("\n".join(lines))))
    except csv.Error as e:
        raise InputError(f"{what} file {Path(path).name}: malformed CSV ({e})") from None
    if not rows or not any(c.strip() for c in rows[0]):
        raise InputError(f"{what} has no header row: {path}")
    return rows


# ------------------------------------------------------------------ contract loading

def build_rule(rec: dict) -> dict:
    col = (rec.get("column") or "").strip()
    if not col:
        raise InputError("contract row with a blank column name")
    typ = (rec.get("type") or "").strip().lower()
    if typ not in TYPES:
        raise InputError(f"contract column '{col}': type must be one of {', '.join(TYPES)}, got {rec.get('type')!r}")
    allowed_raw = (rec.get("allowed") or "").strip()
    allowed = [a.strip() for a in allowed_raw.split("|")] if allowed_raw else []
    if typ == "enum" and not allowed:
        raise InputError(f"contract column '{col}': type enum needs allowed values (pipe-separated)")
    regex = (rec.get("regex") or "").strip()
    rx = None
    if regex:
        try:
            rx = re.compile(regex)
        except re.error as e:
            raise InputError(f"contract column '{col}': invalid regex {regex!r}: {e}") from None
    mnr_raw = (rec.get("max_null_rate") or "").strip()
    mnr = None
    if mnr_raw:
        try:
            mnr = float(mnr_raw)
        except ValueError:
            mnr = -1.0
        if not 0.0 <= mnr <= 1.0:
            raise InputError(f"contract column '{col}': max_null_rate must be between 0 and 1, got {mnr_raw!r}")
    sev = (rec.get("severity") or "").strip().lower() or "error"
    if sev == "warning":
        sev = "warn"
    if sev not in SEVERITIES:
        raise InputError(f"contract column '{col}': severity must be error or warn, got {rec.get('severity')!r}")
    lo = parse_bound(typ, rec.get("min", ""), "min", col)
    hi = parse_bound(typ, rec.get("max", ""), "max", col)
    if lo is not None and hi is not None and lo > hi:
        raise InputError(f"contract column '{col}': min is greater than max")
    owner = (rec.get("owner") or "").strip() or TBD_OWNER
    return {"column": col, "type": typ, "required": yes_no(rec.get("required", ""), "required", col),
            "unique": yes_no(rec.get("unique", ""), "unique", col), "min": lo, "max": hi, "allowed": allowed,
            "regex": regex, "rx": rx, "max_null_rate": mnr, "severity": sev, "owner": owner}


def load_contract_csv(path: Path) -> tuple[list[dict], list[str]]:
    rows = read_csv_text(path, "contract")
    header = [h.strip().lower() for h in rows[0]]
    for need in ("column", "type"):
        if need not in header:
            raise InputError(f"contract is missing the '{need}' column (layout: assets/contract-template.csv)")
    unknown = [h for h in header if h and h not in CONTRACT_COLS and h != "notes"]
    if unknown:
        raise InputError(f"contract has unknown columns: {', '.join(unknown)} (layout: assets/contract-template.csv)")
    recs = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        recs.append(build_rule({h: (r[i] if i < len(r) else "") for i, h in enumerate(header)}))
    return recs, []


ODCS_TYPES = {"string": "string", "integer": "integer", "number": "number", "boolean": "boolean",
              "date": "date", "timestamp": "datetime"}


def _find_skillmeta():
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "scripts" / "skillmeta.py"
        if cand.is_file():
            return cand
    return None


def _strip_yaml(text: str) -> str:
    """Drop block-scalar bodies (`key: |` / `key: >`) and inline `# comments` outside quotes,
    which the repo's YAML subset parser does not handle. Anchors, aliases and tags are rejected."""
    out, skip_indent = [], None
    for raw in text.splitlines():
        indent = len(raw) - len(raw.lstrip(" "))
        if skip_indent is not None:
            if raw.strip() == "" or indent > skip_indent:
                continue
            skip_indent = None
        line, quote = [], None
        for i, ch in enumerate(raw):
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == "#" and (i == 0 or raw[i - 1] in " \t"):
                break
            line.append(ch)
        s = "".join(line).rstrip()
        if re.search(r"(^|[\s:\[,-])[&*!][A-Za-z]", s.split(":", 1)[-1] if ":" in s else s):
            raise InputError("YAML contract uses anchors, aliases or tags, which the YAML subset parser does not "
                             "support; use the CSV contract (assets/contract-template.csv)")
        m = re.match(r"^(\s*(?:- )?[^:]+):\s*[|>][-+]?\s*$", s)
        if m:
            out.append(m.group(1) + ': ""')
            skip_indent = indent
            continue
        out.append(s)
    return "\n".join(out)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_contract_yaml(path: Path) -> tuple[list[dict], list[str]]:
    if not Path(path).is_file():
        raise InputError(f"contract file not found: {path}")
    sm_path = _find_skillmeta()
    if sm_path is None:
        raise InputError("YAML contracts need the repo's scripts/skillmeta.py; use the CSV contract instead")
    sys.path.insert(0, str(sm_path.parent))
    try:
        import skillmeta  # noqa: PLC0415 — repo YAML subset parser
    finally:
        sys.path.pop(0)
    doc = skillmeta.parse_yaml_subset(_strip_yaml(read_text_strict(path, "contract")))
    schema = doc.get("schema") if isinstance(doc, dict) else None
    if not isinstance(schema, list) or not schema:
        raise InputError("YAML contract has no `schema:` list (ODCS v3 layout expected)")
    if len(schema) > 1:
        raise InputError(f"YAML contract has {len(schema)} schema objects; validate one dataset per run "
                         "(split the contract or use the CSV layout)")
    obj = schema[0] if isinstance(schema[0], dict) else {}
    props = obj.get("properties")
    if not isinstance(props, list) or not props:
        raise InputError("YAML contract schema object has no `properties:` list")
    notes: list[str] = []
    recs = []
    for p in props:
        if not isinstance(p, dict) or not str(p.get("name") or "").strip():
            raise InputError("YAML contract property without a name")
        name = str(p["name"]).strip()
        lt = str(p.get("logicalType") or "string").strip()
        if lt not in ODCS_TYPES:
            raise InputError(f"YAML contract property '{name}': logicalType {lt!r} is not supported "
                             f"(supported: {', '.join(ODCS_TYPES)})")
        typ = ODCS_TYPES[lt]
        opts = p.get("logicalTypeOptions") if isinstance(p.get("logicalTypeOptions"), dict) else {}
        enum = p.get("enum", opts.get("enum"))
        allowed = [str(x) for x in enum] if isinstance(enum, list) else []
        regex = str(opts.get("pattern") or "")
        if str(opts.get("format") or "").lower() == "email" and typ == "string":
            typ = "email"
        lo = opts.get("minimum", opts.get("minLength"))
        hi = opts.get("maximum", opts.get("maxLength"))
        sev, mnr, unique_q = "", "", False
        for q in p.get("quality") or []:
            if not isinstance(q, dict):
                continue
            metric = str(q.get("metric") or q.get("rule") or "")
            args = q.get("arguments") if isinstance(q.get("arguments"), dict) else {}
            if q.get("severity"):
                sev = str(q["severity"]).strip().lower()
            if metric == "invalidValues" and isinstance(args.get("validValues"), list) \
                    and _num(q.get("mustBe")) == 0:
                allowed = [str(x) for x in args["validValues"]]
            elif metric == "invalidValues" and args.get("pattern") and _num(q.get("mustBe")) == 0:
                regex = str(args["pattern"])
            elif metric == "duplicateValues" and _num(q.get("mustBe")) == 0:
                unique_q = True
            elif metric == "nullValues" and str(q.get("unit") or "rows") == "percent" \
                    and _num(q.get("mustBeLessOrEqualTo")) is not None:
                mnr = str(_num(q["mustBeLessOrEqualTo"]) / 100.0)
            else:
                notes.append(f"`{name}`: quality metric `{metric or '?'}` not evaluated (outside the supported subset)")
        if allowed and typ == "string":
            typ = "enum"
        required = bool(p.get("required")) or bool(p.get("primaryKey"))
        unique = bool(p.get("unique")) or bool(p.get("primaryKey")) or unique_q
        recs.append(build_rule({"column": name, "type": typ, "required": "yes" if required else "no",
                                "unique": "yes" if unique else "no",
                                "min": "" if lo is None else str(lo), "max": "" if hi is None else str(hi),
                                "allowed": "|".join(allowed), "regex": regex, "max_null_rate": mnr,
                                "severity": sev, "owner": ""}))
    return recs, notes


def load_contract(path: Path) -> tuple[list[dict], list[str]]:
    if path is None:
        raise InputError("--contract is required")
    if Path(path).suffix.lower() in (".yaml", ".yml"):
        recs, notes = load_contract_yaml(path)
    else:
        recs, notes = load_contract_csv(path)
    if not recs:
        raise InputError("contract has no column rows")
    seen = set()
    for r in recs:
        if r["column"] in seen:
            raise InputError(f"contract lists column '{r['column']}' twice")
        seen.add(r["column"])
    return recs, notes


def load_data(path: Path) -> tuple[list[str], list[list[str]], int]:
    if path is None:
        raise InputError("--data is required")
    rows = read_csv_text(path, "data")
    header = [h.strip() for h in rows[0]]
    dup = sorted({h for h in header if header.count(h) > 1})
    if dup:
        raise InputError(f"data header repeats column(s): {', '.join(dup)}")
    body, ragged = [], 0
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        if len(r) != len(header):
            ragged += 1
        body.append([r[i] if i < len(r) else "" for i in range(len(header))])
    return header, body, ragged


def freshness_params(col, as_of, max_age):
    col, as_of, max_age = (col or "").strip(), (as_of or "").strip(), (max_age or "").strip()
    if not col:
        if as_of or max_age:
            raise InputError("--as-of / --max-age-days need --freshness-column")
        return None
    d = None
    if as_of:
        try:
            d = date.fromisoformat(as_of)
        except ValueError:
            raise InputError(f"--as-of must be YYYY-MM-DD, got {as_of!r}") from None
    n = None
    if max_age:
        if not INT_RE.match(max_age) or int(max_age) < 0:
            raise InputError(f"--max-age-days must be a non-negative integer, got {max_age!r}")
        n = int(max_age)
    return {"column": col, "as_of": d, "max_age_days": n}


# ------------------------------------------------------------------ checks

def trunc(v: str) -> str:
    v = v.strip().replace("\n", " ").replace("\r", " ")
    return v if len(v) <= EXAMPLE_LEN else v[: EXAMPLE_LEN - 1] + "…"


def examples(values: list[str]) -> str:
    out: list[str] = []
    for v in values:
        t = trunc(v)
        if t not in out:
            out.append(t)
        if len(out) == MAX_EXAMPLES:
            break
    return " | ".join(out)


def rate(n: int, d: int) -> str:
    return f"{(n / d) if d else 0.0:.3f}"


def check(contract, notes, header, body, ragged, fresh) -> tuple[list[dict], list[dict], dict]:
    n = len(body)
    idx = {h: i for i, h in enumerate(header)}
    by_col = {r["column"]: r for r in contract}
    viol: list[dict] = []

    def add(rule, col, rule_name, failing, denom, ex="", expectation=""):
        viol.append({"column": col, "rule": rule_name, "severity": rule["severity"] if rule else "warn",
                     "failing_rows": failing, "failing_rate": rate(failing, denom), "examples": ex,
                     "owner": rule["owner"] if rule else TBD_OWNER, "expectation": expectation})

    if ragged:
        add({"severity": "error", "owner": TBD_OWNER}, "*", "ragged_row", ragged, n,
            expectation=f"every row has {len(header)} fields")
    for r in contract:
        col = r["column"]
        if col not in idx:
            add(r, col, "missing_column", n, n, expectation="column present in data")
            continue
        vals = [row[idx[col]] for row in body]
        nonnull = [v for v in vals if not is_null(v)]
        nulls = n - len(nonnull)
        parsed = [(v, parse_value(r["type"], v)) for v in nonnull]
        bad_type = [v for v, p in parsed if p is None]
        if bad_type:
            add(r, col, "type", len(bad_type), len(nonnull), examples(bad_type), f"parses as {r['type']}")
        if r["required"] and nulls:
            add(r, col, "required", nulls, n, expectation="no nulls")
        if r["max_null_rate"] is not None and n and nulls / n > r["max_null_rate"] + 1e-12:
            add(r, col, "null_rate", nulls, n, expectation=f"null rate <= {r['max_null_rate']:.3f}")
        if r["unique"]:
            counts: dict[str, int] = {}
            for v in nonnull:
                counts[v.strip()] = counts.get(v.strip(), 0) + 1
            dups = [v for v in nonnull if counts[v.strip()] > 1]
            extra = len(nonnull) - len(counts)
            if extra:
                add(r, col, "unique", extra, len(nonnull), examples(dups), "values unique")
        good = [(v, p) for v, p in parsed if p is not None]
        if r["type"] in LENGTH_TYPES:
            measure = [(v, len(v.strip())) for v, _ in good]
            unit = " characters"
        elif r["type"] in NUMERIC + DATELIKE:
            measure = [(v, p) for v, p in good]
            unit = ""
        else:
            measure, unit = [], ""
        if r["min"] is not None:
            low = [v for v, m in measure if m < r["min"]]
            if low:
                add(r, col, "min", len(low), len(nonnull), examples(low), f">= {fmt_bound(r['min'])}{unit}")
        if r["max"] is not None:
            high = [v for v, m in measure if m > r["max"]]
            if high:
                add(r, col, "max", len(high), len(nonnull), examples(high), f"<= {fmt_bound(r['max'])}{unit}")
        if r["allowed"]:
            allowed = set(r["allowed"])
            notin = [v for v in nonnull if v.strip() not in allowed]
            if notin:
                add(r, col, "allowed", len(notin), len(nonnull), examples(notin),
                    "one of " + "|".join(r["allowed"]))
        if r["rx"] is not None:
            miss = [v for v in nonnull if not r["rx"].fullmatch(v.strip())]
            if miss:
                add(r, col, "regex", len(miss), len(nonnull), examples(miss), f"matches {r['regex']}")
    for h in header:
        if h not in by_col:
            add(None, h, "extra_column", n, n, expectation="column declared in contract")

    fresh_info = {"status": "not requested"}
    if fresh:
        col = fresh["column"]
        if fresh["as_of"] is None or fresh["max_age_days"] is None:
            missing = [x for x, k in (("as_of", "as_of"), ("max_age_days", "max_age_days")) if fresh[k] is None]
            fresh_info = {"status": f"not checked: {' and '.join(missing)} {TBD_OWNER}"}
        else:
            rule = by_col.get(col) or {"severity": "error", "owner": TBD_OWNER}
            cutoff = fresh["as_of"] - timedelta(days=fresh["max_age_days"])
            exp = f"newest {col} on or after {cutoff.isoformat()} (as of {fresh['as_of'].isoformat()}, " \
                  f"max age {fresh['max_age_days']} days)"
            if col not in idx:
                add(rule, col, "freshness", n, n, "column absent", exp)
                fresh_info = {"status": "failed: column absent"}
            else:
                ds = []
                for row in body:
                    v = row[idx[col]]
                    if is_null(v):
                        continue
                    p = parse_value("date", v) or parse_value("datetime", v)
                    if p is not None:
                        ds.append(p.date() if isinstance(p, datetime) else p)
                if not ds:
                    add(rule, col, "freshness", n, n, "no parseable dates", exp)
                    fresh_info = {"status": "failed: no parseable dates"}
                else:
                    newest = max(ds)
                    age = (fresh["as_of"] - newest).days
                    future = [d for d in ds if d > fresh["as_of"]]
                    if future:
                        # Records dated after the as-of date are not "fresh": the timestamps are wrong or the
                        # as-of date is; either way the age cannot be trusted.
                        add(rule, col, "freshness", len(future), n,
                            f"{len(future)} row(s) dated after as-of; newest {newest.isoformat()}; age {age} days",
                            exp + "; no record dated after the as-of date")
                        fresh_info = {"status": f"failed: {len(future)} future-dated record(s), newest "
                                                f"{newest.isoformat()} is after the as-of date (age {age} days)"}
                    elif age > fresh["max_age_days"]:
                        add(rule, col, "freshness", n, n, f"newest {newest.isoformat()}; age {age} days", exp)
                        fresh_info = {"status": f"failed: newest {newest.isoformat()}, age {age} days"}
                    else:
                        fresh_info = {"status": f"passed: newest {newest.isoformat()}, age {age} days"}
            fresh_info["expectation"] = exp
    order = {c: i for i, c in enumerate([r["column"] for r in contract] + [h for h in header if h not in by_col])}
    order["*"] = -1
    viol.sort(key=lambda v: (SEVERITIES.index(v["severity"]), order.get(v["column"], len(order)),
                             RULE_ORDER.index(v["rule"])))
    profile = build_profile(header, body)
    return viol, profile, fresh_info


def infer_type(nonnull: list[str]) -> str:
    if not nonnull:
        return "empty"
    for typ in ("integer", "number", "boolean", "date", "datetime", "email"):
        if all(parse_value(typ, v) is not None for v in nonnull):
            return typ
    return "string"


def build_profile(header, body) -> list[dict]:
    n = len(body)
    out = []
    for i, h in enumerate(header):
        vals = [row[i] for row in body]
        nonnull = [v.strip() for v in vals if not is_null(v)]
        typ = infer_type(nonnull)
        lo = hi = "n/a (text)" if typ in ("string", "email", "boolean") else ""
        if typ in NUMERIC + DATELIKE:
            parsed = [parse_value(typ, v) for v in nonnull]
            pairs = sorted(zip(parsed, nonnull), key=lambda t: t[0])
            lo, hi = pairs[0][1], pairs[-1][1]
        elif typ == "empty":
            lo = hi = "n/a"
        out.append({"column": h, "inferred_type": typ, "null_rate": rate(n - len(nonnull), n),
                    "distinct": len(set(nonnull)), "min": trunc(lo), "max": trunc(hi)})
    return out


# ------------------------------------------------------------------ draft contract

DRAFT_MARK = "# DRAFT contract inferred by validate_contract.py"
KEY_NAME_RE = re.compile(r"(^|_)(id|key|code)$", re.I)
ENUM_MAX_VALUES = 10


def is_draft(path: Path) -> bool:
    try:
        first = Path(path).read_text(encoding="utf-8-sig").splitlines()[:1]
    except (OSError, UnicodeDecodeError):
        return False
    return bool(first) and first[0].startswith(DRAFT_MARK)


def draft_contract(header: list[str], body: list[list[str]], data_name: str) -> str:
    """A reviewable contract proposal from one extract; every rule at warn severity, no owner invented."""
    n = len(body)
    rows = []
    for i, h in enumerate(header):
        vals = [row[i] for row in body]
        nonnull = [v.strip() for v in vals if not is_null(v)]
        nulls = n - len(nonnull)
        typ = infer_type(nonnull)
        allowed, note = "", f"inferred from {len(nonnull)}/{n} non-null values"
        if typ == "empty":
            typ, note = "string", f"all {n} values null in the extract; type unknown — set it"
        distinct = sorted(set(nonnull))
        if typ == "string" and nonnull and len(distinct) <= ENUM_MAX_VALUES and len(distinct) * 2 <= len(nonnull):
            typ, allowed = "enum", "|".join(distinct)
            note += f"; {len(distinct)} distinct values seen — confirm the full code list"
        if typ in NUMERIC + DATELIKE and nonnull:
            parsed = sorted(zip((parse_value(typ, v) for v in nonnull), nonnull), key=lambda t: t[0])
            note += f"; observed {parsed[0][1]} to {parsed[-1][1]} — set min/max"
        unique = (nulls == 0 and n >= 2 and len(distinct) == n and bool(KEY_NAME_RE.search(h.strip())))
        mnr = "" if nulls == 0 else f"{math.ceil(nulls / n * 1000) / 1000:.3f}"
        rows.append({"column": h, "type": typ, "required": "yes" if nulls == 0 else "no",
                     "unique": "yes" if unique else "no", "min": "", "max": "", "allowed": allowed, "regex": "",
                     "max_null_rate": mnr, "severity": "warn", "owner": "", "notes": note})
    buf = io.StringIO()
    buf.write(f"{DRAFT_MARK} from {data_name} ({n} rows). Review every row with the Data owner, set min/max, "
              "severity and owner, then delete this line.\n")
    w = csv.DictWriter(buf, fieldnames=[*CONTRACT_COLS, "notes"], lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: csv_safe(v) for k, v in r.items()})
    return buf.getvalue()


# ------------------------------------------------------------------ rendering

def csv_text(fields: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: csv_safe(v) for k, v in r.items()})
    return buf.getvalue()


VIOL_FIELDS = ["column", "rule", "severity", "failing_rows", "failing_rate", "examples", "owner", "expectation"]
PROFILE_FIELDS = ["column", "inferred_type", "null_rate", "distinct", "min", "max"]


def md_cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def verdict(viol) -> str:
    if any(v["severity"] == "error" for v in viol):
        return "FAIL"
    return "PASS WITH WARNINGS" if viol else "PASS"


def render_md(contract_name, data_name, contract, notes, header, body, viol, profile, fresh_info,
              draft: bool = False) -> str:
    errors = sum(1 for v in viol if v["severity"] == "error")
    warns = len(viol) - errors
    vd = verdict(viol)
    tbd_owned = sum(1 for v in viol if v["owner"] == TBD_OWNER)
    lines = [
        "# Data contract validation", "",
        f"Dataset: `{data_name}` · contract: `{contract_name}`", "",
        "## Summary", "",
        f"- Verdict: **{vd}** — {errors} error-severity and {warns} warn-severity violations.",
        f"- Rows checked: {len(body)}; data columns: {len(header)}; contract columns: {len(contract)}.",
        f"- Freshness: {fresh_info['status']}.",
        f"- Violations without a named owner: {tbd_owned} (owner {TBD_OWNER}).",
    ]
    if draft:
        lines.append(f"- Contract: **DRAFT** inferred from an extract by this script — every rule is a proposal at warn "
                     f"severity. The Data owner confirms types, keys, allowed values and null limits, sets min/max, "
                     f"severity and owners, and deletes the DRAFT line before the contract gates loads "
                     f"(owner {TBD_OWNER}).")
    lines += ["", "## Verdict", ""]
    if vd == "FAIL":
        lines.append(f"**FAIL** — do not use this dataset for training, RAG ingestion or evaluation until the "
                     f"{errors} error-severity violation(s) are fixed at source and the run passes. The run exits 1.")
    elif vd == "PASS WITH WARNINGS":
        lines.append(f"**PASS WITH WARNINGS** — no error-severity violation. Review the {warns} warning(s) with "
                     "their owners before use.")
    else:
        lines.append("**PASS** — the dataset meets every rule in the contract.")
    if draft:
        lines.append("")
        lines.append("The contract is a draft: where it was inferred from this same extract, a pass shows only that the "
                     "draft is consistent with it — it is not evidence of data quality.")
    lines += ["", "## Violations", ""]
    if not viol:
        lines.append("None.")
    else:
        lines += ["| Column | Rule | Severity | Failing rows | Failing rate | Expectation | Examples (max 3, ≤40 chars) | Owner |",
                  "|---|---|---|---|---|---|---|---|"]
        for v in viol:
            lines.append(f"| {md_cell(v['column'])} | {v['rule']} | {v['severity']} | {v['failing_rows']} | "
                         f"{v['failing_rate']} | {md_cell(v['expectation'])} | {md_cell(v['examples']) or '—'} | "
                         f"{md_cell(v['owner'])} |")
    if notes:
        lines += ["", "Contract terms not evaluated:", ""] + [f"- {n}" for n in notes]
    lines += ["", "## Profile", "",
              "| Column | Inferred type | Null rate | Distinct | Min | Max |", "|---|---|---|---|---|---|"]
    for p in profile:
        lines.append(f"| {md_cell(p['column'])} | {p['inferred_type']} | {p['null_rate']} | {p['distinct']} | "
                     f"{md_cell(p['min']) or '—'} | {md_cell(p['max']) or '—'} |")
    lines += ["", "## Method", "",
              "- Null = empty after trimming, or the literal `null` (any case).",
              "- Value rules (type, unique, min, max, allowed, regex) apply to non-null values; their failing rate is "
              "failing ÷ non-null values. `required` and `null_rate` use null rows ÷ all rows.",
              "- `unique` counts rows beyond the first occurrence of each value. `min`/`max` compare numbers for "
              "integer/number, dates for date/datetime, and character length for string/email/enum.",
              "- `extra_column` (in the data, not in the contract) is a warning owned by the Data owner until the "
              "contract declares it.",
              "- Freshness compares the newest date in the freshness column with the supplied as-of date; it is "
              "checked only when the column, as-of date and maximum age are all supplied — never against today. "
              "Records dated after the as-of date fail freshness.",
              "- A date-only `max` on a datetime column includes the whole day; datetimes with an offset are "
              "compared in UTC.",
              "- CSV outputs prefix text cells that start with = + - @ tab or CR with `'` (CSV-injection guard).",
              "- Examples: at most 3 distinct failing values per violation, each truncated to 40 characters. Text "
              "columns' values are withheld from the profile.",
              "- Verdict: any error-severity violation fails the run (exit 1). The check covers the supplied extract "
              "only; it is not a statistical guarantee about data outside it.", ""]
    return "\n".join(lines)


def resolve_contract(args, header, body) -> tuple[Path, str | None]:
    """(contract path, draft text to write or None). --contract wins; else --draft-contract (used if it exists)."""
    if args.contract:
        return Path(args.contract), None
    if not args.draft_contract:
        raise InputError("--contract is required (or --draft-contract PATH to draft one from the data)")
    d = Path(args.draft_contract)
    if d.is_file():
        return d, None
    if args.verify:
        raise InputError(f"--verify needs the drafted contract, not found: {d}")
    return d, draft_contract(header, body, Path(args.data).name)


def produce(args) -> tuple[dict[str, str], list[dict]]:
    header, body, ragged = load_data(args.data)
    cpath, draft_text = resolve_contract(args, header, body)
    if draft_text is not None:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(draft_text, encoding="utf-8")
        print(f"drafted contract from {Path(args.data).name}: {cpath}")
    args.contract = str(cpath)
    contract, notes = load_contract(cpath)
    fresh = freshness_params(args.freshness_column, args.as_of, args.max_age_days)
    viol, profile, fresh_info = check(contract, notes, header, body, ragged, fresh)
    files = {
        "violations.csv": csv_text(VIOL_FIELDS, viol),
        "profile.csv": csv_text(PROFILE_FIELDS, profile),
        "contract-report.md": render_md(Path(args.contract).name, Path(args.data).name, contract, notes, header,
                                        body, viol, profile, fresh_info, draft=is_draft(cpath)),
    }
    return files, viol


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contract", default="", help="contract CSV (assets/contract-template.csv) or ODCS v3 YAML subset")
    ap.add_argument("--draft-contract", default="", metavar="PATH",
                    help="without --contract: draft a contract from the data to PATH (or use PATH if it exists)")
    ap.add_argument("--data", type=Path, help="dataset CSV with a header row")
    ap.add_argument("--freshness-column", default="", help="date/datetime column for the freshness check")
    ap.add_argument("--as-of", default="", help="as-of date YYYY-MM-DD for the freshness check")
    ap.add_argument("--max-age-days", default="", help="maximum age in days of the newest record")
    ap.add_argument("--out-dir", type=Path, help="directory for violations.csv, profile.csv, contract-report.md")
    ap.add_argument("--verify", type=Path, metavar="FILE", help="re-check FILE against the inputs (exit 0 = match)")
    args = ap.parse_args(argv)
    try:
        if not args.verify and not args.out_dir:
            raise InputError("--out-dir is required")
        files, viol = produce(args)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.verify:
        name = args.verify.name
        if name not in files or not args.verify.is_file():
            print(f"verify: {args.verify} is not a file this skill produces ({', '.join(files)})", file=sys.stderr)
            return 1
        ok = args.verify.read_text(encoding="utf-8") == files[name]
        print(f"verify {name}: {'match' if ok else 'MISMATCH — output does not match the data and contract'}")
        return 0 if ok else 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out_dir / name).write_text(text, encoding="utf-8")
    errors = [v for v in viol if v["severity"] == "error"]
    print(f"verdict: {verdict(viol)}; violations: {len(viol)} ({len(errors)} error)")
    if errors:
        print("gate: error-severity violations in " + ", ".join(sorted({f"{v['column']}:{v['rule']}" for v in errors})),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
