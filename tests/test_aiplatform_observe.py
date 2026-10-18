"""Tests for ai-platform/llm-observability/scripts/observe.py (fixtures are fictional)."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/llm-observability/scripts/observe.py"
FX = REPO_ROOT / "skills/ai-platform/llm-observability/evals/fixtures"
BASE = ["--baseline-start", "2026-09-01", "--baseline-end", "2026-09-07"]


def _run(tmp_path, *extra, traces=None, slo=None):
    out = tmp_path / "out"
    r = run_script(SCRIPT, "--traces", str(traces or FX / "traces.jsonl"), "--slo", str(slo or FX / "slo.csv"),
                   "--out-dir", str(out), *extra)
    d = json.loads((out / "dashboard.json").read_text(encoding="utf-8")) if (out / "dashboard.json").exists() else None
    md = (out / "alerts.md").read_text(encoding="utf-8") if (out / "alerts.md").exists() else ""
    return r, d, md


def _span(tid, ts, lat, feature="f", status="ok", **kw):
    o = {"trace_id": tid, "ts": ts, "feature": feature, "model": "m", "latency_ms": lat,
         "input_tokens": 10, "output_tokens": 5, "status": status, "fixture": "fictional"}
    o.update(kw)
    return json.dumps(o)


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_happy_path_metrics_hand_checked(tmp_path):
    r, d, md = _run(tmp_path, *BASE)
    assert r.returncode == 0, r.stderr
    assert d["window"]["spans_current"] == 20 and d["window"]["spans_baseline"] == 14
    cs = d["by_feature"]["claims-summary"]
    # latencies 1200..2100 step 100: p50 rank 5 -> 1600; p95 rank ceil(9.5)=10 -> 2100; 1 error of 10
    assert (cs["latency_p50_ms"], cs["latency_p95_ms"], cs["latency_p99_ms"]) == (1600, 2100, 2100)
    assert cs["error_rate"] == 0.1 and cs["tokens_per_request"] == 1200.0
    assert cs["cost_per_request_usd"] == 0.0024 and cs["eval_score_mean"] == 0.85
    pq = d["by_feature"]["policy-qa"]
    assert pq["cost_per_request_usd"] is None and pq["cost_coverage"] == 0
    o = d["overall"]
    # 20 latencies (600..1500, 1200..2100): p95 rank 19 -> 2000; tokens (10*1200 + 10*500)/20 = 850
    assert o["latency_p95_ms"] == 2000 and o["tokens_per_request"] == 850.0 and o["error_rate"] == 0.05
    assert o["cost_coverage"] == 0.5 and o["feedback_up"] == 2 and o["feedback_down"] == 2
    # drift: tokens 1000 -> 1200 = +20 %; p95 1600 -> 2100 = +31.25 %; eval 0.9 -> 0.85 = -5.56 %
    assert d["drift"]["claims-summary"] == {"drift_tokens_per_request_pct": 20.0,
                                            "drift_latency_p95_ms_pct": 31.25,
                                            "drift_eval_score_mean_pct": -5.56}
    assert d["drift"]["overall"]["drift_latency_p95_ms_pct"] == 25.0
    assert d["breaches"] == 0 and all(s["status"] == "OK" for s in d["slo_results"])
    for sec in ("## Status", "## SLO breaches", "## Drift", "## By feature"):
        assert sec in md
    assert (tmp_path / "out" / "trace-schema.json").exists()


def test_window_breach_exits_1_and_cost_is_never_estimated(tmp_path):
    r, d, md = _run(tmp_path, slo=FX / "slo-breach.csv")
    assert r.returncode == 1 and "1 SLO breach" in r.stderr
    lat, err, cost = d["slo_results"]
    # 24h back from newest span (09-10 15:30): claims spans at 09-09 21:00 .. 09-10 15:00 -> 1800..2100, rank 4 -> 2100
    assert lat["status"] == "BREACH" and lat["observed"] == 2100 and lat["requests_in_window"] == 4
    assert err["status"] == "OK"
    assert cost["status"] == "NO DATA" and cost["observed"] is None
    assert d["drift"] == {} and "drift not computed" in md


def test_nearest_rank_percentiles_on_small_sample(tmp_path):
    t = tmp_path / "t.jsonl"
    lats = [10, 20, 30, 40, 50]
    t.write_text("\n".join(_span(f"t{i}", f"2026-09-0{i + 1}T00:00:00Z", v) for i, v in enumerate(lats)) + "\n")
    slo = tmp_path / "s.csv"
    slo.write_text("metric,threshold,window\nlatency_p50_ms,30,all\n")
    r, d, _ = _run(tmp_path, traces=t, slo=slo)
    assert r.returncode == 0
    # n=5: p50 rank 3 -> 30; p95 rank ceil(4.75)=5 -> 50; p99 rank 5 -> 50
    assert (d["overall"]["latency_p50_ms"], d["overall"]["latency_p95_ms"], d["overall"]["latency_p99_ms"]) == (30, 50, 50)


def test_eval_score_slo_uses_min_direction_and_drift_slo(tmp_path):
    slo = tmp_path / "s.csv"
    slo.write_text("metric,threshold,window,feature\neval_score_mean,0.86,all,claims-summary\n"
                   "drift_latency_p95_ms_pct,30,all,claims-summary\n")
    r, d, _ = _run(tmp_path, *BASE, slo=slo)
    assert r.returncode == 1
    ev, dr = d["slo_results"]
    assert ev["comparator"] == ">=" and ev["observed"] == 0.85 and ev["status"] == "BREACH"
    assert dr["observed"] == 31.25 and dr["status"] == "BREACH"


def test_bad_spans_rejected_and_counted(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join([
        _span("a", "2026-09-01T00:00:00Z", 100),
        "{not json",
        json.dumps({"trace_id": "b", "ts": "2026-09-01T00:00:00Z", "fixture": "fictional"}),
        _span("c", "2026-09-01T00:00:00Z", 100, status="maybe"),
        _span("d", "2026-09-01T01:00:00Z", 300, route="r", feature=None),
    ]) + "\n")
    slo = tmp_path / "s.csv"
    slo.write_text("metric,threshold,window\nerror_rate,0.5,all\n")
    r, d, _ = _run(tmp_path, traces=t, slo=slo)
    assert r.returncode == 0
    assert d["window"]["spans_rejected"] == 3 and d["overall"]["requests"] == 2
    assert set(d["by_feature"]) == {"f", "r"}


def test_missing_and_invalid_inputs_exit_2(tmp_path):
    assert run_script(SCRIPT, "--traces", str(FX / "traces.jsonl"), "--out-dir", str(tmp_path)).returncode == 2
    assert _run(tmp_path, traces=tmp_path / "missing.jsonl")[0].returncode == 2
    bad_metric = tmp_path / "bm.csv"
    bad_metric.write_text("metric,threshold,window\nvibes,1,all\n")
    assert _run(tmp_path, slo=bad_metric)[0].returncode == 2
    bad_window = tmp_path / "bw.csv"
    bad_window.write_text("metric,threshold,window\nerror_rate,0.1,weekly\n")
    assert _run(tmp_path, slo=bad_window)[0].returncode == 2
    assert _run(tmp_path, "--baseline-start", "2026-09-01")[0].returncode == 2
    empty = tmp_path / "e.jsonl"
    empty.write_text("{bad\n")
    assert _run(tmp_path, traces=empty)[0].returncode == 2
