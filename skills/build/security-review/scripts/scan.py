#!/usr/bin/env python3
"""Scan a diff or a repo for the stack's security pitfalls; findings feed the reasoning step.

    python3 -I scripts/scan.py --diff change.patch --findings findings.csv --report review.md
    python3 -I scripts/scan.py --target <repo> --findings findings.csv --report review.md
    python3 -I scripts/scan.py --gate findings.csv        # exit 1 if any critical/high finding

Detectors (file:line evidence; secrets are redacted in the evidence column):
  SEC1 action-without-auth      high      "use server" file exporting async functions with no
                                          auth.getUser / getSession / requireUser / requireRole anywhere in the file
  SEC2 raw-sql-interpolation    critical  sql`…${plain}` (a ${helper(x)} call is treated as parameterised),
                                          query(`…${…}`), "select … " + variable
  SEC3 secret-in-code           critical  sk-…, JWT (eyJ….), AWS AKIA… literals
  SEC4 ssrf-user-url            high      fetch(<identifier>) — URL is a variable, not a literal (heuristic)
  SEC5 dangerous-html           medium    dangerouslySetInnerHTML
  SEC6 rls-bypass-in-handler    high      service-role client used in a route handler or server action
With --diff only added lines are scanned (--target adds a full-repo scan) (context lines count for the auth check). Writes
findings.csv (id, category, severity, file, line, evidence, recommendation) and review.md.
Exit 0 after writing (findings or not); the gate is a separate call so an LLM step can reason on
the findings first. Exit 1 on bad input or in --gate mode when critical/high findings exist. Stdlib.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".sql"}
SKIP_DIRS = {"node_modules", ".next", "dist", "build", "coverage", ".git"}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

USE_SERVER = re.compile(r"^\s*['\"]use server['\"]")
EXPORT_FN = re.compile(r"^[ \t]*export\s+(?:default\s+)?async\s+function\b|^[ \t]*export\s+const\s+\w+\s*=\s*async\b")
AUTH_CHECK = re.compile(r"auth\.getUser\(|getSession\(|requireUser\(|requireRole\(|getClaims\(")
RAW_SQL = re.compile(r"sql`[^`]*\$\{\s*[^}(]*\}|\.(?:query|execute|raw|unsafe)\(\s*`[^`]*\$\{|"
                     r"['\"]\s*(?:select|insert|update|delete)\b[^'\"]*['\"]\s*\+\s*[A-Za-z_]", re.I)
SECRETS = [re.compile(r"\bsk-(?:ant-|live_|test_|proj-)?[A-Za-z0-9_-]{16,}"),
           re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),
           re.compile(r"\bAKIA[0-9A-Z]{16}\b")]
FETCH_VAR = re.compile(r"\bfetch\(\s*([A-Za-z_$][\w$.]*)\s*[,)]")
DANGEROUS_HTML = re.compile(r"dangerouslySetInnerHTML")
SERVICE_ROLE = re.compile(r"SUPABASE_SERVICE_ROLE|createServiceClient\(|createAdminClient\(|serviceRoleClient|service_role")
HTTP_EXPORT = re.compile(r"^\s*export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b|"
                         r"^\s*export\s+const\s+(GET|POST|PUT|PATCH|DELETE)\s*=", re.M)
RECOMMEND = {
    "SEC1": "Call requireUser()/requireRole() (or supabase.auth.getUser()) before any work; derive tenant from the session, never from input.",
    "SEC2": "Use parameterised queries (sql`… ${sql(param)}` tagged helper or the query builder); never concatenate user input into SQL.",
    "SEC3": "Remove the literal, rotate the credential, load it from env (Vercel/Supabase secrets) and add a secrets-scan CI step.",
    "SEC4": "Allow-list hosts, build the URL from a constant base + validated path, set a timeout; never fetch a user-supplied URL.",
    "SEC5": "Sanitise with a vetted library or render as text; if HTML is unavoidable, restrict to trusted authors and sanitise server-side.",
    "SEC6": "Use the RLS-scoped user client in request handlers; service-role only in jobs/webhooks after explicit validation.",
}
CATEGORY = {"SEC1": "authz", "SEC2": "injection", "SEC3": "secrets", "SEC4": "ssrf", "SEC5": "xss", "SEC6": "rls-bypass"}
SEVERITY = {"SEC1": "high", "SEC2": "critical", "SEC3": "critical", "SEC4": "high", "SEC5": "medium", "SEC6": "high"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------ inputs

def parse_diff(text: str) -> dict[str, dict]:
    """{path: {"added": [(line_no, text)], "all": [text]}} from a unified diff."""
    files, cur, new_ln = {}, None, 0
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            path = path[2:] if path.startswith("b/") else path
            cur = files.setdefault(path, {"added": [], "all": []}) if path != "/dev/null" else None
            continue
        if raw.startswith("--- ") or raw.startswith("diff ") or raw.startswith("index "):
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_ln = int(m.group(1)) if m else 1
            continue
        if cur is None:
            continue
        if raw.startswith("+"):
            cur["added"].append((new_ln, raw[1:]))
            cur["all"].append(raw[1:])
            new_ln += 1
        elif raw.startswith("-"):
            continue
        else:
            cur["all"].append(raw[1:] if raw.startswith(" ") else raw)
            new_ln += 1
    return files


def walk_repo(root: Path) -> dict[str, dict]:
    files = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in EXTS:
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        files[rel.as_posix()] = {"added": list(enumerate(lines, 1)), "all": lines}
    return files


# ------------------------------------------------------------------ detectors

def redact(s: str) -> str:
    return s[:8] + "…[redacted]" if len(s) > 8 else "…[redacted]"


def is_handler(path: str, full: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (path.startswith("app/") and name.startswith("route.")) or "/actions/" in path or \
        path.startswith("server/actions/") or bool(USE_SERVER.search(full)) or bool(HTTP_EXPORT.search(full))


def scan_file(path: str, info: dict) -> list[dict]:
    out = []
    full = "\n".join(info["all"])
    ext = Path(path).suffix

    def add(rule, ln, evidence):
        out.append({"id": "", "category": CATEGORY[rule], "rule": rule, "severity": SEVERITY[rule], "file": path,
                    "line": ln, "evidence": evidence.strip()[:140], "recommendation": RECOMMEND[rule]})

    server_action = bool(USE_SERVER.search(full)) and not AUTH_CHECK.search(full)
    handler = is_handler(path, full) if ext != ".sql" else False
    for ln, text in info["added"]:
        if server_action and EXPORT_FN.search(text):
            add("SEC1", ln, text)
        if RAW_SQL.search(text):
            add("SEC2", ln, text)
        for rx in SECRETS:
            for m in rx.finditer(text):
                add("SEC3", ln, text.replace(m.group(0), redact(m.group(0))))
        if ext != ".sql":
            m = FETCH_VAR.search(text)
            if m and not m.group(1).startswith("process.env"):
                add("SEC4", ln, text)
            if DANGEROUS_HTML.search(text):
                add("SEC5", ln, text)
            if handler and SERVICE_ROLE.search(text):
                add("SEC6", ln, text)
    return out


# ------------------------------------------------------------------ outputs

def write_outputs(findings: list[dict], fpath: Path, rpath: Path, scope: str, n_files: int) -> None:
    findings.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["file"], f["line"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"F{i:02d}"
    fpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.parent.mkdir(parents=True, exist_ok=True)
    with fpath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "category", "severity", "file", "line", "evidence", "recommendation"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(findings)
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_ORDER}
    gate = "BLOCK" if counts["critical"] or counts["high"] else "MERGE (no critical/high findings from the scanner)"
    lines = [f"# Security scan — {scope}", "",
             f"**{len(findings)} finding(s) across {n_files} file(s): "
             f"{counts['critical']} critical, {counts['high']} high, {counts['medium']} medium, {counts['low']} low. "
             f"Scanner verdict: {gate}.**", "",
             "## Findings", "", "| # | Sev | Category | File:line | Evidence | Recommendation |", "|---|---|---|---|---|---|"]
    for f in findings:
        ev = f["evidence"].replace("|", "\\|")
        lines.append(f"| {f['id']} | {f['severity']} | {f['category']} ({f['rule']}) | `{f['file']}:{f['line']}` | `{ev}` | {f['recommendation']} |")
    if not findings:
        lines.append("| — | — | — | — | no findings | — |")
    lines += ["", "## Surfaces scanned", "", "| Surface | Files |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in surfaces(findings, n_files).items()]
    lines += ["", "## Method and limits", "",
              "- Pattern scan on added lines (diff mode) or all source lines (repo mode); every finding carries file:line.",
              "- Findings are candidates: the review step must trace entry → sink before rating them final.",
              "- SEC1 checks the whole visible file for an auth call; a helper in another file is not seen — confirm manually.",
              "- SEC4 is a heuristic (fetch of a variable); confirm whether the variable is user-controlled.",
              "- Not covered: IDOR, mass assignment, missing RLS policies (run supabase-schema-rls/rls_lint.py), logic flaws."]
    rpath.write_text("\n".join(lines) + "\n", encoding="utf-8")


def surfaces(findings: list[dict], n_files: int) -> dict:
    cats = {}
    for f in findings:
        cats.setdefault(f["category"], set()).add(f["file"])
    out = {"files scanned": n_files}
    for c, fs in sorted(cats.items()):
        out[c] = ", ".join(sorted(fs))
    return out


def gate(fpath: Path) -> int:
    if not fpath.is_file():
        die(f"findings file not found: {fpath}")
    rows = list(csv.DictReader(fpath.open(encoding="utf-8")))
    blocking = [r for r in rows if r.get("severity") in ("critical", "high")]
    if blocking:
        print(f"gate: BLOCK — {len(blocking)} critical/high finding(s):", file=sys.stderr)
        for r in blocking:
            print(f"  {r['id']} {r['severity']} {r['file']}:{r['line']} ({r['category']})", file=sys.stderr)
        return 1
    print(f"gate: pass — {len(rows)} finding(s), none critical/high")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan a diff or repo for stack security pitfalls")
    ap.add_argument("--diff", help="unified diff file (git diff main...HEAD > change.patch)")
    ap.add_argument("--target", help="repo root to scan in full (may be combined with --diff)")
    ap.add_argument("--gate", metavar="FINDINGS_CSV", help="exit 1 if the findings file has critical/high rows")
    ap.add_argument("--findings", default="findings.csv")
    ap.add_argument("--report", default="review.md")
    a = ap.parse_args()
    if a.gate:
        return gate(Path(a.gate))
    if not a.diff and not a.target:
        die("give --diff <patch> and/or --target <repo>")
    files, scopes = {}, []
    if a.diff:
        p = Path(a.diff)
        if not p.is_file():
            die(f"diff not found: {p}")
        files.update(parse_diff(p.read_text(encoding="utf-8", errors="replace")))
        if not files:
            die(f"no file hunks found in {p} (expected a unified diff with +++ b/<path> headers)")
        scopes.append(p.name)
    if a.target:
        root = Path(a.target)
        if not root.is_dir():
            die(f"target is not a directory: {root}")
        repo = walk_repo(root)
        if not repo:
            die(f"no source files under {root}")
        files.update(repo)
        scopes.append(root.name)
    scope = " + ".join(scopes)
    findings = []
    for path, info in files.items():
        if Path(path).suffix in EXTS:
            findings += scan_file(path, info)
    write_outputs(findings, Path(a.findings), Path(a.report), scope, len(files))
    for f in findings:
        print(f"{f['id']} {f['severity']:8} {f['rule']} {f['file']}:{f['line']}")
    print(f"{len(findings)} finding(s) in {len(files)} file(s) -> {a.findings}, {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
