"""Brownfield JavaScript repo for build/test-strategy-tdd: read before write (flavour, runner, dirs, alias).

Regression for the defect found on a real JavaScript Next.js 14 repo: page.js was classified as a unit,
components/*.js were not recognised as components, and .test.ts / .spec.ts files were written into a repo whose
vitest.config.js only runs *.test.js.
"""
from __future__ import annotations

import json
import shutil

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/test-strategy-tdd"
SCRIPT = SK / "scripts/scaffold_tests.py"
SEED = SK / "scripts/seed_repo.py"
FEATURE = SK / "evals/fixtures/feature-coach.md"
JS_REPO = SK / "evals/fixtures/repo-existing-js"
FILES = "app/portal/page.js,components/AppShell.js,lib/coach.js,app/api/health/route.js"


def scaffold(tmp_path, repo, *extra, feature=FEATURE, files=FILES):
    rep, plan = tmp_path / "r.json", tmp_path / "p.md"
    res = run_script(SCRIPT, str(feature), "--files", files, "--target", str(repo), *extra,
                     "--report", str(rep), "--plan", str(plan))
    data = json.loads(rep.read_text(encoding="utf-8")) if rep.exists() else None
    return res, data, (plan.read_text(encoding="utf-8") if plan.exists() else "")


def seeded(tmp_path):
    repo = tmp_path / "repo"
    assert run_script(SEED, "--from", str(JS_REPO), "--target", str(repo)).returncode == 0
    return repo


