"""Tests for ai-platform/ai-threat-model/scripts/threat_model.py (hand-checked STRIDE/OWASP rules)."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-threat-model/scripts/threat_model.py"
FIX = REPO_ROOT / "skills/ai-platform/ai-threat-model/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Security architect]"
HDR = "id,name,kind,trust_zone,handles_pii,write_actions,internet_facing\n"


def _run(tmp_path, comps: str, flows: str, controls: str | None = None, *extra):
    (tmp_path / "c.csv").write_text(HDR + comps, encoding="utf-8")
    (tmp_path / "f.csv").write_text("from,to,data,crosses_trust_boundary\n" + flows, encoding="utf-8")
    args = ["--components", str(tmp_path / "c.csv"), "--flows", str(tmp_path / "f.csv"),
            "--out-dir", str(tmp_path / "out"), *extra]
    if controls is not None:
        (tmp_path / "k.csv").write_text("threat_id,mitigation_id,status,evidence,owner\n" + controls, encoding="utf-8")
        args += ["--controls", str(tmp_path / "k.csv")]
    res = run_script(SCRIPT, *args)
    p = tmp_path / "out" / "threats.csv"
    rows = {r["threat_id"]: r for r in csv.DictReader(p.open(encoding="utf-8"))} if p.exists() else {}
    return res, rows


# user (internet) -> app (dmz, internet-facing) -> llm (vendor); app has write actions and PII
SMALL_C = ("u,User,user,internet,yes,no,yes\n"
           "app,App,app,dmz,yes,yes,yes\n"
           "m,Model,llm,vendor,no,no,no\n"
           "kb,KB,vector_store,dmz,no,no,no\n")
SMALL_F = "u,app,question,yes\napp,m,prompt,yes\nm,app,completion,yes\nkb,app,chunks,no\n"


def test_stride_per_element_counts(tmp_path):
    res, rows = _run(tmp_path, SMALL_C, SMALL_F)
    assert res.returncode == 0, res.stderr
    stride = lambda el: sorted(r["category"] for r in rows.values() if r["element"] == el and len(r["category"]) == 1)
    assert stride("u") == ["R", "S"]                       # external entity
    assert stride("app") == sorted("STRIDE")               # process
    assert stride("kb") == ["D", "I", "T"]                 # data store
    assert stride("u>app") == ["D", "I", "T"]              # data flow


def test_owasp_rules_by_kind_and_flags(tmp_path):
    res, rows = _run(tmp_path, SMALL_C, SMALL_F)
    owasp = {k for k in rows if ":LLM" in k}
    # llm: LLM01 (reached from u), LLM03, LLM04, LLM07, LLM09, LLM10; no LLM02 (handles_pii=no)
    assert {"m:LLM01", "m:LLM03", "m:LLM04", "m:LLM07", "m:LLM09", "m:LLM10"} <= owasp
    assert "m:LLM02" not in owasp
    # app: LLM02 (pii), LLM05 (fed by llm), LLM06 (write); vector store: LLM04, LLM08
    assert {"app:LLM02", "app:LLM05", "app:LLM06", "kb:LLM04", "kb:LLM08"} <= owasp
    assert len(owasp) == 11


def test_severity_hand_computed(tmp_path):
    res, rows = _run(tmp_path, SMALL_C, SMALL_F)
    # app: internet(1) + boundary(1) -> L=3; S: pii+write -> I=3 -> 9 high
    a = rows["app:S"]
    assert (a["likelihood"], a["impact"], a["severity"]) == ("3", "3", "high")
    # m: not internet, boundary -> L=2; D fixed impact 2 -> 4 medium
    assert (rows["m:D"]["likelihood"], rows["m:D"]["impact"], rows["m:D"]["severity"]) == ("2", "2", "medium")
    # kb>app: no internet end? app is internet-facing -> L=2, crosses no; T: pii(app)+write(app) -> I=3 -> 6 high
    assert (rows["kb>app:T"]["likelihood"], rows["kb>app:T"]["impact"], rows["kb>app:T"]["severity"]) == ("2", "3", "high")
    # kb: L=1 (no internet, no boundary flow), T impact 1 -> low
    assert rows["kb:T"]["severity"] == "low"


def test_controls_status_and_owner(tmp_path):
    ctl = ("app:S,,in_place,MFA,Identity lead\n"
           ",M04,in_place,TLS,Platform owner\n"
           "m:LLM01,,planned,,\n")
    res, rows = _run(tmp_path, SMALL_C, SMALL_F, ctl)
    assert rows["app:S"]["status"] == "mitigated" and rows["app:S"]["owner"] == "Identity lead"
    assert rows["u>app:I"]["status"] == "mitigated"         # only mitigation M04 is in place
    assert rows["app:LLM02"]["status"] == "open"            # M04 is not one of its mitigations
    assert rows["m:LLM01"]["status"] == "planned" and rows["m:LLM01"]["owner"] == TBD
    assert rows["app:T"]["status"] == "open" and rows["app:T"]["owner"] == TBD


def test_gate_boundary(tmp_path):
    res, rows = _run(tmp_path, SMALL_C, SMALL_F)
    n = sum(1 for r in rows.values() if r["severity"] == "high" and r["status"] == "open")
    assert n > 0
    ok = run_script(SCRIPT, "--components", str(tmp_path / "c.csv"), "--flows", str(tmp_path / "f.csv"),
                    "--max-open-high", str(n), "--out-dir", str(tmp_path / "g1"))
    bad = run_script(SCRIPT, "--components", str(tmp_path / "c.csv"), "--flows", str(tmp_path / "f.csv"),
                     "--max-open-high", str(n - 1), "--out-dir", str(tmp_path / "g2"))
    assert ok.returncode == 0 and bad.returncode == 1
    assert (tmp_path / "g2" / "threat-report.md").exists()
    assert f"FAIL: {n} open high vs limit {n - 1}" in (tmp_path / "g2" / "threat-report.md").read_text(encoding="utf-8")


def test_zone_mismatch_forces_boundary(tmp_path):
    res, rows = _run(tmp_path, SMALL_C, "u,app,question,no\n")
    dfd = (tmp_path / "out" / "dfd.md").read_text(encoding="utf-8")
    assert "treated as crossing: u>app" in dfd
    assert rows["u>app:T"]["likelihood"] == "3"


def test_malformed_inputs_exit_2(tmp_path):
    res, _ = _run(tmp_path, "x,X,robot,z,no,no,no\n", "")
    assert res.returncode == 2 and "kind" in res.stderr
    res, _ = _run(tmp_path, SMALL_C, "u,ghost,data,yes\n")
    assert res.returncode == 2 and "unknown component" in res.stderr
    res, _ = _run(tmp_path, "a,A,app,z,maybe,no,no\n", "")
    assert res.returncode == 2 and "yes or no" in res.stderr
    res, _ = _run(tmp_path, SMALL_C, SMALL_F, None, "--max-open-high", "-1")
    assert res.returncode == 2


def test_fixture_counts_and_tbd(tmp_path):
    res = run_script(SCRIPT, "--components", str(FIX / "components.csv"), "--flows", str(FIX / "flows.csv"),
                     "--out-dir", str(tmp_path / "o"))
    assert res.returncode == 0, res.stderr
    rep = (tmp_path / "o" / "threat-report.md").read_text(encoding="utf-8")
    assert "Threats: 101 (34 high, 36 medium, 31 low)" in rep
    rows = list(csv.DictReader((tmp_path / "o" / "threats.csv").open(encoding="utf-8")))
    assert all(r["owner"] == TBD for r in rows)
    assert "```mermaid" in (tmp_path / "o" / "dfd.md").read_text(encoding="utf-8")


def test_deterministic_and_verify(tmp_path):
    outs = []
    for d in ("a", "b"):
        run_script(SCRIPT, "--components", str(FIX / "components.csv"), "--flows", str(FIX / "flows.csv"),
                   "--controls", str(FIX / "controls.csv"), "--out-dir", str(tmp_path / d))
        outs.append([(tmp_path / d / f).read_bytes() for f in ("threats.csv", "dfd.md", "threat-report.md")])
    assert outs[0] == outs[1]
    assert run_script(SCRIPT, "--verify", str(tmp_path / "a" / "threats.csv")).returncode == 0
    bad = tmp_path / "bad.csv"
    text = (tmp_path / "a" / "threats.csv").read_text(encoding="utf-8").replace(",high,", ",low,", 1)
    bad.write_text(text, encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(bad)).returncode == 1
