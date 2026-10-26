#!/usr/bin/env python3
"""Scaffold red tests first: a vitest stub per source file and a Playwright spec per page.

    python3 -I scripts/scaffold_tests.py feature.md --files server/services/export.ts,app/invoices/page.tsx \
        --target <repo> [--tasks tasks.csv] [--flavour ts|js] [--dry-run] --report scaffold-report.json --plan test-plan.md

feature.md: an H1 title and `-` bullets, one per acceptance criterion. For each --files entry
(.js / .jsx / .ts / .tsx alike):
  app/**/page.* | layout.* | template.* | error.* | not-found.*  -> page      -> <e2e dir>/<slug>.spec.<ext>  (test.fixme per criterion)
  components/**/*                                                -> component -> listed for a component test; nothing written
  app/**/route.*                                                 -> API route -> <unit dir>/<path>.test.<ext>
  everything else                                                -> unit      -> <unit dir>/<path>.test.<ext>  (it.todo per criterion)
  a non-code entry (*.sql, docs/*.md, .env.example, *.yml, *.json, …) -> skipped with a note (`non_source` in the
                                                                    report); no stub is ever generated for it
Layer per file follows references/test-pyramid.md (validator / service / query / action / route).

--tasks tasks.csv (the approved plan from spec-to-plan / plan-refine: id, task, acceptance, test, files, …) makes the
plan's own test names win over the per-source-file naming above: every `tests/…(.test|.spec).(js|jsx|ts|tsx)` path a
task's `test` cell names (`tests/unit/checker.test.js: toCsv quotes …`, or any such token in the cell) gets one stub,
whose `it.todo`s are THAT task's acceptance text only (a file several tasks name collects each task's acceptance,
once); a task's `files` are what the stub is headed with and imports. The stub's extension follows the repo flavour
(a `.ts` name in a JavaScript repo is written as `.js` and the rename is reported). Source files such a stub already
covers get no per-file stub. A task whose `test` cell names no path falls back to the per-source-file naming for its
`files`, again with its own acceptance text; a --files entry no task mentions keeps today's behaviour (every criterion
in feature.md). The report carries `tasks` ({path, source, tasks[], criteria[], renamed_from}) and `plan_tests`.

Read before write — the target repo is inspected first and every stub matches what is there:
  flavour   --flavour ts|js wins when given (the pipeline passes the stack profile's flavour). Otherwise:
            tsconfig.json -> TypeScript; jsconfig.json without tsconfig.json -> JavaScript; any .ts/.tsx
            source under app|components|lib|server|src|pages|supabase (build output such as .next/, dist/,
            coverage/, node_modules/ and dot-directories ignored) -> TypeScript; else the extension of the
            SOURCE entries in --files decides (docs/env/md/yaml/json paths never count: all .js/.jsx/.mjs/.cjs
            -> JavaScript; any .ts/.tsx -> TypeScript); no repo and no source files -> TypeScript.
  runner    package.json dependencies/devDependencies: vitest -> `import { describe, it, expect } from "vitest"`;
            jest -> no import (globals); neither -> vitest (the skill's default). mocha / jasmine / ava /
            tap / node:test -> refused (see below).
  unit dir  the first `include` glob of vitest.config.* / testMatch of jest config, else tests/unit.
  e2e dir   `testDir` of playwright.config.* (js|ts|mjs|cjs), else tests/e2e.
  alias     "@/*" in tsconfig.json / jsconfig.json paths -> `@/<module>` import; else a relative import.
Existing files are never overwritten (listed as skipped) — and a sibling of the other flavour
(e.g. lib-coach.test.ts when lib-coach.test.js would be written) counts as existing, so no
conflicting pair is ever created. Each kept test file is read instead: its test titles (it/test,
incl. .todo/.fixme/.skip/.only) are matched to the criteria (same words after normalising, or >= 60%
of the criterion's words in one title) and the criteria it does not cover yet are listed to add by
hand. --dry-run writes nothing.
When the repo cannot be scaffolded safely (unsupported test runner), nothing is written: the report
carries `refused` with the reason, the plan says so, and the exit code is 1 — never a half-install.
Writes scaffold-report.json ({repo, written, skipped, components, non_source, would_write, files,
existing_tests, refused}) and test-plan.md (repo table + pyramid table + criteria map + existing tests). Exit 1 on bad
input (missing feature file, no bullets, no files). Stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

LAYERS = [  # (path marker, feature type, layer, what to cover)
    ("server/validators/", "validator", "unit", "valid, each invalid field, boundary values"),
    ("server/services/", "service", "unit + integration", "each rule branch; each error code; audit written; RLS-denied path"),
    ("lib/db/", "query", "integration", "returns expected rows; tenant filter; PG error mapping"),
    ("server/actions/", "server action", "unit", "parse failure → fieldErrors; auth failure; success maps result"),
    ("app/api/", "API route", "unit + contract", "signature verify; bad payload; recorded payloads parse"),
    ("supabase/functions/", "edge function", "unit", "handler logic with injected client"),
]
SRC_EXT = r"\.(?:tsx?|jsx?|mjs|cjs)$"
# what a stub can be written for: JS/TS source only — never .sql, .md, .yaml, .json, .env* (a migration is covered by the
# RLS lint and the integration suite, not by a vitest stub)
SCAFFOLD_EXT = r"\.(?:tsx?|jsx?|mjs|cjs)$"
# a test path a plan's `test` cell may name: tests/unit/checker.test.js, tests/e2e/invoices.spec.ts, …
TEST_PATH_RE = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*tests?/[\w./-]*?\.(?:test|spec)\.(?:tsx?|jsx?))(?![\w.-])")
PAGE_NAMES = ("page", "layout", "template", "error", "not-found")
SOURCE_DIRS = ("app", "components", "lib", "server", "src", "pages", "supabase")
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "out", "coverage", ".vercel", ".turbo"}
UNSUPPORTED_RUNNERS = ("mocha", "jasmine", "ava", "tap", "node:test", "node --test")
FLAVOURS = ("ts", "js")


# found on a real run: files.txt listed route.test.ts beside route.ts and the scaffold wrote route-test.test.ts
IS_TEST = re.compile(r"(\.(test|spec)\.[cm]?[jt]sx?$)|(^|/)(tests?|__tests__|e2e)/")


def is_source(rel: str) -> bool:
    """A --files entry a stub can be generated for: JS/TS code. SQL, docs, env files, YAML/JSON/Markdown are not."""
    return re.search(SCAFFOLD_EXT, rel.rsplit("/", 1)[-1]) is not None


def clean_rel(f: str) -> str:
    """`./lib/a.js` -> `lib/a.js`; a dotfile (.env.example) keeps its dot — str.lstrip("./") would eat it."""
    return re.sub(r"^(?:\./)+", "", f.strip().replace("\\", "/"))


def split_cell(cell: str) -> list[str]:
    """A tasks.csv `files` cell: comma-, semicolon- or newline-separated repo paths (`; ` from spec-to-plan)."""
    return [clean_rel(x) for x in re.split(r"[,;\n]+", cell or "") if x.strip()]


def test_paths_in(cell: str) -> list[str]:
    """Every test file path a `test` cell names, in order, once."""
    out: list[str] = []
    for m in TEST_PATH_RE.finditer(cell or ""):
        rel = clean_rel(m.group(1))
        if rel not in out:
            out.append(rel)
    return out


def read_tasks(path: Path) -> list[dict]:
    """tasks.csv rows (id, task, acceptance, test, files, …) — the approved plan. Exit 1 when it has no `test` column."""
    import csv
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if rows and not {"test", "acceptance", "files"} <= set(rows[0].keys()):
        die(f"{path}: tasks.csv needs id, acceptance, test and files columns (got {', '.join(rows[0].keys())})")
    return rows


def plan_from_tasks(rows: list[dict], flavour: str) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """(named stubs by test path, acceptance per source file for tasks that name no test path).
    A named stub: {"path", "sources" (the task's code files), "tasks" (ids), "criteria" (each task's acceptance, once),
    "renamed_from" (the plan's spelling when its extension did not match the repo flavour)}."""
    named: dict[str, dict] = {}
    per_source: dict[str, list[str]] = {}
    want = "ts" if flavour == "ts" else "js"
    for row in rows:
        tid = (row.get("id") or "").strip() or "?"
        acceptance = (row.get("acceptance") or "").strip()
        sources = [f for f in split_cell(row.get("files") or "") if is_source(f)]
        paths = test_paths_in(row.get("test") or "")
        if not paths:
            for src in sources:
                if acceptance and acceptance not in per_source.setdefault(src, []):
                    per_source[src].append(acceptance)
            continue
        for rel in paths:
            fixed = re.sub(r"\.(test|spec)\.(tsx?|jsx?)$",
                           lambda m: f".{m.group(1)}." + (want + "x" if m.group(2).endswith("x") else want), rel)
            stub = named.setdefault(fixed, {"path": fixed, "sources": [], "tasks": [], "criteria": [],
                                            "renamed_from": rel if fixed != rel else None})
            stub["tasks"].append(tid)
            for src in sources:
                if src not in stub["sources"]:
                    stub["sources"].append(src)
            if acceptance and acceptance not in stub["criteria"]:
                stub["criteria"].append(acceptance)
    return named, per_source


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_feature(text: str) -> tuple[str, list[str]]:
    title, bullets = "", []
    for ln in text.splitlines():
        m = re.match(r"^#\s+(.*)$", ln)
        if m and not title:
            title = m.group(1).strip()
        b = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", ln)
        if b:
            bullets.append(b.group(1).strip())
    return title or "feature", bullets


TITLE_RE = re.compile(r"""\b(?:it|test)(?:\.(?:todo|fixme|skip|only))?\(\s*(["'`])(.+?)\1""")
STOP = {"a", "an", "the", "and", "or", "of", "to", "is", "are", "be", "gets", "get", "with", "for", "in", "on", "its", "it", "s"}


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def covers(title: str, criterion: str) -> bool:
    """A test title covers a criterion when it has the same words or >= 60% of the criterion's words."""
    cw, tw = words(criterion), words(title)
    if not cw or not tw:
        return False
    return cw == tw or len(cw & tw) / len(cw) >= 0.6


def existing_titles(text: str) -> list[str]:
    return [m.group(2) for m in TITLE_RE.finditer(text)]


# ---------------------------------------------------------------- read before write: the repo

def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _first(root: Path, stem: str, exts=("ts", "js", "mjs", "cjs", "mts", "cts")) -> Path | None:
    for ext in exts:
        p = root / f"{stem}.{ext}"
        if p.is_file():
            return p
    return None


def has_ts_sources(root: Path) -> bool:
    """A .ts/.tsx source (not .d.ts) under a source dir — build output (.next/, dist/, coverage/, node_modules/)
    and dot-directories are never evidence, wherever they sit."""
    for d in SOURCE_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS and not x.startswith(".")]
            if any(f.endswith((".ts", ".tsx")) and not f.endswith(".d.ts") for f in filenames):
                return True
    return False


def detect_repo(root: Path, files: list[str], flavour: str = "") -> dict:
    """Inspect the target once; everything written later follows this. `flavour` (ts|js) wins when given."""
    info = {"exists": root.is_dir(), "flavour": "ts", "flavour_why": "default (no repo, no source files given)",
            "runner": "vitest", "runner_why": "default (no package.json)", "unit_dir": "tests/unit", "e2e_dir": "tests/e2e",
            "e2e_config": None, "unit_config": None, "alias": None, "refused": None}
    # alias: "@/*" in tsconfig/jsconfig paths (greenfield default below); relative imports otherwise
    # flavour — only source entries count (docs/.env/yaml/json paths say nothing about the language)
    sources = [f for f in files if is_source(f) and not f.endswith(".sql")]
    if flavour in FLAVOURS:
        info.update(flavour=flavour, flavour_why=f"--flavour {flavour} (given; the stack profile's flavour)")
    elif root.is_dir() and (root / "tsconfig.json").is_file():
        info.update(flavour="ts", flavour_why="tsconfig.json present")
    elif root.is_dir() and (root / "jsconfig.json").is_file():
        info.update(flavour="js", flavour_why="jsconfig.json present, no tsconfig.json")
    elif root.is_dir() and has_ts_sources(root):
        info.update(flavour="ts", flavour_why=".ts/.tsx sources present")
    elif any(re.search(r"\.tsx?$", f) for f in sources):
        info.update(flavour="ts", flavour_why="--files include .ts/.tsx source")
    elif sources and all(re.search(r"\.(jsx?|mjs|cjs)$", f) for f in sources):
        info.update(flavour="js", flavour_why="no tsconfig.json or .ts sources; the source files in --files are JavaScript")
    elif root.is_dir() and (root / "package.json").is_file():
        info.update(flavour="js", flavour_why="package.json without tsconfig.json or .ts/.tsx sources")
    if flavour and flavour not in FLAVOURS:
        info["flavour_why"] += f" (--flavour {flavour!r} ignored: not ts or js)"
    if not root.is_dir():
        info["alias"] = "@/"  # greenfield: the stack convention (shared/stack-conventions.md) uses @/*
        return info
    # runner
    pkg = {}
    pkg_path = root / "package.json"
    if pkg_path.is_file():
        try:
            pkg = json.loads(_read(pkg_path))
        except ValueError:
            pkg = {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})} if isinstance(pkg, dict) else {}
    test_script = str(((pkg.get("scripts") or {}) if isinstance(pkg, dict) else {}).get("test", ""))
    if "vitest" in deps:
        info.update(runner="vitest", runner_why="vitest in package.json")
    elif "jest" in deps:
        info.update(runner="jest", runner_why="jest in package.json")
    else:
        bad = [r for r in UNSUPPORTED_RUNNERS if r in deps or r in test_script]
        if bad:
            info["refused"] = (f"test runner {bad[0]!r} (package.json) is not vitest or jest; writing vitest stubs next to it "
                               "would leave a half-installed suite — add vitest or jest first, or write these tests by hand")
        info.update(runner="vitest", runner_why="default (package.json names no vitest/jest)" if pkg_path.is_file()
                    else "default (no package.json)")
    # unit dir from the runner config
    vcfg = _first(root, "vitest.config") or _first(root, "vite.config")
    if vcfg:
        info["unit_config"] = vcfg.name
        m = re.search(r"include\s*:\s*\[\s*[\"']([^\"']+)[\"']", _read(vcfg))
        if m:
            info["unit_dir"] = m.group(1).split("*", 1)[0].strip("/") or info["unit_dir"]
    elif info["runner"] == "jest":
        jcfg = _first(root, "jest.config")
        if jcfg:
            info["unit_config"] = jcfg.name
            m = re.search(r"testMatch\s*:\s*\[\s*[\"']<rootDir>/([^\"'*]+)", _read(jcfg))
            if m:
                info["unit_dir"] = m.group(1).strip("/") or info["unit_dir"]
    # e2e dir from playwright config
    pcfg = _first(root, "playwright.config")
    if pcfg:
        info["e2e_config"] = pcfg.name
        m = re.search(r"testDir\s*:\s*[\"']\.?/?([^\"']+)[\"']", _read(pcfg))
        if m:
            info["e2e_dir"] = m.group(1).strip("/") or info["e2e_dir"]
    # import alias
    for cfg in ("tsconfig.json", "jsconfig.json"):
        if (root / cfg).is_file() and re.search(r"""["']@/\*["']\s*:""", _read(root / cfg)):
            info["alias"] = "@/"
            break
    return info