def test_js_nextjs_repo_gets_js_stubs_in_its_own_layout(tmp_path):
    repo = seeded(tmp_path)
    before = {p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8") for p in repo.rglob("*") if p.is_file()}
    res, data, plan = scaffold(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    r = data["repo"]
    assert (r["flavour"], r["runner"], r["unit_dir"], r["e2e_dir"], r["alias"]) == ("js", "vitest", "tests/unit", "tests/e2e", "@/")
    assert r["unit_config"] == "vitest.config.js" and r["e2e_config"] == "playwright.config.js"
    kinds = {f["source"]: f["kind"] for f in data["files"]}
    assert kinds == {"app/portal/page.js": "page", "components/AppShell.js": "component",
                     "lib/coach.js": "unit", "app/api/health/route.js": "unit"}
    assert data["written"] == ["tests/e2e/app-portal-page.spec.js", "tests/unit/app-api-health-route.test.js"]
    assert data["components"] == ["tests/unit/components-appshell.test.jsx"]
    assert data["skipped"] == ["tests/unit/lib-coach.test.js"]
    (e,) = data["existing_tests"]
    assert e["criteria_covered"] == [3] and e["criteria_missing"] == [1, 2]
    # nothing that existed changed, and no TypeScript file entered the JavaScript repo
    after = {p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8") for p in repo.rglob("*") if p.is_file()}
    assert all(after[k] == v for k, v in before.items())
    assert not [k for k in after if k.endswith((".ts", ".tsx"))]
    e2e = after["tests/e2e/app-portal-page.spec.js"]
    assert 'await page.goto("/portal");' in e2e and e2e.count("test.fixme(") == 4
    unit = after["tests/unit/app-api-health-route.test.js"]
    assert 'import { describe, it, expect } from "vitest";' in unit and '"@/app/api/health/route"' in unit
    assert "## Repo (read before write)" in plan and "| Flavour | JavaScript (`.test.js` / `.spec.js`) |" in plan
    assert "| `tests/unit/lib-coach.test.js` | 1 | #3 |" in plan


def test_other_flavour_sibling_counts_as_existing(tmp_path):
    repo = seeded(tmp_path)
    (repo / "tests/unit/lib-coach.test.js").unlink()
    stray = repo / "tests/unit/lib-coach.test.ts"
    stray.write_text('it("a nudge older than 30 days is never shown", () => {});\n', encoding="utf-8")
    res, data, _ = scaffold(tmp_path, repo, files="lib/coach.js")
    assert res.returncode == 0, res.stderr
    assert data["written"] == [] and data["skipped"] == ["tests/unit/lib-coach.test.ts"]
    assert not (repo / "tests/unit/lib-coach.test.js").exists()          # no conflicting pair created
    assert data["existing_tests"][0]["criteria_covered"] == [3]


def test_dirs_follow_existing_configs(tmp_path):
    repo = seeded(tmp_path)
    (repo / "vitest.config.js").write_text('export default { test: { include: ["spec/unit/**/*.test.js"] } };\n', encoding="utf-8")
    (repo / "playwright.config.js").write_text('export default { testDir: "./e2e" };\n', encoding="utf-8")
    res, data, _ = scaffold(tmp_path, repo, files="app/portal/page.js,lib/coach.js")
    assert res.returncode == 0, res.stderr
    assert data["written"] == ["e2e/app-portal-page.spec.js", "spec/unit/lib-coach.test.js"]
    assert 'storageState: "e2e/.auth/member.json"' in (repo / "e2e/app-portal-page.spec.js").read_text(encoding="utf-8")


def test_jest_repo_has_no_vitest_import_and_relative_imports(tmp_path):
    repo = tmp_path / "repo"
    (repo / "lib").mkdir(parents=True)
    (repo / "package.json").write_text(json.dumps({"devDependencies": {"jest": "^29"}}), encoding="utf-8")
    (repo / "lib/coach.js").write_text("export const x = 1;\n", encoding="utf-8")
    res, data, _ = scaffold(tmp_path, repo, files="lib/coach.js")
    assert res.returncode == 0, res.stderr
    assert data["repo"]["runner"] == "jest" and data["repo"]["flavour"] == "js" and data["repo"]["alias"] is None
    unit = (repo / "tests/unit/lib-coach.test.js").read_text(encoding="utf-8")
    assert "vitest" not in unit and '"../../lib/coach"' in unit and "jest: describe / it / expect are globals" in unit


def test_tsconfig_wins_over_js_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tsconfig.json").write_text('{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}', encoding="utf-8")
    res, data, _ = scaffold(tmp_path, repo, files="lib/legacy.js,app/portal/page.js")
    assert res.returncode == 0, res.stderr
    assert data["repo"]["flavour"] == "ts"
    assert data["written"] == ["tests/unit/lib-legacy.test.ts", "tests/e2e/app-portal-page.spec.ts"]


def test_greenfield_defaults_unchanged(tmp_path):
    res, data, _ = scaffold(tmp_path, tmp_path / "fresh", feature=SK / "evals/fixtures/feature.md",
                            files="server/services/export-service.ts,app/(app)/invoices/page.tsx")
    assert res.returncode == 0, res.stderr
    assert data["repo"]["flavour"] == "ts" and data["repo"]["alias"] == "@/"
    assert data["written"] == ["tests/unit/server-services-export-service.test.ts", "tests/e2e/app-app-invoices-page.spec.ts"]


def test_unsupported_runner_refuses_and_writes_nothing(tmp_path):
    repo = seeded(tmp_path)
    (repo / "package.json").write_text(json.dumps({"scripts": {"test": "mocha"}, "devDependencies": {"mocha": "^10"}}), encoding="utf-8")
    before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file())
    res, data, plan = scaffold(tmp_path, repo)
    assert res.returncode == 1 and "refused" in res.stderr
    assert data["refused"] and "mocha" in data["refused"]
    assert data["written"] == [] and data["would_write"] == [] and data["skipped"] == []
    assert sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file()) == before
    assert "**Refused — nothing written.**" in plan


def test_dry_run_on_js_repo_names_js_files_only(tmp_path):
    repo = seeded(tmp_path)
    res, data, _ = scaffold(tmp_path, repo, "--dry-run")
    assert res.returncode == 0 and data["would_write"] == ["tests/e2e/app-portal-page.spec.js", "tests/unit/app-api-health-route.test.js"]
    assert not (repo / "tests/e2e/app-portal-page.spec.js").exists()


def test_fixture_is_never_written_to():
    files = sorted(p.relative_to(JS_REPO).as_posix() for p in JS_REPO.rglob("*") if p.is_file())
    assert files == ["app/api/health/route.js", "app/portal/page.js", "components/AppShell.js", "jsconfig.json", "lib/coach.js",
                     "package.json", "playwright.config.js", "tests/e2e/smoke.spec.js", "tests/unit/lib-coach.test.js",
                     "vitest.config.js"]
    assert shutil.which("python3") is not None


# ---- flavour: --flavour wins; only source files count; build output is never evidence; non-source files are skipped

def test_js_repo_with_docs_and_env_in_the_files_list_gets_js_stubs_and_skips_them_with_a_note(tmp_path):
    """Defect from the first real delivery run: files.txt carried .env.example and docs/RUNBOOK.md, the all-JS rule
    failed and TypeScript stubs (plus docs-runbook-md.test.ts) were written into a JavaScript repo."""
    repo = seeded(tmp_path)
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "RUNBOOK.md").write_text("# Runbook\n", encoding="utf-8")
    (repo / ".env.example").write_text("APP_URL=\n", encoding="utf-8")
    res, data, plan = scaffold(tmp_path, repo, files="lib/coach.js,app/api/health/route.js,.env.example,docs/RUNBOOK.md")
    assert res.returncode == 0, res.stderr
    assert data["repo"]["flavour"] == "js"
    assert data["non_source"] == [".env.example", "docs/RUNBOOK.md"]
    assert all(t.endswith(".test.js") for t in data["written"]) and data["written"]
    assert not list(repo.rglob("*.test.ts")) and not list(repo.rglob("docs-runbook-md.test.*")) and not list(repo.rglob("env-example.test.*"))
    rows = {f["source"]: f for f in data["files"]}
    assert rows["docs/RUNBOOK.md"]["kind"] == "non-source" and rows["docs/RUNBOOK.md"]["test"] == ""
    assert "2 non-source file(s) skipped" in plan and "`docs/RUNBOOK.md`" in plan and "skipped (not a source file)" in plan
    assert "non-source skipped" in res.stdout


