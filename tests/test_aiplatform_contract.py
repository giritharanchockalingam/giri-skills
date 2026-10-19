"""Tests for ai-platform/data-contract-validator/scripts/validate_contract.py (hand-checked rules)."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/data-contract-validator/scripts/validate_contract.py"
FIX = REPO_ROOT / "skills/ai-platform/data-contract-validator/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Data owner]"
HEAD = "column,type,required,unique,min,max,allowed,regex,max_null_rate,severity,owner\n"


def _run(tmp_path, contract: str, data: str, *extra, name="contract.csv"):
    (tmp_path / name).write_text(contract, encoding="utf-8")
    (tmp_path / "data.csv").write_text(data, encoding="utf-8")
    out = tmp_path / "out"
    res = run_script(SCRIPT, "--contract", str(tmp_path / name), "--data", str(tmp_path / "data.csv"),
                     "--out-dir", str(out), *extra)
    viol = {}
    if (out / "violations.csv").exists():
        for r in csv.DictReader((out / "violations.csv").open(encoding="utf-8")):
            viol[(r["column"], r["rule"])] = r
    return res, viol, out


def test_type_nulls_unique_bounds_hand_checked(tmp_path):
    contract = HEAD + ("id,integer,yes,yes,1,100,,,,error,Data steward\n"
                       "score,number,no,no,0,1,,,0.25,warn,ML lead\n")
    data = "id,score\n1,0.5\n2,\n2,1.5\nx,null\n150,0.1\n"
    res, v, _ = _run(tmp_path, contract, data)
    assert res.returncode == 1
    assert v[("id", "type")]["failing_rows"] == "1" and v[("id", "type")]["failing_rate"] == "0.200"
    assert v[("id", "unique")]["failing_rows"] == "1" and v[("id", "unique")]["examples"] == "2"
    assert v[("id", "max")]["examples"] == "150"
    # 2 nulls of 5 rows = 0.400 > 0.25; out-of-range 1.5 of 3 non-null
    assert v[("score", "null_rate")]["failing_rate"] == "0.400" and v[("score", "null_rate")]["severity"] == "warn"
    assert v[("score", "max")]["failing_rate"] == "0.333"
    assert ("id", "required") not in v


def test_missing_extra_allowed_regex_and_tbd_owner(tmp_path):
    contract = HEAD + ("code,enum,no,no,,,A|B,,,error,\n"
                       "ref,string,no,no,,,,R-\\d{3},,warn,Ops lead\n"
                       "absent,string,yes,no,,,,,,error,Ops lead\n")
    data = "code,ref,surplus\nA,R-001,x\nb,R-01,y\nC,R-002,z\n"
    res, v, out = _run(tmp_path, contract, data)
    assert res.returncode == 1
    assert v[("code", "allowed")]["failing_rows"] == "2" and v[("code", "allowed")]["owner"] == TBD
    assert v[("ref", "regex")]["examples"] == "R-01"
    assert v[("absent", "missing_column")]["failing_rate"] == "1.000"
    assert v[("surplus", "extra_column")]["severity"] == "warn" and v[("surplus", "extra_column")]["owner"] == TBD
    report = (out / "contract-report.md").read_text(encoding="utf-8")
    assert "**FAIL**" in report
    chk = run_script("scripts/check_output.py", str(out / "contract-report.md"), "no_unowned_tbd", "--mode", "real")
    assert chk.returncode == 0, chk.stdout


def test_examples_capped_at_three_and_40_chars(tmp_path):
    long = "Z" * 60
    contract = HEAD + "v,integer,no,no,,,,,,error,Owner\n"
    data = "v\n" + "\n".join([long, "a", "b", "c", "d", "a"]) + "\n"
    res, v, _ = _run(tmp_path, contract, data)
    ex = v[("v", "type")]["examples"].split(" | ")
    assert len(ex) == 3 and len(ex[0]) == 40 and ex[0].endswith("…")
    assert v[("v", "type")]["failing_rows"] == "6"


def test_profile_withholds_text_and_reports_numeric_range(tmp_path):
    contract = HEAD + "name,string,no,no,,,,,,warn,O\nqty,integer,no,no,,,,,,warn,O\nd,date,no,no,,,,,,warn,O\n"
    data = "name,qty,d\nalice,10,2026-09-02\nbob,-3,2026-08-30\n,7,\n"
    res, _, out = _run(tmp_path, contract, data)
    assert res.returncode == 0
    prof = {r["column"]: r for r in csv.DictReader((out / "profile.csv").open(encoding="utf-8"))}
    assert prof["name"]["min"] == "n/a (text)" and prof["name"]["null_rate"] == "0.333"
    assert (prof["qty"]["min"], prof["qty"]["max"], prof["qty"]["inferred_type"]) == ("-3", "10", "integer")
    assert (prof["d"]["min"], prof["d"]["max"]) == ("2026-08-30", "2026-09-02")
    text = (out / "profile.csv").read_text() + (out / "contract-report.md").read_text()
    assert "alice" not in text and "bob" not in text


def test_freshness_boundary_and_tbd(tmp_path):
    contract = HEAD + "ts,date,yes,no,,,,,,error,Data steward\n"
    data = "ts\n2026-09-01\n2026-09-10\n"
    ok, v, _ = _run(tmp_path, contract, data, "--freshness-column", "ts", "--as-of", "2026-09-17",
                    "--max-age-days", "7")
    assert ok.returncode == 0 and ("ts", "freshness") not in v
    late, v2, _ = _run(tmp_path, contract, data, "--freshness-column", "ts", "--as-of", "2026-09-18",
                       "--max-age-days", "7")
    assert late.returncode == 1 and v2[("ts", "freshness")]["examples"] == "newest 2026-09-10; age 8 days"
    tbd, _, out = _run(tmp_path, contract, data, "--freshness-column", "ts")
    assert tbd.returncode == 0
    assert f"not checked: as_of and max_age_days {TBD}" in (out / "contract-report.md").read_text()


def test_invalid_contract_and_missing_inputs_exit_2(tmp_path):
    bad_type, _, _ = _run(tmp_path, HEAD + "a,text,no,no,,,,,,error,O\n", "a\n1\n")
    assert bad_type.returncode == 2 and "type must be one of" in bad_type.stderr
    bad_rx, _, _ = _run(tmp_path, HEAD + "a,string,no,no,,,,([,,error,O\n", "a\n1\n")
    assert bad_rx.returncode == 2 and "invalid regex" in bad_rx.stderr
    enum_no_list, _, _ = _run(tmp_path, HEAD + "a,enum,no,no,,,,,,error,O\n", "a\n1\n")
    assert enum_no_list.returncode == 2
    empty, _, _ = _run(tmp_path, HEAD + "a,string,no,no,,,,,,error,O\n", "")
    assert empty.returncode == 2 and "no header" in empty.stderr
    assert run_script(SCRIPT, "--data", str(tmp_path / "data.csv"), "--out-dir", str(tmp_path / "o")).returncode == 2


def test_ragged_rows_and_header_only(tmp_path):
    contract = HEAD + "a,integer,yes,no,,,,,,error,O\nb,integer,no,no,,,,,,error,O\n"
    res, v, _ = _run(tmp_path, contract, "a,b\n1,2\n3\n4,5,6\n")
    assert v[("*", "ragged_row")]["failing_rows"] == "2" and res.returncode == 1
    res2, v2, out = _run(tmp_path, contract, "a,b\n")
    assert res2.returncode == 0 and v2 == {}
    assert "Rows checked: 0" in (out / "contract-report.md").read_text()


def test_yaml_odcs_subset_matches_csv_rules(tmp_path):
    d = tmp_path / "out"
    res = run_script(SCRIPT, "--contract", str(FIX / "contract.yaml"), "--data", str(FIX / "invoices-fail.csv"),
                     "--out-dir", str(d))
    assert res.returncode == 1
    rows = {(r["column"], r["rule"]): r for r in csv.DictReader((d / "violations.csv").open(encoding="utf-8"))}
    assert rows[("customer_email", "null_rate")]["failing_rate"] == "0.500"  # 20 % ODCS threshold
    assert rows[("invoice_id", "unique")]["owner"] == TBD  # primaryKey -> unique; ODCS has no per-column owner
    assert rows[("amount", "min")]["examples"] == "-15.00"
    assert "missingValues` not evaluated" in (d / "contract-report.md").read_text(encoding="utf-8")


def test_yaml_anchor_rejected(tmp_path):
    y = "schema:\n  - name: t\n    properties:\n      - name: a\n        logicalType: *ref\n"
    res, _, _ = _run(tmp_path, y, "a\n1\n", name="c.yaml")
    assert res.returncode == 2 and "anchors" in res.stderr


def test_determinism_and_verify(tmp_path):
    args = ["--contract", str(FIX / "contract.csv"), "--data", str(FIX / "invoices-fail.csv"),
            "--freshness-column", "updated_at", "--as-of", "2026-09-20", "--max-age-days", "7"]
    a, b = tmp_path / "a", tmp_path / "b"
    assert run_script(SCRIPT, *args, "--out-dir", str(a)).returncode == 1
    assert run_script(SCRIPT, *args, "--out-dir", str(b)).returncode == 1
    for f in ("violations.csv", "profile.csv", "contract-report.md"):
        assert (a / f).read_bytes() == (b / f).read_bytes()
        assert run_script(SCRIPT, "--verify", str(a / f), *args).returncode == 0
    tampered = a / "violations.csv"
    tampered.write_text(tampered.read_text().replace("0.500", "0.050"), encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(tampered), *args).returncode == 1


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src
