"""presales/integration-migration-assessor: readout_draft.py (readout without a model step)."""
from __future__ import annotations

import sys

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/integration-migration-assessor"
FX = SK / "evals/fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output  # noqa: E402


def summaries(tmp_path, rates=FX / "rates.csv"):
    scored, ss, ts = tmp_path / "scored.csv", tmp_path / "ss.md", tmp_path / "ts.md"
    r = run_script(SK / "scripts/score_inventory.py", str(FX / "inventory.csv"), "--out", str(scored), "--waves", "3", "--summary")
    ss.write_text(r.stdout, encoding="utf-8")
    run_script(SK / "scripts/tco.py", str(scored), "--rates", str(rates), "--out", str(tmp_path / "tco.csv"),
               "--summary", str(ts), "--json", str(tmp_path / "t.json"))
    return ss, ts


def draft(tmp_path, ss, ts):
    out = tmp_path / "readout.md"
    r = run_script(SK / "scripts/readout_draft.py", "--scoring", str(ss), "--tco", str(ts), "--client", "Acme", "--out", str(out))
    return r, out


def test_readout_sections_and_traceability(tmp_path):
    ss, ts = summaries(tmp_path)
    r, out = draft(tmp_path, ss, ts)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    for h in ("## Bottom line", "## Scoring results", "## Wave plan", "## TCO", "## Risks", "## Next steps"):
        assert h in text
    assert "### Run-rate comparison" in text and "\n# TCO" not in text
    assert "| Payback: not within horizon · 3-year net: -169,000 USD | the business case does not pay back" in text
    res = check_output.run_check(f"numbers_trace_to:[\"{ss}\",\"{ts}\"]", str(out), mode="real")
    assert res["pass"], res["evidence"]
    assert check_output.run_check("no_unowned_tbd", str(out), mode="real")["pass"]


def test_missing_or_wrong_summary_fails(tmp_path):
    ss, ts = summaries(tmp_path)
    r, _ = draft(tmp_path, tmp_path / "none.md", ts)
    assert r.returncode == 1 and "summary not found" in r.stderr
    bad = tmp_path / "bad.md"
    bad.write_text("nothing here\n", encoding="utf-8")
    r, _ = draft(tmp_path, bad, ts)
    assert r.returncode == 1 and "lacks the band and wave tables" in r.stderr
    r, _ = draft(tmp_path, ss, bad)
    assert r.returncode == 1 and "Payback:" in r.stderr
