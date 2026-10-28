"""Harness layer 8: disputable gates (docs/HARNESS.md). A gate finding can be waived only with a rule, a file, a
reason and an owner; a critical never; an expired or incomplete waiver is refused and listed."""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deliver_wv", REPO / "scripts" / "deliver.py")
d = importlib.util.module_from_spec(spec)
sys.modules["deliver_wv"] = d
spec.loader.exec_module(d)

HEADER = ["id", "category", "rule", "severity", "file", "line", "evidence", "recommendation", "status"]
SEC1 = ["F01", "authz", "SEC1", "high", "app/notes/actions.ts", "9", "export async function addNote", "", "new"]
SEC4 = ["F02", "ssrf", "SEC4", "high", "app/planner/client.tsx", "135", "fetch(draftUrl)", "", "new"]
SEC3 = ["F03", "secrets", "SEC3", "critical", "lib/x.ts", "1", "sk_live…[redacted]", "", "new"]


def setup(tmp: Path, rows: list[list[str]], waivers: list[dict]):
    fcsv = tmp / "findings.csv"
    with open(fcsv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)
    wf = tmp / "waivers.json"
    wf.write_text(json.dumps({"waivers": waivers}), encoding="utf-8")
    run = d.Run({"name": "t", "stages": []}, types.SimpleNamespace(provider="none", waivers=str(wf)), tmp)
    return run, fcsv


W1 = {"rule": "SEC1", "file": "app/notes/actions.ts", "reason": "auth via getSessionUser() -> auth.getUser() one import away", "by": "Giri"}
W4 = {"rule": "SEC4", "file": "app/planner/client.tsx", "line": 135, "reason": "browser fetch of a same-origin path", "by": "Giri", "expires": "2099-01-01"}


def test_every_blocking_finding_waived_passes_as_waived_and_records_why(tmp_path):
    run, fcsv = setup(tmp_path, [SEC1, SEC4], [W1, W4])
    rec = {"exit": 1}
    assert run.apply_waivers({"id": "security"}, fcsv, tmp_path, rec) is True
    assert rec["exit"] == 0 and rec["skill_exit"] == 1 and len(rec["waived"]) == 2 and "(by Giri)" in rec["waived"][0]
    rows = list(csv.DictReader(open(tmp_path / "waived.csv", encoding="utf-8")))
    assert [r["rule"] for r in rows] == ["SEC1", "SEC4"] and rows[1]["reason"] == "browser fetch of a same-origin path"


def test_one_unwaived_finding_keeps_the_gate_closed(tmp_path):
    run, fcsv = setup(tmp_path, [SEC1, SEC4], [W1])
    rec = {"exit": 1}
    assert run.apply_waivers({"id": "security"}, fcsv, tmp_path, rec) is False and rec["waived_partial"] == 1 and rec["exit"] == 1


def test_a_critical_is_never_waivable(tmp_path):
    run, fcsv = setup(tmp_path, [SEC3], [{"rule": "SEC3", "file": "lib/x.ts", "reason": "test key", "by": "Giri"}])
    assert run.apply_waivers({"id": "security"}, fcsv, tmp_path, {"exit": 1}) is False


def test_a_waiver_without_reason_or_owner_or_past_expiry_is_refused(tmp_path):
    bad = [{"rule": "SEC1", "file": "app/notes/actions.ts", "reason": "", "by": "Giri"},
           {"rule": "SEC4", "file": "app/planner/client.tsx", "reason": "x", "by": "Giri", "expires": "2001-01-01"}]
    run, fcsv = setup(tmp_path, [SEC1, SEC4], bad)
    rec = {"exit": 1}
    assert run.apply_waivers({"id": "security"}, fcsv, tmp_path, rec) is False
    assert len(rec["waivers_refused"]) == 2 and "missing reason" in rec["waivers_refused"][0] and "expired" in rec["waivers_refused"][1]


def test_a_line_specific_waiver_does_not_cover_another_line(tmp_path):
    moved = SEC4[:5] + ["200"] + SEC4[6:]
    run, fcsv = setup(tmp_path, [moved], [W4])
    assert run.apply_waivers({"id": "security"}, fcsv, tmp_path, {"exit": 1}) is False
