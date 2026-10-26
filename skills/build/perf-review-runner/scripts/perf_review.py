#!/usr/bin/env python3
"""Static performance review of a Next.js (App Router) + React + TypeScript + Supabase repo — a real tool that fails CI.

    python3 -I scripts/perf_review.py --target <repo> --findings findings.csv --report report.md

Scans .ts/.tsx/.js/.jsx/.mjs (skipping node_modules, .next, out, dist, build, coverage, tests/**) for:
  PF1  n-plus-one-query          high    Supabase (`.from(`/`.rpc(`) or `fetch(` call inside a for/while body or a
                                         `.map(`/`.forEach(`/`.flatMap(` callback
  PF2  await-in-loop             medium  `await` inside a for/while body (not `for await`) that is not already a PF1 line
  PF3  select-star               high    `.select("*")` (or a select list containing `*`) on a Supabase query
  PF4  unbounded-list-read       high    a `.from(…).select(…)` read chain with no `.limit(`/`.range(`/`.single(`/`.maybeSingle(`
                                         (writes, `head: true` counts and `.eq("id", …)` point reads are exempt)
  PF5  fetch-in-use-effect       medium  `"use client"` file: a `useEffect(` callback that calls `fetch(`/`.from(`/`.rpc(`
  PF6  heavy-compute-in-render   medium  `"use client"` component body: `.sort(`/`.filter(` over a prop outside
                                         useMemo/useCallback/useEffect — recomputed on every render
  PF7  img-instead-of-next-image medium  `<img` in a .tsx/.jsx file (use next/image)
  PF8  heavy-import-in-page      medium  a known large client-only library imported statically at the top of an
                                         app/**/page|layout file (use next/dynamic)
  PF9  no-store-on-every-fetch   medium  server page where every `fetch(` passes `cache: "no-store"` (no revalidate)
  PF10 sync-fs-read-in-handler   medium  `readFileSync(`/`readdirSync(` inside a route-handler export (per request)
Writes findings.csv (rule, file, line, snippet, severity, status) and report.md (Summary, Findings, [Baseline], Rules).
Exit 1 when any (new) high-severity finding exists or on bad input, 0 otherwise. --quiet prints only the summary.

Existing repo (--baseline findings.csv from an earlier run, the recorded debt): a finding whose rule, file and
snippet match a baseline row (line numbers may move) is `known`; anything else is `new`. The gate then fails only
on new high-severity findings — known debt stays listed — and baseline rows no longer found are reported as
resolved. Without --baseline every finding is `new`. Static only: nothing is executed, no network. Stdlib.
"""
from __future__ import annotations

import argparse
import subprocess
import csv
import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".next", "out", "dist", "build", "coverage", ".git", "tests", "test", "__tests__"}

_GIT_VISIBLE: dict = {}


