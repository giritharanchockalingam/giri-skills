#!/usr/bin/env python3
"""Tech-debt audit of a TypeScript / Next.js repo — the pass a senior engineer makes on joining an unfamiliar codebase.

    python3 -I scripts/audit_debt.py --target <repo> [--baseline findings.csv] [--owners owners.csv] \
        --findings findings.csv --report report.md --plan refactor-plan.md

Static analysis only (no app run, no network, stdlib). Scans .ts/.tsx/.js/.jsx/.mjs, skipping node_modules,
.next, out, dist, build, coverage, .git. Test files (tests/, __tests__/, *.test.*, *.spec.*) join the import
graph (an import from a test counts as a use) but are not audited themselves. Rules:

  TD1 duplicate-logic       medium  near-identical function bodies (>= 6 normalised lines) in two different files
  TD2 god-file              medium  > 400 lines or > 12 exported symbols; HIGH above 800 lines
  TD3 circular-import       high    a cycle in the import graph (relative and `@/` imports)
  TD4 layering-violation    high    app/ importing an app/ sibling route folder; lib/ importing app/ or components/
  TD5 dead-export           medium  an exported symbol no other file imports (framework files and index re-exports excluded)
  TD6 todo-comment          low     TODO / FIXME / HACK comments, one finding per file with the count (age unknown)
  TD7 any-density           medium  more than 5 `any` type usages in one file
  TD8 missing-tests         medium  a lib/ module with no tests/**<stem>* file and no <stem>.test|spec.* sibling

Writes findings.csv (rule, file, line, snippet, severity, status), report.md (Summary, Findings, [Baseline], Rules)
and refactor-plan.md (Summary, Architecture map, Priorities, Sequencing). Exit 1 only on NEW high findings (the
gate), 0 otherwise, 2 on bad input. --baseline findings.csv (an earlier run): a finding that matches a baseline row
is `known` and does not gate — line-level rules (TD1, TD3, TD4, TD5) match on rule+file+snippet, file-level rules
(TD2, TD6, TD7, TD8) on rule+file, so a god file that grew is still the same known debt. Baseline rows no longer
found are reported as resolved. --owners owners.csv (path_prefix,owner): longest-prefix owner per finding; without
a match the owner is `[TO BE BASELINED — owner: tech lead]`. Deterministic: same inputs -> byte-identical outputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".next", "out", "dist", "build", "coverage", ".git"}
EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs")
RESOLVE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", "/index.ts", "/index.tsx", "/index.js")
TEST_DIRS = {"tests", "test", "__tests__", "spec"}
TEST_FILE = re.compile(r"\.(test|spec)\.[jt]sx?$")
FRAMEWORK_FILES = {"page", "layout", "route", "loading", "error", "not-found", "template", "default", "global-error"}
FRAMEWORK_EXPORTS = {"default", "metadata", "generateMetadata", "generateStaticParams", "generateViewport", "viewport",
                     "dynamic", "dynamicParams", "revalidate", "fetchCache", "runtime", "preferredRegion", "maxDuration",
                     "config", "middleware", "register", "onRequestError"}
ROOT_FRAMEWORK = re.compile(r"^(middleware|instrumentation|[\w.-]+\.config)\.[jt]sx?$|^[\w.-]+\.config\.mjs$")

DUP_MIN_LINES = 6
GOD_LINES, GOD_LINES_HIGH, GOD_EXPORTS = 400, 800, 12
ANY_MAX = 5
TBD_OWNER = "[TO BE BASELINED — owner: tech lead]"

RULES = {
    "TD1": ("duplicate-logic", "medium", f"Near-identical function bodies (>= {DUP_MIN_LINES} normalised lines) in two files: one bug, two fixes"),
    "TD2": ("god-file", "medium", f"> {GOD_LINES} lines or > {GOD_EXPORTS} exported symbols (high above {GOD_LINES_HIGH} lines): nobody owns or safely changes it"),
    "TD3": ("circular-import", "high", "A cycle in the import graph: undefined-at-load bugs, untestable modules, no clean build order"),
    "TD4": ("layering-violation", "high", "app/ importing an app/ sibling, or lib/ importing app/ or components/: dependencies point the wrong way"),
    "TD5": ("dead-export", "medium", "An exported symbol no other file imports: dead code or an unowned public surface"),
    "TD6": ("todo-comment", "low", "TODO/FIXME/HACK comments of unknown age: intentions that never became tickets"),
    "TD7": ("any-density", "medium", f"More than {ANY_MAX} `any` usages in one file: the type system is switched off there"),
    "TD8": ("missing-tests", "medium", "A lib/ module with no test file: refactoring it is guesswork"),
}
FILE_LEVEL = {"TD2", "TD6", "TD7", "TD8"}
EFFORT = {"TD1": "S", "TD2": "L", "TD3": "M", "TD4": "S", "TD5": "S", "TD6": "S", "TD7": "M", "TD8": "M"}
PHASES = [
    ("Phase 1 — restore the dependency direction", ("TD3", "TD4"), "cycles and layering violations block safe change everywhere else; break them first (extract the shared piece into lib/ or server/, or invert the import)"),
    ("Phase 2 — split the god files", ("TD2",), "move one responsibility out per PR behind the existing exports; add a characterisation test before each split"),
    ("Phase 3 — one implementation, under test", ("TD1", "TD8"), "collapse duplicates into the lib/ copy and add the missing lib/ tests so Phase 2 and later refactors have a safety net"),
    ("Phase 4 — trim the surface", ("TD5", "TD7", "TD6"), "delete dead exports, type the `any` hot spots, turn each TODO into a ticket or delete it"),
]

IMPORT_RE = re.compile(
    r"""(?:^|\n)[ \t]*(?:import|export)\s+(?P<clause>type\s+)?(?P<spec>[^'"\n;]*?)\s*from\s*['"](?P<path>[^'"]+)['"]"""
    r"""|(?:^|\n)[ \t]*import\s*['"](?P<bare>[^'"]+)['"]"""
    r"""|\b(?:import|require)\(\s*['"](?P<dyn>[^'"]+)['"]\s*\)""")
