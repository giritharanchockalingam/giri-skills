"""Gate skills judge the project's code, never its build output; dry runs charge the builder only for its own change.

Found on a real Next.js repo (tradesignal): a build folder with a custom name (`bo11/dev/server/chunks/…`) produced
1,500 "new high" convention findings and failed the build gate, and untracked docs/ from an earlier session were
counted as the builder's out-of-plan files. Scripts run as subprocesses (suite convention)."""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCANNERS = {
    "conventions": ("skills/build/nextjs-enterprise-conventions/scripts/lint_conventions.py", ["--target"]),
    "perf": ("skills/build/perf-review-runner/scripts/perf_review.py", ["--target"]),
}
LEAK = "const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;\nexport const x = serviceRoleKey;\n"
SLOW = "export async function GET(db) {\n  const { data } = await db.from('orders').select('*');\n  return data;\n}\n"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                   cwd=repo, check=True, capture_output=True)


def make_repo(tmp: Path, *, ignore: bool) -> Path:
    repo = tmp / "app"
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "page.tsx").write_text("export default function Page() { return null }\n", encoding="utf-8")
    build = repo / "bo11" / "dev" / "server" / "chunks"
    build.mkdir(parents=True)
    (build / "chunk.js").write_text(LEAK + SLOW, encoding="utf-8")
    if ignore:
        (repo / ".gitignore").write_text("/bo11/\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def findings(tool: str, repo: Path, tmp: Path) -> list[dict]:
    script, flag = SCANNERS[tool]
    out = tmp / f"{tool}.csv"
    subprocess.run([sys.executable, "-I", str(REPO / script), *flag, str(repo), "--findings", str(out)],
                   capture_output=True, text=True, cwd=tmp)   # a scanner's default report lands in tmp, not the repo
    with open(out, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.mark.parametrize("tool", sorted(SCANNERS))
def test_git_ignored_build_output_is_not_scanned(tool, tmp_path):
    rows = findings(tool, make_repo(tmp_path, ignore=True), tmp_path)
    assert not [r for r in rows if "bo11/" in str(r)], rows


@pytest.mark.parametrize("tool", sorted(SCANNERS))
def test_the_same_file_is_scanned_when_git_tracks_it(tool, tmp_path):
    """The filter is git's, not a name list: committed code under the same folder is still the project's code."""
    rows = findings(tool, make_repo(tmp_path, ignore=False), tmp_path)
    assert [r for r in rows if "bo11/" in str(r)], "a tracked file must still be scanned"


def test_dry_copy_commits_preexisting_work_so_the_diff_is_only_the_builders(tmp_path):
    repo = make_repo(tmp_path, ignore=True)
    (repo / "docs").mkdir()
    (repo / "docs" / "notes.md").write_text("earlier session\n", encoding="utf-8")   # untracked, not the builder's
    code = (
        "import sys, importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('deliver', {str(REPO / 'scripts' / 'deliver.py')!r})\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['deliver'] = m; spec.loader.exec_module(m)\n"
        f"m.commit_preexisting_work(__import__('pathlib').Path({str(repo)!r}))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    assert status.strip() == "", "pre-existing work is in the baseline commit, so the builder's diff starts clean"


@pytest.mark.parametrize("tool", sorted(SCANNERS))
def test_a_tree_nested_inside_another_repo_is_scanned_in_full(tool, tmp_path):
    """Found live: the pipeline lints <out>/postchange-repo under giri-skills/runs/, which giri-skills git-ignores;
    the export must not inherit the outer repository's ignore rules (0 files were linted and the gate failed)."""
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / ".gitignore").write_text("/runs/\n", encoding="utf-8")
    git(outer, "init", "-q")
    inner = outer / "runs" / "x" / "postchange-repo" / "src"
    inner.mkdir(parents=True)
    (inner / "route.ts").write_text(LEAK + SLOW, encoding="utf-8")
    rows = findings(tool, outer / "runs" / "x" / "postchange-repo", tmp_path)
    assert [r for r in rows if "route.ts" in str(r)], "the nested export's own files must be linted"


def test_code_review_does_not_read_lockfile_integrity_hashes_as_secrets(tmp_path):
    """Found on the CAPE greenfield run: package-lock.json's sha512 integrity values gave 481 blocking CR-SECRET."""
    lock = '{\n  "packages": {\n    "node_modules/a": {\n      "integrity": "sha512-' + "Zx9Kq3Lw7Pv2Rt8Nm4Bc6Hy1Jd5Fg0Sa" * 3 + '==",\n      "dev": true\n    }\n  }\n}\n'
    diff = "diff --git a/package-lock.json b/package-lock.json\nnew file mode 100644\n--- /dev/null\n+++ b/package-lock.json\n@@ -0,0 +1,%d @@\n" % len(lock.splitlines())
    diff += "".join("+" + l + "\n" for l in lock.splitlines())
    (tmp_path / "c.patch").write_text(diff, encoding="utf-8")
    r = subprocess.run([sys.executable, "-I", str(REPO / "skills/build/code-review-runner/scripts/review.py"), "--diff", str(tmp_path / "c.patch"),
                        "--json", str(tmp_path / "r.json"), "--md", str(tmp_path / "r.md")], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CR-SECRET" not in (tmp_path / "r.md").read_text(encoding="utf-8")