# ---------------------------------------------------------------- classification and stubs

def classify(rel: str) -> tuple[str, str, str, str]:
    """-> (kind: page|component|unit, feature type, layer, cover). Same for .js/.jsx/.ts/.tsx."""
    name = rel.rsplit("/", 1)[-1]
    stem = re.sub(SRC_EXT, "", name)
    if (rel.startswith("app/") or "/app/" in rel) and stem in PAGE_NAMES and re.search(SRC_EXT, name):
        return "page", "page / flow", "e2e", "critical path: load, act, assert, negative role"
    if (rel.startswith("components/") or "/components/" in rel) and re.search(SRC_EXT, name):
        return "component", "client component", "component", "client form states (pending, error)"
    for marker, ftype, layer, cover in LAYERS:
        if rel.startswith(marker):
            return "unit", ftype, layer, cover
    if stem == "route" and re.search(SRC_EXT, name):
        return "unit", "API route", "unit + contract", "signature verify; bad payload; recorded payloads parse"
    return "unit", "module", "unit", "each exported function: happy path + error branch"


def slug(rel: str) -> str:
    s = re.sub(SRC_EXT, "", rel)
    s = re.sub(r"[()\[\]]", "", s)
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def ts_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def import_path(rel: str, test_rel: str, alias: str | None) -> str:
    mod = re.sub(SRC_EXT, "", rel)
    if alias:
        return alias + mod
    up = "../" * (len(test_rel.split("/")) - 1)
    return (up or "./") + mod


