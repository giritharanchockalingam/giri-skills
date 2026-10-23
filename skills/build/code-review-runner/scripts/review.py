#!/usr/bin/env python3
"""Deterministic first-pass code review of a unified diff (added lines only).

    python3 -I scripts/review.py --diff change.patch [--rules rules.csv] --json review.json --md review.md
    python3 -I scripts/review.py --gate review.json     # exit 1 if any blocking finding

The review covers the Standards axis of the vendored code-review method with fixed detectors;
the Spec axis needs a spec and judgement, so it is left to the optional LLM step.

Detectors (rule id · default severity), run on ADDED lines only:
  CR-SECRET      blocking  key/token literals (AWS, GitHub, Slack, Stripe, Google, private key, JWT,
                           `password|secret|token|api_key = "<literal>"`) and high-entropy string literals
  CR-EVAL        blocking  eval( / exec( / new Function(
  CR-TLS         blocking  disabled TLS verification (verify=False, rejectUnauthorized: false, CERT_NONE,
                           NODE_TLS_REJECT_UNAUTHORIZED=0, InsecureSkipVerify: true, curl -k/--insecure)
  CR-SQL-CONCAT  blocking  SQL text built by + concatenation, f-string, ${} template, % or .format()
  CR-SWALLOW     warning   broad exception swallowed (except: pass, except Exception: pass, empty catch {})
  CR-DEBUG       warning   console.log/debug, debugger, print( (non-test .py), pdb/breakpoint(),
                           System.out.println
  CR-TODO        info      TODO/FIXME/XXX/HACK without an owner: TODO(name), TODO @name, TODO [ABC-12], TODO(#12)
  CR-DUP         info      the same block of >= 3 non-trivial added lines appears more than once
                           (the Duplicated Code smell from the upstream baseline, as a labelled heuristic)
  CR-NO-TESTS    warning   source files changed but no test file changed
Severities: blocking | warning | info. A rules CSV (rule_id,pattern,severity,message,file_glob) adds
custom regex rules; a row whose rule_id is a built-in id and whose pattern is empty overrides that
rule's severity (`off` disables it). Thresholds are CLI options, not facts: --entropy (bits/char,
default 4.0) and --min-secret-len (default 20) tune the high-entropy detector; --large-change
(default 400 changed lines) only labels the size.

Exit codes: 0 no blocking finding · 1 blocking finding(s) (outputs still written) or --gate failed ·
2 missing/invalid input. Stdlib only; writes only --json / --md.
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import math
import re
import sys
from pathlib import Path

SEVERITIES = ("blocking", "warning", "info")
SEV_ORDER = {s: i for i, s in enumerate(SEVERITIES)}

CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt", ".go", ".rb", ".php", ".cs",
            ".scala", ".rs", ".swift", ".sql", ".sh"}
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|"
                       r"\.(test|spec)\.[jt]sx?$|Tests?\.(java|kt|cs)$|(^|/)conftest\.py$")
RISKY_PATH = re.compile(r"auth|login|session|permission|rbac|policy|migration|security|crypto|payment|"
                        r"(^|/)\.env|Dockerfile|\.github/workflows|terraform|\.tf$|settings\.py$|config", re.I)

SECRET_PATTERNS = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{16,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("credential assignment", re.compile(
        r"(?i)\b\w*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token)"
        r"\w*\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']")),
]
# Values that are plainly not credentials: templates, env lookups, and the words tests and docs use for a stand-in
# ("placeholder", "[redacted]", "test-token", "fake", "sample", "secret" by itself, a single character).
PLACEHOLDER = re.compile(r"(?i)^(?:<[^>]+>|\$\{[^}]+\}|x{4,}|\*{4,}|your[_-]|example|placeholder|changeme$|dummy|"
                         r"process\.env|os\.environ|getenv|\[?redacted\]?$|\[[a-z _-]+\]$|(?:test|fake|sample|mock|stub)[_-]?|"
                         r"(?:secret|token|key|password|pass)$|.{0,2}$)")
STRING_LIT = re.compile(r"[\"']([A-Za-z0-9+/=_\-]{16,})[\"']")
EVAL = re.compile(r"(?<![.\w])(?:eval|exec)\s*\(|\bnew\s+Function\s*\(")
TLS = re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=?\s*[\"']?0|"
                 r"InsecureSkipVerify\s*:\s*true|CERT_NONE|_create_unverified_context|\bcurl\b[^\n]*\s(?:-k|--insecure)\b|"
                 r"setHostnameVerifier\([^)]*ALLOW_ALL|TrustAllCerts|check_hostname\s*=\s*False", re.I)
SQL_KW = re.compile(r"(?i)[\"'`f][^\"'`]*\b(?:select\b[^\"'`]*\bfrom|insert\s+into|update\s+\w+\s+set|delete\s+from)\b")
SQL_BUILD = re.compile(r"(?:[\"'`]\s*\+\s*[A-Za-z_(])|(?:[A-Za-z_)\]]\s*\+\s*[\"'`])|(?<![\w])f[\"']|\$\{|"
                       r"[\"']\s*%\s*[\w(]|\.format\(")
SWALLOW_INLINE = re.compile(r"^\s*except(?:\s+(?:Exception|BaseException)(?:\s+as\s+\w+)?)?\s*:\s*(?:pass|\.\.\.)\s*(?:#.*)?$|"
                            r"catch\s*(?:\(\s*\w*(?:\s*:\s*\w+)?\s*\))?\s*\{\s*\}|"
                            r"catch\s*\(\s*(?:final\s+)?(?:Exception|Throwable|RuntimeException)\s+\w+\s*\)\s*\{\s*\}")
SWALLOW_HEAD = re.compile(r"^\s*except(?:\s+(?:Exception|BaseException)(?:\s+as\s+\w+)?)?\s*:\s*(?:#.*)?$")
SWALLOW_BODY = re.compile(r"^\s*(?:pass|\.\.\.)\s*(?:#.*)?$")
DEBUG_JS = re.compile(r"\bconsole\.(?:log|debug|trace)\s*\(|^\s*debugger\s*;?\s*$")
DEBUG_PY = re.compile(r"^\s*print\s*\(|\bpdb\.set_trace\s*\(|^\s*breakpoint\s*\(\s*\)|\bimport\s+pdb\b")
DEBUG_JAVA = re.compile(r"\bSystem\.(?:out|err)\.print(?:ln)?\s*\(|\.printStackTrace\s*\(\s*\)")
TODO = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b(?!\s*(?:\(\s*[@#]?[\w.-]+\s*\)|@\w|\[\s*[A-Z][A-Z0-9]+-\d+\s*\]|:\s*@\w))")

BUILTIN = {
    "CR-SECRET": ("blocking", "Hard-coded secret or high-entropy literal", "Move it to a secret store / env var and rotate it; it is now in history."),
    "CR-EVAL": ("blocking", "Dynamic code execution (eval/exec/new Function)", "Replace with an explicit parser or dispatch table."),
    "CR-TLS": ("blocking", "TLS certificate verification disabled", "Keep verification on; pin or install the CA instead."),
    "CR-SQL-CONCAT": ("blocking", "SQL built by string concatenation/interpolation", "Use parameterised queries / bound parameters."),
    "CR-SWALLOW": ("warning", "Broad exception swallowed", "Catch the specific exception and log or re-raise it."),
    "CR-DEBUG": ("warning", "Debug leftover", "Remove it or route through the project logger."),
    "CR-TODO": ("info", "TODO/FIXME without an owner", "Add an owner or ticket: TODO(name) or TODO [ABC-123]."),
    "CR-DUP": ("info", "Possible Duplicated Code (judgement call)", "Extract the shared block if the duplication is real."),
    "CR-NO-TESTS": ("warning", "Source changed with no test changes", "Add or update tests covering the change."),
}


# ------------------------------------------------------------------ diff parsing

def parse_diff(text: str) -> list[dict]:
    """Return [{path, old_path, status, hunks, added:[(line, text)], removed:int}]."""
    files, cur, new_line = [], None, 0
    old_path = None
    for raw in text.splitlines():
        if raw.startswith("diff --git"):
            cur = None
            old_path = None
            continue
        if raw.startswith("--- "):
            old_path = re.sub(r"^[ab]/", "", raw[4:].strip().split("\t")[0])
            continue
        if raw.startswith("+++ "):
            p = re.sub(r"^[ab]/", "", raw[4:].strip().split("\t")[0])
            status = "added" if old_path == "/dev/null" else ("deleted" if p == "/dev/null" else "modified")
            cur = {"path": old_path if p == "/dev/null" else p, "status": status, "hunks": 0, "added": [], "removed": 0}
            files.append(cur)
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
        if m and cur is not None:
            cur["hunks"] += 1
            new_line = int(m[1])
            continue
        if cur is None or cur["hunks"] == 0:
            continue
        if raw.startswith("+"):
            cur["added"].append((new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-"):
            cur["removed"] += 1
        elif raw.startswith(" ") or raw == "":
            new_line += 1
    return files


def shannon(s: str) -> float:
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    return -sum(n / len(s) * math.log2(n / len(s)) for n in counts.values())


def redact(text: str, secret: str) -> str:
    keep = secret[:4] if len(secret) > 8 else ""
    return text.replace(secret, f"{keep}[redacted]").strip()[:160]


def is_test(path: str) -> bool:
    return bool(TEST_PATH.search(path))


def is_code(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXT


# ------------------------------------------------------------------ detectors

def detect(files: list[dict], entropy: float, min_len: int) -> list[dict]:
    out = []

    def add(rule, f, line, evidence, detail=""):
        out.append({"rule": rule, "file": f["path"], "line": line, "evidence": evidence.strip()[:160],
                    "detail": detail})

    for f in files:
        path, ext, test = f["path"], Path(f["path"]).suffix.lower(), is_test(f["path"])
        added = f["added"]
        for idx, (ln, text) in enumerate(added):
            hit_secret = False
            for label, rx in SECRET_PATTERNS:
                m = rx.search(text)
                if not m:
                    continue
                val = m.group(1) if m.groups() else m.group(0)
                if label == "credential assignment" and PLACEHOLDER.search(val):
                    continue
                add("CR-SECRET", f, ln, redact(text, val), label)
                hit_secret = True
                break
            if not hit_secret:
                for m in STRING_LIT.finditer(text):
                    s = m.group(1)
                    if len(s) >= min_len and shannon(s) >= entropy and not PLACEHOLDER.search(s) \
                            and not re.fullmatch(r"[a-z_\-/.]+|[A-Z_\-]+", s):
                        add("CR-SECRET", f, ln, redact(text, s), f"high-entropy literal ({shannon(s):.2f} bits/char)")
                        break
            if EVAL.search(text) and ext not in (".md", ".txt"):
                add("CR-EVAL", f, ln, text)
            if TLS.search(text):
                add("CR-TLS", f, ln, text)
            if SQL_KW.search(text) and SQL_BUILD.search(text):
                add("CR-SQL-CONCAT", f, ln, text)
            if SWALLOW_INLINE.search(text):
                add("CR-SWALLOW", f, ln, text)
            elif SWALLOW_HEAD.match(text) and idx + 1 < len(added) and added[idx + 1][0] == ln + 1 \
                    and SWALLOW_BODY.match(added[idx + 1][1]):
                add("CR-SWALLOW", f, ln, text + " " + added[idx + 1][1].strip())
            if not test:
                if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs") and DEBUG_JS.search(text):
                    add("CR-DEBUG", f, ln, text)
                elif ext == ".py" and DEBUG_PY.search(text):
                    add("CR-DEBUG", f, ln, text)
                elif ext in (".java", ".kt") and DEBUG_JAVA.search(text):
                    add("CR-DEBUG", f, ln, text)
            m = TODO.search(text)
            if m:
                add("CR-TODO", f, ln, text, m.group(1))
    out += detect_duplicates(files)
    src = [f for f in files if is_code(f["path"]) and not is_test(f["path"]) and f["status"] != "deleted"]
    if src and not any(is_test(f["path"]) for f in files):
        first = src[0]
        line = first["added"][0][0] if first["added"] else 0
        out.append({"rule": "CR-NO-TESTS", "file": first["path"], "line": line,
                    "evidence": f"{len(src)} source file(s) changed: " + ", ".join(f["path"] for f in src[:5]),
                    "detail": ""})
    return out


def detect_duplicates(files: list[dict], window: int = 3) -> list[dict]:
    seen: dict[tuple, tuple] = {}
    out, reported = [], set()
    for f in files:
        lines = [(ln, t.strip()) for ln, t in f["added"]]
        for i in range(len(lines) - window + 1):
            chunk = lines[i:i + window]
            if any(chunk[k + 1][0] != chunk[k][0] + 1 for k in range(window - 1)):
                continue
            key = tuple(t for _, t in chunk)
            if sum(len(t) for t in key) < 40 or any(len(t) < 4 for t in key):
                continue
            if key in seen and seen[key] != (f["path"], chunk[0][0]):
                if key not in reported:
                    first = seen[key]
                    out.append({"rule": "CR-DUP", "file": f["path"], "line": chunk[0][0],
                                "evidence": key[0], "detail": f"same {window}-line block as {first[0]}:{first[1]}"})
                    reported.add(key)
            else:
                seen.setdefault(key, (f["path"], chunk[0][0]))
    return out


# ------------------------------------------------------------------ rules CSV

def load_rules(path: Path) -> tuple[list[dict], dict, list[str]]:
    """Return (custom_rules, severity_overrides, errors)."""
    custom, overrides, errors = [], {}, []
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    need = {"rule_id", "pattern", "severity", "message"}
    if rows and not need <= set(rows[0].keys()):
        return [], {}, [f"rules CSV needs columns {sorted(need)} (file_glob optional)"]
    for i, r in enumerate(rows, 2):
        rid = (r.get("rule_id") or "").strip()
        sev = (r.get("severity") or "").strip().lower()
        pat = (r.get("pattern") or "").strip()
        if not rid or rid.startswith("#"):
            continue
        if sev not in SEVERITIES + ("off",):
            errors.append(f"rules line {i}: severity {sev!r} not in {SEVERITIES + ('off',)}")
            continue
        if rid in BUILTIN and not pat:
            overrides[rid] = sev
            continue
        try:
            rx = re.compile(pat)
        except re.error as e:
            errors.append(f"rules line {i}: bad regex {pat!r}: {e}")
            continue
        if not pat:
            errors.append(f"rules line {i}: custom rule {rid} has no pattern")
            continue
        custom.append({"id": rid, "rx": rx, "severity": sev, "message": (r.get("message") or rid).strip(),
                       "glob": (r.get("file_glob") or "").strip()})
    return custom, overrides, errors


def apply_custom(files, custom) -> list[dict]:
    out = []
    for rule in custom:
        if rule["severity"] == "off":
            continue
        for f in files:
            if rule["glob"] and not fnmatch.fnmatch(f["path"], rule["glob"]):
                continue
            for ln, text in f["added"]:
                if rule["rx"].search(text):
                    out.append({"rule": rule["id"], "file": f["path"], "line": ln, "evidence": text.strip()[:160],
                                "detail": "", "severity": rule["severity"], "message": rule["message"],
                                "fix": "See the team rule."})
    return out


# ------------------------------------------------------------------ review

def review(diff_text: str, rules_path: Path | None, entropy: float, min_len: int, large: int, source: str) -> dict:
    files = parse_diff(diff_text)
    if not files:
        raise ValueError("no file changes found in the diff (expected unified diff with ---/+++ headers)")
    custom, overrides, rule_errors = (load_rules(rules_path) if rules_path else ([], {}, []))
    if rule_errors:
        raise ValueError("; ".join(rule_errors))
    findings = []
    for f in detect(files, entropy, min_len):
        sev, msg, fix = BUILTIN[f["rule"]]
        sev = overrides.get(f["rule"], sev)
        if sev == "off":
            continue
        findings.append({**f, "severity": sev, "message": msg + (f" — {f['detail']}" if f["detail"] else ""), "fix": fix})
    findings += apply_custom(files, custom)
    findings.sort(key=lambda x: (SEV_ORDER[x["severity"]], x["file"], x["line"], x["rule"]))
    for i, x in enumerate(findings, 1):
        x["id"] = f"F{i:02d}"
        x.pop("detail", None)
    added = sum(len(f["added"]) for f in files)
    removed = sum(f["removed"] for f in files)
    tests = [f["path"] for f in files if is_test(f["path"])]
    src = [f["path"] for f in files if is_code(f["path"]) and not is_test(f["path"])]
    risky = [f["path"] for f in files if RISKY_PATH.search(f["path"])]
    counts = {s: sum(1 for x in findings if x["severity"] == s) for s in SEVERITIES}
    size = "large" if added + removed > large else "normal"
    return {
        "skill": "code-review-runner", "source": source,
        "stats": {"files": len(files), "hunks": sum(f["hunks"] for f in files), "added": added, "removed": removed,
                  "changed": added + removed, "size": size, "large_change_threshold": large,
                  "source_files": len(src), "test_files": len(tests), "risky_paths": risky},
        "files": [{"path": f["path"], "status": f["status"], "hunks": f["hunks"], "added": len(f["added"]),
                   "removed": f["removed"], "kind": "test" if is_test(f["path"]) else ("source" if is_code(f["path"]) else "other"),
                   "findings": sum(1 for x in findings if x["file"] == f["path"])} for f in files],
        "tests": {"source_changed": src, "tests_changed": tests,
                  "verdict": "tests changed" if tests else ("no source change" if not src else "MISSING")},
        "counts": counts,
        "verdict": "BLOCK" if counts["blocking"] else "PASS",
        "findings": findings,
        "rules": {"custom": [r["id"] for r in custom], "overrides": overrides,
                  "entropy_bits_per_char": entropy, "min_secret_len": min_len},
        "scope_note": "Deterministic Standards baseline on added lines. The Spec axis (does it do what the "
                      "issue asked) is not checked by this script.",
    }


def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("`", "'")


def render_md(r: dict) -> str:
    s, c = r["stats"], r["counts"]
    out = ["# Code review", "", f"_Generated by code-review-runner from {_cell(r['source'])}. {r['scope_note']}_", "",
           "## Summary", "",
           f"Verdict: **{r['verdict']}** — {c['blocking']} blocking, {c['warning']} warning, {c['info']} info.", "",
           "| Metric | Value |", "|---|---|",
           f"| Files changed | {s['files']} ({s['source_files']} source, {s['test_files']} test) |",
           f"| Hunks | {s['hunks']} |", f"| Lines added / removed | {s['added']} / {s['removed']} |",
           f"| Size | {s['size']} (threshold {s['large_change_threshold']} changed lines) |",
           f"| Risky paths | {', '.join(f'`{p}`' for p in s['risky_paths']) or 'none'} |", ""]

    def table(rows):
        if not rows:
            return ["None.", ""]
        t = ["| ID | File:line | Rule | Severity | Finding | Evidence | Fix |", "|---|---|---|---|---|---|---|"]
        for x in rows:
            t.append(f"| {x['id']} | `{_cell(x['file'])}:{x['line']}` | {x['rule']} | {x['severity']} | "
                     f"{_cell(x['message'])} | `{_cell(x['evidence'])}` | {_cell(x['fix'])} |")
        return t + [""]

    fs = r["findings"]
    out += ["## Blocking", ""] + table([x for x in fs if x["severity"] == "blocking"])
    out += ["## Non-blocking", ""] + table([x for x in fs if x["severity"] != "blocking" and x["rule"] != "CR-NO-TESTS"])
    t = r["tests"]
    out += ["## Tests", "", f"Test verdict: **{t['verdict']}**", "",
            f"- Source files changed: {', '.join(f'`{p}`' for p in t['source_changed']) or 'none'}",
            f"- Test files changed: {', '.join(f'`{p}`' for p in t['tests_changed']) or 'none'}", ""]
    nt = [x for x in fs if x["rule"] == "CR-NO-TESTS"]
    if nt:
        out += table(nt)
    out += ["## Files", "", "| File | Status | Kind | Hunks | +/- | Findings |", "|---|---|---|---|---|---|"]
    for f in r["files"]:
        out.append(f"| `{_cell(f['path'])}` | {f['status']} | {f['kind']} | {f['hunks']} | +{f['added']}/-{f['removed']} | "
                   f"{f['findings']} |")
    return "\n".join(out) + "\n"


def gate(path: Path) -> int:
    try:
        r = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"gate: cannot read {path}: {e}", file=sys.stderr)
        return 1
    n = sum(1 for x in r.get("findings", []) if x.get("severity") == "blocking")
    if n:
        print(f"gate: BLOCK — {n} blocking finding(s)", file=sys.stderr)
        return 1
    print("gate: PASS — no blocking findings")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic code review of a unified diff (added lines only)")
    ap.add_argument("--diff", help="unified diff (git diff <base>...HEAD)")
    ap.add_argument("--rules", help="optional rules CSV: rule_id,pattern,severity,message,file_glob")
    ap.add_argument("--json", dest="json_out", help="write review.json here")
    ap.add_argument("--md", dest="md_out", help="write review.md here")
    ap.add_argument("--gate", metavar="REVIEW_JSON", help="exit 1 if the review has blocking findings")
    ap.add_argument("--entropy", type=float, default=4.0, help="high-entropy threshold, bits/char (default 4.0)")
    ap.add_argument("--min-secret-len", type=int, default=20, help="min literal length for the entropy check")
    ap.add_argument("--large-change", type=int, default=400, help="changed-line count labelled 'large'")
    a = ap.parse_args()
    if a.gate:
        return gate(Path(a.gate))
    if not a.diff or not Path(a.diff).is_file():
        print(f"error: --diff is required and must exist (got {a.diff!r})", file=sys.stderr)
        return 2
    if a.rules and not Path(a.rules).is_file():
        print(f"error: --rules file not found: {a.rules}", file=sys.stderr)
        return 2
    if not a.json_out and not a.md_out:
        print("error: give --json and/or --md", file=sys.stderr)
        return 2
    try:
        r = review(Path(a.diff).read_text(encoding="utf-8", errors="replace"), Path(a.rules) if a.rules else None,
                   a.entropy, a.min_secret_len, a.large_change, Path(a.diff).name)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
    if a.md_out:
        Path(a.md_out).write_text(render_md(r), encoding="utf-8")
    c = r["counts"]
    print(f"review: {r['verdict']} — {c['blocking']} blocking, {c['warning']} warning, {c['info']} info "
          f"across {r['stats']['files']} files")
    return 1 if c["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())
