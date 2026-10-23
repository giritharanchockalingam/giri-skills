"""build/project-bootstrap: the minimal runnable application skeleton (--stack nextjs-js|nextjs-ts).

No npm install here: the checks are static — the files exist, the stack profile reads them, the conventions
linter passes, the CI workflow calls only scripts package.json declares.
"""
from __future__ import annotations

import json
import re

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/project-bootstrap"
SCAFFOLD = SK / "scripts/scaffold.py"
SEED = SK / "scripts/seed_repo.py"
FX = SK / "evals/fixtures/repo-existing"
PROFILE = REPO_ROOT / "scripts/stack_profile.py"
LINT = REPO_ROOT / "skills/build/nextjs-enterprise-conventions/scripts/lint_conventions.py"

OBS_INSTALL = REPO_ROOT / "skills/build/observability-setup/scripts/install.py"

# the observability kit (build/observability-setup, install.py's PLAN minus the liveness route the skeleton owns)
KIT = ["lib/logger.{ext}", "lib/logger/context.{ext}", "app/api/health/deep/route.{ext}", "ops/alerts.yaml", "docs/observability.md",
       "lib/supabase/admin.{ext}", "tests/unit/health-deep.test.{ext}", "tests/unit/logger.test.{ext}", "tests/unit/supabase-admin.test.{ext}"]
JS_SKELETON = ["package.json", "next.config.js", "jsconfig.json", ".eslintrc.json", "vitest.config.js",
               "app/layout.js", "app/page.js", "app/api/health/route.js", "lib/app-info.js",
               "tests/unit/health.test.js", ".gitignore"] + [k.format(ext="js") for k in KIT]
TS_SKELETON = ["package.json", "next.config.js", "tsconfig.json", ".eslintrc.json", "vitest.config.ts",
               "app/layout.tsx", "app/page.tsx", "app/api/health/route.ts", "lib/app-info.ts",
               "tests/unit/health.test.ts", ".gitignore"] + [k.format(ext="ts") for k in KIT]


def scaffold(tmp_path, *extra, name="Demo App"):
    proj, rep = tmp_path / "proj", tmp_path / "report.json"
    r = run_script(SCAFFOLD, "--target", str(proj), "--name", name, "--report", str(rep), *extra)
    assert r.returncode == 0, r.stderr
    return proj, json.loads(rep.read_text(encoding="utf-8")), r


def profile(proj) -> dict:
    r = run_script(PROFILE, str(proj))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_new_repo_writes_js_skeleton_and_profile_reads_it(tmp_path):
    proj, rep, _ = scaffold(tmp_path)
    assert rep["stack"] == "nextjs-js" and rep["app_skeleton"] == "written" and rep["observability"] == "written"
    for f in JS_SKELETON:
        assert (proj / f).is_file(), f
        assert f in rep["written"], f
    assert not (proj / "tsconfig.json").exists()
    p = profile(proj)
    assert (p["framework"], p["flavour"], p["test_runner"], p["package_manager"]) == ("nextjs", "js", "vitest", "npm")
    assert p["deploy_target"] == "vercel"


def test_nextjs_ts_variant(tmp_path):
    proj, rep, _ = scaffold(tmp_path, "--stack", "nextjs-ts")
    assert rep["stack"] == "nextjs-ts"
    for f in TS_SKELETON:
        assert (proj / f).is_file(), f
    assert not (proj / "jsconfig.json").exists() and not (proj / "app/page.js").exists() and not (proj / "lib/logger.js").exists()
    assert rep["observability"] == "written"
    pkg = json.loads((proj / "package.json").read_text(encoding="utf-8"))
    assert pkg["scripts"]["typecheck"] == "tsc --noEmit"
    assert {"typescript", "@types/react", "@types/node"} <= set(pkg["devDependencies"])
    assert '"strict": true' in (proj / "tsconfig.json").read_text(encoding="utf-8")
    p = profile(proj)
    assert (p["framework"], p["flavour"], p["test_runner"], p["package_manager"]) == ("nextjs", "ts", "vitest", "npm")