def unit_stub(rel: str, title: str, bullets: list[str], test_rel: str, repo: dict, sources: list[str] | None = None) -> str:
    """One vitest/jest stub. `sources`: every code file the stub covers (a plan-named test may cover several); the
    first is `rel`, the module the import comment names."""
    sources = sources or [rel]
    lines = [f"// Red first: generated by test-strategy-tdd for {', '.join(sources)}. Replace each todo with a failing test."]
    if repo["runner"] == "vitest":
        lines.append('import { describe, it, expect } from "vitest";')
    else:
        lines.append("// jest: describe / it / expect are globals")
    lines += [f'// import {{ ... }} from "{import_path(src, test_rel, repo["alias"])}";' for src in sources]
    lines += ["", f"describe({ts_str(title + ' — ' + rel)}, () => {{"]
    lines += [f"  it.todo({ts_str(b)});" for b in bullets]
    lines += ["  it.todo(\"rejects invalid input / forbidden role / cross-tenant access\");", "});", ""]
    return "\n".join(lines)


def e2e_stub(rel: str, title: str, bullets: list[str], e2e_dir: str) -> str:
    route = "/" + re.sub(r"^(?:src/)?app/|/?(?:" + "|".join(PAGE_NAMES) + r")" + SRC_EXT, "", rel)
    route = re.sub(r"/\([^)]*\)", "", route) or "/"
    lines = [f"// Red first: generated by test-strategy-tdd for {rel}. Replace each fixme with a real flow.",
             'import { test, expect } from "@playwright/test";', "",
             f"test.describe({ts_str(title + ' — ' + route)}, () => {{",
             f'  test.use({{ storageState: "{e2e_dir}/.auth/member.json" }});', ""]
    for b in bullets:
        lines += [f"  test.fixme({ts_str(b)}, async ({{ page }}) => {{", f"    await page.goto({ts_str(route)});",
                  "    await expect(page).toHaveURL(/./);", "  });", ""]
    lines += ["  test.fixme(\"denies a user without permission\", async ({ page }) => {",
              f"    await page.goto({ts_str(route)});", "    await expect(page.getByText(/not allowed/i)).toBeVisible();",
              "  });", "});", ""]
    return "\n".join(lines)


