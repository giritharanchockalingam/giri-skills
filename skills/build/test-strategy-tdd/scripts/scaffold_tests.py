#!/usr/bin/env python3
"""Scaffold red tests first: a vitest stub per source file and a Playwright spec per page.

    python3 -I scripts/scaffold_tests.py feature.md --files server/services/export.ts,app/invoices/page.tsx \
        --target <repo> [--flavour ts|js] [--dry-run] --report scaffold-report.json --plan test-plan.md

feature.md: an H1 title and `-` bullets, one per acceptance criterion. For each --files entry
(.js / .jsx / .ts / .tsx alike):
  app/**/page.* | layout.* | template.* | error.* | not-found.*  -> page      -> <e2e dir>/<slug>.spec.<ext>  (test.fixme per criterion)
  components/**/*                                                -> component -> listed for a component test; nothing written
  app/**/route.*                                                 -> API route -> <unit dir>/<path>.test.<ext>
  everything else                                                -> unit      -> <unit dir>/<path>.test.<ext>  (it.todo per criterion)
  a non-source entry (docs/*.md, .env.example, *.yml, *.json, …)  -> skipped with a note (`non_source` in the
                                                                    report); no stub is ever generated for it
Layer per file follows references/test-pyramid.md (validator / service / query / action / route /
migration).

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
    ("supabase/migrations/", "migration / RLS", "integration", "positive + negative per policy"),
    ("supabase/functions/", "edge function", "unit", "handler logic with injected client"),
]
SRC_EXT = r"\.(?:tsx?|jsx?|mjs|cjs)$"
# what a stub can be written for: JS/TS source, plus SQL under supabase/ (migrations / RLS, see LAYERS)
SCAFFOLD_EXT = r"\.(?:tsx?|jsx?|mjs|cjs|sql)$"
PAGE_NAMES = ("page", "layout", "template", "error", "not-found")
SOURCE_DIRS = ("app", "components", "lib", "server", "src", "pages", "supabase")
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "out", "coverage", ".vercel", ".turbo"}
UNSUPPORTED_RUNNERS = ("mocha", "jasmine", "ava", "tap", "node:test", "node --test")
FLAVOURS = ("ts", "js")


def is_source(rel: str) -> bool:
    """A --files entry a stub can be generated for; docs, env files, YAML/JSON/Markdown and the like are not."""
    return re.search(SCAFFOLD_EXT, rel.rsplit("/", 1)[-1]) is not None


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


def unit_stub(rel: str, title: str, bullets: list[str], test_rel: str, repo: dict) -> str:
    lines = [f"// Red first: generated by test-strategy-tdd for {rel}. Replace each todo with a failing test."]
    if repo["runner"] == "vitest":
        lines.append('import { describe, it, expect } from "vitest";')
    else:
        lines.append("// jest: describe / it / expect are globals")
    lines += [f'// import {{ ... }} from "{import_path(rel, test_rel, repo["alias"])}";', "",
              f"describe({ts_str(title + ' — ' + rel)}, () => {{"]
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
    # `./lib/a.js` -> `lib/a.js`; a dotfile (.env.example) keeps its dot — str.lstrip("./") would eat it
    files = [re.sub(r"^(?:\./)+", "", f.strip().replace("\\", "/")) for f in a.files.split(",") if f.strip()]
    if not files:
        die("--files is empty")
    target = Path(a.target)
    if target.exists() and not target.is_dir():
        die(f"target is not a directory: {target}")

    repo = detect_repo(target, files, a.flavour.strip().lower())
    ext = "ts" if repo["flavour"] == "ts" else "js"
    cext = "tsx" if repo["flavour"] == "ts" else "jsx"
    unit_dir, e2e_dir = repo["unit_dir"], repo["e2e_dir"]
    refused = repo["refused"]
    report = {"target": str(target), "dry_run": a.dry_run, "title": title, "criteria": bullets, "repo": repo,
              "refused": refused, "written": [], "skipped": [], "components": [], "non_source": [], "would_write": [],
              "files": [], "existing_tests": []}
    if not any(is_source(f) for f in files):
        die("--files names no source file (" + ", ".join(files) + "): nothing to scaffold a test for")
    for rel in files:
        if not is_source(rel):   # docs, env, yaml, json …: no test file is ever generated for these
            report["non_source"].append(rel)
            report["files"].append({"source": rel, "kind": "non-source", "type": "not source", "layer": "—",
                                    "cover": "—", "test": "", "note": "skipped: not a source file (no stub generated)"})
            continue
        kind, ftype, layer, cover = classify(rel)
        if kind == "page":
            test_rel, content = f"{e2e_dir}/{slug(rel)}.spec.{ext}", e2e_stub(rel, title, bullets, e2e_dir)
        elif kind == "component":
            test_rel, content = f"{unit_dir}/{slug(rel)}.test.{cext}", ""
        else:
            test_rel = f"{unit_dir}/{slug(rel)}.test.{ext}"
            content = unit_stub(rel, title, bullets, test_rel, repo)
        row = {"source": rel, "kind": kind, "type": ftype, "layer": layer, "cover": cover, "test": test_rel}
        report["files"].append(row)
        if kind == "component":
            report["components"].append(test_rel)
            continue
        if refused:
            continue
        dest = target / test_rel
        existing = dest if dest.exists() else sibling_conflict(dest)
        if existing is not None:
            kept_rel = existing.relative_to(target).as_posix()
            row["test"] = kept_rel
            report["skipped"].append(kept_rel)
            titles = existing_titles(_read(existing))
            covered = [i for i, b in enumerate(bullets, 1) if any(covers(t, b) for t in titles)]
            report["existing_tests"].append({"test": kept_rel, "titles": titles, "criteria_covered": covered,
                                             "criteria_missing": [i for i in range(1, len(bullets) + 1) if i not in covered]})
            continue
        if a.dry_run:
            report["would_write"].append(test_rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        report["written"].append(test_rel)

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
              + (" — dry run, nothing written" if a.dry_run else "") + ".**", ""]
    if report["non_source"]:
        lines += ["Not source files — no stub generated (docs, env or config travel with the change, they are not tested here): "
                  + ", ".join(f"`{f}`" for f in report["non_source"]) + ".", ""]
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
        status = ("manual (component)" if r["kind"] == "component" else "refused" if refused
                  else "exists — kept" if r["test"] in report["skipped"] else "would write" if a.dry_run else "written")
        lines.append(f"| `{r['source']}` | {r['type']} | {r['layer']} | {r['cover']} | `{r['test']}` | {status} |")
    lines += ["", "## Criteria map", "", "| # | Criterion | Tests |", "|---|---|---|"]
    tests = ", ".join(f"`{r['test']}`" for r in report["files"] if r["kind"] not in ("component", "non-source")) or "—"
    for i, b in enumerate(bullets, 1):
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
          + f" [{flavour_name}, {repo['runner']}] -> {rp}, {pp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