def test_package_json_contract(tmp_path):
    proj, _, _ = scaffold(tmp_path)
    pkg = json.loads((proj / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "demo-app" and pkg["private"] is True
    assert {"dev", "build", "start", "lint", "typecheck", "test"} <= set(pkg["scripts"])
    assert pkg["scripts"]["test"] == "vitest run"
    assert pkg["dependencies"]["next"].startswith("^14.")
    assert {"react", "react-dom"} <= set(pkg["dependencies"])
    assert "vitest" in pkg["devDependencies"] and "@vitest/coverage-v8" in pkg["devDependencies"]
    for ver in list(pkg["dependencies"].values()) + list(pkg["devDependencies"].values()):
        assert re.fullmatch(r"\^\d+\.\d+\.\d+", ver), ver          # pinned caret ranges, never "latest" or "*"
    assert "@supabase" not in (proj / "package.json").read_text(encoding="utf-8").lower()   # the client library is feature work, not bootstrap
    assert pkg["dependencies"]["server-only"] == "^0.0.1"                                   # imported by the kit's deep route and lib/supabase/admin


def test_ci_workflow_matches_skeleton(tmp_path):
    proj, _, _ = scaffold(tmp_path)
    ci = (proj / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    pkg = json.loads((proj / "package.json").read_text(encoding="utf-8"))
    for script in re.findall(r"npm run (\w[\w:-]*)", ci):
        assert script in pkg["scripts"], f"ci.yml calls npm run {script}, not in package.json"
    assert "npm ci" in ci and "npm test -- --coverage" in ci
    assert "hashFiles('package-lock.json')" in ci          # fresh bootstrap has no lockfile yet: install still works
    assert "hashFiles('scripts/rls_lint.py')" in ci        # RLS lint only once supabase-schema-rls installed it
    vit = (proj / "vitest.config.js").read_text(encoding="utf-8")
    assert "json-summary" in vit                           # feeds the coverage gate (coverage-summary.json)


def test_skeleton_passes_nextjs_conventions_with_zero_high(tmp_path):
    for stack in ("nextjs-js", "nextjs-ts"):
        sub = tmp_path / stack
        sub.mkdir()
        proj, _, _ = scaffold(sub, "--stack", stack)
        r = run_script(LINT, "--target", str(proj), "--findings", str(sub / "f.csv"), "--report", str(sub / "r.md"), "--quiet")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "0 high" in r.stdout


def test_health_route_is_liveness_only_and_tested(tmp_path):
    proj, _, _ = scaffold(tmp_path)
    route = (proj / "app/api/health/route.js").read_text(encoding="utf-8")
    assert "export function GET" in route and "ok: true" in route
    assert "force-dynamic" in route and "no-store" in route and "toISOString" in route
    assert not re.search(r"\bfetch\s*\(|supabase|createClient", route)   # observability's liveness rule
    test = (proj / "tests/unit/health.test.js").read_text(encoding="utf-8")
    assert 'from "vitest"' in test and '"@/app/api/health/route"' in test and "body.ok).toBe(true)" in test
    gi = (proj / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules" in gi and ".next" in gi and ".env*" in gi and "!.env.example" in gi


def test_security_headers_in_next_config(tmp_path):
    proj, _, _ = scaffold(tmp_path)
    cfg = (proj / "next.config.js").read_text(encoding="utf-8")
    for h in ("Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"):
        assert h in cfg, h
    assert "poweredByHeader: false" in cfg


def obs_dry_run(tmp_path, proj) -> dict:
    """observability-setup's own installer, dry run, on the bootstrapped repo — what the portal's PR gate runs."""
    rj = tmp_path / "install-report.json"
    r = run_script(OBS_INSTALL, "--target", str(proj), "--dry-run", "--report-json", str(rj), "--report-md", str(tmp_path / "install-report.md"))
    assert r.returncode == 0, r.stderr
    return json.loads(rj.read_text(encoding="utf-8"))


def observability_missing(written: list[str]) -> list[str]:
    """Mirror of studio/lib/scorecards/checks.ts observabilityMissing(): context.* only counts when the logger itself is missing."""
    no_logger = any(re.fullmatch(r"lib/logger\.[a-z]+", p) for p in written)
    return [p for p in written if no_logger or not re.fullmatch(r"lib/logger/context\.[a-z]+", p)]


def test_fresh_bootstrap_has_every_observability_piece(tmp_path):
    """G6: the PR gate "Observability (logging, health, alerts)" passed nothing on the first greenfield repo. Now a fresh
    bootstrap, js or ts, leaves install.py --dry-run with nothing to write and nothing to propose."""
    for stack, ext in (("nextjs-js", "js"), ("nextjs-ts", "ts")):
        sub = tmp_path / stack
        sub.mkdir()
        proj, rep, out = scaffold(sub, "--stack", stack, name="demo-app")
        for k in KIT:
            assert k.format(ext=ext) in rep["written"], k
        d = obs_dry_run(sub, proj)
        assert d["flavour"] == ext
        assert d["written"] == [] and observability_missing(d["written"]) == []      # scorecard: 0 missing
        assert d["proposed"] == [] and d["conflicts"] == []                            # identical to the kit, not "customised"
        assert sorted(s["path"] for s in d["skipped"]) == sorted([f"lib/logger.{ext}", f"lib/logger/context.{ext}", f"app/api/health/deep/route.{ext}", "ops/alerts.yaml", "docs/observability.md"])
        assert [k["path"] for k in d["kept"]] == [f"app/api/health/route.{ext}"]      # the skeleton's own liveness route
        assert d["health_gaps"][0]["missing"] == []                                    # gap-free against the standard
        assert d["console_calls"] == []
        env = (proj / ".env.example").read_text(encoding="utf-8")
        for var in ("LOG_LEVEL", "LOG_PRETTY", "SERVICE_NAME", "HEALTH_CHECK_TOKEN", "NEXT_PUBLIC_SUPABASE_URL"):
            assert re.search(rf"^{var}=", env, re.M), var
        assert "# Observability — proj" in (proj / "docs/observability.md").read_text(encoding="utf-8")   # install.py's own label: the target dir


def test_kit_files_are_the_observability_assets_verbatim(tmp_path):
    """No duplicated templates: the written kit files are install.py's assets (project substituted), byte for byte."""
    proj, _, _ = scaffold(tmp_path, "--stack", "nextjs-ts", name="demo-app")
    assets = REPO_ROOT / "skills/build/observability-setup/assets"
    assert (proj / "lib/logger.ts").read_text(encoding="utf-8") == (assets / "logger.ts").read_text(encoding="utf-8")
    assert (proj / "app/api/health/deep/route.ts").read_text(encoding="utf-8") == (assets / "health-deep-route.ts").read_text(encoding="utf-8")
    assert (proj / "ops/alerts.yaml").read_text(encoding="utf-8") == (assets / "alert-rules.yaml").read_text(encoding="utf-8")
    assert (proj / "docs/observability.md").read_text(encoding="utf-8") == (assets / "slo-starter.md").read_text(encoding="utf-8").replace("{{PROJECT}}", "proj")


def test_deep_health_and_logger_have_unit_tests(tmp_path):
    proj, _, _ = scaffold(tmp_path)
    deep = (proj / "tests/unit/health-deep.test.js").read_text(encoding="utf-8")
    assert 'from "@/app/api/health/deep/route"' in deep and 'vi.mock("server-only"' in deep and 'vi.mock("@/lib/supabase/admin"' in deep
    for title in ("requires the bearer token", "answers 503 down when a required dependency", "answers 200 degraded"):
        assert title in deep, title
    logger = (proj / "tests/unit/logger.test.js").read_text(encoding="utf-8")
    assert 'from "@/lib/logger"' in logger and "redacts secrets" in logger and "withLogContext" in logger
    admin = (proj / "lib/supabase/admin.js").read_text(encoding="utf-8")
    assert 'import "server-only"' in admin and "NOT_CONFIGURED" in admin and "@supabase/supabase-js" in admin   # placeholder says what replaces it
    assert "createClient(" not in admin.replace("//   return createClient(", "")                                 # no client library call yet


def test_existing_kit_file_is_kept_and_reported(tmp_path):
    """A target with no package.json but its own logger: install.py's plan keeps it (never overwrites) and the report says why."""
    proj = tmp_path / "proj"
    (proj / "lib").mkdir(parents=True)
    (proj / "lib/logger.js").write_text("// THEIR LOGGER\n", encoding="utf-8")
    rep = tmp_path / "report.json"
    r = run_script(SCAFFOLD, "--target", str(proj), "--name", "x", "--report", str(rep))
    assert r.returncode == 0, r.stderr
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert (proj / "lib/logger.js").read_text(encoding="utf-8") == "// THEIR LOGGER\n"
    assert "lib/logger.js" in data["kept"] and "lib/logger.js" not in data["written"]
    assert "keep   lib/logger.js (observability:" in r.stdout
    assert "lib/logger/context.js" in data["written"] and "app/api/health/deep/route.js" in data["written"]
    assert data["observability"] == "written"


def test_existing_repo_with_package_json_gets_no_skeleton(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "package.json").write_text('{"name": "theirs", "dependencies": {"next": "13.5.0"}}', encoding="utf-8")
    rep = tmp_path / "report.json"
    r = run_script(SCAFFOLD, "--target", str(proj), "--name", "theirs", "--report", str(rep))
    assert r.returncode == 0, r.stderr
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert data["app_skeleton"] == "kept" and data["observability"] == "kept" and "package.json" in data["kept"]
    assert "keep   package.json" in r.stdout
    for f in ("app/page.js", "app/api/health/route.js", "jsconfig.json", "next.config.js", ".gitignore", "tests/unit/health.test.js",
              "lib/logger.js", "lib/logger/context.js", "app/api/health/deep/route.js", "ops/alerts.yaml", "docs/observability.md", "lib/supabase/admin.js"):
        assert not (proj / f).exists(), f
        assert f not in data["written"]
    assert (proj / "package.json").read_text(encoding="utf-8").startswith('{"name": "theirs"')
    assert (proj / "docs/SPEC.md").is_file() and ".github/workflows/ci.yml" in data["written"]


def test_existing_docs_without_package_json_still_get_skeleton(tmp_path):
    proj = tmp_path / "proj"
    assert run_script(SEED, "--from", str(FX), "--target", str(proj)).returncode == 0
    rep = tmp_path / "report.json"
    r = run_script(SCAFFOLD, "--target", str(proj), "--name", "tidewater-booking", "--report", str(rep))
    assert r.returncode == 0, r.stderr
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert data["kept"] == ["docs/SPEC.md", "CLAUDE.md"] and data["app_skeleton"] == "written" and data["observability"] == "written"
    assert (proj / "package.json").is_file() and (proj / "app/api/health/route.js").is_file() and (proj / "lib/logger.js").is_file()


def test_skeleton_is_idempotent_and_dry_run_writes_nothing(tmp_path):
    proj, _, _ = scaffold(tmp_path)
    (proj / "app/page.js").write_text("// USER EDIT", encoding="utf-8")
    rep = tmp_path / "report2.json"
    r = run_script(SCAFFOLD, "--target", str(proj), "--name", "Demo App", "--report", str(rep))
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert r.returncode == 0 and data["written"] == [] and data["app_skeleton"] == "kept" and data["observability"] == "kept"
    assert (proj / "app/page.js").read_text(encoding="utf-8") == "// USER EDIT"
    d = run_script(SCAFFOLD, "--target", str(tmp_path / "dry"), "--name", "x", "--stack", "nextjs-ts", "--dry-run")
    assert d.returncode == 0 and "would write app/page.tsx" in d.stdout and not (tmp_path / "dry").exists()


def test_bad_stack_rejected(tmp_path):
    r = run_script(SCAFFOLD, "--target", str(tmp_path / "p"), "--name", "x", "--stack", "remix")
    assert r.returncode == 2
