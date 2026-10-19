"""Tests for ai-platform/ai-slo-definition/scripts/slo.py (hand-checked SLO arithmetic)."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-slo-definition/scripts/slo.py"
FIX = REPO_ROOT / "skills/ai-platform/ai-slo-definition/evals/fixtures"
T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
TBD_PO = "[TO BE BASELINED — owner: Product owner]"


def _log(p: Path, rows: list[tuple], cols=("timestamp", "latency_ms", "status", "quality_pass", "cost_usd")) -> Path:
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    return p


def _minutes(n: int, err=lambda i: False, lat=lambda i: 100, q=lambda i: "1", cost=lambda i: "0.001"):
    return [((T0 + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ"), lat(i), "error" if err(i) else "ok",
             q(i), cost(i)) for i in range(n)]


def _run(tmp_path, rows, targets: str | None = None, cols=None, name="out"):
    lp = _log(tmp_path / "log.csv", rows, cols) if cols else _log(tmp_path / "log.csv", rows)
    args = ["--log", str(lp), "--out-dir", str(tmp_path / name)]
    if targets is not None:
        (tmp_path / "t.csv").write_text(targets, encoding="utf-8")
        args += ["--targets", str(tmp_path / "t.csv")]
    res = run_script(SCRIPT, *args)
    out = tmp_path / name / "slos.csv"
    got = {r["sli"]: r for r in csv.DictReader(out.open(encoding="utf-8"))} if out.exists() else {}
    return res, got


def _json(tmp_path, name="out"):
    return json.loads((tmp_path / name / "slo.json").read_text(encoding="utf-8"))


def test_nearest_rank_percentiles(tmp_path):
    # latencies 1..20 ms: p50 rank ceil(10)=10 -> 10, p95 rank ceil(19)=19 -> 19, p99 rank ceil(19.8)=20 -> 20
    res, _ = _run(tmp_path, _minutes(20, lat=lambda i: i + 1))
    s = _json(tmp_path)["summary"]
    assert (s["p50_ms"], s["p95_ms"], s["p99_ms"]) == ("10", "19", "20")


def test_budget_and_burn_hand_checked(tmp_path):
    # 120 requests over 2 h, errors at minutes 10 and 100: SLI 118/120; objective 0.99
    res, got = _run(tmp_path, _minutes(120, err=lambda i: i in (10, 100)),
                    "sli,objective,threshold,window_days\navailability,0.99,,30\n")
    a = got["availability"]
    assert a["observed"] == "0.98333"
    assert a["budget_consumed"] == "1.667"  # (2/120)/0.01
    assert a["burn_rate"] == "1.667"  # last 1h (minutes 60..119): 1 error / 60 -> (1/60)/0.01
    assert a["status"] == "breached" and res.returncode == 1


def test_exact_boundary_consumed_one_is_not_breached(tmp_path):
    t = "sli,objective,threshold,window_days\navailability,0.99,,30\n"
    res, got = _run(tmp_path, _minutes(100, err=lambda i: i == 0), t)  # 1/100 / 0.01 = exactly 1
    assert got["availability"]["budget_consumed"] == "1.000" and got["availability"]["status"] == "met"
    assert res.returncode == 0
    res2, got2 = _run(tmp_path, _minutes(100, err=lambda i: i in (0, 1)), t)
    assert got2["availability"]["status"] == "breached" and res2.returncode == 1


def test_fast_burn_page_makes_at_risk(tmp_path):
    # 2 days at 1/min = 2880 requests; 9 errors in the last hour, 2 of them in the last 5 minutes
    errs = {2880 - 60 + k for k in range(0, 60, 8)}  # 8 errors spread over the last hour
    errs |= {2879}
    res, got = _run(tmp_path, _minutes(2880, err=lambda i: i in errs),
                    "sli,objective,threshold,window_days\navailability,0.99,,30\n")
    a = got["availability"]
    # consumed = 9/2880/0.01 = 0.3125; 1h burn = (9/60)/0.01 = 15 >= 14.4; 5m: 2 errors in 5 -> 40
    assert a["budget_consumed"] == "0.313" and a["burn_rate"] == "15.000"
    assert a["status"] == "at-risk" and res.returncode == 0
    fast = _json(tmp_path)["slos"][0]["alerts"][0]
    assert fast["fires"] is True and fast["short"] == [2, 5]


def test_window_days_scales_thresholds(tmp_path):
    res, _ = _run(tmp_path, _minutes(30), "sli,objective,threshold,window_days\navailability,0.999,,28\n")
    al = _json(tmp_path)["slos"][0]["alerts"]
    # 2% x 28 x 24 / 1 = 13.44 ; 5% x 672 / 6 = 5.6 ; 10% x 672 / 72 = 0.9333
    assert abs(al[0]["threshold"]["value"] - 13.44) < 1e-9
    assert abs(al[1]["threshold"]["value"] - 5.6) < 1e-9
    assert abs(al[2]["threshold"]["value"] - 0.933333333) < 1e-8
    md = (tmp_path / "out" / "slo-spec.md").read_text()
    assert "| availability | fast-burn page | 1 h / 5 m | 13.44 |" in md
    assert "| availability | ticket | 3 d / 6 h | 0.93 | n/a |" in md  # 30-minute log cannot cover 3 d


def test_latency_and_cost_threshold_and_proposals(tmp_path):
    rows = _minutes(40, err=lambda i: i == 39, lat=lambda i: 1000 + 10 * i, cost=lambda i: f"{0.0011 + i * 0.0001:.4f}")
    res, got = _run(tmp_path, rows)
    # latency over 39 ok rows (1000..1380): p95 rank ceil(37.05)=38 -> 1370 -> proposal 1400 ms @0.95
    assert got["latency"]["objective"] == "0.95" and got["latency"]["threshold"] == "1400"
    # cost 40 rows 0.0011..0.0050: p95 rank 38 -> 0.0048 -> proposal 0.005
    assert got["cost"]["threshold"] == "0.005"
    # availability 39/40 = 0.975 -> highest ladder level <= 0.975 is 0.95
    assert got["availability"]["objective"] == "0.95"
    assert all(r["status"] == "proposed" and r["note"] == TBD_PO for r in got.values())
    res2, got2 = _run(tmp_path, rows, "sli,objective,threshold,window_days\nlatency,0.9,1300,30\n", name="o2")
    # ok latencies <= 1300: 1000..1300 = 31 of 39 -> 0.79487; consumed (8/39)/0.1 = 2.051
    assert got2["latency"]["observed"] == "0.79487" and got2["latency"]["budget_consumed"] == "2.051"
    assert got2["availability"]["status"] == "proposed" and res2.returncode == 1


def test_no_ladder_fit_and_unmeasured_slis_are_tbd_with_owner(tmp_path):
    cols = ("timestamp", "latency_ms", "status")
    rows = [r[:3] for r in _minutes(20, err=lambda i: i < 4)]  # availability 0.8 < 0.9
    res, got = _run(tmp_path, rows, cols=cols)
    assert got["availability"]["objective"] == TBD_PO and "quality" not in got and "cost" not in got
    md = (tmp_path / "out" / "slo-spec.md").read_text()
    assert "[TO BE BASELINED — owner: Eval lead]" in md and "[TO BE BASELINED — owner: FinOps lead]" in md
    for line in md.splitlines():
        if "[TO BE BASELINED" in line:
            assert line.count("[TO BE BASELINED") == line.count("— owner: ")


def test_input_errors_exit_2(tmp_path):
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2
    bad_status = [("2026-01-05T00:00:00Z", 100, "timeout", "1", "0.001")]
    assert _run(tmp_path, bad_status)[0].returncode == 2
    mixed = [("2026-01-05T00:00:00Z", 100, "ok", "1", "0.001"), ("2026-01-05T00:01:00", 100, "ok", "1", "0.001")]
    assert _run(tmp_path, mixed)[0].returncode == 2
    ok = _minutes(5)
    for t in ("sli,objective,threshold,window_days\navailability,1,,30\n",
              "sli,objective,threshold,window_days\nlatency,0.9,,30\n",
              "sli,objective,threshold,window_days\nuptime,0.9,,30\n",
              "sli,objective,threshold,window_days\navailability,0.9,,30\navailability,0.99,,30\n"):
        res, _ = _run(tmp_path, ok, t)
        assert res.returncode == 2, t
    cols = ("timestamp", "latency_ms", "status")
    res, _ = _run(tmp_path, [r[:3] for r in ok], "sli,objective\nquality,0.9\n", cols=cols)
    assert res.returncode == 2 and "quality" in res.stderr


def test_fixture_determinism_and_verify(tmp_path):
    outs = []
    for d in ("a", "b"):
        res = run_script(SCRIPT, "--log", str(FIX / "requests-incident.csv"), "--targets", str(FIX / "targets.csv"),
                         "--system", "Northwind Billing Assistant", "--out-dir", str(tmp_path / d))
        assert res.returncode == 1 and "availability" in res.stderr
        outs.append({f: (tmp_path / d / f).read_bytes() for f in ("slos.csv", "slo-spec.md", "slo.json")})
    assert outs[0] == outs[1]
    for f in ("slos.csv", "slo-spec.md"):
        assert run_script(SCRIPT, "--verify", str(tmp_path / "a" / f)).returncode == 0
    j = tmp_path / "a" / "slo.json"
    doc = json.loads(j.read_text())
    doc["slos"][0]["status"] = "met"  # tamper: claim the breached SLO is met
    j.write_text(json.dumps(doc))
    assert run_script(SCRIPT, "--verify", str(tmp_path / "a" / "slos.csv")).returncode == 1


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src
