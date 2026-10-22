"""Read-before-write for build/observability-setup/scripts/install.py: language flavour, no .ts/.js siblings,
'exists, kept' health routes with a gap table, env vars only for written files, conflict abort (exit 1)."""
from __future__ import annotations

import json
import shutil

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/observability-setup"
INSTALL = SK / "scripts/install.py"
SIBLINGS = SK / "scripts/check_siblings.py"
FX_JS = SK / "evals/fixtures/repo-js-existing-health"
FX_TS = SK / "evals/fixtures/repo-existing"
JS_FILES = ["lib/logger.js", "lib/logger/context.js", "app/api/health/deep/route.js"]


def install(tmp_path, repo, *extra):
    j, m = tmp_path / "r.json", tmp_path / "r.md"
    res = run_script(INSTALL, "--target", str(repo), *extra, "--report-json", str(j), "--report-md", str(m))
    return res, json.loads(j.read_text(encoding="utf-8")), m.read_text(encoding="utf-8")


def files(repo):
    return sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file())


def js_repo(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FX_JS, repo)
    return repo


def test_js_repo_gets_js_files_and_keeps_existing_health_route(tmp_path):
    """The brownfield defect: route.ts beside route.js and a lib/logger.ts in a JavaScript repo."""
    repo = js_repo(tmp_path)
    route_before = (repo / "app/api/health/route.js").read_text(encoding="utf-8")
    res, data, md = install(tmp_path, repo, "--project", "vg-portal")
    assert res.returncode == 0, res.stderr
    assert data["flavour"] == "js"
    for rel in JS_FILES:
        assert (repo / rel).is_file(), rel
        assert rel in data["written"]
    assert not any(p.endswith((".ts", ".tsx")) for p in files(repo)), files(repo)
    assert not (repo / "app/api/health/route.ts").exists() and not (repo / "app/api/health/route.js.proposed").exists()
    assert (repo / "app/api/health/route.js").read_text(encoding="utf-8") == route_before
    assert data["kept"] == [{"path": "app/api/health/route.js", "planned": "app/api/health/route.js",
                             "reason": data["kept"][0]["reason"]}]
    assert data["kept"][0]["reason"].startswith("exists, kept")
    assert run_script(SIBLINGS, str(repo)).returncode == 0
    assert (repo / "lib/logger.js").read_text(encoding="utf-8") == (SK / "assets/logger.js").read_text(encoding="utf-8")
    assert "## Kept (exists, kept — no sibling created)" in md and "`app/api/health/route.js` — exists, kept" in md


def test_existing_health_route_gap_table(tmp_path):
    repo = js_repo(tmp_path)
    _, data, md = install(tmp_path, repo)
    gap = data["health_gaps"]
    assert len(gap) == 1 and gap[0]["path"] == "app/api/health/route.js" and gap[0]["responds"] is True
    assert gap[0]["missing"] == ["liveness has no dependency calls"]       # it probes Supabase with fetch()
    assert "`app/api/health/route.js` — responds (exports GET); missing versus the standard: liveness has no dependency calls" in md
    assert "| exports GET | ok |" in md and "| liveness has no dependency calls | MISSING |" in md
    assert "move the check to /api/health/deep" in md


def test_health_route_without_get_is_flagged_but_run_exits_zero(tmp_path):
    repo = js_repo(tmp_path)
    (repo / "app/api/health/route.js").write_text("export const runtime = 'edge';\nexport async function POST() { return Response.json({}); }\n", encoding="utf-8")
    res, data, md = install(tmp_path, repo)
    assert res.returncode == 0
    assert data["health_gaps"][0]["responds"] is False
    assert "DOES NOT RESPOND (no GET export)" in md


def test_env_vars_only_for_written_files_and_env_structure_kept(tmp_path):
    repo = js_repo(tmp_path)
    before = (repo / ".env.example").read_text(encoding="utf-8")
    _, data, _ = install(tmp_path, repo)
    after = (repo / ".env.example").read_text(encoding="utf-8")
    assert after.startswith(before) and "# public-export:end" in after
    assert data["env_added"] == ["HEALTH_CHECK_TOKEN", "LOG_LEVEL", "LOG_PRETTY", "SERVICE_NAME"]
    assert "NEXT_PUBLIC_SUPABASE_URL" not in data["env_added"]            # already present
    # once everything is in place a re-run adds nothing and touches nothing
    res, data2, _ = install(tmp_path, repo)
    assert res.returncode == 0 and data2["written"] == [] and data2["env_added"] == []
    assert (repo / ".env.example").read_text(encoding="utf-8") == after
    assert sorted(s["path"] for s in data2["skipped"]) == sorted(JS_FILES + ["ops/alerts.yaml", "docs/observability.md"])


def test_console_calls_listed_in_js_repo_and_jsx_files(tmp_path):
    repo = js_repo(tmp_path)
    _, data, _ = install(tmp_path, repo)
    assert {"path": "app/error.js", "line": 4, "call": "console.error"} in data["console_calls"]
    assert {"path": "app/api/orders/route.js", "line": 4, "call": "console.log"} in data["console_calls"]


