"""Tests for presales/exec-deck-redline/scripts/redline.py (text export path; pptx needs an optional dep)."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/exec-deck-redline/scripts/redline.py"
FX = REPO_ROOT / "skills/presales/exec-deck-redline/evals/fixtures"


def build(tmp_path, deck):
    led, uns = tmp_path / "ledger.csv", tmp_path / "uns.csv"
    return run_script(SCRIPT, str(deck), "--ledger", str(led), "--unsourced", str(uns)), led, uns


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_ledger_and_unsourced_from_text_export(tmp_path):
    r, led, uns = build(tmp_path, FX / "deck.md")
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(led.open(encoding="utf-8")))
    assert [r_["slide"] for r_ in rows] == ["1", "2", "3", "4", "5"]
    assert rows[0]["title"] == "Order Hub: steering committee update" and rows[0]["verdict"] == ""
    assert rows[2]["numbers_found"] == "6.2%; 3%; 310,000; 40%"
    assert "2026" not in rows[1]["numbers_found"]                      # dates are not numbers
    u = list(csv.DictReader(uns.open(encoding="utf-8")))
    assert {(x["slide"], x["number"]) for x in u} == {("3", "6.2%"), ("3", "3%"), ("3", "310,000"), ("3", "40%")}
    # slide 1's $420,000 has a Source footnote; slide 2's 118 is sourced inline
    r2, _, uns2 = build(tmp_path, FX / "deck-sourced.md")
    assert r2.returncode == 0 and uns2.read_text(encoding="utf-8").strip() == "slide,number,context"


def test_apply_fills_verdicts(tmp_path):
    _, led, _ = build(tmp_path, FX / "deck.md")
    rl = tmp_path / "redline.md"
    rl.write_text("## Redline table\n| Slide # | Original title | Verdict | Reason |\n|---|---|---|---|\n"
                  "| 1 | x | [KEEP] | decision on slide 1 |\n| 3 | Benefits | [SHARPEN] + [TBD] | 40% unsourced |\n"
                  "| n/a | not a slide | [CUT] | ignored |\n", encoding="utf-8")
    r = run_script(SCRIPT, "--apply", str(rl), "--ledger", str(led))
    assert r.returncode == 0, r.stderr
    rows = {r_["slide"]: r_ for r_ in csv.DictReader(led.open(encoding="utf-8"))}
    assert rows["1"]["verdict"] == "[KEEP]" and rows["1"]["reason"] == "decision on slide 1"
    assert rows["3"]["verdict"] == "[SHARPEN] + [TBD]"
    assert rows["2"]["verdict"] == "" and "3 slides without verdict" in r.stdout
    # the unfilled template applies nothing
    tmpl = REPO_ROOT / "skills/presales/exec-deck-redline/assets/redline-template.md"
    r = run_script(SCRIPT, "--apply", str(tmpl), "--ledger", str(led))
    assert r.returncode == 0 and rows["1"]["verdict"] == "[KEEP]"


def test_bad_input_exits_1(tmp_path):
    assert build(tmp_path, tmp_path / "missing.md")[0].returncode == 1
    nosep = tmp_path / "d.txt"
    nosep.write_text("just text\n", encoding="utf-8")
    r = build(tmp_path, nosep)[0]
    assert r.returncode == 1 and "separators" in r.stderr
    odd = tmp_path / "d.key"
    odd.write_text("x", encoding="utf-8")
    assert build(tmp_path, odd)[0].returncode == 1
    assert run_script(SCRIPT, "--apply", str(tmp_path / "nope.md"), "--ledger", str(tmp_path / "l.csv")).returncode == 1
    assert run_script(SCRIPT, "--ledger", str(tmp_path / "l.csv")).returncode == 1


def test_pptx_without_dependency_fails_clearly(tmp_path):
    try:
        import pptx  # noqa: F401
    except ImportError:
        pass
    else:
        import pytest
        pytest.skip("python-pptx installed; the graceful-error path is not exercised")
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"PK\x03\x04 not really a deck")
    r = build(tmp_path, deck)[0]
    assert r.returncode == 1 and "pip install python-pptx" in r.stderr
