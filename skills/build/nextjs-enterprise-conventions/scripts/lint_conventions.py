#!/usr/bin/env python3
"""Lint a Next.js repo against shared/stack-conventions.md — a real tool that fails CI.

    python3 -I scripts/lint_conventions.py --target <repo> --findings findings.csv --report report.md

Scans .ts/.tsx (skipping node_modules, .next, dist, build, coverage, tests/**) for:
  NX1 supabase-in-component   high    `.from('…')`, `.rpc(`, `createClient(` inside components/ or app/**/page.tsx
  NX2 console-log             medium  `console.log(`
  NX3 action-without-zod      high    "use server" file: exported async function whose body has no `.parse(`/`.safeParse(`
  NX4 service-role-exposed    high    `SUPABASE_SERVICE_ROLE` referenced outside server/, lib/supabase/server*, lib/env.ts
  NX5 raw-sql-outside-lib-db  high    sql`…` outside lib/db/
Writes findings.csv (rule, file, line, snippet, severity, status) and report.md. Exit 1 when any
high-severity finding exists (or on bad input), 0 otherwise. --quiet prints only the summary.

Existing repo (--baseline findings.csv from an earlier run, the recorded debt): a finding whose rule,
file and snippet match a baseline row (line numbers may move) is `known`; anything else is `new`.
The gate then fails only on new high-severity findings — existing debt stays listed, in the report
and the CSV, but no longer blocks unrelated work — and baseline rows no longer found are reported
as resolved. Without --baseline every finding is `new`. Stdlib, offline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".next", "dist", "build", "coverage", ".git", "tests", "test", "__tests__"}
EXTS = {".ts", ".tsx"}
RULES = {
    "NX1": ("supabase-in-component", "high", "No Supabase call outside lib/db or server/services (stack-conventions: Data access)"),
    "NX2": ("console-log", "medium", "Structured logging via lib/logger only; no console.log in committed code"),
    "NX3": ("action-without-zod", "high", "Every server action parses its input with zod before work"),
    "NX4": ("service-role-exposed", "high", "Service-role key only in server-side code; never near the client"),
    "NX5": ("raw-sql-outside-lib-db", "high", "Raw SQL lives in lib/db only"),
}
SUPABASE_CALL = re.compile(r"\.from\(\s*['\"`]|\.rpc\(|\bcreateClient\(")
CONSOLE_LOG = re.compile(r"\bconsole\.log\(")
USE_SERVER = re.compile(r"^\s*['\"]use server['\"]\s*;?\s*$", re.M)
EXPORT_FN = re.compile(r"^[ \t]*export\s+(?:default\s+)?async\s+function\s+(\w+)?\s*\(", re.M)
SERVICE_ROLE = re.compile(r"SUPABASE_SERVICE_ROLE")
SQL_TAG = re.compile(r"\bsql`")
SERVICE_ROLE_OK = ("server/", "lib/supabase/server", "lib/env.ts")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def source_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.suffix not in EXTS or not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        yield p, rel.as_posix()


def is_component_surface(rel: str) -> bool:
    return rel.startswith("components/") or "/components/" in rel or \
        (rel.startswith("app/") and rel.rsplit("/", 1)[-1] in ("page.tsx", "page.ts", "layout.tsx"))


def line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def body_after(text: str, pos: int) -> str:
    """Text of the `{ … }` block that starts at the first `{` after pos (brace-matched)."""
    start = text.find("{", pos)
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def lint_file(text: str, rel: str) -> list[dict]:
    out = []
    lines = text.splitlines()

    def add(rule, ln):
        name, sev, _ = RULES[rule]
        out.append({"rule": rule, "file": rel, "line": ln, "snippet": lines[ln - 1].strip()[:120], "severity": sev})

    if is_component_surface(rel):
        for m in SUPABASE_CALL.finditer(text):
            add("NX1", line_no(text, m.start()))
    for m in CONSOLE_LOG.finditer(text):
        add("NX2", line_no(text, m.start()))
    if USE_SERVER.search(text):
        for m in EXPORT_FN.finditer(text):
            body = body_after(text, m.end())
            if ".parse(" not in body and ".safeParse(" not in body:
                add("NX3", line_no(text, m.start()))
    if not rel.startswith(SERVICE_ROLE_OK):
        for m in SERVICE_ROLE.finditer(text):
            add("NX4", line_no(text, m.start()))
    if not rel.startswith("lib/db/"):
        for m in SQL_TAG.finditer(text):
            add("NX5", line_no(text, m.start()))
    return out


def load_baseline(path: Path) -> list[tuple[str, str, str]]:
    if not path.is_file():
        die(f"baseline not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in ("rule", "file", "snippet") if c not in (reader.fieldnames or [])]
        if missing:
            die(f"baseline lacks column(s) {missing} (expected a findings.csv from this script)")
        return [((r.get("rule") or "").strip(), (r.get("file") or "").strip(), (r.get("snippet") or "").strip())
                for r in reader if (r.get("rule") or "").strip() and not (r.get("rule") or "").startswith("#")]


def apply_baseline(findings: list[dict], baseline: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Mark each finding known/new (one baseline row matches one finding); return the unmatched (resolved) rows."""
    pool = list(baseline)
    for f in findings:
        key = (f["rule"], f["file"], f["snippet"])
        if key in pool:
            pool.remove(key)
            f["status"] = "known"
        else:
            f["status"] = "new"
    return pool


