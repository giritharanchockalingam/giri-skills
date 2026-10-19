"""presales/solution-architecture-doc: --current change-from-current-state view."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/solution-architecture-doc"
SCRIPT = SK / "scripts/arch_doc.py"
FX = SK / "evals/fixtures"


def doc(tmp_path, *extra, components=FX / "components.json"):
    out = tmp_path / "a.md"
    r = run_script(SCRIPT, str(components), "--out", str(out), "--nfr", str(tmp_path / "n.csv"), *extra)
    return r, (out.read_text(encoding="utf-8") if out.exists() else "")


def test_change_view_and_adrs(tmp_path):
    r, md = doc(tmp_path, "--current", str(FX / "current-state.json"))
    assert r.returncode == 0, r.stderr
    for row in ("| Order store (`db`) | re-platformed | Oracle 12c | PostgreSQL 16 |",
                "| Event backbone (`events`) | added | — | Kafka (managed) |",
                "| Legacy OMS (`legacy_oms`) | retired | Oracle Forms | — |",
                "| Supplier fax gateway (external) | retired | external | — |",
                "| ERP (SAP S/4) → Order service | pattern changed | sync SOAP | batch file |",
                "| Legacy OMS → Supplier fax gateway | retired | batch file | — |"):
        assert row in md, row
    assert "Re-platform Order store: Oracle 12c → PostgreSQL 16" in md
    assert md.index("## Change from current state") < md.index("## Integration map")


def test_same_state_has_no_changes(tmp_path):
    r, md = doc(tmp_path, "--current", str(FX / "components.json"))
    assert r.returncode == 0
    assert "0 added, 0 retired, 0 re-platformed" in md and "| — | no integration change | | |" in md
    assert "Retire " not in md


def test_without_current_no_section(tmp_path):
    _, md = doc(tmp_path)
    assert "## Change from current state" not in md


def test_invalid_current_fails(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"system": "x", "containers": []}), encoding="utf-8")
    r, _ = doc(tmp_path, "--current", str(bad))
    assert r.returncode == 1 and "non-empty 'containers'" in r.stderr
