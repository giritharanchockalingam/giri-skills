"""Read-before-write regression tests for build/ci-cd-vercel-github/scripts/install_ci.py.

The brownfield defect: a JavaScript Next.js repo that deploys to AWS (aws-deploy-*.yml, bare vercel.json, no
Vercel secrets) got preview.yml + prod.yml written and then the run failed on its kept ci.yml — a half-install.
"""
from __future__ import annotations

import json
import shutil

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/ci-cd-vercel-github"
SCRIPT = SK / "scripts/install_ci.py"
ASSETS = SK / "assets/workflows"
AWS_FX = SK / "evals/fixtures/repo-aws-existing-ci"
VERCEL_FX = SK / "evals/fixtures/repo-existing-ci"


def install(tmp_path, repo, *extra):
    j, m = tmp_path / "ci-report.json", tmp_path / "ci-report.md"
    res = run_script(SCRIPT, "--target", str(repo), "--report-json", str(j), "--report-md", str(m), *extra)
    data = json.loads(j.read_text(encoding="utf-8")) if j.exists() else None
    return res, data, (m.read_text(encoding="utf-8") if m.exists() else "")


def copy_fixture(tmp_path, fx):
    repo = tmp_path / "repo"
    shutil.copytree(fx, repo)
    return repo


def test_aws_javascript_repo_gets_no_vercel_workflows_and_no_half_install(tmp_path):
    repo = copy_fixture(tmp_path, AWS_FX)
    wf = repo / ".github/workflows"
    before = {p.name: p.read_text(encoding="utf-8") for p in wf.iterdir()}
    res, data, md = install(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    # read before write
    assert data["flavour"]["flavour"] == "javascript"
    assert data["deploy"]["detected"] == "aws" and data["deploy"]["effective"] == "skip"
    assert data["deploy"]["deploy_workflows"] == "skipped" and data["deploy"]["override"] == ""
    assert set(data["deploy"]["signals"]) == {"aws"}          # vercel.json + *.vercel.app hostname are not Vercel signals
    # no Vercel deploy workflows, nothing of the team's touched
    assert not (wf / "preview.yml").exists() and not (wf / "prod.yml").exists()
    assert {p.name: p.read_text(encoding="utf-8") for p in wf.iterdir()} == before
    by = {w["workflow"]: w for w in data["workflows"]}
    assert by["preview.yml"]["action"] == "skipped" and by["prod.yml"]["action"] == "skipped"
    assert by["ci.yml"]["action"] == "kept"
    assert by["ci.yml"]["missing_jobs"] == ["lint-typecheck-test", "rls-lint", "secrets-scan"]
    assert data["writes"] == [".github/ci-additions.yml"]
    # the additions file is JavaScript-aware and names what the team must add
    adds = (repo / ".github/ci-additions.yml").read_text(encoding="utf-8")
    assert "--include='*.js' --include='*.jsx'" in adds
    assert by["ci.yml"]["npm_scripts_missing"] == ["lint", "typecheck"]
    # the report says it plainly
    assert "this repo deploys to **AWS**" in md and "gate: NEEDS-MERGE" in md
    assert "| Deploy target detected | AWS |" in md
    assert "`.github/workflows/prod.yml` | skipped |" in md
    assert "- `ci / lint-typecheck-test`" in md and "preview / e2e" not in md.split("## Branch protection")[1]
    assert "JavaScript repo: add a `typecheck` script" in md


def test_explicit_deploy_vercel_overrides_detection(tmp_path):
    repo = copy_fixture(tmp_path, AWS_FX)
    res, data, md = install(tmp_path, repo, "--deploy", "vercel")
    assert res.returncode == 0, res.stderr
    assert data["deploy"]["detected"] == "aws" and data["deploy"]["effective"] == "vercel"
    assert data["deploy"]["override"] == "vercel" and data["deploy"]["deploy_workflows"] == "write"
    wf = repo / ".github/workflows"
    assert (wf / "preview.yml").is_file() and (wf / "prod.yml").is_file()
    assert (wf / "prod.yml").read_text(encoding="utf-8") == (ASSETS / "prod.yml").read_text(encoding="utf-8")
    assert "- `preview / e2e`" in md


def test_explicit_deploy_skip_on_a_vercel_repo(tmp_path):
    repo = copy_fixture(tmp_path, VERCEL_FX)
    res, data, _ = install(tmp_path, repo, "--deploy", "skip")
    assert res.returncode == 0, res.stderr
    assert data["deploy"]["effective"] == "skip" and data["deploy"]["override"] == "skip"
    assert not (repo / ".github/workflows/preview.yml").exists()
    assert sorted(data["writes"]) == []                       # ci.yml kept and complete: nothing to write


def test_typescript_vercel_repo_stays_the_happy_path(tmp_path):
    repo = copy_fixture(tmp_path, VERCEL_FX)
    (repo / "tsconfig.json").write_text("{}", encoding="utf-8")
    res, data, _ = install(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    assert data["flavour"]["flavour"] == "typescript" and data["flavour"]["evidence"] == "tsconfig.json"
    assert data["deploy"]["detected"] == "none" and data["deploy"]["effective"] == "vercel"
    assert data["gate"] == "PASS" and data["ok"] is True
    for name in ("preview.yml", "prod.yml"):            # assets verbatim for the TypeScript path
        assert (repo / ".github/workflows" / name).read_text(encoding="utf-8") == (ASSETS / name).read_text(encoding="utf-8")


def test_strong_vercel_signal_in_workflow_is_detected(tmp_path):
    repo = tmp_path / "repo"
    wf = repo / ".github/workflows"
    wf.mkdir(parents=True)
    (wf / "deploy.yml").write_text(
        "name: deploy\non:\n  push:\njobs:\n  d:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: vercel deploy --prebuilt --token=${{ secrets.VERCEL_TOKEN }}\n", encoding="utf-8")
    res, data, _ = install(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    assert data["deploy"]["detected"] == "vercel" and data["deploy"]["signals"]["vercel"] == [".github/workflows/deploy.yml"]
    assert (wf / "prod.yml").is_file()


def test_other_providers_block_vercel_workflows(tmp_path):
    cases = {
        "azure": "      - uses: azure/webapps-deploy@v3\n",
        "gcp": "      - uses: google-github-actions/deploy-cloudrun@v2\n",
        "fly.io": "      - run: flyctl deploy --remote-only\n",
        "railway": "      - run: npx railway up\n",
    }
    for key, step in cases.items():
        repo = tmp_path / key
        wf = repo / ".github/workflows"
        wf.mkdir(parents=True)
        (wf / "deploy.yml").write_text("name: deploy\non:\n  push:\njobs:\n  d:\n    runs-on: ubuntu-latest\n    steps:\n" + step,
                                       encoding="utf-8")
        res, data, md = install(tmp_path / key, repo)
        assert res.returncode == 0, res.stderr
        assert data["deploy"]["detected"] == key, key
        assert data["deploy"]["deploy_workflows"] == "skipped"
        assert (wf / "ci.yml").is_file() and not (wf / "preview.yml").exists()
        assert "NOT written" in md


def test_commented_vercel_mentions_do_not_count(tmp_path):
    repo = copy_fixture(tmp_path, AWS_FX)
    ci = repo / ".github/workflows/ci.yml"
    ci.write_text(ci.read_text(encoding="utf-8") + "# legacy: vercel deploy --prod --token=${{ secrets.VERCEL_TOKEN }}\n",
                  encoding="utf-8")
    res, data, _ = install(tmp_path, repo)
    assert res.returncode == 0 and data["deploy"]["detected"] == "aws"


def test_yaml_sibling_is_kept_not_shadowed(tmp_path):
    repo = tmp_path / "repo"
    wf = repo / ".github/workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yaml").write_text((ASSETS / "ci.yml").read_text(encoding="utf-8"), encoding="utf-8")
    res, data, _ = install(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    ci = next(w for w in data["workflows"] if w["workflow"] == "ci.yml")
    assert ci["action"] == "kept" and ci["path"] == ".github/workflows/ci.yaml"
    assert not (wf / "ci.yml").exists()                       # never a ci.yml beside ci.yaml


def test_clashing_additions_file_aborts_atomically(tmp_path):
    repo = copy_fixture(tmp_path, AWS_FX)
    (repo / ".github/ci-additions.yml").write_text("jobs:\n  mine:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
    snapshot = {p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8") for p in repo.rglob("*") if p.is_file()}
    res, data, md = install(tmp_path, repo)
    assert res.returncode == 1
    assert "already exists with different content" in res.stderr and "nothing written" in res.stderr
    assert {p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8") for p in repo.rglob("*") if p.is_file()} == snapshot
    assert data["gate"] == "ABORTED" and data["writes"] == [] and "## Conflicts (nothing was written)" in md


def test_fresh_javascript_repo_gets_js_aware_ci(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app/page.jsx").write_text("export default function P(){return <main/>}\n", encoding="utf-8")
    res, data, _ = install(tmp_path, repo)
    assert res.returncode == 0, res.stderr
    assert data["flavour"]["flavour"] == "javascript" and data["gate"] == "PASS"
    assert "--include='*.jsx'" in (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert (repo / ".github/workflows/prod.yml").is_file()    # greenfield: Vercel stays the default target


def test_help_lists_deploy_choices():
    res = run_script(SCRIPT, "--help")
    assert res.returncode == 0 and "{auto,vercel,skip}" in res.stdout
