"""Tests for presales/proposal-writer/scripts/assemble.py."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/proposal-writer/scripts/assemble.py"
SK = REPO_ROOT / "skills/presales/proposal-writer"
FX = SK / "evals/fixtures"
LIB = SK / "assets/section-library.md"


def run(tmp_path, themes, *extra):
    out, ph, src = tmp_path / "proposal.md", tmp_path / "ph.csv", tmp_path / "src.md"
    r = run_script(SCRIPT, str(themes), "--library", str(LIB), "--out", str(out), "--placeholders", str(ph),
                   "--sources", str(src), *extra)
    return r, out, ph, src


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_assembles_in_library_order_with_themes(tmp_path):
    r, out, ph, src = run(tmp_path, FX / "win-themes.json", "--discovery", str(FX / "discovery-pack.md"),
                          "--estimate", str(FX / "estimate-memo.md"))
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Northwind Retail — Order Hub Integration — Proposal")
    heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert heads[0].startswith("## 0.") and heads[-1].startswith("## 12.")
    assert not any(h.startswith("## 13.") for h in heads)           # internal checklist not shipped
    assert "- **T1 Peak-proof order orchestration** — no war room next peak (proof: Northwind peak post-mortem" in text
    assert "(proof: [TO BE BASELINED — owner: Bid manager])" in text          # T3 has no proof
    assert "Evidence from discovery" in text and "war room for nine days" in text
    assert "Basis: estimate memo bottom line" in text and "USD 1,472,000" in text
    assert "<" not in text.replace("<!--", "")                        # no raw placeholders survive
    rows = list(csv.DictReader(ph.open(encoding="utf-8")))
    assert rows and {"placeholder", "section", "owner"} <= set(rows[0])
    assert any(r_["placeholder"] == "duration" for r_ in rows)
    assert "## estimate memo" in src.read_text(encoding="utf-8")


def test_thin_themes_produce_markers_not_numbers(tmp_path):
    r, out, ph, src = run(tmp_path, FX / "win-themes-thin.json")
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "[TO BE BASELINED — owner: Bid manager]" in text
    assert "USD" not in text and "1,472,000" not in text
    assert len(list(csv.DictReader(ph.open(encoding="utf-8")))) > 10


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.json")[0].returncode == 1
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    assert run(tmp_path, bad)[0].returncode == 1
    nothemes = tmp_path / "nt.json"
    nothemes.write_text(json.dumps({"client": "A", "initiative": "B", "themes": []}), encoding="utf-8")
    r = run(tmp_path, nothemes)[0]
    assert r.returncode == 1 and "themes" in r.stderr
    nolib = tmp_path / "lib.md"
    nolib.write_text("# no sections here\n", encoding="utf-8")
    r = run_script(SCRIPT, str(FX / "win-themes.json"), "--library", str(nolib), "--out", str(tmp_path / "p.md"),
                   "--placeholders", str(tmp_path / "p.csv"))
    assert r.returncode == 1
