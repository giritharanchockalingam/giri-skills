"""Tests for ai-platform/slm-demo-builder/scripts/gen_synthetic.py."""
from __future__ import annotations

import csv
import json
import re

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/slm-demo-builder/scripts/gen_synthetic.py"
FX = REPO_ROOT / "skills/ai-platform/slm-demo-builder/evals/fixtures"


def rows(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_generates_entities_deterministically_without_real_pii(tmp_path):
    r = run_script(SCRIPT, str(FX / "demo-spec.md"), "--out-dir", str(tmp_path / "a"), "--seed", "7")
    assert r.returncode == 0, r.stderr
    man = json.loads((tmp_path / "a" / "data-manifest.json").read_text(encoding="utf-8"))
    assert [e["entity"] for e in man["entities"]] == ["customers", "tickets"]
    assert man["entities"][0]["rows"] == 50 and man["entities"][1]["rows"] == 120     # volumes from the spec table
    assert man["pii_guard"] == "passed" and man["demo"] == "Support triage showroom"
    cust = rows(tmp_path / "a" / "data" / "customers.csv")
    assert len(cust) == 50 and cust[0]["customer_id"] == "C00001"
    assert all(c["email"].endswith("@example.com") for c in cust)
    assert all(re.fullmatch(r"[a-z]+\.[a-z]+\d+@example\.com", c["email"]) for c in cust)
    assert all(c["email"].split("@")[0].split(".")[0] == c["name"].split(" ")[0].lower() for c in cust)
    assert all(c["segment"] in ("enterprise", "mid", "small") and c["active"] in ("true", "false") for c in cust)
    tix = rows(tmp_path / "a" / "data" / "tickets.csv")
    ids = {c["customer_id"] for c in cust}
    assert len(tix) == 120 and all(t["customer_id"] in ids for t in tix)
    assert all(1 <= int(t["priority"]) <= 4 and re.fullmatch(r"\d\.\d", t["csat"]) for t in tix)
    assert all("2025-10-17" <= t["opened"] <= "2026-01-15" for t in tix)
    # no real-looking domains or phone/ssn patterns anywhere in the output
    blob = (tmp_path / "a" / "data" / "customers.csv").read_text() + (tmp_path / "a" / "data" / "tickets.csv").read_text()
    assert not re.search(r"@(?!example\.com)[a-z0-9.-]+\.[a-z]{2,}", blob)
    assert not re.search(r"\b\d{3}-\d{2}-\d{4}\b", blob) and not re.search(r"\(\d{3}\) ?\d{3}-\d{4}", blob)
    # deterministic
    run_script(SCRIPT, str(FX / "demo-spec.md"), "--out-dir", str(tmp_path / "b"), "--seed", "7")
    assert (tmp_path / "a" / "data" / "tickets.csv").read_bytes() == (tmp_path / "b" / "data" / "tickets.csv").read_bytes()
    run_script(SCRIPT, str(FX / "demo-spec.md"), "--out-dir", str(tmp_path / "c"), "--seed", "8")
    assert (tmp_path / "a" / "data" / "tickets.csv").read_bytes() != (tmp_path / "c" / "data" / "tickets.csv").read_bytes()


def test_rows_flag_applies_when_spec_has_no_volume(tmp_path):
    spec = tmp_path / "s.md"
    spec.write_text("# Demo Spec — X — v0.1 — d\n\n## 7. Synthetic data plan\n### orders\n| Field | Type | Example | Constraints |\n|---|---|---|---|\n| order_id | id | O00001 | prefix=O |\n| total | float | 10.00 | min=1; max=100 |\n", encoding="utf-8")
    r = run_script(SCRIPT, str(spec), "--out-dir", str(tmp_path), "--rows", "7")
    assert r.returncode == 0, r.stderr
    assert len(rows(tmp_path / "data" / "orders.csv")) == 7


def test_pii_guard_and_bad_input_exit_1(tmp_path):
    r = run_script(SCRIPT, str(FX / "demo-spec-pii.md"), "--out-dir", str(tmp_path / "p"))
    assert r.returncode == 1 and "PII guard: applicants.ssn" in r.stderr and not (tmp_path / "p" / "data").exists()
    spec = tmp_path / "s.md"
    spec.write_text("## 7. Synthetic data plan\n### people\n| Field | Type | Example | Constraints |\n|---|---|---|---|\n| card_number | text | x | |\n", encoding="utf-8")
    assert "PII guard" in run_script(SCRIPT, str(spec), "--out-dir", str(tmp_path)).stderr
    spec.write_text("## 7. Synthetic data plan\n### people\n| Field | Type | Example | Constraints |\n|---|---|---|---|\n| x | uuid | x | |\n", encoding="utf-8")
    assert "unknown type" in run_script(SCRIPT, str(spec), "--out-dir", str(tmp_path)).stderr
    spec.write_text("# nothing\n", encoding="utf-8")
    assert run_script(SCRIPT, str(spec), "--out-dir", str(tmp_path)).returncode == 1
    assert run_script(SCRIPT, str(tmp_path / "no.md"), "--out-dir", str(tmp_path)).returncode == 1
