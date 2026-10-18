"""docs/ADLC.md is generated from skill metadata and must stay in sync."""
from conftest import run_script


def test_adlc_doc_is_current_and_covers_every_stage():
    r = run_script("scripts/gen_adlc_doc.py", "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    from conftest import REPO_ROOT
    text = (REPO_ROOT / "docs" / "ADLC.md").read_text(encoding="utf-8")
    assert "**gap**" not in text
