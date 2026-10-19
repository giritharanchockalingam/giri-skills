"""Tests for ai-platform/pii-data-inventory/scripts/scan_pii.py (hand-checked detections)."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/pii-data-inventory/scripts/scan_pii.py"
FIX = REPO_ROOT / "skills/ai-platform/pii-data-inventory/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Privacy officer]"

# All values are fictional test values (example.com, 555 numbers, documentation IP ranges, test cards).
RAW = {
    "card": ["4111 1111 1111 1111", "4111 1111 1111 1112"],          # Luhn ok / Luhn fails
    "id_code": ["123-45-6789", "000-12-3456", "666-12-3456", "912-34-5678"],  # only the first is valid
    "contact": ["jane.tester@example.com", "(612) 555-0142", "+16125550188", ""],
}


def _write_csv(p: Path, cols: dict[str, list[str]]) -> Path:
    n = max(len(v) for v in cols.values())
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(cols))
        for i in range(n):
            w.writerow([v[i] if i < len(v) else "" for v in cols.values()])
    return p


def _scan(tmp_path, cols, policy: str | None = None, *extra):
    data = _write_csv(tmp_path / "data.csv", cols)
    args = ["--data", str(data), "--out-dir", str(tmp_path / "out"), *extra]
    if policy is not None:
        (tmp_path / "policy.csv").write_text(policy, encoding="utf-8")
        args += ["--policy", str(tmp_path / "policy.csv")]
    res = run_script(SCRIPT, *args)
    inv = tmp_path / "out" / "pii-inventory.csv"
    rows = {r["column"]: r for r in csv.DictReader(inv.open(encoding="utf-8"))} if inv.exists() else {}
    return res, rows


def test_luhn_card_and_ssn_validity(tmp_path):
    res, rows = _scan(tmp_path, {"card": RAW["card"], "id_code": RAW["id_code"]})
    assert res.returncode == 0, res.stderr
    assert rows["card"]["pii_types"] == "payment_card" and rows["card"]["match_rate"] == "0.500"
    assert rows["id_code"]["pii_types"] == "ssn" and rows["id_code"]["match_rate"] == "0.250"
    assert rows["id_code"]["matches"] == "1"


def test_email_phone_and_empty_excluded_from_rate(tmp_path):
    res, rows = _scan(tmp_path, {"contact": RAW["contact"], "row": ["1", "2", "3", "4"]})
    r = rows["contact"]
    assert set(r["pii_types"].split(";")) == {"email", "phone"}
    assert r["match_rate"] == "1.000" and r["matches"] == "3" and r["rows_scanned"] == "4"


def test_ip_and_dob_only_in_dob_column(tmp_path):
    cols = {"host_ip": ["192.0.2.1", "2001:db8::1"], "date_of_birth": ["1990-04-12", "04/12/1990"],
            "created": ["1990-04-12", "2001-01-01"]}
    res, rows = _scan(tmp_path, cols)
    assert rows["host_ip"]["pii_types"] == "ipv4;ipv6"
    assert rows["date_of_birth"]["pii_types"] == "dob" and rows["date_of_birth"]["match_rate"] == "1.000"
    assert rows["created"]["pii_types"] == "none" and rows["created"]["handling"] == "n/a"


def test_column_name_hints(tmp_path):
    cols = {"first_name": ["Alpha"], "product_name": ["Widget"], "ip_address": ["n/a"],
            "mailingAddress": ["1 Example St"], "username": ["tester1"]}
    res, rows = _scan(tmp_path, cols)
    assert rows["first_name"]["pii_types"] == "name" and rows["first_name"]["basis"] == "name-hint"
    assert rows["product_name"]["pii_types"] == "none"
    assert rows["ip_address"]["pii_types"] == "none"
    assert rows["mailingAddress"]["pii_types"] == "address"
    assert rows["username"]["pii_types"] == "none"


def test_embedded_email_and_ssn_in_free_text(tmp_path):
    cols = {"comment": ["call me, mail a.tester@example.com", "ssn 123-45-6789 on file", "nothing here"]}
    res, rows = _scan(tmp_path, cols, "pii_type,handling\nemail,mask\nssn,drop\n")
    r = rows["comment"]
    assert r["pii_types"] == "email;ssn" and r["matches"] == "2" and r["match_rate"] == "0.667"
    assert r["handling"] == "drop"  # strictest of mask, drop


def test_no_raw_values_in_any_output(tmp_path):
    cols = {"card": RAW["card"], "id_code": RAW["id_code"], "contact": RAW["contact"]}
    res, _ = _scan(tmp_path, cols)
    out = tmp_path / "out"
    text = (out / "pii-report.md").read_text() + (out / "pii-inventory.csv").read_text()
    for raw in ("4111 1111 1111 1111", "123-45-6789", "jane.tester@example.com", "(612) 555-0142", "+16125550188"):
        assert raw not in text
    assert "j***@e***.com" in text and "***-**-6789" in text and "**** 1111" in text and "***-***-0142" in text
    for f in ("pii-report.md", "pii-inventory.csv"):
        chk = run_script(SCRIPT, "--leak-check", str(out / f), "--data", str(tmp_path / "data.csv"))
        assert chk.returncode == 0, chk.stdout


def test_leak_check_catches_raw(tmp_path):
    data = _write_csv(tmp_path / "d.csv", {"contact": RAW["contact"]})
    res = run_script(SCRIPT, "--leak-check", str(data), "--data", str(data))
    assert res.returncode == 1 and "3 raw" in res.stdout


def test_no_policy_is_tbd_and_strict_fails(tmp_path):
    res, rows = _scan(tmp_path, {"contact": RAW["contact"]})
    assert res.returncode == 0 and rows["contact"]["handling"] == TBD
    res2, _ = _scan(tmp_path, {"contact": RAW["contact"]}, None, "--strict")
    assert res2.returncode == 1 and "contact" in res2.stderr


def test_partial_policy_gap_and_full_policy(tmp_path):
    res, rows = _scan(tmp_path, {"contact": RAW["contact"]}, "pii_type,handling\nemail,mask\n", "--strict")
    assert res.returncode == 1 and rows["contact"]["handling"] == TBD
    res2, rows2 = _scan(tmp_path, {"contact": RAW["contact"]}, "pii_type,handling\nemail,allow\nphone,tokenize\n", "--strict")
    assert res2.returncode == 0 and rows2["contact"]["handling"] == "tokenize"


def test_invalid_policy_exit_2(tmp_path):
    res, _ = _scan(tmp_path, {"contact": RAW["contact"]}, "pii_type,handling\nemail,encrypt\n")
    assert res.returncode == 2 and "encrypt" in res.stderr
    res2, _ = _scan(tmp_path, {"contact": RAW["contact"]}, "pii_type,handling\npassport,drop\n")
    assert res2.returncode == 2


def test_missing_data_exit_2(tmp_path):
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2
    assert run_script(SCRIPT, "--data", str(tmp_path / "nope.csv"), "--out-dir", str(tmp_path / "o")).returncode == 2


def test_fixture_happy_path(tmp_path):
    out = tmp_path / "o"
    res = run_script(SCRIPT, "--data", str(FIX / "customers-sample.csv"), "--policy", str(FIX / "policy.csv"),
                     "--strict", "--out-dir", str(out))
    assert res.returncode == 0, res.stderr
    rows = {r["column"]: r for r in csv.DictReader((out / "pii-inventory.csv").open(encoding="utf-8"))}
    assert rows["ssn"]["handling"] == "drop" and rows["card_number"]["handling"] == "tokenize"
    assert rows["notes"]["pii_types"] == "none"


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src


# --- brownfield: changes since the last inventory (--previous) ---

def _scan_prev(tmp_path, previous: Path, data: Path = FIX / "customers-sample.csv"):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--data", str(data), "--policy", str(FIX / "policy.csv"), "--previous", str(previous),
                   "--out-dir", str(out))
    rows = {x["column"]: x for x in csv.DictReader((out / "pii-inventory.csv").open(encoding="utf-8"))} \
        if (out / "pii-inventory.csv").exists() else {}
    md = (out / "pii-report.md").read_text(encoding="utf-8") if (out / "pii-report.md").exists() else ""
    return r, rows, md


def test_previous_inventory_changes_classified(tmp_path):
    r, rows, md = _scan_prev(tmp_path, FIX / "inventory-previous.csv")
    assert r.returncode == 0, r.stderr
    assert rows["last_login_ip"]["change_vs_previous"] == "new"
    assert rows["comment"]["change_vs_previous"] == "pii-added"
    assert rows["card_number"]["change_vs_previous"] == "handling-changed"
    assert rows["email"]["change_vs_previous"] == "unchanged"
    assert "| fax_number | removed | was phone | mask |" in md
    assert "4 column change(s)" in md
    leak = run_script(SCRIPT, "--leak-check", str(tmp_path / "out/pii-report.md"), "--data", str(FIX / "customers-sample.csv"))
    assert leak.returncode == 0


def test_previous_same_as_current_reports_no_change(tmp_path):
    first = tmp_path / "first"
    r = run_script(SCRIPT, "--data", str(FIX / "customers-sample.csv"), "--policy", str(FIX / "policy.csv"),
                   "--out-dir", str(first))
    assert r.returncode == 0
    r, rows, md = _scan_prev(tmp_path, first / "pii-inventory.csv")
    assert {x["change_vs_previous"] for x in rows.values()} == {"unchanged"}
    assert "0 column change(s)" in md and "PII that was not in the last inventory" not in md


def test_previous_pii_removed(tmp_path):
    prev = tmp_path / "prev.csv"
    prev.write_text("column,pii_types,handling\nproduct_name,name,tokenize\n", encoding="utf-8")
    _, rows, _ = _scan_prev(tmp_path, prev)
    assert rows["product_name"]["change_vs_previous"] == "pii-removed"


def test_bad_previous_exits_2(tmp_path):
    prev = tmp_path / "prev.csv"
    prev.write_text("col,types\nx,y\n", encoding="utf-8")
    r, _, _ = _scan_prev(tmp_path, prev)
    assert r.returncode == 2 and "previous inventory needs columns" in r.stderr


def test_no_previous_keeps_original_layout(tmp_path):
    out = tmp_path / "o"
    run_script(SCRIPT, "--data", str(FIX / "customers-sample.csv"), "--out-dir", str(out))
    header = (out / "pii-inventory.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "column,pii_types,match_rate,rows_scanned,handling,matches,basis"
