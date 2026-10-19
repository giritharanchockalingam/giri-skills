"""career/jd-fit-scorer: --resume (existing résumé as evidence)."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/career/jd-fit-scorer"
SCRIPT = SK / "scripts/score.py"
FX = SK / "evals/fixtures"


def score(*extra, profile=FX / "profile-constraints.txt"):
    r = run_script(SCRIPT, "--jd", str(FX / "jd.txt"), "--profile", str(profile), "--json", *extra)
    return r, (json.loads(r.stdout) if r.returncode == 0 else None)


def test_resume_lines_are_cited_evidence():
    r, res = score("--resume", str(FX / "master-resume.md"))
    assert r.returncode == 0, r.stderr
    api = next(row for row in res["rows"] if row["requirement"].startswith("Experience with API gateway"))
    assert api["status"] == "MATCH" and api["evidence"].startswith("MR-L22:")
    erp = next(row for row in res["rows"] if "ERP consolidation" in row["requirement"])
    assert erp["evidence"].startswith("MR-L13:")


def test_constraints_only_profile_without_resume_scores_low():
    r, res = score()
    r2, res2 = score("--resume", str(FX / "master-resume.md"))
    assert res["total"] < res2["total"]
    assert all(row["evidence"] in ("",) or row["bucket"] == "culture" for row in res["rows"])


def test_bullet_resume_lines(tmp_path):
    cv = tmp_path / "cv.md"
    cv.write_text("# CV (fictional)\n- Ran a FinOps program cutting cloud cost management spend 20%\n", encoding="utf-8")
    r, res = score("--resume", str(cv))
    finops = next(row for row in res["rows"] if row["requirement"].startswith("Cloud cost management"))
    assert finops["status"] in ("MATCH", "PARTIAL") and finops["evidence"].startswith("résumé: Ran a FinOps")


def test_missing_resume_exits_2(tmp_path):
    r, _ = score("--resume", str(tmp_path / "none.md"))
    assert r.returncode == 2 and "file not found" in r.stderr
