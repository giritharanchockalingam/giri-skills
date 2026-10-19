"""Tests for validate_contract.py --draft-contract (greenfield: no contract yet)."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/data-contract-validator/scripts/validate_contract.py"
FIX = REPO_ROOT / "skills/ai-platform/data-contract-validator/evals/fixtures"


def _draft_rows(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# DRAFT contract inferred by validate_contract.py")
    return {r["column"]: r for r in csv.DictReader(lines[1:])}


def test_draft_from_extract_then_validate(tmp_path):
    d = tmp_path / "contract-draft.csv"
    r = run_script(SCRIPT, "--data", str(FIX / "invoices-warn.csv"), "--draft-contract", str(d), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rows = _draft_rows(d)
    assert rows["invoice_id"]["unique"] == "yes" and rows["invoice_id"]["required"] == "yes"
    assert rows["amount"]["type"] == "number" and rows["amount"]["unique"] == "no"
    assert rows["amount"]["min"] == "" and "observed 18.99 to 1500.00" in rows["amount"]["notes"]
    assert rows["currency"]["type"] == "enum" and rows["currency"]["allowed"] == "EUR|GBP|USD"
    assert rows["customer_email"]["max_null_rate"] == "0.125" and rows["customer_email"]["required"] == "no"
    assert {x["severity"] for x in rows.values()} == {"warn"} and {x["owner"] for x in rows.values()} == {""}
    rep = (tmp_path / "contract-report.md").read_text(encoding="utf-8")
    assert "Contract: **DRAFT**" in rep and "not evidence of data quality" in rep
    for name in ("violations.csv", "profile.csv", "contract-report.md"):
        v = run_script(SCRIPT, "--verify", str(tmp_path / name), "--contract", "", "--draft-contract", str(d),
                       "--data", str(FIX / "invoices-warn.csv"))
        assert v.returncode == 0, v.stdout + v.stderr


def test_existing_draft_under_review_is_used_not_overwritten(tmp_path):
    d = tmp_path / "contract-draft.csv"
    assert run_script(SCRIPT, "--data", str(FIX / "invoices-warn.csv"), "--draft-contract", str(d),
                      "--out-dir", str(tmp_path / "a")).returncode == 0
    # the owner tightens the draft: status becomes an error-severity enum without 'refunded'
    text = d.read_text(encoding="utf-8").replace("status,string,yes,no,,,,,,warn,,",
                                                 "status,enum,yes,no,,,open|paid|disputed,,,error,Billing data steward,")
    d.write_text(text, encoding="utf-8")
    r = run_script(SCRIPT, "--data", str(FIX / "invoices-warn.csv"), "--draft-contract", str(d), "--out-dir", str(tmp_path / "b"))
    assert r.returncode == 1  # the owner's rule now catches 'refunded'
    assert d.read_text(encoding="utf-8") == text
    assert "status,allowed,error" in (tmp_path / "b" / "violations.csv").read_text(encoding="utf-8")


def test_signed_off_contract_is_not_marked_draft(tmp_path):
    d = tmp_path / "contract-draft.csv"
    assert run_script(SCRIPT, "--data", str(FIX / "invoices-warn.csv"), "--draft-contract", str(d),
                      "--out-dir", str(tmp_path / "a")).returncode == 0
    signed = tmp_path / "contract.csv"
    signed.write_text("\n".join(d.read_text(encoding="utf-8").splitlines()[1:]) + "\n", encoding="utf-8")
    r = run_script(SCRIPT, "--contract", str(signed), "--data", str(FIX / "invoices-warn.csv"), "--out-dir", str(tmp_path / "b"))
    assert r.returncode == 0, r.stderr
    assert "DRAFT" not in (tmp_path / "b" / "contract-report.md").read_text(encoding="utf-8")


def test_contract_wins_over_draft_and_no_contract_no_draft_exits_2(tmp_path):
    d = tmp_path / "contract-draft.csv"
    r = run_script(SCRIPT, "--contract", str(FIX / "contract.csv"), "--draft-contract", str(d),
                   "--data", str(FIX / "invoices-warn.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert not d.exists()
    r = run_script(SCRIPT, "--data", str(FIX / "invoices-warn.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 2 and "--contract is required" in r.stderr


def test_key_heuristic_and_all_null_column(tmp_path):
    data = tmp_path / "d.csv"
    data.write_text("order_id,amount,note,tier\n1,10,,a\n2,20,,a\n3,30,,b\n4,40,,b\n", encoding="utf-8")
    d = tmp_path / "c.csv"
    assert run_script(SCRIPT, "--data", str(data), "--draft-contract", str(d), "--out-dir", str(tmp_path / "o")).returncode == 0
    rows = _draft_rows(d)
    assert rows["order_id"]["unique"] == "yes" and rows["order_id"]["type"] == "integer"
    assert rows["amount"]["unique"] == "no"  # distinct but not named like a key
    assert rows["note"]["max_null_rate"] == "1.000" and "type unknown" in rows["note"]["notes"]
    assert rows["tier"]["type"] == "enum" and rows["tier"]["allowed"] == "a|b"
