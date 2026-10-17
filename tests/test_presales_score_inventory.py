"""Tests for presales/integration-migration-assessor/scripts/score_inventory.py."""
from __future__ import annotations

from pathlib import Path

from conftest import run_script

SCRIPT = "skills/presales/integration-migration-assessor/scripts/score_inventory.py"

INVENTORY = (
    "interface_id,name,source_system,target_system,pattern,transformation,"
    "target_connector,endpoint_count,volume_class,error_handling,security,"
    "test_coverage,documentation,criticality\n"
    "INT-001,Order Sync,ERP,CRM,sync,mapping,native,3,medium,default,basic,"
    "automated,current,medium\n"
    "INT-002,Legacy Feed,Mainframe,Data Lake,batch,heavy,none,12,high,custom,"
    "regulated,none,none,high\n"
)

BANDS = {"Simple", "Medium", "Complex", "Very complex"}


def _inventory(tmp_path: Path, text: str = INVENTORY) -> Path:
    p = tmp_path / "inventory.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_summary_bands(tmp_path):
    inv = _inventory(tmp_path)
    r = run_script(SCRIPT, "--summary", str(inv))
    assert r.returncode == 0, r.stderr
    assert "Band" in r.stdout


def test_out_scored_csv(tmp_path):
    inv = _inventory(tmp_path)
    out = tmp_path / "scored.csv"
    r = run_script(SCRIPT, "--out", str(out), str(inv))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert "weighted_score" in header
    assert "band" in header
    rows = out.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 3  # header + 2 interfaces


def test_validate_hard_failure(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "interface_id,name,source_system\nINT-001,Order Sync,ERP\n", encoding="utf-8"
    )
    r = run_script(SCRIPT, "--validate", str(bad))
    assert r.returncode == 4
    assert "validation: FAILED" in (r.stdout + r.stderr)


def test_missing_file(tmp_path):
    r = run_script(SCRIPT, "--summary", str(tmp_path / "nope.csv"))
    assert r.returncode == 2
