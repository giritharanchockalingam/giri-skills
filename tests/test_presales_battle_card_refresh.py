"""presales/competitive-positioning: --previous-claims refresh."""
from __future__ import annotations

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/competitive-positioning"
SCRIPT = SK / "scripts/battle_card.py"
FX = SK / "evals/fixtures"


def card(tmp_path, *extra, theirs=FX / "their-claims.csv"):
    out = tmp_path / "card.md"
    r = run_script(SCRIPT, str(FX / "our-capabilities.csv"), str(theirs), str(FX / "concerns.csv"), "--out", str(out), *extra)
    return r, (out.read_text(encoding="utf-8") if out.exists() else "")


def test_refresh_lists_new_withdrawn_rerated(tmp_path):
    r, md = card(tmp_path, "--previous-claims", str(FX / "their-claims-previous.csv"))
    assert r.returncode == 0, r.stderr
    assert "| Lower blended rate | re-rated | 2 → 4 |" in md
    assert "| No certified Apigee engineers | withdrawn (not in the current intel) | 1 → — |" in md
    assert "fictional" not in md
    assert md.index("## Changes since the last card") < md.index("## Landmines")


def test_closed_wedge_is_called_out(tmp_path):
    prev = tmp_path / "prev.csv"
    prev.write_text("claim,source,strength\nPeak-season cutover experience,,2\n", encoding="utf-8")
    now = tmp_path / "now.csv"
    now.write_text("claim,source,strength\nPeak-season cutover experience,Reference call 2026-10-01,4\n", encoding="utf-8")
    r, md = card(tmp_path, "--previous-claims", str(prev), theirs=now)
    assert r.returncode == 0, r.stderr
    assert "| Peak-season cutover experience | re-rated | 2 → 4 |" in md
    assert "Wedges closed by the new evidence" in md
    assert "Peak-season cutover rehearsal and parallel run vs \"Peak-season cutover experience\": they were 2, now 4" in md


def test_same_claims_no_change(tmp_path):
    r, md = card(tmp_path, "--previous-claims", str(FX / "their-claims.csv"))
    assert r.returncode == 0 and "| — | no change in their claims | |" in md


def test_no_previous_no_section_and_bad_strength_fails(tmp_path):
    _, md = card(tmp_path)
    assert "## Changes since the last card" not in md
    bad = tmp_path / "bad.csv"
    bad.write_text("claim,source,strength\nX,,9\n", encoding="utf-8")
    r, _ = card(tmp_path, "--previous-claims", str(bad))
    assert r.returncode == 1 and "previous claims row 1" in r.stderr
