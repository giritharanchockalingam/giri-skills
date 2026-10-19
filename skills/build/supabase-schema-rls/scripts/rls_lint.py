#!/usr/bin/env python3
"""rls_lint.py — offline linter for Supabase migrations and client code.

Checks (all static, stdlib only; run with: python3 -I rls_lint.py supabase/migrations):
  RLS001  table created without `enable row level security` anywhere in the migration set
  RLS002  table has RLS enabled but zero policies — unless a migration acknowledges it as intentional with
          `-- rls-lint: deny-all <schema.>table <reason>` (server-only tables; the reason is required)
  RLS003  policy on a tenant-scoped table (has tenant_id column) whose predicate lacks `tenant_id`
  RLS004  insert/update policy without `with check`
  RLS005  policy granted `to public` (or no `to` clause → defaults to public)
  RLS006  `security definer` function without `set search_path`
  RLS007  migration file without a `-- rollback:` block
  RLS008  policy reads claims from `user_metadata` (user-editable)
  RLS009  service-role usage in client directories (--client-dirs)
  RLS010  `using (true)` on a non-select policy, or on select without `to anon` being intentional (warn)

Existing migration history: files are replayed in name order, as they are applied — `drop policy`
withdraws the findings of the policy it drops (the replaced policy is judged, not the old one), `drop
table` removes the table, and `alter table … add column tenant_id` makes a table tenant-scoped.
--applied-through <file>: migrations up to and including that file name are already applied; RLS007
is not raised for them (an applied migration is never edited, so its missing rollback cannot be fixed
there) — every other finding still stands, because it describes the schema as it is.

Exit 1 if any error-level finding. Use --warn-only to downgrade everything to warnings.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

CREATE_TABLE_RE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:(?P<schema>\w+)\.)?\"?(?P<name>\w+)\"?\s*\((?P<body>.*?)\)\s*;",
    re.I | re.S,
)
ENABLE_RLS_RE = re.compile(
    r"alter\s+table\s+(?:only\s+)?(?:(?P<schema>\w+)\.)?\"?(?P<name>\w+)\"?\s+enable\s+row\s+level\s+security",
    re.I,
)
POLICY_RE = re.compile(
    r"create\s+policy\s+\"?(?P<pname>\w+)\"?\s+on\s+(?:(?P<schema>\w+)\.)?\"?(?P<table>\w+)\"?"
    r"(?P<rest>.*?);",
    re.I | re.S,
)
FOR_RE = re.compile(r"\bfor\s+(select|insert|update|delete|all)\b", re.I)
TO_RE = re.compile(r"\bto\s+((?:\w+\s*,\s*)*\w+)", re.I)
USING_RE = re.compile(r"\busing\s*\(", re.I)
WITH_CHECK_RE = re.compile(r"\bwith\s+check\s*\(", re.I)
SECDEF_FN_RE = re.compile(
    r"create\s+(?:or\s+replace\s+)?function\s+(?P<fn>[\w.\"]+)\s*\(.*?\)(?P<tail>.*?)(?:\$\$|\bas\s+')",
    re.I | re.S,
)
ROLLBACK_RE = re.compile(r"^\s*--\s*rollback:", re.I | re.M)
USER_META_RE = re.compile(r"user_metadata", re.I)
USING_TRUE_RE = re.compile(r"\busing\s*\(\s*true\s*\)", re.I)
SERVICE_ROLE_RE = re.compile(
    r"SUPABASE_SERVICE_ROLE_KEY|service_role|serviceRoleKey|createAdminClient|supabaseAdmin",
)
DROP_POLICY_RE = re.compile(
    r"drop\s+policy\s+(?:if\s+exists\s+)?\"?(?P<pname>\w+)\"?\s+on\s+(?:(?P<schema>\w+)\.)?\"?(?P<table>\w+)\"?",
    re.I,
)
DROP_TABLE_RE = re.compile(
    r"drop\s+table\s+(?:if\s+exists\s+)?(?P<names>(?:(?:\w+\.)?\"?\w+\"?\s*,\s*)*(?:\w+\.)?\"?\w+\"?)",
    re.I,
)
COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)

IGNORE_TABLES = {"schema_migrations", "supabase_migrations"}


@dataclass
class Finding:
    code: str
    level: str  # error | warn
    file: str
    line: int
    msg: str


@dataclass
class Table:
    name: str
    schema: str
    file: str
    line: int
    tenant_scoped: bool
    rls_enabled: bool = False
    policies: list = field(default_factory=list)


DENY_ALL_ACK_RE = re.compile(r"--[ \t]*rls-lint:[ \t]*deny-all[ \t]+(?:(?P<schema>\w+)\.)?(?P<table>\w+)[ \t]+[^\s][^\n]{2,}", re.I)   # reason on the same line


def strip_comments(sql: str) -> str:
    # keep newlines so line numbers hold
    return COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), sql)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _key(schema, name) -> str:
    return f"{(schema or 'public').lower()}.{name.lower()}"


def lint_migrations(mig_dir: Path, findings: list[Finding], applied_through: str = "") -> None:
    files = [mig_dir] if mig_dir.is_file() else sorted(mig_dir.glob("*.sql"))
    if not files:
        findings.append(Finding("RLS000", "warn", str(mig_dir), 0, "no .sql migrations found"))
        return

    tables: dict[str, Table] = {}
    all_sql: list[tuple[Path, str]] = []
    deny_all_ok: set[str] = set()   # tables a migration explicitly acknowledges as deny-all (server-only), with a reason

    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        applied = bool(applied_through) and f.name <= applied_through
        if not ROLLBACK_RE.search(raw) and not applied:
            findings.append(Finding("RLS007", "error", str(f), 1, "missing `-- rollback:` block"))
        for m in DENY_ALL_ACK_RE.finditer(raw):
            deny_all_ok.add(f"{(m.group('schema') or 'public').lower()}.{m.group('table').lower()}")
        sql = strip_comments(raw)
        all_sql.append((f, sql))
        events = [(m.start(), "create", m) for m in CREATE_TABLE_RE.finditer(sql)]
        events += [(m.start(), "drop", m) for m in DROP_TABLE_RE.finditer(sql)]
        for _, kind, m in sorted(events, key=lambda e: e[0]):
            if kind == "drop":
                for raw_name in m.group("names").split(","):
                    parts = raw_name.strip().replace('"', "").split(".")
                    tables.pop(_key(parts[0] if len(parts) == 2 else None, parts[-1]), None)
                continue
            name = m.group("name").lower()
            if name in IGNORE_TABLES:
                continue
            schema = (m.group("schema") or "public").lower()
            body = m.group("body").lower()
            tenant_scoped = bool(re.search(r"\btenant_id\b", body))
            tables[f"{schema}.{name}"] = Table(name, schema, str(f), line_of(sql, m.start()), tenant_scoped)
        # columns added later
        for m in re.finditer(r"alter\s+table\s+(?:only\s+)?(?:(\w+)\.)?\"?(\w+)\"?\s+add\s+(?:column\s+)?(?:if\s+not\s+exists\s+)?\"?tenant_id\"?", sql, re.I):
            key = f"{(m.group(1) or 'public').lower()}.{m.group(2).lower()}"
            if key in tables:
                tables[key].tenant_scoped = True

    pending: dict[tuple[str, str], list[Finding]] = {}   # (table, policy) -> its findings, withdrawn on drop policy
    for f, sql in all_sql:
        for m in ENABLE_RLS_RE.finditer(sql):
            key = f"{(m.group('schema') or 'public').lower()}.{m.group('name').lower()}"
            if key in tables:
                tables[key].rls_enabled = True
            elif m.group("schema") is None or m.group("schema").lower() == "public":
                # table created outside this migration set; still fine
                tables.setdefault(key, Table(m.group("name").lower(), "public", str(f), line_of(sql, m.start()), False)).rls_enabled = True

        events = [(m.start(), "create", m) for m in POLICY_RE.finditer(sql)]
        events += [(m.start(), "drop", m) for m in DROP_POLICY_RE.finditer(sql)]
        events += [(m.start(), "drop_table", m) for m in DROP_TABLE_RE.finditer(sql)]
        for _, kind, m in sorted(events, key=lambda e: e[0]):
            if kind == "drop_table":                # its policies go with it: withdraw their findings
                for raw_name in m.group("names").split(","):
                    parts = raw_name.strip().replace('"', "").split(".")
                    gone = _key(parts[0] if len(parts) == 2 else None, parts[-1])
                    for pk in [pk for pk in pending if pk[0] == gone]:
                        for fd in pending.pop(pk):
                            findings.remove(fd)
                        if gone in tables and pk[1] in tables[gone].policies:
                            tables[gone].policies.remove(pk[1])   # a re-created table starts without them
                continue
            key = f"{(m.group('schema') or 'public').lower()}.{m.group('table').lower()}"
            if kind == "drop":
                pname = m.group("pname")
                for fd in pending.pop((key, pname), []):
                    findings.remove(fd)
                if key in tables and pname in tables[key].policies:
                    tables[key].policies.remove(pname)
                continue
            before = len(findings)
            rest = m.group("rest")
            ln = line_of(sql, m.start())
            op = (FOR_RE.search(rest).group(1).lower() if FOR_RE.search(rest) else "all")
            to = TO_RE.search(rest)
            roles = [r.strip().lower() for r in to.group(1).split(",")] if to else ["public"]
            has_using = bool(USING_RE.search(rest))
            has_check = bool(WITH_CHECK_RE.search(rest))
            tbl = tables.get(key)
            if tbl is not None:
                tbl.policies.append(m.group("pname"))
            if "public" in roles:
                findings.append(Finding("RLS005", "error", str(f), ln, f"policy {m.group('pname')} applies `to public` (name roles: authenticated / anon)"))
            if op in ("insert", "update", "all") and not has_check:
                findings.append(Finding("RLS004", "error", str(f), ln, f"policy {m.group('pname')} ({op}) lacks `with check`"))
            if tbl is not None and tbl.tenant_scoped and tbl.schema == "public" and not re.search(r"\btenant_id\b", rest, re.I):
                findings.append(Finding("RLS003", "error", str(f), ln, f"policy {m.group('pname')} on tenant table {key} has no tenant_id predicate"))
            if USER_META_RE.search(rest):
                findings.append(Finding("RLS008", "error", str(f), ln, f"policy {m.group('pname')} reads user_metadata (user-editable); use app_metadata"))
            if USING_TRUE_RE.search(rest):
                lvl = "warn" if op == "select" else "error"
                findings.append(Finding("RLS010", lvl, str(f), ln, f"policy {m.group('pname')} uses `using (true)` on {op}"))
            pending[(key, m.group("pname"))] = pending.get((key, m.group("pname")), []) + findings[before:]

        for m in SECDEF_FN_RE.finditer(sql):
            tail = m.group("tail")
            if re.search(r"security\s+definer", tail, re.I) and not re.search(r"set\s+search_path", tail, re.I):
                findings.append(Finding("RLS006", "error", str(f), line_of(sql, m.start()), f"security definer function {m.group('fn')} without `set search_path`"))

    for key, t in tables.items():
        if t.schema != "public":
            continue
        if not t.rls_enabled:
            findings.append(Finding("RLS001", "error", t.file, t.line, f"table {key} created without `enable row level security`"))
        elif not t.policies and key not in deny_all_ok:
            findings.append(Finding("RLS002", "error", t.file, t.line, f"table {key} has RLS enabled but no policies (deny-all; if intentional add `-- rls-lint: deny-all {key} <reason>`)"))


def lint_client_dirs(paths: list[str], root: Path, findings: list[Finding]) -> None:
    exts = {".ts", ".tsx", ".js", ".jsx", ".mjs"}
    for p in paths:
        base = root / p
        if not base.exists():
            continue
        files = [base] if base.is_file() else [x for x in base.rglob("*") if x.suffix in exts]
        for f in files:
            if "node_modules" in f.parts or ".next" in f.parts:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if SERVICE_ROLE_RE.search(line) and "// rls-lint: allow" not in line:
                    findings.append(Finding("RLS009", "error", str(f), i, "service-role reference in client-side directory"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline RLS linter for Supabase migrations.")
    ap.add_argument("migrations", nargs="?", default="supabase/migrations", help="migrations directory, or a single .sql file")
    ap.add_argument("--client-dirs", nargs="*", default=[], help="dirs/files that must not reference service role (e.g. app components)")
    ap.add_argument("--root", default=".", help="repo root for --client-dirs")
    ap.add_argument("--warn-only", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="print only the summary line")
    ap.add_argument("--applied-through", default="", metavar="FILE",
                    help="migration file name up to which the history is already applied (no RLS007 for those)")
    args = ap.parse_args()

    findings: list[Finding] = []
    mig = Path(args.migrations)
    if not (mig.is_dir() or (mig.is_file() and mig.suffix.lower() == ".sql")):
        print(f"error: not a migrations directory or a .sql file: {mig}", file=sys.stderr)
        return 2
    lint_migrations(mig, findings, Path(args.applied_through).name if args.applied_through else "")
    lint_client_dirs(args.client_dirs, Path(args.root), findings)

    findings.sort(key=lambda x: (x.file, x.line, x.code))
    errors = 0
    for fd in findings:
        lvl = "warn" if args.warn_only else fd.level
        if lvl == "error":
            errors += 1
        if not args.quiet:
            print(f"{fd.file}:{fd.line}: {lvl.upper()} {fd.code} {fd.msg}")
    print(f"rls_lint: {len(findings)} findings, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
