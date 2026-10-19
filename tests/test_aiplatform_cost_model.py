"""Tests for ai-platform/llm-cost-model/scripts/cost_model.py.

Expected numbers are hand-computed from the fictional fixture (see references/cost-method.md):
  support-chat on fict-large: 50M x 3 + 50M x 0.30 + 20M x 15 = 465.00 (no cache 600.00)
  doc-summary  on fict-large: 80M x 3 + 10M x 15 = 390.00
  support-chat on fict-small: 50M x 0.25 + 50M x 0.025 + 20M x 1.25 = 38.75
"""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SKILL = "skills/ai-platform/llm-cost-model"
SCRIPT = f"{SKILL}/scripts/cost_model.py"
FX = REPO_ROOT / SKILL / "evals" / "fixtures"
TBB = "[TO BE BASELINED — owner: FinOps lead]"


def _args(assignment="assignment.csv", prices=None, workload=None):
    return ["--workload", str(workload or FX / "workload.csv"), "--prices", str(prices or FX / "prices.csv"),
            "--assignment", str(FX / assignment) if "/" not in str(assignment) else str(assignment)]


def _run(tmp_path, *extra, **kw):
    out = tmp_path / "out"
    r = run_script(SCRIPT, *_args(**kw), *extra, "--out", str(out))
    d = json.loads((out / "cost-model.json").read_text()) if (out / "cost-model.json").exists() else None
    md = (out / "cost-model.md").read_text() if (out / "cost-model.md").exists() else ""
    return r, d, md


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_feature_costs_hand_checked(tmp_path):
    r, d, _ = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    sc, ds = d["features"]["support-chat"], d["features"]["doc-summary"]
    assert (sc["input_tokens_month"], sc["cached_input_tokens_month"], sc["output_tokens_month"]) == \
        (100_000_000, 50_000_000, 20_000_000)
    assert (sc["cost_input"], sc["cost_cached_input"], sc["cost_output"], sc["cost_month"]) == (150.0, 15.0, 300.0, 465.0)
    assert (sc["cost_without_caching"], sc["caching_saving"], sc["cost_per_request"]) == (600.0, 135.0, 0.00465)
    assert (ds["cost_month"], ds["caching_saving"], ds["cost_per_request"]) == (390.0, 0.0, 0.0195)


def test_totals_and_by_model(tmp_path):
    _, d, _ = _run(tmp_path)
    assert d["monthly_total"] == 855.0 and d["requests_per_month"] == 120_000
    assert d["cost_per_request"] == 0.007125
    assert d["caching_saving_total"] == 135.0 and d["cost_without_caching_total"] == 990.0
    assert d["by_model"]["fict-large"]["cost_month"] == 855.0


def test_what_if_cheapest_eligible(tmp_path):
    _, d, md = _run(tmp_path)
    rows = {r["feature"]: r for r in d["what_if"]["rows"]}
    assert (rows["support-chat"]["cheapest_model"], rows["support-chat"]["cheapest_cost"],
            rows["support-chat"]["saving"]) == ("fict-small", 38.75, 426.25)
    # doc-summary only eligible for its current model -> no saving
    assert rows["doc-summary"]["cheapest_model"] == "fict-large" and rows["doc-summary"]["saving"] == 0.0
    assert d["what_if"]["total_if_all_swapped"] == 428.75 and d["what_if"]["saving_if_all_swapped"] == 426.25
    assert "| support-chat | fict-large | 465.00 | fict-small | 38.75 | 426.25 |" in md


def test_budget_within_and_alerts(tmp_path):
    r, d, md = _run(tmp_path, "--budget", "1000")
    assert r.returncode == 0
    b = d["budget"]
    assert (b["utilisation_pct"], b["headroom"], b["over_budget"]) == (85.5, 145.0, False)
    assert [(a["level_pct"], a["amount"], a["reached"]) for a in b["alerts"]] == \
        [(50.0, 500.0, True), (80.0, 800.0, True), (100.0, 1000.0, False)]
    assert "**within budget**" in md


def test_over_budget_exits_1_with_outputs(tmp_path):
    r, d, md = _run(tmp_path, "--budget", "800")
    assert r.returncode == 1
    assert d["budget"]["over_budget"] is True and d["budget"]["headroom"] == -55.0
    assert "**OVER BUDGET**" in md


def test_custom_alert_levels(tmp_path):
    _, d, _ = _run(tmp_path, "--budget", "1000", "--alert-levels", "90,75")
    assert [a["level_pct"] for a in d["budget"]["alerts"]] == [75.0, 90.0]


def test_no_budget_is_to_be_baselined(tmp_path):
    r, d, md = _run(tmp_path)
    assert r.returncode == 0 and d["budget"] is None
    assert TBB in md.split("## Budget")[1]


def test_sections_present(tmp_path):
    _, _, md = _run(tmp_path, "--budget", "1000")
    for s in ("## Monthly total", "## By feature", "## What-if", "## Budget", "## Sources"):
        assert s in md