EXPORT_DECL = re.compile(r"^[ \t]*export\s+(?:declare\s+)?(?:default\s+)?(?:async\s+)?(?:function\s*\*?|class|const|let|var|type|interface|enum|abstract\s+class)\s+(\w+)", re.M)
EXPORT_DEFAULT = re.compile(r"^[ \t]*export\s+default\b", re.M)
EXPORT_LIST = re.compile(r"^[ \t]*export\s+(?:type\s+)?\{([^}]*)\}(?!\s*from)", re.M)
FUNC_HEAD = re.compile(
    r"(?:^|\n)[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w*)\s*\([^)]*\)[^{;\n]*\{"
    r"|(?:^|\n)[ \t]*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=>{]+)?=>\s*\{")
TODO_RE = re.compile(r"(?://|/\*|\*|#)\s*(TODO|FIXME|HACK)\b")
ANY_RE = re.compile(r"(?<![\w$.])any(?![\w$])")


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    return any(p in TEST_DIRS for p in parts[:-1]) or bool(TEST_FILE.search(parts[-1]))


def source_files(root: Path) -> list[tuple[Path, str]]:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or not p.name.endswith(EXTS) or p.name.endswith(".d.ts"):
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        out.append((p, rel.as_posix()))
    return out


def _scan(text: str, blank_strings: bool) -> str:
    """One pass over the source: comments become whitespace (newlines kept, so line numbers hold); string and
    template literals keep their quotes and, with blank_strings, lose their contents."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, j))
            i = j
        elif c in "'\"`":
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\":
                    j += 1
                elif text[j] == "\n" and c != "`":
                    break
                j += 1
            j = min(j + 1, n)
            lit = text[i:j]
            out.append(c + "\n" * lit.count("\n") + c if blank_strings else lit)
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def strip_comments(text: str) -> str:
    return _scan(text, blank_strings=False)


def strip_strings(text: str) -> str:
    """Blank string contents (call on comment-stripped or raw text; one pass handles both)."""
    return _scan(text, blank_strings=True)


def line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def brace_block(text: str, open_pos: int) -> str:
    depth = 0
    for i in range(open_pos, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_pos:i + 1]
    return text[open_pos:]


# ------------------------------------------------------------------ import graph

def resolve_import(spec: str, importer_rel: str, files: set[str]) -> str | None:
    """Resolve a relative or `@/` import to a repo-relative file path (None for packages or unresolved)."""
    if spec.startswith("@/"):
        base = spec[2:]
    elif spec.startswith("."):
        parts = importer_rel.split("/")[:-1]
        for seg in spec.split("/"):
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg not in (".", ""):
                parts.append(seg)
        base = "/".join(parts)
    else:
        return None
    base = re.sub(r"\.(ts|tsx|js|jsx|mjs)$", "", base) if base.endswith(EXTS) and base not in files else base
    if base in files:
        return base
    for suf in RESOLVE_SUFFIXES:
        if base + suf in files:
            return base + suf
    return None


def parse_imports(text: str, rel: str, files: set[str]) -> list[dict]:
    """[{target, line, names}] — names is a set of imported symbols, or {"*"} when every export counts as used."""
    out = []
    for m in IMPORT_RE.finditer(text):
        spec = m.group("path") or m.group("bare") or m.group("dyn")
        target = resolve_import(spec, rel, files)
        if not target or target == rel:
            continue
        names: set[str] = set()
        clause = (m.group("spec") or "").strip()
        if m.group("bare") or m.group("dyn") or clause == "*" or re.match(r"\*\s+as\s+\w+", clause):
            names = {"*"}
        elif clause:
            braces = re.search(r"\{([^}]*)\}", clause)
            if braces:
                for item in braces.group(1).split(","):
                    item = item.strip()
                    if not item:
                        continue
                    item = re.sub(r"^type\s+", "", item)
                    names.add(item.split(" as ")[0].strip())
            head = re.sub(r"\{[^}]*\}", "", clause).strip().strip(",").strip()
            if head:
                if head.startswith("*"):
                    names.add("*")
                else:
                    names.add("default")
            if m.group(0).lstrip().startswith("export") and not braces and not head:
                names.add("*")   # `export * from`
        else:
            names = {"*"}   # `export * from './x'` parses with an empty clause
        out.append({"target": target, "line": line_no(text, m.start()) + (1 if m.group(0).startswith("\n") else 0), "names": names, "spec": spec})
    return out


def parse_exports(text: str) -> list[tuple[str, int]]:
    """[(name, line)] of symbols this file exports (default export named "default")."""
    out, seen = [], set()
    for m in EXPORT_DECL.finditer(text):
        name = "default" if re.match(r"[ \t]*export\s+(?:declare\s+)?default\b", m.group(0)) else m.group(1)
        if name not in seen:
            seen.add(name)
            out.append((name, line_no(text, m.start())))
    for m in EXPORT_DEFAULT.finditer(text):
        if "default" not in seen:
            seen.add("default")
            out.append(("default", line_no(text, m.start())))
    for m in EXPORT_LIST.finditer(text):
        for item in m.group(1).split(","):
            item = re.sub(r"^type\s+", "", item.strip())
            if not item:
                continue
            name = item.split(" as ")[-1].strip() if " as " in item else item
            if name not in seen:
                seen.add(name)
                out.append((name, line_no(text, m.start())))
    return out


# ------------------------------------------------------------------ rules

def find_duplicates(sources: dict[str, str]) -> list[dict]:
    groups: dict[str, list[tuple[str, int, str]]] = {}
    for rel in sorted(sources):
        text = strip_comments(sources[rel])
        for m in FUNC_HEAD.finditer(text):
            name = m.group(1) or m.group(2) or "(anonymous)"
            body = brace_block(text, m.end() - 1)
            norm = [re.sub(r"\s+", " ", ln).strip() for ln in body.splitlines()]
            norm = [ln for ln in norm if ln and ln not in ("{", "}")]
            if len(norm) < DUP_MIN_LINES:
                continue
            h = hashlib.sha256("\n".join(norm).encode("utf-8")).hexdigest()[:16]
            groups.setdefault(h, []).append((rel, line_no(text, m.start()) + (1 if m.group(0).startswith("\n") else 0), name))
    out = []
    for h, members in groups.items():
        files = sorted({f for f, _, _ in members})
        if len(files) < 2:
            continue
        first = members[0]
        for rel, ln, name in members[1:]:
            if rel == first[0]:
                continue
            out.append(finding("TD1", rel, ln, f"{name}() duplicates {first[2]}() in {first[0]} ({len(members)} copies)"))
    return out


def find_god_files(sources: dict[str, str], exports: dict[str, list]) -> list[dict]:
    out = []
    for rel, text in sources.items():
        n_lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        n_exports = len(exports.get(rel, []))
        if n_lines > GOD_LINES or n_exports > GOD_EXPORTS:
            sev = "high" if n_lines > GOD_LINES_HIGH else "medium"
            out.append(finding("TD2", rel, 1, f"{n_lines} lines, {n_exports} exported symbols", sev))
    return out


def find_cycles(graph: dict[str, list[dict]]) -> list[dict]:
    adj = {k: sorted({e["target"] for e in v}) for k, v in graph.items()}
    index, low, stack, on, sccs, counter = {}, {}, [], set(), [], [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj.get(v, []):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(sorted(comp))

    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))
    for v in sorted(adj):
        if v not in index:
            strong(v)
    out = []
    for comp in sccs:
        if len(comp) < 2:
            continue
        first = comp[0]
        edge = next((e for e in graph[first] if e["target"] in comp), None)
        chain = " -> ".join(comp + [first])
        out.append(finding("TD3", first, edge["line"] if edge else 1, f"cycle: {chain}"))
    return out


def layer_of(rel: str) -> str:
    return rel.split("/", 1)[0] if "/" in rel else ""


def find_layering(graph: dict[str, list[dict]]) -> list[dict]:
    out = []
    for rel in sorted(graph):
        src = layer_of(rel)
        src_dir = rel.rsplit("/", 1)[0] + "/"
        for e in graph[rel]:
            tgt = e["target"]
            tl = layer_of(tgt)
            if src == "lib" and tl in ("app", "components"):
                out.append(finding("TD4", rel, e["line"], f"lib/ imports {tl}/: {e['spec']}"))
            elif src == "app" and tl == "app":
                tgt_dir = tgt.rsplit("/", 1)[0] + "/"
                private = any(seg.startswith("_") for seg in tgt.split("/")[1:-1])   # app/_components etc. are not routes
                if not private and not (tgt_dir.startswith(src_dir) or src_dir.startswith(tgt_dir)):
                    out.append(finding("TD4", rel, e["line"], f"app/ imports a sibling route folder: {e['spec']}"))
    return out


def find_dead_exports(graph: dict[str, list[dict]], exports: dict[str, list], audited: set[str]) -> list[dict]:
    used: dict[str, set[str]] = {}
    for rel, edges in graph.items():
        for e in edges:
            used.setdefault(e["target"], set()).update(e["names"])
    out = []
    for rel in sorted(audited):
        name = rel.rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        if stem == "index" or ("/" not in rel and ROOT_FRAMEWORK.match(name)):
            continue
        framework = rel.startswith("app/") and stem in FRAMEWORK_FILES
        u = used.get(rel, set())
        if "*" in u:
            continue
        for sym, ln in exports.get(rel, []):
            if framework and (sym in FRAMEWORK_EXPORTS or stem == "route"):
                continue
            if sym not in u:
                out.append(finding("TD5", rel, ln, f"export {sym} is never imported"))
    return out


def find_todos(sources: dict[str, str]) -> list[dict]:
    out = []
    for rel, text in sources.items():
        hits = [line_no(text, m.start()) for m in TODO_RE.finditer(text)]
        if hits:
            out.append(finding("TD6", rel, hits[0], f"{len(hits)} TODO/FIXME/HACK comment(s); age unknown (no history read)"))
    return out


def find_any(sources: dict[str, str]) -> list[dict]:
    out = []
    for rel, text in sources.items():
        if not rel.endswith((".ts", ".tsx")):
            continue
        clean = strip_strings(strip_comments(text))
        hits = [line_no(clean, m.start()) for m in ANY_RE.finditer(clean)]
        if len(hits) > ANY_MAX:
            out.append(finding("TD7", rel, hits[0], f"{len(hits)} `any` usages (max {ANY_MAX})"))
    return out


def find_missing_tests(audited: set[str], all_files: set[str]) -> list[dict]:
    test_files = [f for f in all_files if is_test_path(f)]
    out = []
    for rel in sorted(audited):
        if not rel.startswith("lib/") or not rel.endswith((".ts", ".tsx")):
            continue
        stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if stem == "index":
            continue
        folder = rel.rsplit("/", 1)[0]
        has = any(stem in t.rsplit("/", 1)[-1] for t in test_files if t.split("/")[0] in TEST_DIRS) or \
            any(t.startswith(folder + "/") and TEST_FILE.search(t) and t.rsplit("/", 1)[-1].startswith(stem + ".") for t in test_files)
        if not has:
            out.append(finding("TD8", rel, 1, f"no tests/**{stem}* and no {stem}.test|spec.* sibling"))
    return out


def finding(rule: str, rel: str, line: int, snippet: str, severity: str | None = None) -> dict:
    return {"rule": rule, "file": rel, "line": line, "snippet": snippet[:160], "severity": severity or RULES[rule][1]}


# ------------------------------------------------------------------ baseline / owners

def load_baseline(path: Path) -> list[tuple[str, str, str]]:
    if not path.is_file():
        die(f"baseline not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in ("rule", "file", "snippet") if c not in (reader.fieldnames or [])]
        if missing:
            die(f"baseline lacks column(s) {missing} (expected a findings.csv from this script)")
        rows = []
        for r in reader:
            rule = (r.get("rule") or "").strip()
            if not rule or rule.startswith("#"):
                continue
            rows.append((rule, (r.get("file") or "").strip(), (r.get("snippet") or "").strip()))
        return rows


def baseline_key(rule: str, file: str, snippet: str) -> tuple:
    return (rule, file) if rule in FILE_LEVEL else (rule, file, snippet)


def apply_baseline(findings: list[dict], baseline: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    pool = {baseline_key(*b): list() for b in baseline}
    for b in baseline:
        pool[baseline_key(*b)].append(b)
    for f in findings:
        k = baseline_key(f["rule"], f["file"], f["snippet"])
        if pool.get(k):
            pool[k].pop(0)
            f["status"] = "known"
        else:
            f["status"] = "new"
    return sorted(b for rows in pool.values() for b in rows)


def load_owners(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        die(f"owners file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "path_prefix" not in reader.fieldnames or "owner" not in reader.fieldnames:
            die("owners csv needs columns path_prefix,owner")
        rows = [((r.get("path_prefix") or "").strip(), (r.get("owner") or "").strip()) for r in reader]
    rows = [(p, o) for p, o in rows if p and o and not p.startswith("#")]
    return sorted(rows, key=lambda x: -len(x[0]))


def owner_for(rel: str, owners: list[tuple[str, str]]) -> str:
    for prefix, owner in owners:
        if rel.startswith(prefix):
            return owner
    return TBD_OWNER


# ------------------------------------------------------------------ architecture map

FOLDER_LABEL = {
    "app": "routes, pages and route handlers (App Router)",
    "pages": "routes (Pages Router)",
    "components": "UI components",
    "lib": "shared utilities and data access",
    "server": "server-side services and actions",
    "hooks": "client hooks",
    "utils": "shared utilities",
    "types": "shared types",
    "styles": "styling",
    "public": "static assets",
}


def architecture_map(graph: dict[str, list[dict]], all_files: set[str]) -> list[dict]:
    folders: dict[str, dict] = {}
    for rel in sorted(all_files):
        fo = layer_of(rel) or "(root)"
        d = folders.setdefault(fo, {"files": 0, "out": set(), "in": set()})
        d["files"] += 1
    for rel, edges in graph.items():
        src = layer_of(rel) or "(root)"
        for e in edges:
            tgt = layer_of(e["target"]) or "(root)"
            if tgt != src:
                folders[src]["out"].add(tgt)
                folders[tgt]["in"].add(src)
    rows = []
    for fo in sorted(folders):
        d = folders[fo]
        label = FOLDER_LABEL.get(fo)
        if fo in TEST_DIRS:
            role = "tests"
        elif not d["in"] and d["out"]:
            role = "entry surface (nothing imports it)"
        elif d["in"] and not d["out"]:
            role = "foundation (imports no other folder)"
        elif d["in"] and d["out"]:
            role = "intermediate layer"
        else:
            role = "isolated (no internal imports either way)"
        rows.append({"folder": fo + "/" if fo != "(root)" else "(root)", "files": d["files"],
                     "imports": ", ".join(sorted(d["out"])) or "—", "imported_by": ", ".join(sorted(d["in"])) or "—",
                     "responsibility": f"{label} — {role}" if label else role})
    return rows


# ------------------------------------------------------------------ outputs

def write_findings(path: Path, findings: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["rule", "file", "line", "snippet", "severity", "status"])
        w.writeheader()
        w.writerows(findings)


def summary_line(findings: list[dict], n_files: int, resolved) -> tuple[str, str, int]:
    high = sum(1 for f in findings if f["severity"] == "high")
    med = sum(1 for f in findings if f["severity"] == "medium")
    low = len(findings) - high - med
    new_high = sum(1 for f in findings if f["severity"] == "high" and f["status"] == "new")
    based = resolved is not None
    head = f"**{len(findings)} finding(s) in {n_files} audited file(s): {high} high, {med} medium, {low} low"
    if based:
        known = sum(1 for f in findings if f["status"] == "known")
        head += f"; {len(findings) - known} new, {known} known from the baseline, {len(resolved)} resolved"
    gate = ("Gate: FAIL (new high-severity findings)." if new_high else
            "Gate: PASS (no new high-severity findings; known debt listed below)." if high else "Gate: PASS.") if based \
        else ("Gate: FAIL (high-severity findings)." if new_high else "Gate: PASS.")
    return head + ".** " + gate, gate, new_high


def write_report(path: Path, findings: list[dict], n_files: int, target: Path, resolved) -> None:
    by_rule: dict[str, list] = {}
    for f in findings:
        by_rule.setdefault(f["rule"], []).append(f)
    head, _, _ = summary_line(findings, n_files, resolved)
    lines = [f"# Tech-debt audit — {target.name}", "", head, "",
             "Static analysis only: no app run, no git history read, no network. TODO age is unknown; "
             "thresholds are parameters (see Rules).", "",
             "## Summary", "", "| Rule | Name | Severity | Count |", "|---|---|---|---|"]
    for rule, (name, sev, _) in RULES.items():
        lines.append(f"| {rule} | {name} | {sev}{' / high > ' + str(GOD_LINES_HIGH) + ' lines' if rule == 'TD2' else ''} | {len(by_rule.get(rule, []))} |")
    lines += ["", "## Findings", "", "| Rule | File:line | Severity | Status | Snippet |", "|---|---|---|---|---|"]
    for f in findings:
        snippet = f["snippet"].replace("|", "\\|")
        lines.append(f"| {f['rule']} | `{f['file']}:{f['line']}` | {f['severity']} | {f['status']} | {snippet} |")
    if not findings:
        lines.append("| — | — | — | — | no findings |")
    if resolved is not None:
        lines += ["", "## Baseline", "",
                  "Known findings are recorded debt: they stay listed and in the plan but do not gate. Resolved since the baseline:", ""]
        lines += [f"- {r} `{f_}` — {s_}" for r, f_, s_ in resolved] or ["- none"]
    lines += ["", "## Rules", ""]
    for rule, (name, sev, why) in RULES.items():
        lines.append(f"- **{rule} {name}** ({sev}) — {why}")
    lines += ["", "Fix hints per rule: `references/debt-rules.md`."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


SEV_RANK = {"high": 0, "medium": 1, "low": 2}


def write_plan(path: Path, findings: list[dict], n_files: int, target: Path, resolved, arch: list[dict],
               owners: list[tuple[str, str]]) -> None:
    head, gate, _ = summary_line(findings, n_files, resolved)
    ordered = sorted(findings, key=lambda f: (SEV_RANK[f["severity"]], f["status"] != "new", f["rule"], f["file"], f["line"]))
    unowned = sum(1 for f in findings if owner_for(f["file"], owners) == TBD_OWNER)
    lines = [f"# Refactoring plan — {target.name}", "", "## Summary", "", head, "",
             f"- Audited files: {n_files}; folders mapped: {len(arch)}",
             "- Ordered by: severity (high → low), then new before known, then rule",
             f"- Effort S/M/L is a per-rule default (see Priorities), not an estimate of your codebase; owners come from `--owners` "
             f"(longest path prefix) and otherwise read `{TBD_OWNER}` — {unowned} item(s) still need an owner",
             "- Static analysis only; confirm each item against the code before scheduling it", "",
             "## Architecture map", "", "Folder responsibilities inferred from the import graph (who imports whom), not from documentation.", "",
             "| Folder | Files | Imports from | Imported by | Inferred responsibility |", "|---|---|---|---|---|"]
    for r in arch:
        lines.append(f"| `{r['folder']}` | {r['files']} | {r['imports']} | {r['imported_by']} | {r['responsibility']} |")
    lines += ["", "## Priorities", "", "| # | Finding | File:line | Effort | Risk | Status | Owner |", "|---|---|---|---|---|---|---|"]
    for i, f in enumerate(ordered, 1):
        snippet = f["snippet"].replace("|", "\\|")
        lines.append(f"| {i} | {f['rule']} {RULES[f['rule']][0]}: {snippet} | `{f['file']}:{f['line']}` | {EFFORT[f['rule']]} | "
                     f"{f['severity']} | {f['status']} | {owner_for(f['file'], owners)} |")
    if not ordered:
        lines.append("| — | no findings | — | — | — | — | — |")
    lines += ["", "## Sequencing", ""]
    for title, rules, why in PHASES:
        items = [f for f in ordered if f["rule"] in rules]
        lines.append(f"### {title} ({len(items)} item(s))")
        lines.append(f"{why}.")
        for f in items:
            lines.append(f"- {f['rule']} `{f['file']}:{f['line']}` — {f['snippet']} [{f['status']}; effort {EFFORT[f['rule']]}; owner: {owner_for(f['file'], owners)}]")
        if not items:
            lines.append("- nothing in this phase")
        lines.append("")
    lines += ["Re-run the audit after each phase with the previous `findings.csv` as `--baseline`: the gate then fails only on new high findings, "
              "and resolved items are listed under Baseline in `report.md`."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ main

def verify_findings(path: Path) -> int:
    """Re-check a findings.csv: header, known rule ids, severity consistent with the rule, status new|known."""
    if not path.is_file():
        die(f"findings not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        want = ["rule", "file", "line", "snippet", "severity", "status"]
        if reader.fieldnames != want:
            die(f"findings header {reader.fieldnames} != {want}")
        bad = []
        for i, r in enumerate(reader, 2):
            rule = r["rule"]
            if rule not in RULES:
                bad.append(f"row {i}: unknown rule {rule}")
            elif r["severity"] not in ("high", "medium", "low") or (rule != "TD2" and r["severity"] != RULES[rule][1]) \
                    or (rule == "TD2" and r["severity"] not in ("medium", "high")):
                bad.append(f"row {i}: severity {r['severity']} does not match {rule}")
            if r["status"] not in ("new", "known"):
                bad.append(f"row {i}: status {r['status']} not new|known")
            if not r["file"] or not r["line"].isdigit():
                bad.append(f"row {i}: file/line missing")
    if bad:
        die("; ".join(bad[:5]), 1)
    print(f"verified {path}")
    return 0


def audit(target: Path) -> tuple[list[dict], int, list[dict]]:
    files = source_files(target)
    if not files:
        die(f"no .ts/.tsx/.js/.jsx/.mjs source files under {target}")
    all_rel = {rel for _, rel in files}
    texts = {rel: p.read_text(encoding="utf-8", errors="replace") for p, rel in files}
    audited = {rel for rel in all_rel if not is_test_path(rel)}
    if not audited:
        die(f"only test files under {target}; nothing to audit")
    graph = {rel: parse_imports(strip_comments(texts[rel]), rel, all_rel) for rel in sorted(all_rel)}
    exports = {rel: parse_exports(strip_comments(texts[rel])) for rel in audited}
    src = {rel: texts[rel] for rel in sorted(audited)}
    findings = (find_duplicates(src) + find_god_files(src, exports) + find_cycles({k: v for k, v in graph.items() if k in audited})
                + find_layering({k: v for k, v in graph.items() if k in audited}) + find_dead_exports(graph, exports, audited)
                + find_todos(src) + find_any(src) + find_missing_tests(audited, all_rel))
    findings.sort(key=lambda f: (f["file"], f["line"], f["rule"], f["snippet"]))
    return findings, len(audited), architecture_map(graph, all_rel)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tech-debt audit of a TypeScript / Next.js repo (TD1–TD8)")
    ap.add_argument("--target", default="", help="repo root")
    ap.add_argument("--verify", default="", help="verify a findings.csv written by this script (columns, rule ids, severities, statuses); exit 0 when valid")
    ap.add_argument("--baseline", default="", help="findings.csv from an earlier run: known debt that does not gate")
    ap.add_argument("--owners", default="", help="owners.csv (path_prefix,owner) for the plan's Owner column")
    ap.add_argument("--findings", default="findings.csv")
    ap.add_argument("--report", default="report.md")
    ap.add_argument("--plan", default="refactor-plan.md")
    ap.add_argument("--quiet", action="store_true", help="print only the summary line")
    a = ap.parse_args()
    if a.verify:
        return verify_findings(Path(a.verify))
    if not a.target:
        die("--target is required (or --verify <findings.csv>)")
    target = Path(a.target)
    if not target.is_dir():
        die(f"target is not a directory: {target}")
    owners = load_owners(Path(a.owners)) if a.owners else []
    baseline = load_baseline(Path(a.baseline)) if a.baseline else None
    findings, n_files, arch = audit(target)
    resolved = apply_baseline(findings, baseline) if baseline is not None else None
    if resolved is None:
        for f in findings:
            f["status"] = "new"
    write_findings(Path(a.findings), findings)
    write_report(Path(a.report), findings, n_files, target, resolved)
    write_plan(Path(a.plan), findings, n_files, target, resolved, arch, owners)
    new_high = [f for f in findings if f["severity"] == "high" and f["status"] == "new"]
    if not a.quiet:
        for f in findings:
            print(f"{f['severity']:6} {f['rule']} {f['file']}:{f['line']}  {f['snippet']}" + ("  (known)" if f["status"] == "known" else ""))
    print(f"{len(findings)} finding(s) in {n_files} file(s); {len(new_high)} {'new ' if resolved is not None else ''}high -> {a.findings}, {a.report}, {a.plan}")
    if new_high:
        print(f"gate: FAIL — {len(new_high)} {'new ' if resolved is not None else ''}high-severity finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