def sibling_conflict(dest: Path) -> Path | None:
    """An existing test for the same source in the other flavour (lib-coach.test.ts vs .test.js)."""
    name = dest.name
    for a, b in ((".test.ts", ".test.js"), (".test.tsx", ".test.jsx"), (".spec.ts", ".spec.js")):
        for x, y in ((a, b), (b, a)):
            if name.endswith(x):
                other = dest.with_name(name[: -len(x)] + y)
                return other if other.exists() else None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold vitest/playwright stubs from a feature description")
    ap.add_argument("feature", help="feature.md: H1 title + one bullet per acceptance criterion")
    ap.add_argument("--files", required=True, help="comma-separated source files the feature touches (repo-relative)")
    ap.add_argument("--target", required=True, help="repo root (tests/ is created under it)")
    ap.add_argument("--tasks", default="", help="tasks.csv of the approved plan (id, task, acceptance, test, files, …): "
                                                "a task's `test` cell naming tests/… paths decides the stub names and each "
                                                "stub carries that task's acceptance only")
    ap.add_argument("--flavour", default="", help="ts|js: the language flavour the stubs take (wins over detection; "
                                                  "any other value is ignored)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", default="scaffold-report.json")
    ap.add_argument("--plan", default="test-plan.md")
    a = ap.parse_args()
    fpath = Path(a.feature)
    if not fpath.is_file():
        die(f"feature file not found: {fpath}")
    title, bullets = parse_feature(fpath.read_text(encoding="utf-8", errors="replace"))
    if not bullets:
        die("feature.md has no bullets (one per acceptance criterion)")
    files = [clean_rel(f) for f in a.files.split(",") if f.strip()]
    if not files:
        die("--files is empty")
    target = Path(a.target)
    if target.exists() and not target.is_dir():
        die(f"target is not a directory: {target}")
    tasks_rows: list[dict] = []
    if a.tasks:
        tpath = Path(a.tasks)
        if not tpath.is_file():
            die(f"tasks file not found: {tpath}")
        tasks_rows = read_tasks(tpath)

    repo = detect_repo(target, files, a.flavour.strip().lower())
    ext = "ts" if repo["flavour"] == "ts" else "js"
    cext = "tsx" if repo["flavour"] == "ts" else "jsx"
    unit_dir, e2e_dir = repo["unit_dir"], repo["e2e_dir"]
    refused = repo["refused"]
    named, per_source = plan_from_tasks(tasks_rows, repo["flavour"]) if tasks_rows else ({}, {})
    covered = {src for st in named.values() for src in st["sources"]}   # code files a plan-named stub already covers
    report = {"target": str(target), "dry_run": a.dry_run, "title": title, "criteria": bullets, "repo": repo,
              "refused": refused, "written": [], "skipped": [], "components": [], "non_source": [], "would_write": [],
              "files": [], "existing_tests": [], "tasks_file": str(a.tasks) if a.tasks else None,
              "plan_tests": sorted(named), "tasks": []}
    if not any(is_source(f) for f in files) and not named:
        die("--files names no source file (" + ", ".join(files) + "): nothing to scaffold a test for")

    def emit(row: dict, test_rel: str, content: str, criteria: list[str]) -> None:
        """Never overwrite: an existing file (or its other-flavour sibling) is kept and read; else dry-run or write."""
        row["criteria"] = criteria
        if refused:
            return
        dest = target / test_rel
        existing = dest if dest.exists() else sibling_conflict(dest)
        if existing is not None:
            kept_rel = existing.relative_to(target).as_posix()
            row["test"] = kept_rel
            report["skipped"].append(kept_rel)
            titles = existing_titles(_read(existing))
            idx = [bullets.index(c) + 1 if c in bullets else None for c in criteria]
            covered_i = [i for i, c in zip(idx, criteria) if i and any(covers(t, c) for t in titles)]
            report["existing_tests"].append({"test": kept_rel, "titles": titles, "criteria_covered": covered_i,
                                             "criteria_missing": [i for i in idx if i and i not in covered_i]})
            return
        if a.dry_run:
            report["would_write"].append(test_rel)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        report["written"].append(test_rel)

    for rel in files:
        if not is_source(rel):   # .sql, docs, env, yaml, json …: no test file is ever generated for these
            report["non_source"].append(rel)
            report["files"].append({"source": rel, "kind": "non-source", "type": "not code", "layer": "—",
                                    "cover": "—", "test": "", "criteria": [],
                                    "note": "skipped: not a source file (no stub generated — only JS/TS code gets one)"})
            continue
        if IS_TEST.search(rel):   # a test the plan lists as a file to write: it IS the test, never stub a test for it
            report["files"].append({"source": rel, "kind": "test", "type": "test file", "layer": "—", "cover": "—",
                                    "test": rel, "criteria": [], "note": "skipped: already a test file (no stub for a test)"})
            continue
        kind, ftype, layer, cover = classify(rel)
        if rel in covered:       # the plan names the test for this file: no per-file stub beside it
            tests = [p for p, st in named.items() if rel in st["sources"]]
            report["files"].append({"source": rel, "kind": kind, "type": ftype, "layer": layer, "cover": cover,
                                    "test": ", ".join(tests), "criteria": [c for p in tests for c in named[p]["criteria"]],
                                    "note": "covered by the plan's test file(s)", "plan": True})
            continue
        criteria = per_source.get(rel) or bullets   # the task's own acceptance when the plan names this file; else all
        if kind == "page":
            test_rel, content = f"{e2e_dir}/{slug(rel)}.spec.{ext}", e2e_stub(rel, title, criteria, e2e_dir)
        elif kind == "component":
            test_rel, content = f"{unit_dir}/{slug(rel)}.test.{cext}", ""
        else:
            test_rel = f"{unit_dir}/{slug(rel)}.test.{ext}"
            content = unit_stub(rel, title, criteria, test_rel, repo)
        row = {"source": rel, "kind": kind, "type": ftype, "layer": layer, "cover": cover, "test": test_rel, "criteria": criteria}
        report["files"].append(row)
        if kind == "component":
            report["components"].append(test_rel)
            continue
        emit(row, test_rel, content, criteria)

    for test_rel, st in named.items():   # the plan's own test files, one stub each, that task's acceptance only
        is_e2e = ".spec." in test_rel.rsplit("/", 1)[-1]
        pages = [src for src in st["sources"] if classify(src)[0] == "page"]
        primary = (pages[0] if is_e2e and pages else next((src for src in st["sources"] if classify(src)[0] != "page"), None)
                   or (st["sources"][0] if st["sources"] else None))
        rel = primary or re.sub(r"\.(test|spec)\.(tsx?|jsx?)$", "", test_rel.rsplit("/", 1)[-1])
        kind, ftype, layer, cover = classify(primary) if primary else ("unit", "module", "unit", "each exported function: happy path + error branch")
        if is_e2e:
            content = e2e_stub(primary if pages else f"app/{rel}/page.{ext}", title, st["criteria"], e2e_dir)
            kind = "page"
        else:
            content = unit_stub(rel, title, st["criteria"], test_rel, repo, st["sources"] or None)
        row = {"source": ", ".join(st["sources"]) or "—", "kind": kind, "type": ftype, "layer": layer, "cover": cover,
               "test": test_rel, "tasks": st["tasks"], "plan": True}
        if st["renamed_from"]:
            row["renamed_from"] = st["renamed_from"]
        report["files"].append(row)
        report["tasks"].append({"path": test_rel, "source": st["sources"], "tasks": st["tasks"], "criteria": st["criteria"],
                                "renamed_from": st["renamed_from"]})
        emit(row, test_rel, content, st["criteria"])

    rp, pp = Path(a.report), Path(a.plan)
    rp.parent.mkdir(parents=True, exist_ok=True)
    pp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    flavour_name = "TypeScript" if repo["flavour"] == "ts" else "JavaScript"
    lines = [f"# Test plan — {title}", ""]
    if refused:
        lines += [f"**Refused — nothing written.** {refused}", ""]
    lines += [f"**{len(bullets)} acceptance criteria across {len(files)} file(s); "
              f"{len(report['written'])} stub(s) written, {len(report['skipped'])} kept (already exist), "
              f"{len(report['components'])} component test(s) to write by hand"
              + (f", {len(report['non_source'])} non-source file(s) skipped" if report["non_source"] else "")
              + (f"; {len(named)} test file(s) named by the plan ({Path(a.tasks).name})" if named else "")
              + (" — dry run, nothing written" if a.dry_run else "") + ".**", ""]
    if report["non_source"]:
        lines += ["Not code files — no stub generated (SQL migrations are covered by the RLS lint and the integration suite; "
                  "docs, env or config travel with the change, they are not tested here): "
                  + ", ".join(f"`{f}`" for f in report["non_source"]) + ".", ""]
    if named:
        lines += ["Test files named by the plan's `test` cells (each stub carries its task's acceptance only): "
                  + ", ".join(f"`{t}` ({', '.join(named[t]['tasks'])})" for t in sorted(named)) + ".", ""]
        renamed = [st for st in named.values() if st["renamed_from"]]
        if renamed:
            lines += ["Renamed to the repo flavour: " + ", ".join(f"`{st['renamed_from']}` → `{st['path']}`" for st in renamed) + ".", ""]
    lines += [
              "## Repo (read before write)", "", "| Setting | Value | Why |", "|---|---|---|",
              f"| Flavour | {flavour_name} (`.test.{ext}` / `.spec.{ext}`) | {repo['flavour_why']} |",
              f"| Unit runner | {repo['runner']} | {repo['runner_why']} |",
              f"| Unit dir | `{unit_dir}/` | {repo['unit_config'] or 'default'} |",
              f"| E2E dir | `{e2e_dir}/` | {repo['e2e_config'] or 'default (no playwright.config)'} |",
              f"| Import alias | {('`' + repo['alias'] + '`') if repo['alias'] else 'relative paths'} | "
              f"{'tsconfig/jsconfig paths' if repo['alias'] else 'no @/* alias found'} |", "",
              "## Pyramid", "", "| Source | Type | Layer | Cover | Test file | Status |", "|---|---|---|---|---|---|"]
    for r in report["files"]:
        if r["kind"] == "non-source":
            lines.append(f"| `{r['source']}` | {r['type']} | — | — | — | skipped (not a source file) |")
            continue
        if r.get("note", "").startswith("covered by the plan"):
            lines.append(f"| `{r['source']}` | {r['type']} | {r['layer']} | {r['cover']} | `{r['test']}` | covered by the plan's test |")
            continue
        status = ("manual (component)" if r["kind"] == "component" else "refused" if refused
                  else "exists — kept" if r["test"] in report["skipped"] else "would write" if a.dry_run else "written")
        if r.get("tasks"):
            status += f" (plan: {', '.join(r['tasks'])})"
        lines.append(f"| `{r['source']}` | {r['type']} | {r['layer']} | {r['cover']} | `{r['test']}` | {status} |")
    lines += ["", "## Criteria map", "", "| # | Criterion | Tests |", "|---|---|---|"]
    stub_rows = [r for r in report["files"] if r["kind"] not in ("component", "non-source") and not r.get("note", "").startswith("covered")]
    for i, b in enumerate(bullets, 1):
        tests = ", ".join(f"`{r['test']}`" for r in stub_rows if b in (r.get("criteria") or [])) or "—"
        lines.append(f"| {i} | {b} | {tests} |")
    if report["existing_tests"]:
        lines += ["", "## Existing tests (kept — add the missing criteria by hand)", "",
                  "| Test file | Tests found | Criteria covered | Criteria to add |", "|---|---|---|---|"]
        for e in report["existing_tests"]:
            lines.append(f"| `{e['test']}` | {len(e['titles'])} | "
                         f"{', '.join(f'#{i}' for i in e['criteria_covered']) or 'none'} | "
                         f"{'; '.join(f'#{i} {bullets[i - 1]}' for i in e['criteria_missing']) or 'none'} |")
    lines += ["", "## Red → green", "",
              "1. Replace each `it.todo` / `test.fixme` with a failing test (assertion failure, not import error).",
              "2. Implement the minimum to pass; run the full unit suite after each task.",
              "3. Negative cases are mandatory: invalid input, forbidden role, cross-tenant, not-found.",
              "4. Coverage gate: ≥ 80% on `server/` (`npm test -- --coverage`)."]
    pp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if refused:
        print(f"refused: {refused} -> {rp}, {pp}", file=sys.stderr)
        return 1
    print(f"{'dry-run: ' if a.dry_run else ''}{len(report['written'])} written, {len(report['skipped'])} skipped, "
          f"{len(report['components'])} component(s) manual"
          + (f", {len(report['non_source'])} non-source skipped" if report["non_source"] else "")
          + (f", {len(named)} named by the plan" if named else "")
          + f" [{flavour_name}, {repo['runner']}] -> {rp}, {pp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
