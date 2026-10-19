#!/usr/bin/env python3
"""Audit migrations for tenant isolation basics: tenant_id column, RLS enabled, tenant-leading index.

    python3 -I scripts/tenancy_audit.py --migrations supabase/migrations --out audit.csv --report audit.md \
        [--exempt tenants,plans,profiles] [--rbac rbac-matrix.csv]

Reads every .sql file (comments stripped) and, per `create table`, checks:
  has_tenant_id   a `tenant_id` column in the column list
  rls_enabled     `alter table <t> enable row level security`
  tenant_index    an index, primary key or unique constraint whose first column is tenant_id
  policies        number of `create policy … on <t>`
Files are read in name order, as they are applied, so an existing migration history is audited as the
schema it builds: `alter table <t> add column tenant_id` in a later file counts as the column,
`alter table <t> add [constraint x] primary key|unique (tenant_id, …)` as the tenant-leading key, and a
`drop table <t>` removes the table from the audit; `changed_in` lists the later files that altered it.
--rbac: the RBAC matrix (assets/rbac-matrix.csv layout) is cross-checked against the audited tables —
matrix resources with no table in the migrations, and tenant-scoped tables no matrix row covers — and
reported under "RBAC coverage" (advisory: the gate is the per-table findings).
Tables listed in --exempt (default: tenants, plans, feature_flags, profiles — global by design) are
reported but not counted as findings. Writes audit.csv (table, file, has_tenant_id, rls_enabled,
tenant_index, policies, exempt, status, findings) and audit.md. Exit 1 on bad input or when any
non-exempt table has a finding (a linter: fix the migration, re-run). Stdlib, offline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

DEFAULT_EXEMPT = "tenants,plans,feature_flags,profiles"
CREATE_TABLE = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:(\w+)\.)?\"?(\w+)\"?\s*\(", re.I)
ENABLE_RLS = re.compile(r"alter\s+table\s+(?:only\s+)?(?:\w+\.)?\"?(\w+)\"?\s+enable\s+row\s+level\s+security", re.I)
CREATE_INDEX = re.compile(r"create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?\w*\s*on\s+(?:only\s+)?(?:\w+\.)?\"?(\w+)\"?\s*(?:using\s+\w+\s*)?\(\s*\"?(\w+)", re.I)
CREATE_POLICY = re.compile(r"create\s+policy\s+\"?[\w-]+\"?\s+on\s+(?:\w+\.)?\"?(\w+)\"?", re.I)
KEY_IN_TABLE = re.compile(r"(?:primary\s+key|unique)\s*\(\s*\"?(\w+)", re.I)
ALTER_ADD_KEY = re.compile(r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:\w+\.)?\"?(\w+)\"?\s+add\s+(?:constraint\s+\"?[\w-]+\"?\s+)?(?:primary\s+key|unique)\s*\(\s*\"?(\w+)", re.I)
ALTER_ANY = re.compile(r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:\w+\.)?\"?(\w+)\"?", re.I)
DROP_TABLE = re.compile(r"drop\s+table\s+(?:if\s+exists\s+)?((?:(?:\w+\.)?\"?\w+\"?\s*,\s*)*(?:\w+\.)?\"?\w+\"?)", re.I)
TENANT_CANDIDATES = ("tenant_id", "workspace_id", "organization_id", "org_id", "account_id", "team_id")


def tenant_col_re(col: str) -> re.Pattern:
    return re.compile(r"(?:^|[\s,(])\"?" + re.escape(col) + r"\"?\s+\w", re.I)


def alter_add_col_re(col: str) -> re.Pattern:
    return re.compile(r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:\w+\.)?\"?(\w+)\"?\s+add\s+(?:column\s+)?(?:if\s+not\s+exists\s+)?\"?"
                      + re.escape(col) + r"\"?\s+\w", re.I)


def inline_key_re(col: str) -> re.Pattern:
    """`<col> uuid primary key` / `<col> uuid not null unique …` declared on the column itself."""
    return re.compile(r"(?:^|[\s,(])\"?" + re.escape(col) + r"\"?\s+[\w ()]*?\b(?:primary\s+key|unique)\b", re.I)


def tenant_root(col: str) -> str:
    """workspace_id → workspaces: the tenant table itself, which cannot carry its own tenant key."""
    base = col[:-3] if col.lower().endswith("_id") else col
    return (base + "es" if base.endswith("s") else base + "s").lower()


def detect_tenant_column(files: list[Path]) -> str:
    """The tenancy key this schema actually uses: the candidate column found in the most `create table` bodies
    (ties and no match fall back to tenant_id). Evidence-based, never guessed from names alone."""
    counts = {c: 0 for c in TENANT_CANDIDATES}
    for f in files:
        sql = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        for m in CREATE_TABLE.finditer(sql):
            body = table_body(sql, m.end() - 1)
            for c in TENANT_CANDIDATES:
                if tenant_col_re(c).search(body):
                    counts[c] += 1
    best = max(TENANT_CANDIDATES, key=lambda c: (counts[c], c == "tenant_id"))
    return best if counts[best] > 0 else "tenant_id"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", "", sql)


def table_body(sql: str, start: int) -> str:
    depth, i = 0, start
    while i < len(sql):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[start:i + 1]
        i += 1
    return sql[start:]


def audit(files: list[Path], exempt: set[str], col: str = "tenant_id") -> list[dict]:
    """Replay the migrations in order; one row per table that still exists at the end. `col` is the tenancy key."""
    col_l, TENANT_COL, ALTER_ADD_TENANT = col.lower(), tenant_col_re(col), alter_add_col_re(col)
    tables: dict[str, dict] = {}
    rls, idx, pol = set(), set(), {}
    for f in files:
        sql = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        events = [(m.start(), "create", m) for m in CREATE_TABLE.finditer(sql)]
        events += [(m.start(), "drop", m) for m in DROP_TABLE.finditer(sql)]
        for _, kind, m in sorted(events, key=lambda e: e[0]):
            if kind == "drop":
                for raw in m.group(1).split(","):
                    name = raw.strip().split(".")[-1].strip('"').lower()
                    tables.pop(name, None)
                    rls.discard(name)
                    idx.discard(name)
                    pol.pop(name, None)
                continue
            name = m.group(2).lower()
            body = table_body(sql, m.end() - 1)
            t = tables.setdefault(name, {"table": name, "file": f.name, "has_tenant_id": False, "tenant_index": False,
                                         "changed_in": []})
            t["has_tenant_id"] = t["has_tenant_id"] or bool(TENANT_COL.search(body))
            if any(k.group(1).lower() == col_l for k in KEY_IN_TABLE.finditer(body)) or inline_key_re(col).search(body):
                idx.add(name)
        for m in ALTER_ADD_TENANT.finditer(sql):
            if m.group(1).lower() in tables:
                tables[m.group(1).lower()]["has_tenant_id"] = True
        idx |= {m.group(1).lower() for m in ALTER_ADD_KEY.finditer(sql) if m.group(2).lower() == col_l}
        for m in ALTER_ANY.finditer(sql):
            t = tables.get(m.group(1).lower())
            if t and t["file"] != f.name and f.name not in t["changed_in"]:
                t["changed_in"].append(f.name)
        rls |= {m.group(1).lower() for m in ENABLE_RLS.finditer(sql)}
        idx |= {m.group(1).lower() for m in CREATE_INDEX.finditer(sql) if m.group(2).lower() == col_l}
        for m in CREATE_POLICY.finditer(sql):
            pol[m.group(1).lower()] = pol.get(m.group(1).lower(), 0) + 1
    rows = []
    for name, t in sorted(tables.items()):
        t["changed_in"] = ";".join(t["changed_in"])
        t["rls_enabled"] = name in rls
        t["tenant_index"] = name in idx
        t["policies"] = pol.get(name, 0)
        root = tenant_root(col)
        t["exempt"] = name in exempt or name == root or name.endswith("_" + root)
        findings = []
        if not t["has_tenant_id"]:
            findings.append(f"missing {col}")
        if not t["rls_enabled"]:
            findings.append("RLS not enabled")
        if not t["tenant_index"]:
            findings.append(f"no index leading with {col}")
        if t["rls_enabled"] and t["policies"] == 0:
            findings.append("RLS enabled but no policy (table unreachable — intended?)")
        if t["exempt"]:
            findings = [x for x in findings if x not in (f"missing {col}", f"no index leading with {col}")]
        t["findings"] = "; ".join(findings)
        t["status"] = "ok" if not findings else "finding"
        rows.append(t)
    return rows


def rbac_coverage(path: Path, rows: list[dict]) -> dict:
    """Matrix resources without a table, and tenant-scoped tables without a matrix row."""
    if not path.is_file():
        die(f"rbac matrix not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if "resource" not in (reader.fieldnames or []):
            die(f"rbac matrix has no 'resource' column: {path}")
        resources = sorted({(r.get("resource") or "").strip().split(".")[-1].lower() for r in reader
                            if (r.get("resource") or "").strip() and not (r.get("action") or "").startswith("#")})
    tables = {r["table"] for r in rows}
    scoped = sorted(r["table"] for r in rows if not r["exempt"])
    return {"matrix": path.name, "resources": resources,
            "resources_without_table": [x for x in resources if x not in tables],
            "tables_without_rbac": [t for t in scoped if t not in resources]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit migrations for tenant_id, RLS and tenant-leading indexes")
    ap.add_argument("--migrations", required=True, help="directory of .sql files (or one file)")
    ap.add_argument("--exempt", default=DEFAULT_EXEMPT, help=f"comma-separated global tables (default: {DEFAULT_EXEMPT})")
    ap.add_argument("--out", default="audit.csv")
    ap.add_argument("--report", default="audit.md")
    ap.add_argument("--rbac", default="", help="RBAC matrix CSV to cross-check against the audited tables")
    ap.add_argument("--tenant-column", default="tenant_id",
                    help=f"the tenancy key column (default tenant_id); 'auto' picks the one the schema uses among {', '.join(TENANT_CANDIDATES)}")
    a = ap.parse_args()
    src = Path(a.migrations)
    if src.is_file():
        files = [src]
    elif src.is_dir():
        files = sorted(src.rglob("*.sql"))
    else:
        die(f"migrations not found: {src}")
    if not files:
        die(f"no .sql files under {src}")
    exempt = {x.strip().lower() for x in a.exempt.split(",") if x.strip()}
    col = a.tenant_column.strip()
    if col == "auto":
        col = detect_tenant_column(files)
    elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", col):
        die(f"bad --tenant-column: {col}")
    rows = audit(files, exempt, col)
    if not rows:
        die("no `create table` statements found")
    cov = rbac_coverage(Path(a.rbac), rows) if a.rbac else None
    cols = ["table", "file", "has_tenant_id", "rls_enabled", "tenant_index", "policies", "exempt", "status", "findings",
            "changed_in"]
    out, rep = Path(a.out), Path(a.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    rep.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (str(v).lower() if isinstance(v, bool) else v) for k, v in r.items()})
    bad = [r for r in rows if r["status"] == "finding"]
    lines = [f"# Tenancy audit — {src.name}", "",
             f"**{len(rows)} table(s) in {len(files)} migration file(s): {len(bad)} with findings. "
             + ("Gate: FAIL." if bad else "Gate: PASS.") + "**", "",
             f"Tenancy key: `{col}`" + (" (detected from the schema)" if a.tenant_column == "auto" else "") + ".", "",
             "## Tables", "", f"| Table | {col} | RLS | tenant-leading index | Policies | Exempt | Findings |", "|---|---|---|---|---|---|---|"]
    yn = lambda b: "yes" if b else "no"  # noqa: E731
    for r in rows:
        lines.append(f"| `{r['table']}` | {yn(r['has_tenant_id'])} | {yn(r['rls_enabled'])} | {yn(r['tenant_index'])} | "
                     f"{r['policies']} | {yn(r['exempt'])} | {r['findings'] or '—'} |")
    altered = [r for r in rows if r["changed_in"]]
    if altered:
        lines += ["", "## Altered by later migrations", ""]
        lines += [f"- `{r['table']}` — created in `{r['file']}`, altered in {', '.join(f'`{x}`' for x in r['changed_in'].split(';'))}"
                  for r in altered]
    if cov is not None:
        lines += ["", "## RBAC coverage", "", f"Matrix `{cov['matrix']}`: {len(cov['resources'])} resource(s).", ""]
        lines += [f"- `{x}` is in the matrix but no migration creates it — add the table or drop the rows"
                  for x in cov["resources_without_table"]]
        lines += [f"- `{t}` is tenant-scoped but no matrix row covers it — add its actions before generating policies"
                  for t in cov["tables_without_rbac"]]
        if not cov["resources_without_table"] and not cov["tables_without_rbac"]:
            lines.append("- every matrix resource has a table and every tenant-scoped table has matrix rows")
    lines += ["", "## Rules", "",
              f"- Every tenant-scoped table: `{col} not null`, `enable row level security`, ≥1 policy, composite index leading with `{col}` (shared/stack-conventions.md).",
              f"- Exempt (global) tables: {', '.join(sorted(exempt)) or 'none'} — still need RLS and a policy.",
              "- Hand findings to supabase-schema-rls for the migration; never edit an applied migration."]
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for r in bad:
        print(f"finding  {r['table']} ({r['file']}): {r['findings']}")
    print(f"{len(rows)} table(s), {len(bad)} with findings -> {out}, {rep}")
    if bad:
        print(f"gate: FAIL — {len(bad)} table(s) need tenancy fixes", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
