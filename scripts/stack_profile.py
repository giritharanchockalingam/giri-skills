#!/usr/bin/env python3
"""Read the stack facts of a repository — once, before stage 1 of a delivery pipeline. Never guessed.

    python3 scripts/stack_profile.py <repo> [--json stack-profile.json]

Every fact is read from a file in the repo and carries its evidence; a fact with no evidence is
"unknown" (strings), "none" (test_runner, e2e) or null (migrations_dir, monorepo_root, baselines):

  flavour          ts | js | python | unknown     tsconfig.json / .ts sources; jsconfig.json / .js sources;
                                                  pyproject.toml, setup.py, requirements.txt / .py sources
  framework        nextjs | nuxt | remix | sveltekit | vite-react | express | fastapi | django | flask | unknown
                                                  package.json dependencies, pyproject/requirements
  package_manager  pnpm | yarn | bun | npm | uv | poetry | pipenv | pip | unknown
                                                  lockfile, or package.json "packageManager"
  test_runner      vitest | jest | pytest | none   dependencies; pytest.ini / [tool.pytest] / tests/conftest.py
  e2e              playwright | cypress | none     dependencies or a playwright/cypress config file
  deploy_target    vercel | aws | azure | gcp | fly | railway | netlify | unknown
                                                  .github/workflows/*.yml, .vercel/project.json, vercel.json,
                                                  fly.toml, railway.json/toml, netlify.toml, package.json scripts
  migrations_dir   first of supabase/migrations, prisma/migrations, drizzle, migrations, alembic/versions,
                   db/migrate that exists (repo-relative) or null
  monorepo_root    the repo or an ancestor (<= 4 levels) holding pnpm-workspace.yaml, turbo.json, nx.json,
                   lerna.json or package.json "workspaces"; else null
  baselines        {nextjs, perf, ui, debt}: docs/baselines/<check>-findings.csv when present, else null —
                   the recorded debt the lint skills receive as their `baseline` input

An empty or missing directory yields a profile of unknowns (exit 0; `exists: false` when missing).
Output: sorted-key JSON, deterministic. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "coverage", "out", ".vercel", "vendor",
             ".venv", "venv", "__pycache__", ".turbo", ".cache"}
SOURCE_DIRS = ("app", "pages", "components", "lib", "server", "src", "utils", "hooks")
VERCEL_STRONG = re.compile(r"\bvercel\s+(?:deploy|pull|build|link|promote|rollback)\b|\bnpx\s+vercel\b"
                           r"|VERCEL_(?:TOKEN|ORG_ID|PROJECT_ID)\b|vercel-action|uses:\s*vercel/", re.I)
PROVIDERS = {
    "aws": re.compile(r"aws-actions/|amazon-ecr|\becs\b|\bcdk\b|\bsam\s+(?:build|deploy|package)\b"
                      r"|\baws\s+(?:ecs|ecr|s3|lambda|cloudformation|cloudfront)\b", re.I),
    "azure": re.compile(r"uses:\s*azure/|\baz\s+(?:webapp|containerapp|aks|functionapp)\b", re.I),
    "gcp": re.compile(r"google-github-actions|\bgcloud\s+run\b", re.I),
    "fly": re.compile(r"\bfly\.io\b|superfly/flyctl|\bflyctl\b", re.I),
    "railway": re.compile(r"\brailway\b", re.I),
    "netlify": re.compile(r"netlify/actions|\bnetlify\s+deploy\b", re.I),
}
FRAMEWORKS_JS = [("next", "nextjs"), ("nuxt", "nuxt"), ("@remix-run/react", "remix"), ("@sveltejs/kit", "sveltekit"),
                 ("express", "express")]
FRAMEWORKS_PY = [("fastapi", "fastapi"), ("django", "django"), ("flask", "flask")]
MIGRATION_DIRS = ("supabase/migrations", "prisma/migrations", "drizzle", "migrations", "alembic/versions", "db/migrate")
MONOREPO_MARKERS = ("pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json")
BASELINE_CHECKS = ("nextjs", "perf", "ui", "debt")


def walk(root: Path, exts: tuple[str, ...], limit: int = 4000) -> list[Path]:
    out: list[Path] = []
    stack = [root]
    while stack and len(out) < limit:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in SKIP_DIRS and not p.name.startswith("."):
                    stack.append(p)
            elif p.suffix in exts:
                out.append(p)
    return out


def read_json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def deps_of(pkg: dict) -> dict:
    d = {}
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        v = pkg.get(k)
        if isinstance(v, dict):
            d.update({str(a): str(b) for a, b in v.items()})
    return d


def python_requirements(repo: Path) -> str:
    text = ""
    for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.py", "setup.cfg", "Pipfile"):
        p = repo / name
        if p.is_file():
            text += "\n" + read_text(p).lower()
    return text


def detect_flavour(repo: Path, pkg: dict, py_text: str) -> tuple[str, str]:
    if (repo / "tsconfig.json").is_file():
        return "ts", "tsconfig.json"
    ts = [p for p in walk(repo, (".ts", ".tsx")) if not p.name.endswith(".d.ts")]
    if ts:
        return "ts", f"{len(ts)} .ts/.tsx source file(s)"
    if (repo / "jsconfig.json").is_file():
        return "js", "jsconfig.json, no tsconfig.json"
    js = walk(repo, (".js", ".jsx", ".mjs", ".cjs"))
    if js and (pkg or any(p.parts[len(repo.parts)] in SOURCE_DIRS for p in js if len(p.parts) > len(repo.parts) + 1)):
        return "js", f"{len(js)} .js/.jsx source file(s), no tsconfig.json"
    if pkg:
        return "js", "package.json without tsconfig.json or .ts sources"
    if py_text.strip() or walk(repo, (".py",)):
        return "python", "pyproject.toml / requirements.txt / setup.py or .py sources"
    return "unknown", "no package.json, tsconfig.json, jsconfig.json, Python project file or sources"


def detect_framework(pkg: dict, py_text: str) -> tuple[str, str]:
    deps = deps_of(pkg)
    for dep, name in FRAMEWORKS_JS:
        if dep in deps:
            return name, f"package.json depends on {dep}"
    if "vite" in deps and "react" in deps:
        return "vite-react", "package.json depends on vite and react"
    for dep, name in FRAMEWORKS_PY:
        if re.search(rf"(?m)^\s*(?:\"|')?{dep}\b", py_text) or re.search(rf"[\"'\[,\s]{dep}(?:[>=<~\[\"'\s,]|$)", py_text):
            return name, f"Python project file names {dep}"
    return "unknown", "no known framework dependency"


def detect_package_manager(repo: Path, pkg: dict, py_text: str) -> tuple[str, str]:
    pm = str(pkg.get("packageManager", ""))
    if pm:
        return pm.split("@")[0], f"package.json packageManager {pm}"
    for lock, name in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun"),
                       ("package-lock.json", "npm")):
        if (repo / lock).is_file():
            return name, lock
    for lock, name in (("uv.lock", "uv"), ("poetry.lock", "poetry"), ("Pipfile.lock", "pipenv"), ("Pipfile", "pipenv"),
                       ("requirements.txt", "pip")):
        if (repo / lock).is_file():
            return name, lock
    if "[tool.poetry]" in py_text:
        return "poetry", "pyproject.toml [tool.poetry]"
    if "[tool.uv]" in py_text:
        return "uv", "pyproject.toml [tool.uv]"
    return "unknown", "no lockfile or packageManager field"


def detect_test_runner(repo: Path, pkg: dict, py_text: str) -> tuple[str, str]:
    deps = deps_of(pkg)
    if "vitest" in deps:
        return "vitest", "package.json depends on vitest"
    if "jest" in deps:
        return "jest", "package.json depends on jest"
    if any((repo / f).is_file() for f in ("vitest.config.ts", "vitest.config.js", "vitest.config.mts", "vitest.config.mjs")):
        return "vitest", "vitest config file"
    if any((repo / f).is_file() for f in ("jest.config.ts", "jest.config.js", "jest.config.mjs", "jest.config.cjs")):
        return "jest", "jest config file"
    if "pytest" in py_text or (repo / "pytest.ini").is_file() or (repo / "tests" / "conftest.py").is_file() \
            or (repo / "conftest.py").is_file():
        return "pytest", "pytest in project file, pytest.ini or conftest.py"
    return "none", "no test runner dependency or config"


def detect_e2e(repo: Path, pkg: dict) -> tuple[str, str]:
    deps = deps_of(pkg)
    if "@playwright/test" in deps or "playwright" in deps:
        return "playwright", "package.json depends on playwright"
    if any((repo / f).is_file() for f in ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs",
                                           "playwright.config.cjs")):
        return "playwright", "playwright config file"
    if "cypress" in deps or any((repo / f).is_file() for f in ("cypress.config.ts", "cypress.config.js")):
        return "cypress", "cypress dependency or config"
    return "none", "no e2e dependency or config"


def detect_deploy(repo: Path, pkg: dict) -> tuple[str, str]:
    signals: dict[str, list[str]] = {}

    def add(name: str, why: str) -> None:
        signals.setdefault(name, []).append(why)

    wf = repo / ".github" / "workflows"
    if wf.is_dir():
        for f in sorted(wf.iterdir()):
            if f.suffix not in (".yml", ".yaml"):
                continue
            text = read_text(f)
            rel = f".github/workflows/{f.name}"
            if VERCEL_STRONG.search(text):
                add("vercel", rel)
            for name, rx in PROVIDERS.items():
                if rx.search(text):
                    add(name, rel)
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    for name, cmd in sorted(scripts.items()):
        if re.search(r"\bvercel\b", str(cmd)):
            add("vercel", f"package.json scripts.{name}")
    if (repo / ".vercel" / "project.json").is_file():
        add("vercel", ".vercel/project.json")
    if (repo / "fly.toml").is_file():
        add("fly", "fly.toml")
    if (repo / "railway.json").is_file() or (repo / "railway.toml").is_file():
        add("railway", "railway.json/toml")
    if (repo / "netlify.toml").is_file():
        add("netlify", "netlify.toml")
    if "vercel" in signals:
        return "vercel", ", ".join(signals["vercel"])
    others = [n for n in ("aws", "azure", "gcp", "fly", "railway", "netlify") if n in signals]
    if len(others) == 1:
        return others[0], ", ".join(signals[others[0]])
    if len(others) > 1:
        return "unknown", "conflicting deploy signals: " + "; ".join(f"{n}: {', '.join(signals[n])}" for n in others)
    if (repo / "vercel.json").is_file():
        return "vercel", "vercel.json (weak: config only, no link or deploy step)"
    return "unknown", "no deploy workflow, link or platform config"


def detect_migrations(repo: Path) -> str | None:
    for rel in MIGRATION_DIRS:
        if (repo / rel).is_dir():
            return rel
    return None


def detect_monorepo(repo: Path) -> str | None:
    cur = repo
    for _ in range(5):
        if any((cur / m).is_file() for m in MONOREPO_MARKERS):
            return str(cur)
        pkg = read_json(cur / "package.json") if (cur / "package.json").is_file() else {}
        if pkg.get("workspaces"):
            return str(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def detect_baselines(repo: Path) -> dict:
    out = {}
    for check in BASELINE_CHECKS:
        p = repo / "docs" / "baselines" / f"{check}-findings.csv"
        out[check] = str(p) if p.is_file() else None
    return out


def profile(repo: Path) -> dict:
    repo = repo.expanduser().resolve()
    exists = repo.is_dir()
    pkg = read_json(repo / "package.json") if exists and (repo / "package.json").is_file() else {}
    py_text = python_requirements(repo) if exists else ""
    if not exists:
        facts = {k: ("unknown", "directory does not exist") for k in ("flavour", "framework", "package_manager", "deploy_target")}
        facts.update(test_runner=("none", "directory does not exist"), e2e=("none", "directory does not exist"))
        mig, mono, baselines = None, None, {c: None for c in BASELINE_CHECKS}
    else:
        facts = {"flavour": detect_flavour(repo, pkg, py_text), "framework": detect_framework(pkg, py_text),
                 "package_manager": detect_package_manager(repo, pkg, py_text),
                 "test_runner": detect_test_runner(repo, pkg, py_text), "e2e": detect_e2e(repo, pkg),
                 "deploy_target": detect_deploy(repo, pkg)}
        mig, mono, baselines = detect_migrations(repo), detect_monorepo(repo), detect_baselines(repo)
    out = {k: v[0] for k, v in facts.items()}
    out.update({"repo": str(repo), "exists": exists, "migrations_dir": mig, "monorepo_root": mono,
                "baselines": baselines, "has_package_json": bool(pkg),
                "evidence": {k: v[1] for k, v in facts.items()}})
    out["evidence"]["migrations_dir"] = mig or "none of " + ", ".join(MIGRATION_DIRS)
    out["evidence"]["monorepo_root"] = mono or "no workspace marker in the repo or its ancestors"
    out["evidence"]["baselines"] = "docs/baselines/<check>-findings.csv per check"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Read a repository's stack profile (facts with evidence, never guessed)")
    ap.add_argument("repo")
    ap.add_argument("--json", metavar="FILE", help="write the profile here (default: stdout)")
    a = ap.parse_args()
    data = profile(Path(a.repo))
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(text, encoding="utf-8")
        print(f"stack profile: {data['flavour']}/{data['framework']} pm={data['package_manager']} "
              f"tests={data['test_runner']} e2e={data['e2e']} deploy={data['deploy_target']} -> {a.json}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
