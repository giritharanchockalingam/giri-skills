"""Tests for presales/effort-estimator/scripts/estimate.py."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import copy_asset, run_script

SCRIPT = "skills/presales/effort-estimator/scripts/estimate.py"
WBS = "skills/presales/effort-estimator/assets/wbs-template.csv"
RATES = "skills/presales/effort-estimator/assets/rate-card.example.csv"

EXPECTED_JSON_KEYS = {"total", "phases", "basis_mix", "unresolved", "cost"}


def _estimate(tmp_path: Path, *extra: str):
    wbs = copy_asset(WBS, tmp_path)
    return run_script(SCRIPT, "--iterations", "2000", "--seed", "42", *extra, str(wbs))


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_happy_path_json(tmp_path):
    r = _estimate(tmp_path, "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert EXPECTED_JSON_KEYS <= set(data)
    assert data["total"]["50"] > 0


def test_seed_is_deterministic(tmp_path):
    a = _estimate(tmp_path, "--json")
    b = _estimate(tmp_path, "--json")
    assert a.returncode == 0 and b.returncode == 0
    assert json.loads(a.stdout)["total"] == json.loads(b.stdout)["total"]


def test_with_rate_card(tmp_path):
    wbs = copy_asset(WBS, tmp_path)
    rates = copy_asset(RATES, tmp_path)
    r = run_script(
        SCRIPT, "--iterations", "1000", "--seed", "7", "--json",
        "--rates", str(rates), str(wbs),
    )
    assert r.returncode == 0, r.stderr
    assert "cost" in json.loads(r.stdout)


def test_missing_wbs_file(tmp_path):
    r = run_script(SCRIPT, "--iterations", "100", str(tmp_path / "nope.csv"))
    assert r.returncode == 2


def test_missing_required_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("task_id,phase,role\n1,Phase 1,Engineer\n", encoding="utf-8")
    r = run_script(SCRIPT, "--iterations", "100", str(bad))
    assert r.returncode == 2


# --- regression tests for audit 2026-10-19 findings -------------------------------------------

AUDIT_WBS = (
    "task_id,phase,work_package,task,role,driver_group,count,unit_o,unit_m,unit_p,"
    "optimistic,most_likely,pessimistic,basis,predecessors,notes\n"
    "1.1,Discover,Mobilize,Kickoff,Program Manager,,,,,,3,5,8,JUD,,\n"
    "1.2,Discover,Inventory,API inventory,Solution Architect,apis,60,0.25,0.5,1,,,,PAR,1.1,\n"
    "2.1,Build,Wave 1,Migrate simple proxies,Developer,apis,40,1,2,4,,,,PAR,1.2,\n"
    "2.2,Build,Wave 2,Migrate complex proxies,Developer,apis,20,3,5,10,,,,ANA,2.1,\n"
    "2.3,Build,Security,\"OAuth, mTLS and key rotation\",Solution Architect,,,,,,10,15,25,JUD,1.2,\n"
    "3.1,Test,QA,Regression automation,QA Engineer,,,,,,20,30,50,JUD,2.1,\n"
    "3.2,Test,Perf,Performance test,QA Engineer,,,,,,5,8,15,JUD,2.2,\n"
    "4.1,Cutover,Go-live,Cutover and hypercare,Developer,,,,,,10,15,30,JUD,3.1,\n"
    "9.1,Cross,PM,Program management,Program Manager,,,,,,30,40,60,JUD,,\n"
)
RATE_HDR = "role,grade,location,cost_rate,bill_rate,currency,valid_until,notes\n"
AUDIT_RATES = RATE_HDR + (
    "Program Manager,M3,onshore,950,1500,USD,2027-06-30,\n"
    "Solution Architect,M2,onshore,850,1300,USD,2027-06-30,\n"
    "Developer,S2,offshore,280,480,USD,2027-06-30,\n"
    "QA Engineer,S2,offshore,250,420,USD,2027-06-30,\n"
)
AUDIT_RATES_DUP = RATE_HDR + (
    "Program Manager,M3,onshore,950,1500,USD,2027-06-30,\n"
    "Solution Architect,M2,onshore,850,1300,USD,2027-06-30,\n"
    "Developer,S2,onshore,700,1100,USD,2027-06-30,\n"
    "Developer,S2,offshore,2300,4000,INR,2027-06-30,\n"
    "QA Engineer,S2,offshore,250,420,USD,2025-01-31,expired\n"
)


def _w(tmp_path: Path, name: str, text: str, bom: bool = False) -> Path:
    p = tmp_path / name
    p.write_text(("\ufeff" if bom else "") + text, encoding="utf-8")
    return p


def _with_location(wbs: str, loc_by_task: dict[str, str]) -> str:
    lines = wbs.strip("\n").split("\n")
    out = [lines[0] + ",location"]
    for ln in lines[1:]:
        out.append(ln + "," + loc_by_task.get(ln.split(",", 1)[0], ""))
    return "\n".join(out) + "\n"


def _run(*args: str):
    return run_script(SCRIPT, "--iterations", "2000", "--seed", "7", *args)


def test_audit_role_priced_at_two_locations_without_wbs_location_exits_2(tmp_path):
    """Finding (critical): rate card keyed by role only kept the LAST Developer row."""
    r = _run("--rates", str(_w(tmp_path, "r.csv", AUDIT_RATES_DUP)), str(_w(tmp_path, "w.csv", AUDIT_WBS)))
    assert r.returncode == 2
    assert "Developer" in r.stderr and "location" in r.stderr
    assert "Traceback" not in r.stderr


def test_audit_duplicate_role_and_location_rows_exit_2(tmp_path):
    rates = AUDIT_RATES + "Developer,S3,offshore,300,500,USD,2027-06-30,\n"
    r = _run("--rates", str(_w(tmp_path, "r.csv", rates)), str(_w(tmp_path, "w.csv", AUDIT_WBS)))
    assert r.returncode == 2 and "duplicate rows for role 'Developer'" in r.stderr


def test_audit_rate_matches_on_role_and_location(tmp_path):
    usd_only = AUDIT_RATES_DUP.replace("2300,4000,INR", "280,480,USD")
    wbs = _with_location(AUDIT_WBS, {"2.1": "offshore", "2.2": "offshore", "4.1": "onshore"})
    r = _run("--json", "--as-of", "2026-10-18", "--rates", str(_w(tmp_path, "r.csv", usd_only)),
             str(_w(tmp_path, "w.csv", wbs)))
    assert r.returncode == 0, r.stderr
    rows = {(x["role"], x["location"]): x for x in json.loads(r.stdout)["cost"]["rows"]}
    assert rows[("Developer", "offshore")]["cost_rate"] == 280
    assert rows[("Developer", "onshore")]["cost_rate"] == 700


def test_audit_mixed_currencies_without_fx_exit_2(tmp_path):
    """Finding (critical): INR and USD costs were summed under one label."""
    wbs = _with_location(AUDIT_WBS, {"2.1": "offshore", "2.2": "offshore", "4.1": "onshore"})
    r = _run("--rates", str(_w(tmp_path, "r.csv", AUDIT_RATES_DUP)), str(_w(tmp_path, "w.csv", wbs)))
    assert r.returncode == 2
    assert "mixes currencies (INR, USD)" in r.stderr and "--fx" in r.stderr
    # a reporting currency without the FX rate for the other currency is still refused
    r = _run("--currency", "USD", "--rates", str(_w(tmp_path, "r.csv", AUDIT_RATES_DUP)), str(_w(tmp_path, "w.csv", wbs)))
    assert r.returncode == 2 and "no FX rate supplied for INR" in r.stderr


def test_audit_mixed_currencies_converted_only_with_explicit_fx(tmp_path):
    wbs = _with_location(AUDIT_WBS, {"2.1": "offshore", "2.2": "offshore", "4.1": "onshore"})
    rates = _w(tmp_path, "r.csv", AUDIT_RATES_DUP)
    w = _w(tmp_path, "w.csv", wbs)
    r = _run("--json", "--currency", "USD", "--fx", "INR=0.012", "--rates", str(rates), str(w))
    assert r.returncode == 0, r.stderr
    cost = json.loads(r.stdout)["cost"]
    assert cost["currency"] == "USD" and cost["fx_used"] == {"INR": 0.012}
    off = next(x for x in cost["rows"] if x["location"] == "offshore" and x["role"] == "Developer")
    assert off["rate_currency"] == "INR"
    assert abs(off["cost_p80"] - off["pd_p80"] * 2300 * 0.012) < 1e-6
    assert abs(cost["cost_p80"] - sum(x.get("cost_p80", 0) for x in cost["rows"])) < 1e-6
    md = _run("--currency", "USD", "--fx", "INR=0.012", "--rates", str(rates), str(w)).stdout
    assert "FX applied" in md and "| Cost (USD) |" in md


def test_audit_bom_rate_card_matches_like_plain(tmp_path):
    """Finding (high): BOM rate card matched no role -> cost silently 0."""
    w = _w(tmp_path, "w.csv", AUDIT_WBS)
    plain = _run("--json", "--rates", str(_w(tmp_path, "r.csv", AUDIT_RATES)), str(w))
    bom = _run("--json", "--rates", str(_w(tmp_path, "rb.csv", AUDIT_RATES, bom=True)), str(w))
    assert plain.returncode == 0 and bom.returncode == 0, bom.stderr
    a, b = json.loads(plain.stdout)["cost"], json.loads(bom.stdout)["cost"]
    assert b["missing_roles"] == [] and b["currency"] == "USD"
    assert b["cost_p80"] == a["cost_p80"] > 0


def test_audit_bom_wbs_is_read(tmp_path):
    r = _run("--json", str(_w(tmp_path, "w.csv", AUDIT_WBS, bom=True)))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["total"]["50"] > 0


def test_audit_negative_effort_exits_2(tmp_path):
    """Finding (high): negative three-point values produced negative P50 with exit 0."""
    wbs = AUDIT_WBS.split("\n")[0] + "\n1.1,Build,x,Task A,Developer,,,,,,-50,-40,-30,JUD,,\n"
    r = _run(str(_w(tmp_path, "w.csv", wbs)))
    assert r.returncode == 2 and "must be >= 0" in r.stderr
    wbs = AUDIT_WBS.split("\n")[0] + "\n1.2,Build,x,Task C,Developer,,-5,1,2,3,,,,PAR,,\n"
    r = _run(str(_w(tmp_path, "w2.csv", wbs)))
    assert r.returncode == 2 and "count must be >= 0" in r.stderr


def test_audit_non_numeric_and_non_finite_effort_exit_2(tmp_path):
    hdr = AUDIT_WBS.split("\n")[0]
    for bad in ("abc", "nan", "inf"):
        wbs = f"{hdr}\n1.1,Build,x,Task A,Developer,,,,,,1,{bad},3,JUD,,\n"
        r = _run(str(_w(tmp_path, f"w-{bad}.csv", wbs)))
        assert r.returncode == 2, (bad, r.stdout)
        assert "most_likely" in r.stderr and "Traceback" not in r.stderr


def test_placeholder_counts_still_unresolved_not_errors(tmp_path):
    # the template's "[TO BE BASELINED]" counts remain unresolved rows, not input errors
    r = _estimate(tmp_path, "--json")
    assert r.returncode == 0, r.stderr
    assert {"1.2", "2.1"} <= set(json.loads(r.stdout)["unresolved"])


def test_audit_duplicate_task_id_exits_2(tmp_path):
    """Finding (medium): duplicate task_id samples were pooled under one key."""
    hdr = AUDIT_WBS.split("\n")[0]
    wbs = f"{hdr}\n1.1,Build,x,Task A,Developer,,,,,,5,10,20,JUD,,\n1.1,Build,x,Task B,Developer,,,,,,10,20,30,JUD,,\n"
    r = _run(str(_w(tmp_path, "w.csv", wbs)))
    assert r.returncode == 2 and "duplicate task_id '1.1'" in r.stderr


def test_audit_duration_marked_tbd_not_invented(tmp_path):
    """Finding (medium): description promised duration the script never computed."""
    w = _w(tmp_path, "w.csv", AUDIT_WBS)
    md = _run(str(w))
    assert md.returncode == 0
    assert "## Duration" in md.stdout
    assert "Duration: [TO BE BASELINED — owner: Estimation lead]" in md.stdout
    js = json.loads(_run("--json", str(w)).stdout)
    assert js["duration"] == "[TO BE BASELINED — owner: Estimation lead]"
    tpl = (Path(__file__).resolve().parents[1] / "skills/presales/effort-estimator/assets/estimate-summary-template.md").read_text(encoding="utf-8")
    assert "[TO BE BASELINED — owner: Estimation lead]" in tpl.split("| Duration |", 1)[1].split("\n", 1)[0]


def test_audit_expired_rate_is_flagged(tmp_path):
    """Finding (low): an expired rate (2025-01-31) was used without a warning."""
    rates = AUDIT_RATES.replace("QA Engineer,S2,offshore,250,420,USD,2027-06-30", "QA Engineer,S2,offshore,250,420,USD,2025-01-31")
    args = ("--as-of", "2026-10-18", "--rates", str(_w(tmp_path, "r.csv", rates)), str(_w(tmp_path, "w.csv", AUDIT_WBS)))
    r = _run(*args)
    assert r.returncode == 0
    assert "QA Engineer (offshore): expired 2025-01-31" in r.stdout
    assert "expired 2025-01-31" in r.stderr
    js = json.loads(_run("--json", *args).stdout)
    assert js["cost"]["rate_validity_issues"] == ["QA Engineer (offshore): expired 2025-01-31"]


def test_audit_non_utf8_input_exits_2(tmp_path):
    b = tmp_path / "bin.csv"
    b.write_bytes(b"\x7fELF\x02\x01\x01\x00" + bytes(range(128, 256)) * 4)
    r = _run(str(b))
    assert r.returncode == 2 and "not a UTF-8 CSV" in r.stderr and "Traceback" not in r.stderr
    r = _run("--rates", str(b), str(_w(tmp_path, "w.csv", AUDIT_WBS)))
    assert r.returncode == 2 and "not a UTF-8 CSV" in r.stderr