def test_flavour_flag_wins_over_detection(tmp_path):
    repo = seeded(tmp_path)                                                   # a JavaScript repo
    res, data, _ = scaffold(tmp_path, repo, "--flavour", "ts", files="lib/other.js")
    assert res.returncode == 0 and data["repo"]["flavour"] == "ts" and "--flavour ts" in data["repo"]["flavour_why"]
    assert data["written"] == ["tests/unit/lib-other.test.ts"]
    ts_repo = tmp_path / "ts"
    ts_repo.mkdir(); (ts_repo / "tsconfig.json").write_text("{}", encoding="utf-8")
    res, data, _ = scaffold(tmp_path, ts_repo, "--flavour", "js", files="lib/a.ts")
    assert res.returncode == 0 and data["repo"]["flavour"] == "js" and data["written"] == ["tests/unit/lib-a.test.js"]
    res, data, _ = scaffold(tmp_path / "u", ts_repo, "--flavour", "unknown", files="lib/b.ts")   # a profile's unknown flavour
    assert res.returncode == 0 and data["repo"]["flavour"] == "ts" and "ignored" in data["repo"]["flavour_why"]


def test_build_output_and_jsconfig_never_make_a_js_repo_typescript(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "page.js").write_text("export default function Page() { return null }\n", encoding="utf-8")
    (repo / "package.json").write_text('{"name": "x", "devDependencies": {"vitest": "1"}}', encoding="utf-8")
    for junk in (".next/types/app/page.ts", "app/.next/types/layout.ts", "lib/dist/index.ts", "lib/node_modules/pkg/index.ts",
                 "src/coverage/lcov.ts", "lib/.cache/x.ts"):
        (repo / junk).parent.mkdir(parents=True, exist_ok=True)
        (repo / junk).write_text("export {};\n", encoding="utf-8")
    res, data, _ = scaffold(tmp_path, repo, files="app/page.js,docs/README.md")
    assert res.returncode == 0, res.stderr
    assert data["repo"]["flavour"] == "js" and data["written"] == ["tests/e2e/app-page.spec.js"]
    (repo / "jsconfig.json").write_text('{"compilerOptions": {"paths": {"@/*": ["./*"]}}}', encoding="utf-8")
    res, data, _ = scaffold(tmp_path / "j", repo, files="lib/util.js,docs/README.md")
    assert data["repo"]["flavour"] == "js" and data["repo"]["flavour_why"] == "jsconfig.json present, no tsconfig.json"
    res, data, _ = scaffold(tmp_path / "n", repo, files="docs/README.md,.env.example")
    assert res.returncode == 1 and "names no source file" in res.stderr