def write_report(path: Path, findings: list[dict], n_files: int, target: Path,
                 resolved: list[tuple[str, str, str]] | None = None) -> None:
    by_rule = {}
    for f in findings:
        by_rule.setdefault(f["rule"], []).append(f)
    high = sum(1 for f in findings if f["severity"] == "high")
    new_high = sum(1 for f in findings if f["severity"] == "high" and f["status"] == "new")
    based = resolved is not None
    head = f"**{len(findings)} finding(s) in {n_files} file(s): {high} high, {len(findings) - high} medium"
    if based:
        known = sum(1 for f in findings if f["status"] == "known")
        head += f"; {len(findings) - known} new, {known} known from the baseline, {len(resolved)} resolved"
    gate = ("Gate: FAIL (new high-severity findings)." if new_high else
            "Gate: PASS (no new high-severity findings; known debt listed below)." if high else "Gate: PASS.") if based \
        else ("Gate: FAIL (high-severity findings)." if high else "Gate: PASS.")
    lines = [f"# Conventions lint — {target.name}", "", head + ".** " + gate, "",
             "## Summary", "", "| Rule | Name | Severity | Count |", "|---|---|---|---|"]
    for rule, (name, sev, _) in RULES.items():
        lines.append(f"| {rule} | {name} | {sev} | {len(by_rule.get(rule, []))} |")
    lines += ["", "## Findings", "", "| Rule | File:line | Severity | Status | Snippet |", "|---|---|---|---|---|"]
    for f in findings:
        snippet = f["snippet"].replace("|", "\\|")
        lines.append(f"| {f['rule']} | `{f['file']}:{f['line']}` | {f['severity']} | {f['status']} | `{snippet}` |")
    if not findings:
        lines.append("| — | — | — | — | no findings |")
    if based:
        lines += ["", "## Baseline", "",
                  "Known findings are recorded debt: fix them in their own PRs and re-record the baseline. Resolved since the baseline:", ""]
        lines += [f"- {r} `{f_}` — {s_}" for r, f_, s_ in resolved] or ["- none"]
    lines += ["", "## Rules", ""]
    for rule, (name, sev, why) in RULES.items():
        lines.append(f"- **{rule} {name}** ({sev}) — {why}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint a Next.js repo against the stack conventions")
    ap.add_argument("--target", required=True, help="repo root")
    ap.add_argument("--findings", default="findings.csv")
    ap.add_argument("--report", default="report.md")
    ap.add_argument("--quiet", action="store_true", help="print only the summary line")
    ap.add_argument("--baseline", default="", help="findings.csv from an earlier run: known debt that does not gate")
    a = ap.parse_args()
    target = Path(a.target)
    if not target.is_dir():
        die(f"target is not a directory: {target}")
    findings, n_files = [], 0
    for p, rel in source_files(target):
        n_files += 1
        findings += lint_file(p.read_text(encoding="utf-8", errors="replace"), rel)
    if n_files == 0:
        die(f"no .ts/.tsx files under {target}")
    findings.sort(key=lambda f: (f["file"], f["line"], f["rule"]))
    resolved = apply_baseline(findings, load_baseline(Path(a.baseline))) if a.baseline else None
    if resolved is None:
        for f in findings:
            f["status"] = "new"
    fp, rp = Path(a.findings), Path(a.report)
    fp.parent.mkdir(parents=True, exist_ok=True)
    rp.parent.mkdir(parents=True, exist_ok=True)
    with fp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["rule", "file", "line", "snippet", "severity", "status"])
        w.writeheader()
        w.writerows(findings)
    write_report(rp, findings, n_files, target, resolved)
    high = [f for f in findings if f["severity"] == "high" and f["status"] == "new"]
    if not a.quiet:
        for f in findings:
            print(f"{f['severity']:6} {f['rule']} {f['file']}:{f['line']}  {f['snippet']}"
                  + ("  (known)" if f["status"] == "known" else ""))
    print(f"{len(findings)} finding(s) in {n_files} file(s); {len(high)} {'new ' if resolved is not None else ''}high -> {fp}, {rp}")
    if high:
        print(f"gate: FAIL — {len(high)} {'new ' if resolved is not None else ''}high-severity finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