def test_flavour_detection(tmp_path):
    # tsconfig.json wins
    repo = tmp_path / "a"
    (repo / "app").mkdir(parents=True)
    (repo / "tsconfig.json").write_text("{}", encoding="utf-8")
    (repo / "app/page.js").write_text("export default function P(){return null}\n", encoding="utf-8")
    _, data, _ = install(tmp_path, repo)
    assert data["flavour"] == "ts" and (repo / "lib/logger.ts").is_file() and not (repo / "lib/logger.js").exists()
    # a .tsx under components without tsconfig -> ts
    repo = tmp_path / "b"
    (repo / "components").mkdir(parents=True)
    (repo / "components/Btn.tsx").write_text("export const B = () => null;\n", encoding="utf-8")
    _, data, _ = install(tmp_path, repo)
    assert data["flavour"] == "ts" and "components/Btn.tsx" in data["flavour_evidence"]
    # only .js source -> js; .ts under node_modules does not count
    repo = tmp_path / "c"
    (repo / "node_modules/x").mkdir(parents=True)
    (repo / "node_modules/x/index.ts").write_text("export {};\n", encoding="utf-8")
    (repo / "app").mkdir()
    (repo / "app/layout.js").write_text("export default function L({children}){return children}\n", encoding="utf-8")
    _, data, _ = install(tmp_path, repo)
    assert data["flavour"] == "js" and (repo / "app/api/health/route.js").is_file()
    assert not any(p.endswith(".ts") for p in files(repo) if not p.startswith("node_modules/"))
    # empty target keeps the greenfield TypeScript default; --flavour overrides
    repo = tmp_path / "d"
    _, data, _ = install(tmp_path, repo)
    assert data["flavour"] == "ts"
    repo = tmp_path / "e"
    _, data, _ = install(tmp_path, repo, "--flavour", "js")
    assert data["flavour"] == "js" and (repo / "lib/logger/context.js").is_file()


def test_other_flavour_module_is_kept_not_duplicated(tmp_path):
    """A lone lib/logger.ts inside a JavaScript repo: kept, no lib/logger.js and no .proposed beside it."""
    repo = js_repo(tmp_path)
    (repo / "lib/logger.ts").write_text("export const log = console;\n", encoding="utf-8")
    res, data, _ = install(tmp_path, repo, "--flavour", "js")
    assert res.returncode == 0
    assert not (repo / "lib/logger.js").exists() and not (repo / "lib/logger.ts.proposed").exists()
    assert [k["path"] for k in data["kept"]] == ["lib/logger.ts", "app/api/health/route.js"]
    assert "lib/logger/context.js" in data["written"] and "LOG_LEVEL" not in data["env_added"]


def test_existing_conflicting_pair_aborts_with_nothing_written(tmp_path):
    repo = js_repo(tmp_path)
    (repo / "app/api/health/route.ts").write_text("export function GET() { return Response.json({}); }\n", encoding="utf-8")
    before = files(repo)
    j, m = tmp_path / "r.json", tmp_path / "r.md"
    res = run_script(INSTALL, "--target", str(repo), "--report-json", str(j), "--report-md", str(m))
    assert res.returncode == 1 and "conflicting files already in the repo" in res.stderr
    assert files(repo) == before                                            # not a half-install
    data = json.loads(j.read_text(encoding="utf-8"))
    assert data["written"] == [] and data["env_added"] == []
    assert data["conflicts"][0]["existing"] == ["app/api/health/route.ts", "app/api/health/route.js"]
    assert "Aborted — nothing written" in m.read_text(encoding="utf-8")
    assert run_script(SIBLINGS, str(repo)).returncode == 1


def test_typescript_fixture_still_happy_path(tmp_path):
    """The TypeScript + Vercel brownfield fixture keeps its behaviour (regression guard for the general case)."""
    repo = tmp_path / "repo"
    shutil.copytree(FX_TS, repo)
    res, data, _ = install(tmp_path, repo)
    assert res.returncode == 0 and data["flavour"] == "ts"
    assert (repo / "app/api/health/route.ts").is_file() and (repo / "lib/logger.ts.proposed").is_file()
    assert data["kept"] == [] and data["health_gaps"] == []
    assert run_script(SIBLINGS, str(repo)).returncode == 0


def test_dry_run_in_js_repo_writes_nothing_but_reports_kept(tmp_path):
    repo = js_repo(tmp_path)
    before = files(repo)
    res, data, md = install(tmp_path, repo, "--dry-run")
    assert res.returncode == 0 and files(repo) == before
    assert data["flavour"] == "js" and data["written"] == JS_FILES + ["ops/alerts.yaml", "docs/observability.md"]
    assert data["kept"][0]["path"] == "app/api/health/route.js" and "Dry run" in md
