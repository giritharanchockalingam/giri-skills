#!/usr/bin/env python3
"""Audit migrations for tenant isolation basics: tenant_id column, RLS enabled, tenant-leading index.

    python3 -I scripts/tenancy_audit.py --migrations supabase/migrations --out audit.csv --report audit.md \
        [--exempt tenants,plans,profiles]

Reads every .sql file (comments stripped) and, per `create table`, checks:
  has_tenant_id   a `tenant_id` column in the column list
  rls_enabled     `alter table <t> enable row level security`
  tenant_index    an index, primary key or unique constraint whose first column is tenant_id
  policies        number of `create policy … on <t>`
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
TENANT_COL = re.compile(r"(?:^|[\s,(])\"?tenant_id\"?\s+\w", re.I)


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


def audit(files: list[Path], exempt: set[str]) -> list[dict]:
    tables: dict[str, dict] = {}
    rls, idx, pol = set(), set(), {}
    for f in files:
        sql = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        for m in CREATE_TABLE.finditer(sql):
            name = m.group(2).lower()
            body = table_body(sql, m.end() - 1)
            t = tables.setdefault(name, {"table": name, "file": f.name, "has_tenant_id": False, "tenant_index": False})
            t["has_tenant_id"] = t["has_tenant_id"] or bool(TENANT_COL.search(body))
            if any(k.group(1).lower() == "tenant_id" for k in KEY_IN_TABLE.finditer(body)):
                idx.add(name)
        rls |= {m.group(1).lower() for m in ENABLE_RLS.finditer(sql)}
        idx |= {m.group(1).lower() for m in CREATE_INDEX.finditer(sql) if m.group(2).lower() == "tenant_id"}
        for m in CREATE_POLICY.finditer(sql):
            pol[m.group(1).lower()] = pol.get(m.group(1).lower(), 0) + 1
    rows = []
    for name, t in sorted(tables.items()):
        t["rls_enabled"] = name in rls
        t["tenant_index"] = name in idx
        t["policies"] = pol.get(name, 0)
        t["exempt"] = name in exempt
        findings = []
        if not t["has_tenant_id"]:
            findings.append("missing tenant_id")
        if not t["rls_enabled"]:
            findings.append("RLS not enabled")
        if not t["tenant_index"]:
            findings.append("no index leading with tenant_id")
        if t["rls_enabled"] and t["policies"] == 0:
            findings.append("RLS enabled but no policy (table unreachable — intended?)")
        if t["exempt"]:
            findings = [x for x in findings if x not in ("missing tenant_id", "no index leading with tenant_id")]
        t["findings"] = "; ".join(findings)
        t["status"] = "ok" if not findings else "finding"
        rows.append(t)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit migrations for tenant_id, RLS and tenant-leading indexes")
    ap.add_argument("--migrations", required=True, help="directory of .sql files (or one file)")
    ap.add_argument("--exempt", default=DEFAULT_EXEMPT, help=f"comma-separated global tables (default: {DEFAULT_EXEMPT})")
    ap.add_argument("--out", default="audit.csv")
    ap.add_argument("--report", default="audit.md")
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
    rows = audit(files, exempt)
    if not rows:
        die("no `create table` statements found")
    cols = ["table", "file", "has_tenant_id", "rls_enabled", "tenant_index", "policies", "exempt", "status", "findings"]
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
             "## Tables", "", "| Table | tenant_id | RLS | tenant-leading index | Policies | Exempt | Findings |", "|---|---|---|---|---|---|---|"]
    yn = lambda b: "yes" if b else "no"  # noqa: E731
    for r in rows:
        lines.append(f"| `{r['table']}` | {yn(r['has_tenant_id'])} | {yn(r['rls_enabled'])} | {yn(r['tenant_index'])} | "
                     f"{r['policies']} | {yn(r['exempt'])} | {r['findings'] or '—'} |")
    lines += ["", "## Rules", "",
              "- Every tenant-scoped table: `tenant_id not null`, `enable row level security`, ≥1 policy, composite index leading with `tenant_id` (shared/stack-conventions.md).",
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