def git_ignored(root: Path, rel: Path) -> bool:
    """True for a file git ignores in a repository: build output under any name (a custom distDir such as `bo11/`,
    `.next-*`), caches, local env files. Found on a real repo where 1,500 findings came from a build folder the fixed
    SKIP_DIRS list did not name. Outside a git repository nothing is filtered beyond SKIP_DIRS."""
    key = str(root.resolve())
    if key not in _GIT_VISIBLE:
        try:
            # only when `root` IS a repository's top level: a tree exported inside another repository (the delivery
            # pipeline's <out>/postchange-repo under giri-skills/runs/, which giri-skills ignores) must not inherit
            # that repository's ignore rules — found live: every file of the export read as ignored, 0 files linted
            top = subprocess.run(["git", "-C", key, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30)
            if top.returncode != 0 or Path(top.stdout.strip()).resolve() != Path(key):
                _GIT_VISIBLE[key] = None
                return False
            r = subprocess.run(["git", "-C", key, "ls-files", "-co", "--exclude-standard", "-z"],
                               capture_output=True, text=True, timeout=120)
            _GIT_VISIBLE[key] = (set(r.stdout.split("\0")) - {""}) if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            _GIT_VISIBLE[key] = None
    visible = _GIT_VISIBLE[key]
    return visible is not None and rel.as_posix() not in visible

EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs"}
JSX_EXTS = {".tsx", ".jsx"}
RULES = {
    "PF1": ("n-plus-one-query", "high", "One query per row: move the lookup out of the loop (`.in()`, a join/embedded select, or one RPC)"),
    "PF2": ("await-in-loop", "medium", "Sequential awaits serialize independent work: collect the promises and `Promise.all` them"),
    "PF3": ("select-star", "high", "`select(\"*\")` ships every column over the wire and defeats covering indexes: name the columns"),
    "PF4": ("unbounded-list-read", "high", "A list read without `.limit`/`.range` grows with the table: paginate (`.range(from, to)`) or cap it"),
    "PF5": ("fetch-in-use-effect", "medium", "Fetching in useEffect waterfalls after hydration: fetch in the server component and pass props"),
    "PF6": ("heavy-compute-in-render", "medium", "sort/filter over props in the render body runs on every render: wrap in useMemo keyed on the inputs"),
    "PF7": ("img-instead-of-next-image", "medium", "`<img>` skips resizing, lazy loading and modern formats: use next/image with width/height"),
    "PF8": ("heavy-import-in-page", "medium", "A large client-only library at the top of a page lands in the route bundle: load it with next/dynamic"),
    "PF9": ("no-store-on-every-fetch", "medium", "`cache: \"no-store\"` on every fetch makes the page fully dynamic: add `next: { revalidate }` or tags where data allows"),
    "PF10": ("sync-fs-read-in-handler", "medium", "Synchronous file read + parse per request blocks the event loop: read once at module scope or cache it"),
}
HEAVY_LIBS = (
    "recharts", "chart.js", "react-chartjs-2", "plotly.js", "react-plotly.js", "d3", "three", "@react-three/fiber",
    "monaco-editor", "@monaco-editor/react", "codemirror", "@codemirror/view", "mapbox-gl", "leaflet", "react-leaflet",
    "pdfjs-dist", "react-pdf", "jspdf", "html2canvas", "xlsx", "quill", "react-quill", "@tiptap/react", "ag-grid-react",
    "@fullcalendar/react", "moment", "lodash",
)
PAGE_NAMES = {"page.tsx", "page.ts", "page.jsx", "page.js", "layout.tsx", "layout.jsx", "layout.js"}
ROUTE_NAMES = {"route.ts", "route.js", "route.tsx", "route.mjs"}
HOOKS_EXCLUDED = ("useMemo", "useCallback", "useEffect", "useLayoutEffect")

USE_CLIENT = re.compile(r"^\s*['\"]use client['\"]\s*;?\s*$", re.M)
LOOP_HEAD = re.compile(r"\b(for\s+await|for|while)\s*\(")
CALLBACK_HEAD = re.compile(r"\.(?:map|forEach|flatMap)\s*\(")
DATA_CALL = re.compile(r"\.from\(\s*['\"`]|\.rpc\(|\bfetch\(")
AWAIT = re.compile(r"\bawait\b")
FROM_CALL = re.compile(r"\.from\(\s*['\"`]")
SELECT_ARG = re.compile(r"\.select\(\s*(['\"`])(.*?)\1", re.S)
USE_EFFECT = re.compile(r"\buseEffect\s*\(")
IMG_TAG = re.compile(r"<img\b")
IMPORT_FROM = re.compile(r"^[ \t]*import\s+(?!type\b)[^;]*?\bfrom\s+['\"]([^'\"]+)['\"]", re.M)
FETCH_CALL = re.compile(r"\bfetch\s*\(")
NO_STORE = re.compile(r"cache\s*:\s*['\"]no-store['\"]")
HANDLER = re.compile(r"^[ \t]*export\s+(?:async\s+)?(?:function\s+(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*\(|"
                     r"const\s+(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*=)", re.M)
SYNC_FS = re.compile(r"\b(?:readFileSync|readdirSync)\s*\(")
# A component: `function Name(` or `const Name[: Type] = (params) =>` — PascalCase, parenthesised params only
COMPONENT = re.compile(r"(?:^|\n)[ \t]*(?:export\s+)?(?:default\s+)?(?:function\s+[A-Z]\w*\s*\(|const\s+[A-Z]\w*\s*(?::[^=]+)?=\s*\([^)]*\)\s*(?::\s*[\w.<>\[\]]+)?\s*=>)")
HOOK_CALL = re.compile(r"\b(?:" + "|".join(HOOKS_EXCLUDED) + r")\s*\(")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def source_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.suffix not in EXTS or not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]) or git_ignored(root, rel):
            continue
        yield p, rel.as_posix()


