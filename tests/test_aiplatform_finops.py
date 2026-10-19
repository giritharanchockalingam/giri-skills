"""Tests for ai-platform/ai-finops-chargeback/scripts/chargeback.py (hand-checked money math)."""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-finops-chargeback/scripts/chargeback.py"
FIX = REPO_ROOT / "skills/ai-platform/ai-finops-chargeback/evals/fixtures"
TBD = "[TO BE BASELINED — owner: FinOps lead]"
UHEAD = "date,team,feature,model,requests,input_tokens,output_tokens,cached_input_tokens\n"
PHEAD = "model,input_per_1m,output_per_1m,cached_input_per_1m,effective_from\n"


def _run(tmp_path, usage: str, prices: str, budgets: str | None = None, *extra):
    (tmp_path / "u.csv").write_text(usage, encoding="utf-8")
    (tmp_path / "p.csv").write_text(prices, encoding="utf-8")
    args = ["--usage", str(tmp_path / "u.csv"), "--prices", str(tmp_path / "p.csv")]
    if budgets is not None:
        (tmp_path / "b.csv").write_text(budgets, encoding="utf-8")
        args += ["--budgets", str(tmp_path / "b.csv")]
    out = tmp_path / "out"
    res = run_script(SCRIPT, *args, *extra, "--out-dir", str(out))
    return res, out


