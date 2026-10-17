"""Tests for ai-platform/infra-gpu-sizing/scripts/size.py."""
from __future__ import annotations

import json

from conftest import run_script

SCRIPT = "skills/ai-platform/infra-gpu-sizing/scripts/size.py"

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
