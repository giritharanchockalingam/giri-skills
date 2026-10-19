"""presales/client-research-brief: --previous refresh and --draft-only cited brief."""
from __future__ import annotations

import re

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/client-research-brief"
SCRIPT = SK / "scripts/brief_skeleton.py"
FX = SK / "evals/fixtures"


def brief(tmp_path, *extra, notes=FX / "notes.md"):
    sk, fin = tmp_path / "skeleton.md", tmp_path / "brief.md"
    r = run_script(SCRIPT, "--notes", str(notes), "--company", "Northwind Pumps", "--out", str(sk),
                   "--final", str(fin), *extra)
    return r, sk.read_text(encoding="utf-8") if sk.exists() else "", fin.read_text(encoding="utf-8") if fin.exists() else None


def test_final_needs_draft_only(tmp_path):
    r, sk, fin = brief(tmp_path)
    assert r.returncode == 0 and fin is None and "## Changes since the last brief" not in sk


def test_draft_brief_cites_every_item(tmp_path):
    r, sk, fin = brief(tmp_path, "--draft-only")
    assert r.returncode == 0, r.stderr
    sk_ids = set(re.findall(r"\| (S\d+) \|", sk))
    cited = set(re.findall(r"\[(S\d+)\]", fin))
    assert cited and cited <= sk_ids
    assert "1. revenue up 6% and a \"digital core\" program mentioned on p.12 [S1] — so what:" in fin
    assert "| 1 | Dana Whitfield became CIO in 2025, previously ran integration at a utility. | notes L7 |" in fin
    assert fin.count("| S1 |") == 1


def test_refresh_marks_new_and_dropped(tmp_path):
    r, sk, fin = brief(tmp_path, "--previous", str(FX / "brief-previous.md"), "--draft-only")
    assert r.returncode == 0, r.stderr
    assert "NEW (L4, Recent news)" in sk and "NEW (L2" not in sk and "NEW (L3" not in sk
    assert "NEW (L1," not in sk                                  # the notes' own heading is not material
    assert "Not re-confirmed: https://example.com/news/northwind-crm-2023" in fin
    assert sk.count("NEW since last brief — verify and cite") == 5


def test_identical_previous_has_no_new_material(tmp_path):
    notes = tmp_path / "n.md"
    notes.write_text("https://example.com/a — founded 1990, 300 employees\n", encoding="utf-8")
    prev = tmp_path / "prev.md"
    prev.write_text("| S1 | https://example.com/a | | | |\n", encoding="utf-8")
    r, sk, _ = brief(tmp_path, "--previous", str(prev), notes=notes)
    assert r.returncode == 0 and "- No new material since the last brief." in sk


def test_missing_previous_exits_2(tmp_path):
    r, _, _ = brief(tmp_path, "--previous", str(tmp_path / "nope.md"))
    assert r.returncode == 2 and "previous brief not found" in r.stderr
