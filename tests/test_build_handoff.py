"""Tests for build/handoff-and-thread-close/scripts/handoff.py and make_fixture_repo.py."""
from __future__ import annotations

import subprocess

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/handoff-and-thread-close/scripts/handoff.py"
FIXTURE = "skills/build/handoff-and-thread-close/scripts/make_fixture_repo.py"
SK = REPO_ROOT / "skills/build/handoff-and-thread-close"
LAYOUT = SK / "evals/fixtures/repo-files"
TMPL = SK / "assets/HANDOFF.md"
SECTIONS = ["## State:", "## Done this thread", "## Changed files", "## Open items", "## Next thread starts with"]


def build_repo(tmp_path):
    repo = tmp_path / "repo"
    r = run_script(FIXTURE, "--from", str(LAYOUT), "--target", str(repo))
    assert r.returncode == 0, r.stderr
    return repo


def handoff(tmp_path, repo, *extra):
    out = tmp_path / "HANDOFF.md"
    r = run_script(SCRIPT, "--target", str(repo), "--state", "partial — export shipped, e2e pending",
                   "--template", str(TMPL), "--out", str(out), *extra)
    return r, out


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True).stdout


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0
    assert run_script(FIXTURE, "--help").returncode == 0


def test_fixture_repo_layout(tmp_path):
    repo = build_repo(tmp_path)
    subjects = git(repo, "log", "--format=%s").split("\n")
    assert subjects[:3] == ["test: unit test for export service", "feat: invoice CSV export service and route",
                            "chore: bootstrap repo with HANDOFF"]
    assert (repo / "docs/notes.md").is_file() and "docs/notes.md" in git(repo, "status", "--porcelain")
    assert not (repo / "COMMIT_MSG").exists()
    # rebuilding into the same target works; a foreign repo is refused
    assert run_script(FIXTURE, "--from", str(LAYOUT), "--target", str(repo)).returncode == 0
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    subprocess.run(["git", "init", "-q", str(foreign)], check=True)
    assert run_script(FIXTURE, "--from", str(LAYOUT), "--target", str(foreign)).returncode == 1


def test_handoff_since_previous_handoff_commit(tmp_path):
    repo = build_repo(tmp_path)
    r, out = handoff(tmp_path, repo, "--project", "demo-app")
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# HANDOFF — demo-app — ")
    for s in SECTIONS:
        assert s in text, s
    assert "## State: partial — export shipped, e2e pending" in text
    assert "- feat: invoice CSV export service and route (`" in text
    assert "chore: bootstrap repo with HANDOFF" not in text                    # before the last HANDOFF commit
    assert "- `server/services/export-service.ts` — added: feat: invoice CSV export service and route" in text
    assert "- `tests/unit/export-service.test.ts` — added: test: unit test for export service" in text
    assert "- `docs/notes.md` — uncommitted: [TO BE BASELINED — owner: ___]" in text
    assert "- Decide export file format CSV vs XLSX (owner: Giri)" in text      # carried forward
    assert "uncommitted changes present (1 file(s))" in text
    assert "Read docs/HANDOFF.md, CLAUDE.md." in text
    assert "- …" not in text
    assert text.count("\n") <= 80


def test_since_ref_and_date(tmp_path):
    repo = build_repo(tmp_path)
    first = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    r, out = handoff(tmp_path, repo, "--since", first)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "feat: invoice CSV export" in text and "test: unit test" in text and "chore: bootstrap" not in text
    r, out = handoff(tmp_path, repo, "--since", "2000-01-01")
    assert r.returncode == 0, r.stderr
    assert "chore: bootstrap repo with HANDOFF" in out.read_text(encoding="utf-8")
    assert handoff(tmp_path, repo, "--since", "no-such-ref")[0].returncode == 1


def test_write_to_repo_and_next_run_uses_it(tmp_path):
    repo = build_repo(tmp_path)
    r, out = handoff(tmp_path, repo, "--write-to-repo")
    assert r.returncode == 0, r.stderr
    assert (repo / "docs/HANDOFF.md").read_text(encoding="utf-8") == out.read_text(encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qam", "docs: handoff"], cwd=str(repo), check=True)
    r, out = handoff(tmp_path, repo)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "- no commits since last HANDOFF commit" in text
    assert "- Decide export file format CSV vs XLSX (owner: Giri)" in text     # still carried


def test_no_previous_handoff_uses_whole_history(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "feat: first"], cwd=str(repo), check=True)
    r, out = handoff(tmp_path, repo)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "- feat: first (`" in text and "- `a.txt` — added: feat: first" in text
    assert "none carried (no previous docs/HANDOFF.md open items)" in text


def test_bad_input_exits_1(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    r, _ = handoff(tmp_path, plain)
    assert r.returncode == 1 and "not a git repository" in r.stderr
    sub = tmp_path / "repo-sub"
    build_repo(tmp_path)
    (tmp_path / "repo" / "sub").mkdir()
    r = run_script(SCRIPT, "--target", str(tmp_path / "repo" / "sub"), "--state", "x", "--out", str(tmp_path / "h.md"))
    assert r.returncode == 1 and "not a repository root" in r.stderr
    assert run_script(SCRIPT, "--target", str(sub), "--state", "x", "--out", str(tmp_path / "h.md")).returncode == 1
