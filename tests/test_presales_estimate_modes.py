"""presales/effort-estimator: --previous change section and --draft-only memo."""
from __future__ import annotations

import json
import sys

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/effort-estimator"
SCRIPT = SK / "scripts/estimate.py"
FX = SK / "evals/fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output  # noqa: E402


def est(tmp_path, *extra, rates=True):
    md, memo = tmp_path / "estimate.md", tmp_path / "memo.md"
    args = [str(FX / "wbs.csv")] + (["--rates", str(FX / "rates.csv")] if rates else []) + \
        ["--iterations", "20000", "--seed", "7", "--out", str(md), "--memo", str(memo), "--client", "Acme", *extra]
    r = run_script(SCRIPT, *args)
    return r, (md.read_text(encoding="utf-8") if md.exists() else ""), (memo.read_text(encoding="utf-8") if memo.exists() else None)


def test_memo_only_with_draft_only(tmp_path):
    r, md, memo = est(tmp_path)
    assert r.returncode == 0 and memo is None and "## Change vs previous estimate" not in md


def test_draft_memo_traces_to_report(tmp_path):
    r, md, memo = est(tmp_path, "--draft-only")
    assert r.returncode == 0, r.stderr
    assert memo.startswith("# Estimate Memo — Acme — draft")
    res = check_output.run_check("numbers_trace_to:estimate.md", str(tmp_path / "memo.md"), mode="real", cwd=str(tmp_path))
    assert res["pass"], res["evidence"]
    assert check_output.run_check("no_unowned_tbd", str(tmp_path / "memo.md"), mode="real")["pass"]


def test_draft_memo_without_rates_has_no_price(tmp_path):
    r, md, memo = est(tmp_path, "--draft-only", rates=False)
    assert r.returncode == 0
    assert "| Price | pending rate card — [TO BE BASELINED — owner: Estimation lead]" in memo


def test_previous_change_table(tmp_path):
    r, md, memo = est(tmp_path, "--previous", str(FX / "estimate-previous.json"), "--draft-only")
    assert r.returncode == 0, r.stderr
    for row in ("| Total P80 (pd) | 225 | 246 | +21 |", "| Phase 3 - Cutover P80 (pd) | — | 15 | new |",
                "| Cross-phase P80 (pd) | 88 | 88 | +0 |", "| Price @P80 (USD) | 204,080 | 216,160 | +12,080 |"):
        assert row in md and row in memo
    assert md.index("## Change vs previous estimate") < md.index("## Duration")


def test_previous_price_not_compared_without_rates(tmp_path):
    r, md, _ = est(tmp_path, "--previous", str(FX / "estimate-previous.json"), rates=False)
    assert r.returncode == 0 and "| Price @P80 | not compared |" in md


def test_bad_previous_exits_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"phases": {}}), encoding="utf-8")
    r, _, _ = est(tmp_path, "--previous", str(bad))
    assert r.returncode == 2 and "not an estimate.json" in r.stderr
    r, _, _ = est(tmp_path, "--previous", str(tmp_path / "none.json"))
    assert r.returncode == 2 and "previous estimate not found" in r.stderr
