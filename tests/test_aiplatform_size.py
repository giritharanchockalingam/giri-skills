"""Tests for ai-platform/infra-gpu-sizing/scripts/size.py."""
from __future__ import annotations

import json

import pytest

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/infra-gpu-sizing/scripts/size.py"
SKILL = REPO_ROOT / "skills/ai-platform/infra-gpu-sizing"

BASE_SETS = [
    "daily_active_users=1000",
    "requests_per_user_per_day=10",
    "tokens_in_per_request=500",
    "tokens_out_per_request=200",
    "active_hours_per_day=8",
    "peak_factor=2",
    "decode_tokens_per_s_per_gpu=50",
    "prefill_tokens_per_s_per_gpu=1000",
    "rental_usd_per_gpu_hour=2.0",
]


def _args(*extra: str):
    args: list[str] = []
    for s in BASE_SETS:
        args += ["--set", s]
    return args + list(extra)


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_happy_path_json():
    r = run_script(SCRIPT, *_args("--json"))
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["cost_monthly_usd"]["rental"]["total"] > 0
    assert "capacity" in data


def test_table_output():
    r = run_script(SCRIPT, *_args())
    assert r.returncode == 0, r.stderr
    assert "MONTHLY COST" in r.stdout


def test_no_inputs_exits_2():
    r = run_script(SCRIPT)
    assert r.returncode == 2


def test_non_numeric_value_exits_1():
    r = run_script(SCRIPT, "--set", "daily_active_users=abc")
    assert r.returncode == 1
    assert "non-numeric" in (r.stdout + r.stderr)


# --- brownfield: compare the fleet running today (current_gpus) ---

def _fleet(*sets):
    r = run_script(SCRIPT, "--inputs", str(SKILL / "evals/fixtures/inputs-existing-fleet.csv"), "--json", *sets)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_existing_fleet_over_provisioned():
    f = _fleet()["current_fleet"]
    assert (f["current_gpus"], f["sized_gpus_with_spare"], f["delta_gpus"]) == (6, 2, 4)
    assert f["verdict"] == "over-provisioned"
    assert f["delta_usd_per_month_at_rental_rate"] == 6132.0  # 4 x 730 h x 2.10
    assert (f["cheapest_option"], f["saving_vs_current_usd_per_month"]) == ("rental", 6132.0)


@pytest.mark.parametrize("gpus,verdict", [("2", "right-sized"), ("1", "under-provisioned")])
def test_existing_fleet_verdicts(gpus, verdict):
    res = _fleet("--set", f"current_gpus={gpus}")
    assert res["current_fleet"]["verdict"] == verdict
    if verdict == "under-provisioned":
        assert any("short of the sized need" in n for n in res["notes"])


def test_no_current_gpus_no_fleet_block():
    r = run_script(SCRIPT, "--inputs", str(SKILL / "evals/fixtures/inputs.csv"), "--json")
    assert "current_fleet" not in json.loads(r.stdout)


def test_fractional_current_gpus_rejected():
    r = run_script(SCRIPT, "--inputs", str(SKILL / "evals/fixtures/inputs-existing-fleet.csv"),
                   "--set", "current_gpus=2.5")
    assert r.returncode != 0 and "whole number" in r.stderr