def line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def balanced(text: str, start: int, open_ch: str, close_ch: str) -> tuple[int, int]:
    """(start, end) of the balanced open..close span beginning at the first open_ch at/after start; end exclusive."""
    s = text.find(open_ch, start)
    if s < 0:
        return (-1, -1)
    depth = 0
    for i in range(s, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return (s, i + 1)
    return (s, len(text))


def body_span(text: str, pos: int) -> tuple[int, int]:
    """Span of the `{ … }` block that starts at the first `{` after pos."""
    return balanced(text, pos, "{", "}")


def loop_bodies(text: str):
    """(head_pos, is_for_await, body_start, body_end) for every for/while loop."""
    for m in LOOP_HEAD.finditer(text):
        _, head_end = balanced(text, m.end() - 1, "(", ")")
        if head_end < 0:
            continue
        bs, be = body_span(text, head_end)
        if bs < 0:
            continue
        yield m.start(), m.group(1).startswith("for ") and "await" in m.group(1), bs, be


def callback_bodies(text: str):
    """Span of the arguments of every `.map(`/`.forEach(`/`.flatMap(` call (the callback lives inside)."""
    for m in CALLBACK_HEAD.finditer(text):
        s, e = balanced(text, m.end() - 1, "(", ")")
        if s >= 0:
            yield s, e


def query_chain(text: str, pos: int) -> str:
    """The method chain that starts at `.from(` at pos: `.from(...).select(...).eq(...)` up to the first non-chain char."""
    i = pos
    end = pos
    while True:
        if i >= len(text) or text[i] != ".":
            break
        j = i + 1
        while j < len(text) and (text[j].isalnum() or text[j] == "_"):
            j += 1
        k = j
        while k < len(text) and text[k] in " \t\r\n":
            k += 1
        if k < len(text) and text[k] == "(":
            _, k = balanced(text, k, "(", ")")
            if k < 0:
                break
        end = k
        i = k
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
    return text[pos:end]


def select_has_star(arg: str) -> bool:
    flat = re.sub(r"\([^()]*\)", "", arg)   # drop embedded `rel(cols)` lists, then look at top-level columns
    cols = [c.strip() for c in flat.split(",")]
    return "*" in cols or "(*)" in arg.replace(" ", "")


def prop_names(params: str) -> list[str]:
    """Names bound by a component's first parameter: `{ a, b: c, d = 1 }: Props` -> [a, c, d]; `props` -> [props]."""
    params = params.strip()
    if params.startswith("{"):
        inner = params[1:params.find("}")] if "}" in params else params[1:]
        names = []
        for item in inner.split(","):
            item = item.strip()
            if not item or item.startswith("..."):
                continue
            if ":" in item:
                item = item.split(":", 1)[1]
            item = item.split("=", 1)[0].strip()
            if re.fullmatch(r"\w+", item):
                names.append(item)
        return names
    name = params.split(":", 1)[0].strip()
    return [name] if re.fullmatch(r"\w+", name) else []


def excluded_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans = []
    for m in HOOK_CALL.finditer(text, start, end):
        s, e = balanced(text, m.end() - 1, "(", ")")
        if s >= 0:
            spans.append((s, min(e, end)))
    return spans


def in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def lint_file(text: str, rel: str) -> list[dict]:
    lines = text.splitlines()
    seen: set[tuple[str, int]] = set()
    out: list[dict] = []
    name = rel.rsplit("/", 1)[-1]
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    is_client = bool(USE_CLIENT.search(text))
    is_page = rel.startswith("app/") and name in PAGE_NAMES
    is_route = rel.startswith("app/") and name in ROUTE_NAMES

    def add(rule: str, pos: int) -> None:
        ln = line_no(text, pos)
        if (rule, ln) in seen:
            return
        seen.add((rule, ln))
        rname, sev, _ = RULES[rule]
        out.append({"rule": rule, "file": rel, "line": ln, "snippet": lines[ln - 1].strip()[:120], "severity": sev})

    # PF1 — data call inside a loop body or an iteration callback
    pf1_lines: set[int] = set()
    for _, _, bs, be in loop_bodies(text):
        for m in DATA_CALL.finditer(text, bs, be):
            add("PF1", m.start())
            pf1_lines.add(line_no(text, m.start()))
    for s, e in callback_bodies(text):
        for m in DATA_CALL.finditer(text, s, e):
            add("PF1", m.start())
            pf1_lines.add(line_no(text, m.start()))

    # PF2 — await inside a for/while body (for await excluded), unless the line is already an N+1 finding
    for _, is_for_await, bs, be in loop_bodies(text):
        if is_for_await:
            continue
        for m in AWAIT.finditer(text, bs, be):
            if line_no(text, m.start()) not in pf1_lines:
                add("PF2", m.start())

    # PF3 / PF4 — per Supabase query chain
    for m in FROM_CALL.finditer(text):
        chain = query_chain(text, m.start())
        if ".select(" not in chain or re.search(r"head\s*:\s*true", chain):
            continue
        sel = SELECT_ARG.search(chain)
        if sel and select_has_star(sel.group(2)):
            add("PF3", m.start() + sel.start())
        is_write = any(w in chain for w in (".insert(", ".update(", ".delete(", ".upsert("))
        bounded = any(b in chain for b in (".limit(", ".range(", ".single(", ".maybeSingle(")) or \
            re.search(r"\.eq\(\s*['\"]id['\"]", chain)
        if not is_write and not bounded:
            add("PF4", m.start())

    if is_client:
        # PF5 — data fetching inside useEffect
        for m in USE_EFFECT.finditer(text):
            s, e = balanced(text, m.end() - 1, "(", ")")
            if s >= 0 and DATA_CALL.search(text, s, e):
                add("PF5", m.start())
        # PF6 — sort/filter over props in the component body, outside memo hooks
        for cm in COMPONENT.finditer(text):
            ps, pe = balanced(text, cm.start(), "(", ")")
            if ps < 0:
                continue
            names = prop_names(text[ps + 1:pe - 1])
            if not names:
                continue
            arrow = text.find("=>", pe)
            body_at = arrow + 2 if "=>" in cm.group(0) and arrow >= 0 else pe
            bs, be = body_span(text, body_at)
            if bs < 0:
                continue
            excl = excluded_spans(text, bs, be)
            pat = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b[\w.]*\.(?:filter|sort)\(")
            for m in pat.finditer(text, bs, be):
                if not in_spans(m.start(), excl):
                    add("PF6", m.start())

    # PF7 — raw <img>
    if suffix in JSX_EXTS:
        for m in IMG_TAG.finditer(text):
            add("PF7", m.start())

    if is_page:
        # PF8 — heavy client-only library imported statically in a page/layout
        for m in IMPORT_FROM.finditer(text):
            spec = m.group(1)
            if any(spec == lib or spec.startswith(lib + "/") for lib in HEAVY_LIBS):
                add("PF8", m.start())
        # PF9 — server page where every fetch is no-store
        if not is_client:
            fetches = []
            for m in FETCH_CALL.finditer(text):
                s, e = balanced(text, m.end() - 1, "(", ")")
                fetches.append((m.start(), bool(NO_STORE.search(text[s:e])) if s >= 0 else False))
            if fetches and all(ns for _, ns in fetches):
                for pos, _ in fetches:
                    add("PF9", pos)

    if is_route:
        # PF10 — synchronous fs read inside a handler export
        for hm in HANDLER.finditer(text):
            bs, be = body_span(text, hm.end())
            if bs < 0:
                continue
            for m in SYNC_FS.finditer(text, bs, be):
                add("PF10", m.start())

    return out


def norm_snippet(s: str) -> str:
    """One form for both sides of a baseline match: a snippet is cut at a fixed width AFTER stripping, so a live
    one can end in whitespace (`m.id, `) while the CSV round-trip strips it — strip and collapse internal runs."""
    return " ".join(str(s or "").split())


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
    pool = [(r, fl, norm_snippet(s)) for r, fl, s in baseline]
    for f in findings:
        key = (f["rule"], f["file"], norm_snippet(f["snippet"]))
        if key in pool:
            pool.remove(key)
            f["status"] = "known"
        else:
            f["status"] = "new"
    return pool


def write_report(path: Path, findings: list[dict], n_files: int, target: Path,
                 resolved: list[tuple[str, str, str]] | None = None) -> None:
    by_rule: dict[str, list[dict]] = {}
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
    lines = [f"# Performance review — {target.name}", "", head + ".** " + gate, "",
             "Static review of the source only: nothing was executed, no traffic was measured. Confirm hot paths with "
             "production metrics before and after a fix.", "",
             "## Summary", "", "| Rule | Name | Severity | Count |", "|---|---|---|---|"]
    for rule, (rname, sev, _) in RULES.items():
        lines.append(f"| {rule} | {rname} | {sev} | {len(by_rule.get(rule, []))} |")
    lines += ["", "## Findings", "", "| Rule | File:line | Severity | Status | Snippet |", "|---|---|---|---|---|"]
    for f in findings:
        snippet = f["snippet"].replace("|", "\\|")
        lines.append(f"| {f['rule']} | `{f['file']}:{f['line']}` | {f['severity']} | {f['status']} | `{snippet}` |")
    if not findings:
        lines.append("| — | — | — | — | no findings |")
    if based:
        lines += ["", "## Baseline", "",
                  "Known findings are recorded debt: fix them in their own PRs and re-record the baseline. "
                  "Resolved since the baseline:", ""]
        lines += [f"- {r} `{f_}` — {s_}" for r, f_, s_ in resolved] or ["- none"]
    lines += ["", "## Rules", ""]
    for rule, (rname, sev, fix) in RULES.items():
        lines.append(f"- **{rule} {rname}** ({sev}) — {fix}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Static performance review of a Next.js + Supabase repo")
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
        die(f"no .ts/.tsx/.js/.jsx/.mjs source files under {target}")
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
            print(f"{f['severity']:6} {f['rule']:4} {f['file']}:{f['line']}  {f['snippet']}"
                  + ("  (known)" if f["status"] == "known" else ""))
    print(f"{len(findings)} finding(s) in {n_files} file(s); {len(high)} {'new ' if resolved is not None else ''}high -> {fp}, {rp}")
    if high:
        print(f"gate: FAIL — {len(high)} {'new ' if resolved is not None else ''}high-severity finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
