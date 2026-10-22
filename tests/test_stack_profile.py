"""scripts/stack_profile.py — facts read from fixture repos, unknowns never guessed, deterministic JSON."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "scripts/stack_profile.py"
FIX = REPO_ROOT / "tests" / "fixtures"


def profile(repo: Path, tmp_path: Path | None = None) -> dict:
    if tmp_path is not None:
        out = tmp_path / "stack-profile.json"
        r = run_script(SCRIPT, str(repo), "--json", str(out))
        assert r.returncode == 0, r.stderr
        assert "stack profile:" in r.stdout
        return json.loads(out.read_text())
    r = run_script(SCRIPT, str(repo))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def facts(p: dict) -> dict:
    return {k: p[k] for k in ("flavour", "framework", "package_manager", "test_runner", "e2e", "deploy_target",
                              "migrations_dir", "monorepo_root")}


def test_js_nextjs_aws_repo(tmp_path):
    p = profile(FIX / "delivery-repo", tmp_path)
    assert facts(p) == {"flavour": "js", "framework": "nextjs", "package_manager": "npm", "test_runner": "vitest",
                        "e2e": "playwright", "deploy_target": "aws", "migrations_dir": None, "monorepo_root": None}
    assert p["baselines"] == {"nextjs": None, "perf": None, "ui": None}
    assert p["evidence"]["deploy_target"] == ".github/workflows/aws-deploy-production.yml"
    assert p["evidence"]["flavour"] == "jsconfig.json, no tsconfig.json"


def test_ts_nextjs_vercel_supabase_repo():
    p = profile(FIX / "stack-profile" / "ts-vercel-supabase")
    assert facts(p) == {"flavour": "ts", "framework": "nextjs", "package_manager": "pnpm", "test_runner": "jest",
                        "e2e": "none", "deploy_target": "vercel", "migrations_dir": "supabase/migrations", "monorepo_root": None}
    assert p["baselines"]["perf"].endswith("docs/baselines/perf-findings.csv")
    assert p["baselines"]["nextjs"] is None and p["baselines"]["ui"] is None
    assert ".vercel/project.json" in p["evidence"]["deploy_target"]
    assert "packageManager pnpm@9.12.0" in p["evidence"]["package_manager"]


def test_python_repo():
    p = profile(FIX / "stack-profile" / "python-repo")
    assert facts(p) == {"flavour": "python", "framework": "fastapi", "package_manager": "poetry", "test_runner": "pytest",
                        "e2e": "none", "deploy_target": "unknown", "migrations_dir": None, "monorepo_root": None}


def test_empty_dir_is_all_unknowns_never_guessed():
    p = profile(FIX / "stack-profile" / "empty-dir")
    assert facts(p) == {"flavour": "unknown", "framework": "unknown", "package_manager": "unknown", "test_runner": "none",
                        "e2e": "none", "deploy_target": "unknown", "migrations_dir": None, "monorepo_root": None}
    assert p["exists"] is True and p["baselines"] == {"nextjs": None, "perf": None, "ui": None}


def test_missing_dir_reports_exists_false(tmp_path):
    p = profile(tmp_path / "nope")
    assert p["exists"] is False and p["flavour"] == "unknown" and p["evidence"]["flavour"] == "directory does not exist"


def test_vercel_json_alone_is_a_weak_signal_that_does_not_beat_aws(tmp_path):
    repo = tmp_path / "r"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "vercel.json").write_text("{}")
    (repo / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}')
    p = profile(repo)
    assert p["deploy_target"] == "vercel" and "weak" in p["evidence"]["deploy_target"]
    (repo / ".github" / "workflows" / "deploy.yml").write_text("steps:\n  - uses: aws-actions/configure-aws-credentials@v4\n")
    assert profile(repo)["deploy_target"] == "aws"


def test_conflicting_deploy_signals_stay_unknown(tmp_path):
    repo = tmp_path / "r"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "a.yml").write_text("uses: aws-actions/x@v1\n")
    (repo / ".github" / "workflows" / "b.yml").write_text("uses: google-github-actions/deploy@v1\n")
    p = profile(repo)
    assert p["deploy_target"] == "unknown" and "conflicting" in p["evidence"]["deploy_target"]


def test_monorepo_root_is_found_in_an_ancestor(tmp_path):
    root = tmp_path / "mono"
    pkg = root / "apps" / "web"
    pkg.mkdir(parents=True)
    (root / "pnpm-workspace.yaml").write_text("packages:\n  - apps/*\n")
    (pkg / "package.json").write_text('{"dependencies": {"next": "15.0.0"}, "devDependencies": {"vitest": "2.0.0"}}')
    p = profile(pkg)
    assert p["monorepo_root"] == str(root.resolve()) and p["framework"] == "nextjs" and p["test_runner"] == "vitest"


def test_output_is_deterministic_and_sorted(tmp_path):
    a = run_script(SCRIPT, str(FIX / "delivery-repo")).stdout
    b = run_script(SCRIPT, str(FIX / "delivery-repo")).stdout
    assert a == b
    keys = list(json.loads(a).keys())
    assert keys == sorted(keys)
