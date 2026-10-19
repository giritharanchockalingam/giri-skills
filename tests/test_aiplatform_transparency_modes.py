"""Tests for transparency_notice.py --published-notice (redline of the notice users see today)."""
from __future__ import annotations

import importlib.util
import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-transparency-notice/scripts/transparency_notice.py"
FIX = REPO_ROOT / "skills/ai-platform/ai-transparency-notice/evals/fixtures"


def _mod():
    spec = importlib.util.spec_from_file_location("transparency_notice", REPO_ROOT / SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_redline_against_published_notice(tmp_path):
    r = run_script(SCRIPT, "--facts", str(FIX / "facts.csv"), "--published-notice", str(FIX / "published-notice.md"),
                   "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rl = (tmp_path / "notice-redline.md").read_text(encoding="utf-8")
    assert "Sentences: 6 unchanged, 3 changed, 3 added, 1 removed." in rl
    assert "| changed | Last updated: 2026-03-02. | Last updated: 2026-09-30. |" in rl
    assert "| added | — | It is not for legal or tax advice. |" in rl
    assert '"Every answer is checked by our billing team." — no current fact supports' in rl
    data = json.loads((tmp_path / "transparency.json").read_text(encoding="utf-8"))
    assert data["redline"] == {"unchanged": 6, "changed": 3, "added": 3, "removed": 1}
    assert "Published notice redlined" in (tmp_path / "system-card.md").read_text(encoding="utf-8")


def test_no_published_notice_no_redline(tmp_path):
    r = run_script(SCRIPT, "--facts", str(FIX / "facts.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "notice-redline.md").exists()
    assert "redline" not in json.loads((tmp_path / "transparency.json").read_text(encoding="utf-8"))


def test_identical_notice_is_all_unchanged(tmp_path):
    r = run_script(SCRIPT, "--facts", str(FIX / "facts.csv"), "--out-dir", str(tmp_path / "a"))
    assert r.returncode == 0, r.stderr
    r = run_script(SCRIPT, "--facts", str(FIX / "facts.csv"), "--published-notice", str(tmp_path / "a" / "notice.md"),
                   "--out-dir", str(tmp_path / "b"))
    assert r.returncode == 0, r.stderr
    rl = (tmp_path / "b" / "notice-redline.md").read_text(encoding="utf-8")
    assert "Sentences: 12 unchanged, 0 changed, 0 added, 0 removed." in rl
    assert "None: every published sentence is still supported by a current fact." in rl


def test_redline_matching_is_one_to_one():
    m = _mod()
    rows = m.redline(["Last updated: 2026-01-01.", "Old claim here."],
                     ["Last updated: 2026-09-30.", "Last updated: 2026-10-01."])
    assert [r["status"] for r in rows] == ["changed", "added", "removed"]
    assert rows[0]["published"] == "Last updated: 2026-01-01."


def test_missing_or_empty_published_notice_exits_2(tmp_path):
    r = run_script(SCRIPT, "--facts", str(FIX / "facts.csv"), "--published-notice", str(tmp_path / "nope.md"),
                   "--out-dir", str(tmp_path))
    assert r.returncode == 2 and "published notice file not found" in r.stderr
    empty = tmp_path / "empty.md"
    empty.write_text("<!-- nothing -->\n# Title only\n", encoding="utf-8")
    r = run_script(SCRIPT, "--facts", str(FIX / "facts.csv"), "--published-notice", str(empty), "--out-dir", str(tmp_path))
    assert r.returncode == 2 and "no sentences" in r.stderr
