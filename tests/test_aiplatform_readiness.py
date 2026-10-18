"""Tests for ai-platform/data-readiness-assessment/scripts/assess.py (hand-checked numbers)."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/data-readiness-assessment/scripts/assess.py"
FIX = REPO_ROOT / "skills/ai-platform/data-readiness-assessment/evals/fixtures"

# 4 rows (fictional): rows 2 and 3 identical; id 2 repeats; v has 3 nulls ("", "", "NA")
TINY = "id,d,v,notes\n1,2026-09-01,10,fictional\n2,2026-09-10,,fictional\n2,2026-09-10,,fictional\n3,,NA,fictional\n"
ALL_REQS = ("key,value\nmin_rows,4\nmax_null_pct,50\nrequired_columns,id;d;v\nunique_key,id\n"
            "max_duplicate_rows,1\ndate_column,d\nmax_age_days,30\n")


def _w(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def _run(tmp_path, data=TINY, reqs=ALL_REQS, *extra):
    d = _w(tmp_path / "data.csv", data)
    r = _w(tmp_path / "reqs.csv", reqs)
    out = tmp_path / "out"
    res = run_script(SCRIPT, "--data", str(d), "--requirements", str(r), "--out-dir", str(out), *extra)
    js = json.loads((out / "readiness.json").read_text()) if (out / "readiness.json").exists() else None
    return res, js, out


def _dim(js, name):
    return next(d for d in js["dimensions"] if d["dimension"] == name)


def test_profile_numbers(tmp_path):
    res, js, _ = _run(tmp_path, TINY, ALL_REQS, "--as-of", "2026-09-20")
    p = js["profile"]
    assert (p["rows"], p["columns"], p["duplicate_rows"]) == (4, 4, 1)
    cols = {c["column"]: c for c in p["column_profile"]}
    assert cols["v"]["nulls"] == 3 and cols["v"]["null_pct"] == 75.0
    assert cols["d"]["null_pct"] == 25.0 and cols["d"]["inferred_type"] == "date"
    assert cols["id"]["inferred_type"] == "integer" and cols["id"]["distinct"] == 3
    assert cols["v"]["inferred_type"] == "integer"


def test_dimension_scoring_and_not_ready_exit_1(tmp_path):
    res, js, _ = _run(tmp_path, TINY, ALL_REQS, "--as-of", "2026-09-20")
    assert res.returncode == 1
    assert js["verdict"] == "Not ready"
    assert _dim(js, "volume")["status"] == "pass"
    comp = _dim(js, "completeness")
    assert comp["status"] == "fail" and comp["observed"] == 75.0 and comp["columns_over"] == ["v"]
    assert _dim(js, "schema")["status"] == "pass"
    uq = _dim(js, "uniqueness")
    assert uq["status"] == "fail" and uq["observed"] == 1 and uq["owner"] == "Data steward"
    assert _dim(js, "duplicates")["status"] == "pass"  # 1 duplicate row <= 1 allowed
    fr = _dim(js, "freshness")
    assert fr["status"] == "pass" and fr["observed"] == 10 and fr["newest_date"] == "2026-09-10"


def test_ready_on_fixture(tmp_path):
    out = tmp_path / "o"
    res = run_script(SCRIPT, "--data", str(FIX / "orders-sample.csv"), "--requirements", str(FIX / "requirements.csv"),
                     "--as-of", "2026-10-01", "--out-dir", str(out))
    assert res.returncode == 0, res.stderr
    js = json.loads((out / "readiness.json").read_text())
    assert js["verdict"] == "Ready" and js["summary"] == {"pass": 6, "fail": 0, "TBD": 0, "dimensions": 6}
    assert _dim(js, "freshness")["observed"] == 3  # 2026-10-01 - 2026-09-28


def test_absent_threshold_is_tbd_not_pass(tmp_path):
    res, js, out = _run(tmp_path, TINY, "key,value\nmin_rows,4\nmax_null_pct,\n", "--as-of", "2026-09-20")
    assert res.returncode == 0
    assert js["verdict"] == "Ready-with-gaps"
    assert js["summary"]["TBD"] == 5 and js["summary"]["pass"] == 1
    comp = _dim(js, "completeness")
    assert comp["status"] == "TBD" and comp["marker"] == "[TO BE BASELINED — owner: Data owner]"
    md = (out / "readiness.md").read_text()
    for s in ("## Verdict", "## Dimensions", "## Column profile", "## Gaps and owners"):
        assert s in md
    assert "owner: Data owner]" in md


def test_freshness_tbd_without_as_of(tmp_path):
    res, js, _ = _run(tmp_path, TINY, "key,value\ndate_column,d\nmax_age_days,30\n")
    fr = _dim(js, "freshness")
    assert fr["status"] == "TBD" and fr["missing_keys"] == ["as_of"]


def test_date_column_absent_fails(tmp_path):
    res, js, _ = _run(tmp_path, TINY, "key,value\ndate_column,shipped\nmax_age_days,30\n", "--as-of", "2026-09-20")
    assert res.returncode == 1 and _dim(js, "freshness")["status"] == "fail"


def test_missing_required_column_fails_schema(tmp_path):
    res, js, _ = _run(tmp_path, TINY, "key,value\nrequired_columns,id;region\n")
    sc = _dim(js, "schema")
    assert sc["status"] == "fail" and sc["missing_columns"] == ["region"] and sc["owner"] == "Data engineer"


def test_composite_key_unique(tmp_path):
    data = "a,b\n1,x\n1,y\n2,x\n"
    res, js, _ = _run(tmp_path, data, "key,value\nunique_key,a;b\n")
    assert _dim(js, "uniqueness")["status"] == "pass"


def test_null_key_fails_uniqueness(tmp_path):
    res, js, _ = _run(tmp_path, "a,b\n1,x\n,y\n", "key,value\nunique_key,a\n")
    uq = _dim(js, "uniqueness")
    assert uq["status"] == "fail" and uq["null_key_rows"] == 1 and uq["observed"] == 0


def test_type_inference(tmp_path):
    data = "f,b,s,dt\n1.5,true,abc,2026-01-01T10:00:00\n2,no,12,2026-01-02\n"
    res, js, _ = _run(tmp_path, data, "key,value\n")
    t = {c["column"]: c["inferred_type"] for c in js["profile"]["column_profile"]}
    assert t == {"f": "float", "b": "boolean", "s": "string", "dt": "datetime"}


def test_unknown_key_noted(tmp_path):
    res, js, _ = _run(tmp_path, TINY, "key,value\nmin_accuracy,0.9\n")
    assert any("min_accuracy" in n for n in js["notes"])


def test_invalid_requirement_value_exit_2(tmp_path):
    res, js, _ = _run(tmp_path, TINY, "key,value\nmin_rows,lots\n")
    assert res.returncode == 2 and "min_rows" in res.stderr


def test_missing_requirements_arg_exit_2(tmp_path):
    d = _w(tmp_path / "d.csv", TINY)
    res = run_script(SCRIPT, "--data", str(d), "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 2


def test_missing_data_file_exit_2(tmp_path):
    r = _w(tmp_path / "r.csv", ALL_REQS)
    res = run_script(SCRIPT, "--data", str(tmp_path / "nope.csv"), "--requirements", str(r), "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 2 and not (tmp_path / "o").exists()


def test_bad_as_of_exit_2(tmp_path):
    res, _, _ = _run(tmp_path, TINY, ALL_REQS, "--as-of", "01/10/2026")
    assert res.returncode == 2


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src