def test_unpriced_assigned_model_exits_2(tmp_path):
    r, _, _ = _run(tmp_path, assignment="assignment-unpriced.csv")
    assert r.returncode == 2 and "fict-medium" in r.stderr


def test_missing_cached_price_charges_full_input(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("model,price_in_per_1m,price_out_per_1m,source,as_of\nfict-large,3,15,fictional,2026-09-01\n"
                 "fict-small,0.25,1.25,fictional,2026-09-01\n")
    _, d, _ = _run(tmp_path, prices=p)
    sc = d["features"]["support-chat"]
    assert sc["cost_month"] == 600.0 and sc["caching_saving"] == 0.0
    assert any("charged at the full input price" in n for n in d["notes"])


def test_unsourced_price_marked(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("model,price_in_per_1m,price_out_per_1m,cached_in_per_1m,source,as_of\n"
                 "fict-large,3,15,0.3,,\nfict-small,0.25,1.25,0.025,fictional,2026-09-01\n")
    r, d, md = _run(tmp_path, prices=p)
    assert r.returncode == 0
    assert d["prices"]["fict-large"]["unsourced"] is True
    assert TBB in md.split("## Sources")[1]


def test_unpriced_eligible_model_excluded(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("feature,model,eligible_models\nsupport-chat,fict-large,fict-nano\ndoc-summary,fict-large,\n")
    _, d, _ = _run(tmp_path, assignment=a)
    row = d["what_if"]["rows"][0]
    assert row["eligible_unpriced"] == ["fict-nano"] and row["cheapest_model"] is None


def test_unassigned_feature_exits_2(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("feature,model\nsupport-chat,fict-large\n")
    r = run_script(SCRIPT, *_args(assignment=a))
    assert r.returncode == 2 and "doc-summary" in r.stderr


def test_bad_values_exit_2(tmp_path):
    w = tmp_path / "w.csv"
    w.write_text("feature,requests_per_month,input_tokens,output_tokens,cached_input_share\nsupport-chat,10,10,10,1.5\n"
                 "doc-summary,1,1,1,\n")
    assert run_script(SCRIPT, *_args(workload=w)).returncode == 2  # share > 1
    assert run_script(SCRIPT, *_args(), "--budget", "abc").returncode == 2
    assert run_script(SCRIPT, *_args(), "--budget", "0").returncode == 2


def test_template_rows_are_not_data(tmp_path):
    r = run_script(SCRIPT, *_args(workload=REPO_ROOT / SKILL / "assets" / "workload-template.csv"))
    assert r.returncode == 2 and "no data rows" in r.stderr


def test_missing_required_flag_exits_2():
    assert run_script(SCRIPT, "--workload", str(FX / "workload.csv")).returncode == 2


# --- brownfield: modelled vs billed (--actuals) ---

def test_actuals_variance_hand_checked(tmp_path):
    r, d, md = _run(tmp_path, "--budget", "1000", "--actuals", str(FX / "actuals.csv"))
    assert r.returncode == 0, r.stderr
    a = d["actuals"]
    by = {x["feature"]: x for x in a["rows"]}
    assert by["support-chat"]["variance"] == 147.40 and by["support-chat"]["variance_pct"] == 31.7
    assert by["support-chat"]["actual_cost_per_request"] == round(612.40 / 131000, 6)
    assert by["doc-summary"]["variance"] == -18.85 and by["doc-summary"]["variance_pct"] == -4.8
    assert [x["feature"] for x in a["rows"]] == ["support-chat", "doc-summary"]  # largest |variance| first
    assert a["unmodelled"] == [{"feature": "ticket-tagging", "actual_cost": 48.2}]
    assert (a["modelled_total_matched"], a["actual_total_matched"], a["actual_total_all"]) == (855.0, 983.55, 1031.75)
    assert a["billed_vs_budget_pct"] == 103.2
    assert "## Actuals vs model" in md and "Billed but not in the model: ticket-tagging" in md


def test_actuals_missing_feature_and_no_source(tmp_path):
    act = tmp_path / "act.csv"
    act.write_text("feature,actual_cost\nsupport-chat,465\n")
    r, d, md = _run(tmp_path, "--actuals", str(act))
    assert r.returncode == 0, r.stderr
    a = d["actuals"]
    assert a["not_billed"] == ["doc-summary"] and a["period"] == TBB and a["source"] == TBB
    assert a["billed_vs_budget_pct"] is None
    assert next(x for x in a["rows"] if x["feature"] == "support-chat")["variance"] == 0.0
    assert "In the model but absent from the bill: doc-summary." in md


def test_actuals_bad_input_exits_2(tmp_path):
    act = tmp_path / "act.csv"
    act.write_text("feature,actual_cost\nsupport-chat,lots\n")
    r, _, _ = _run(tmp_path, "--actuals", str(act))
    assert r.returncode == 2 and "not numeric" in r.stderr


def test_no_actuals_no_section(tmp_path):
    _, d, md = _run(tmp_path)
    assert "actuals" not in d and "Actuals vs model" not in md