def _rows(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []


def _level(out, level):
    return [r for r in _rows(out / "showback.csv") if r["level"] == level]


def test_fixture_totals_reconcile_to_the_cent(tmp_path):
    out = tmp_path / "o"
    res = run_script(SCRIPT, "--usage", str(FIX / "usage.csv"), "--prices", str(FIX / "prices.csv"),
                     "--budgets", str(FIX / "budgets.csv"), "--out-dir", str(out))
    assert res.returncode == 0, res.stderr
    total = Decimal(_level(out, "total")[0]["cost_usd"])
    assert total == Decimal("370.39")  # hand-checked in references/method.md
    months = [Decimal(r["cost_usd"]) for r in _level(out, "month")]
    teams = [Decimal(r["cost_usd"]) for r in _level(out, "team")]
    models = [Decimal(r["cost_usd"]) for r in _level(out, "model")]
    assert months == [Decimal("281.01"), Decimal("89.38")]
    assert sum(months) == sum(teams) == sum(models) == total
    priced = [r for r in _level(out, "detail") if r["cost_usd"] != TBD]
    assert abs(sum(Decimal(r["cost_usd"]) for r in priced) - total) <= Decimal("0.005") * len(priced)
    chk = run_script("scripts/check_output.py", str(out / "finops-report.md"),
                     f'numbers_trace_to:["{out}/showback.csv","{out}/anomalies.csv","{out}/budget.csv"]',
                     "no_unowned_tbd", "--mode", "real")
    assert chk.returncode == 0, chk.stdout


def test_price_in_effect_on_each_date_and_cached_rate(tmp_path):
    usage = UHEAD + ("2026-09-14,t,f,m,10,2000000,100000,1000000\n"
                     "2026-09-15,t,f,m,10,2000000,100000,1000000\n")
    prices = PHEAD + "m,2.00,10.00,0.50,2026-09-01\nm,1.00,10.00,0.20,2026-09-15\n"
    res, out = _run(tmp_path, usage, prices)
    assert res.returncode == 0, res.stderr
    # 09-14: 1M*2 + 1M*0.5 + 0.1M*10 = 3.50 ; 09-15: 1M*1 + 1M*0.2 + 1.0 = 2.20
    assert _level(out, "total")[0]["cost_usd"] == "5.70"
    assert _level(out, "total")[0]["cost_per_1k_requests"] == "285.0000"


def test_no_cached_price_charges_full_input_and_note(tmp_path):
    usage = UHEAD + "2026-09-01,t,f,m,1,1000000,0,400000\n"
    res, out = _run(tmp_path, usage, PHEAD + "m,1.00,2.00,,2026-01-01\n")
    assert _level(out, "total")[0]["cost_usd"] == "1.00"
    assert "cached input tokens are charged at the full input price" in (out / "finops-report.md").read_text()


def test_unpriced_usage_is_tbd_and_excluded(tmp_path):
    usage = UHEAD + ("2026-09-01,t,f,known,1,1000000,0,0\n"
                     "2026-09-01,t,f,ghost,5,1000000,0,0\n"
                     "2026-08-31,t,f,known,7,1000000,0,0\n")
    res, out = _run(tmp_path, usage, PHEAD + "known,1.00,1.00,,2026-09-01\n")
    assert res.returncode == 0
    assert _level(out, "total")[0]["cost_usd"] == "1.00" and _level(out, "total")[0]["requests"] == "1"
    un = {r["model"] + r["month"]: r for r in _level(out, "detail") if r["cost_usd"] == TBD}
    assert set(un) == {"ghost2026-09", "known2026-08"}
    report = (out / "finops-report.md").read_text()
    assert "model not in price sheet" in report and "no price in effect before 2026-09-01" in report
    chk = run_script("scripts/check_output.py", str(out / "finops-report.md"), "no_unowned_tbd", "--mode", "real")
    assert chk.returncode == 0


def test_rounding_only_at_output(tmp_path):
    # each row 333,333 output tokens at 1.00/1M = 0.333333; three rows total 0.999999 -> 1.00 (not 0.99)
    usage = UHEAD + "".join(f"2026-09-0{d},t,f{d},m,1,0,333333,0\n" for d in (1, 2, 3))
    res, out = _run(tmp_path, usage, PHEAD + "m,1.00,1.00,,2026-01-01\n")
    assert [r["cost_usd"] for r in _level(out, "detail")] == ["0.33", "0.33", "0.33"]
    assert _level(out, "total")[0]["cost_usd"] == "1.00"


def _daily(costs: list[int]) -> str:
    # requests carry the cost: 1,000,000 output tokens at 1.00/1M per unit -> cost == units
    return UHEAD + "".join(f"2026-09-{i + 1:02d},t,f,m,1,0,{c * 1000000},0\n" for i, c in enumerate(costs))


def test_anomaly_rule_window_and_minimum_history(tmp_path):
    prices = PHEAD + "m,1.00,1.00,,2026-01-01\n"
    early, out = _run(tmp_path, _daily([1, 2, 1, 2, 1, 2, 50]), prices)  # spike with only 6 prior days
    assert _rows(out / "anomalies.csv") == []
    res, out = _run(tmp_path, _daily([1, 2, 1, 2, 1, 2, 1, 50]), prices)  # 7 prior days
    rows = _rows(out / "anomalies.csv")
    assert len(rows) == 1 and rows[0]["date"] == "2026-09-08" and rows[0]["prior_days"] == "7"
    # mean 10/7 = 1.428571; sample sd sqrt((4*(3/7)^2 + 3*(4/7)^2)/6) = sqrt(2/7) = 0.534522; threshold 3.032139
    assert (rows[0]["trailing_mean_usd"], rows[0]["trailing_sd_usd"], rows[0]["threshold_usd"]) == \
           ("1.4286", "0.5345", "3.0321")
    flat, out = _run(tmp_path, _daily([5] * 10), prices)  # sd 0 and equal cost: not an anomaly
    assert _rows(out / "anomalies.csv") == []


def test_forecast_variance_status_and_strict(tmp_path):
    usage = UHEAD + "2026-08-31,t,f,m,1,0,4000000,0\n2026-09-10,t,f,m,1,0,10000000,0\n"
    prices = PHEAD + "m,1.00,1.00,,2026-01-01\n"
    budgets = "team,month,budget_usd\nt,2026-08,5\nt,2026-09,25\nt,2026-10,1\n"
    res, out = _run(tmp_path, usage, prices, budgets, "--strict")
    b = {r["month"]: r for r in _rows(out / "budget.csv")}
    assert (b["2026-08"]["forecast"], b["2026-08"]["status"]) == ("4.00", "WITHIN BUDGET")
    # 10.00 over 10 of 30 days -> 30.00 forecast vs 25 budget
    assert (b["2026-09"]["forecast"], b["2026-09"]["variance"], b["2026-09"]["status"]) == ("30.00", "-5.00", "OVER BUDGET")
    assert b["2026-10"]["status"] == "NOT STARTED" and b["2026-10"]["forecast"] == "n/a"
    assert res.returncode == 1 and "t 2026-09" in res.stderr
    res2, out2 = _run(tmp_path, usage, prices, budgets, "--strict", "--as-of", "2026-09-30")
    b2 = {r["month"]: r for r in _rows(out2 / "budget.csv")}
    assert b2["2026-09"]["forecast"] == "10.00" and res2.returncode == 0
    res3, _ = _run(tmp_path, usage, prices, budgets, "--as-of", "2026-09-01")
    assert res3.returncode == 2 and "before the latest usage date" in res3.stderr


def test_no_budgets_is_tbd_not_invented(tmp_path):
    res, out = _run(tmp_path, UHEAD + "2026-09-01,t,f,m,1,0,1000000,0\n", PHEAD + "m,1,1,,2026-01-01\n")
    row = _rows(out / "budget.csv")[0]
    assert row["budget"] == TBD and row["variance"] == TBD and row["status"] == "NO BUDGET"
    assert res.returncode == 0


def test_invalid_inputs_exit_2(tmp_path):
    p = PHEAD + "m,1,1,,2026-01-01\n"
    cases = [
        (UHEAD + "2026-13-01,t,f,m,1,0,0,0\n", p, None, "not a YYYY-MM-DD"),
        (UHEAD + "2026-09-01,t,f,m,-1,0,0,0\n", p, None, "non-negative integer"),
        (UHEAD + "2026-09-01,t,f,m,1,10,0,20\n", p, None, "exceeds input_tokens"),
        (UHEAD + "2026-09-01,t,f,m,1,0,0,0\n", p + "m,2,2,,2026-01-01\n", None, "two price rows"),
        (UHEAD + "2026-09-01,t,f,m,1,0,0,0\n", p, "team,month,budget_usd\nt,2026-9,5\n", "not YYYY-MM"),
        (UHEAD, p, None, "no data rows"),
        ("date,team\n2026-09-01,t\n", p, None, "missing column"),
    ]
    for usage, prices, budgets, msg in cases:
        res, _ = _run(tmp_path, usage, prices, budgets)
        assert res.returncode == 2 and msg in res.stderr, (msg, res.stderr)
    assert run_script(SCRIPT, "--usage", str(FIX / "usage.csv"), "--out-dir", str(tmp_path / "x")).returncode == 2


def test_determinism_and_verify(tmp_path):
    args = ["--usage", str(FIX / "usage.csv"), "--prices", str(FIX / "prices.csv"), "--budgets", str(FIX / "budgets.csv")]
    a, b = tmp_path / "a", tmp_path / "b"
    assert run_script(SCRIPT, *args, "--out-dir", str(a)).returncode == 0
    assert run_script(SCRIPT, *args, "--out-dir", str(b)).returncode == 0
    for f in ("showback.csv", "anomalies.csv", "budget.csv", "finops-report.md"):
        assert (a / f).read_bytes() == (b / f).read_bytes()
        assert run_script(SCRIPT, "--verify", str(a / f), *args).returncode == 0
    # verify accepts empty optional values, as the runner passes them
    assert run_script(SCRIPT, "--verify", str(a / "budget.csv"), *args, "--as-of", "").returncode == 0
    tampered = a / "budget.csv"
    tampered.write_text(tampered.read_text().replace("269.96", "249.96"), encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(tampered), *args).returncode == 1


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src


# ---------------------------------------------------------------- audit 2026-10-19 regressions

def test_audit_csv_injection_escaped_numbers_untouched(tmp_path):
    usage = (UHEAD + "2026-10-05,legal,\"=HYPERLINK(\"\"http://evil\"\",\"\"x\"\")\",gpt-x,10,1000,100,0\n"
                     "2026-10-06,\"=cmd|'/c calc'!A1\",chat,gpt-x,10,1000,100,0\n"
                     "2026-10-06,ops,chat,@model,10,1000,100,0\n")
    prices = PHEAD + "gpt-x,2.00,8.00,0.50,2026-08-01\n"
    res, out = _run(tmp_path, usage, prices, "team,month,budget_usd\nlegal,2026-10,0.001\n")
    assert res.returncode == 0, res.stderr
    for f in ("showback.csv", "budget.csv"):
        for r in _rows(out / f):
            for v in r.values():
                assert not (v.startswith(("=", "+", "@", "\t", "\r")) or (v.startswith("-") and not v[1:2].isdigit())), (f, v)
    teams = {r["team"] for r in _level(out, "team")}
    assert "'=cmd|'/c calc'!A1" in teams
    assert any(r["feature"].startswith("'=HYPERLINK") for r in _level(out, "team_feature"))
    assert any(r["model"] == "'@model" for r in _level(out, "detail"))
    legal = [b for b in _rows(out / "budget.csv") if b["team"] == "legal"][0]
    assert legal["variance"].startswith("-") and Decimal(legal["variance"]) < 0  # numeric value not escaped
    for f in ("showback.csv", "budget.csv"):
        v = run_script(SCRIPT, "--verify", str(out / f), "--usage", str(tmp_path / "u.csv"), "--prices",
                       str(tmp_path / "p.csv"), "--budgets", str(tmp_path / "b.csv"))
        assert v.returncode == 0, v.stdout


def test_audit_ragged_usage_row_rejected(tmp_path):
    usage = ("date,team,feature,model,requests,input_tokens,output_tokens\n"
             "2026-10-01,a,f,gpt-x,10,1000,0\n2026-10-01,a,f,gpt-x,10,1000,0,extra\n")
    res, out = _run(tmp_path, usage, PHEAD + "gpt-x,2.00,8.00,0.50,2026-08-01\n")
    assert res.returncode == 2 and "line 3" in res.stderr and "ragged" in res.stderr
    ok, _ = _run(tmp_path, "date,team,feature,model,requests,input_tokens,output_tokens\n2026-10-01,a,f,gpt-x,10,1000,0,\n",
                 PHEAD + "gpt-x,2.00,8.00,0.50,2026-08-01\n")
    assert ok.returncode == 0  # an empty trailing field drops nothing


def test_audit_exact_duplicate_usage_rows_reported(tmp_path):
    usage = ("date,team,feature,model,requests,input_tokens,output_tokens\n"
             "2026-10-01,a,f,gpt-x,10,1000,0\n2026-10-01,a,f,gpt-x,10,1000,0\n2026-10-02,a,f,gpt-x,10,1000,0\n")
    res, out = _run(tmp_path, usage, PHEAD + "gpt-x,2.00,8.00,0.50,2026-08-01\n")
    assert res.returncode == 0 and "duplicate" in res.stderr and "2, 3" in res.stderr
    md = (out / "finops-report.md").read_text(encoding="utf-8")
    assert "Exact-duplicate usage rows: 1 group(s) (usage lines 2, 3)" in md
    assert _level(out, "total")[0]["requests"] == "30"  # still summed as supplied


def test_audit_non_utf8_input_exit_2(tmp_path):
    (tmp_path / "bin.csv").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\xff\xfe\xfd")
    (tmp_path / "p.csv").write_text(PHEAD + "gpt-x,2.00,8.00,0.50,2026-08-01\n", encoding="utf-8")
    res = run_script(SCRIPT, "--usage", str(tmp_path / "bin.csv"), "--prices", str(tmp_path / "p.csv"),
                     "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 2 and "Traceback" not in res.stderr and "UTF-8" in res.stderr
