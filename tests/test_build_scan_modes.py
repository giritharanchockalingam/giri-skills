"""build/security-review: --draft-only review record and the existing-repo (diff + target) scan."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/security-review"
SCRIPT = SK / "scripts/scan.py"
FX = SK / "evals/fixtures"


def scan(tmp_path, *args):
    f, r, s = tmp_path / "findings.csv", tmp_path / "review.md", tmp_path / "security-review.md"
    res = run_script(SCRIPT, *args, "--findings", str(f), "--report", str(r), "--final", str(s))
    rows = list(csv.DictReader(f.open(encoding="utf-8"))) if f.exists() else []
    return res, rows, (s.read_text(encoding="utf-8") if s.exists() else None)


def test_final_only_written_with_draft_only(tmp_path):
    res, _, final = scan(tmp_path, "--diff", str(FX / "change-clean.patch"))
    assert res.returncode == 0 and final is None


def test_draft_record_clean_diff(tmp_path):
    res, rows, final = scan(tmp_path, "--diff", str(FX / "change-clean.patch"), "--draft-only")
    assert res.returncode == 0, res.stderr
    assert rows == []
    for h in ("## Findings (worst first)", "## Threat model record", "## Surfaces reviewed", "## Verification"):
        assert h in final
    assert "| Verdict | MERGE (scanner candidates only — trace before sign-off) |" in final
    assert "no scanner findings" in final


def test_draft_record_risky_diff_blocks(tmp_path):
    res, rows, final = scan(tmp_path, "--diff", str(FX / "change-risky.patch"), "--draft-only")
    assert res.returncode == 0                       # the gate is a separate call
    assert "| Verdict | BLOCK |" in final
    assert all(f"| {r['id']} |" in final for r in rows)
    assert "candidate (scanner)" in final and "Regression tests for Critical/High | [TO BE BASELINED — owner: Developer]" in final


def test_existing_repo_scanned_with_diff(tmp_path):
    res, rows, final = scan(tmp_path, "--diff", str(FX / "change-clean.patch"), "--target", str(FX / "repo-existing"),
                            "--draft-only")
    assert res.returncode == 0, res.stderr
    assert [(r["severity"], r["file"]) for r in rows] == [("medium", "components/ReleaseNotes.tsx")]
    assert "| `components/ReleaseNotes.tsx` | [TO BE BASELINED — owner: Tech lead] | no → F01 | F01 |" in final
    assert "change-clean.patch + repo-existing" in final
    assert run_script(SCRIPT, "--gate", str(tmp_path / "findings.csv")).returncode == 0
