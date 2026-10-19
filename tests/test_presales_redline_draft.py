"""presales/exec-deck-redline: --draft-only mechanical redline, applied back to the ledger."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/exec-deck-redline"
SCRIPT = SK / "scripts/redline.py"
FX = SK / "evals/fixtures"


def build(tmp_path, deck, *extra):
    l, u, r = tmp_path / "ledger.csv", tmp_path / "uns.csv", tmp_path / "redline.md"
    res = run_script(SCRIPT, str(deck), "--ledger", str(l), "--unsourced", str(u), "--redline-out", str(r), *extra)
    return res, l, (r.read_text(encoding="utf-8") if r.exists() else None)


def test_redline_out_needs_draft_only(tmp_path):
    res, _, red = build(tmp_path, FX / "deck.md")
    assert res.returncode == 0 and red is None


def test_draft_redline_rows_and_rewrites(tmp_path):
    res, ledger, red = build(tmp_path, FX / "deck.md", "--draft-only")
    assert res.returncode == 0, res.stderr
    assert "| 1 | Order Hub: steering committee update | [KEEP] |" in red
    assert "| 3 | Benefits | [SHARPEN] + [TBD] | 4 figure(s) without a source; title is a label" in red
    assert ("Split shipments fall from [TO BE BASELINED — owner: Deck owner] to "
            "[TO BE BASELINED — owner: Deck owner] in year 2") in red
    assert "| Decision ask | none — slides 1–2 state it | — |" in red
    ap = run_script(SCRIPT, "--apply", str(tmp_path / "redline.md"), "--ledger", str(ledger))
    assert ap.returncode == 0
    rows = {r["slide"]: r for r in csv.DictReader(ledger.open(encoding="utf-8"))}
    assert rows["3"]["verdict"] == "[SHARPEN] + [TBD]" and rows["1"]["verdict"] == "[KEEP]"


def test_sourced_deck_and_missing_ask(tmp_path):
    deck = tmp_path / "d.md"
    words = " ".join(["word"] * 70)
    deck.write_text(f"--- slide 1 ---\nContext\nWe have grown {words}\n--- slide 2 ---\n"
                    "Costs fall 12% in year one (source: finance pack 2026)\n", encoding="utf-8")
    res, _, red = build(tmp_path, deck, "--draft-only")
    assert res.returncode == 0
    assert "body has 73 words (limit 60)" in red
    assert "| — | none | every figure names a source | — |" in red
    assert "| Decision ask | Slide 1: the decision as an assertion" in red
