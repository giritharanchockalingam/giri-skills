"""Tests for career/outreach-and-followup/scripts/fill.py."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/career/outreach-and-followup/scripts/fill.py"
SK = REPO_ROOT / "skills/career/outreach-and-followup"
FX = SK / "evals/fixtures"


def run(tmp_path: Path, msg_type: str, context: Path):
    msg, cad = tmp_path / "message.md", tmp_path / "cadence.csv"
    r = run_script(SCRIPT, "--type", msg_type, "--context", str(context), "--message", str(msg), "--cadence", str(cad), cwd=SK)
    rows = list(csv.DictReader(cad.open(encoding="utf-8"))) if cad.exists() else None
    return r, msg, rows


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_thank_you_filled_only_from_context(tmp_path):
    r, msg, rows = run(tmp_path, "thank-you", FX / "context-thank-you.json")
    assert r.returncode == 0, r.stderr
    text = msg.read_text(encoding="utf-8")
    assert "Dana, thank you for the time today. Your point about open enrollment is the one window" in text
    assert "[SB-05], and I'd approach it here by sequencing" in text and "[SB-nn]" not in text
    assert "Morgan Adeyemi-Park" in text and "<" not in text.split("## Facts")[0].replace("<!--", "")
    assert "## Unfilled placeholders\n\nnone" in text
    assert rows == [{"touch": "Touch 1", "date": "2026-03-11", "channel": "email", "template": "3A Reinforce",
                     "basis": "Post-interview thank-you: Within 24 h", "stop_rule": "One per interviewer"}]


def test_thin_context_leaves_owned_markers_not_facts(tmp_path):
    r, msg, rows = run(tmp_path, "referral-ask", FX / "context-referral-thin.json")
    assert r.returncode == 0, r.stderr
    text = msg.read_text(encoding="utf-8")
    assert "Priya, I'm applying for VP, Enterprise Applications ([TO BE BASELINED — owner: Sender]) at Helix Logistics" in text
    assert "- A: req ID" in text and "- B: Name" in text
    assert "$" not in text.split("## Facts")[0].replace("$XXM", "")     # no invented outcome figure
    # business-day cadence from a Thursday: Day 0, Day 5, Day 12; third touch switches channel
    assert [(x["touch"], x["date"], x["channel"]) for x in rows] == [
        ("Touch 1", "2026-03-12", "LinkedIn"), ("Touch 2", "2026-03-19", "LinkedIn"), ("Touch 3", "2026-03-30", "email")]
    assert rows[0]["stop_rule"] == "Stop after 3; thank and move on"


def test_status_check_uses_timeline_when_given(tmp_path):
    ctx = {"recipient": "Sam Ortiz", "company": "Helix Logistics (fictional)", "role": "VP, Enterprise Applications",
           "last_touch_date": "2026-03-02", "timeline_date": "2026-03-13", "specifics": ["timeline: the week of March 9"]}
    p = tmp_path / "ctx.json"
    p.write_text(json.dumps(ctx), encoding="utf-8")
    r, msg, rows = run(tmp_path, "status-check", p)
    assert r.returncode == 0, r.stderr
    assert [(x["touch"], x["date"]) for x in rows] == [("Touch 1", "2026-03-17"), ("Touch 2", "2026-03-26")]
    text = msg.read_text(encoding="utf-8")
    assert "when we spoke on 2026-03-02 you mentioned a decision around the week of March 9" in text
    assert "by 2026-03-11?" in text                                  # Deadline − 2 computed from the timeline


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, "decline", tmp_path / "missing.json")[0].returncode == 1
    p = tmp_path / "ctx.json"
    p.write_text(json.dumps({"recipient": "Sam", "company": "X", "role": "Y"}), encoding="utf-8")
    r = run(tmp_path, "decline", p)[0]
    assert r.returncode == 1 and "last_touch_date" in r.stderr
    p.write_text(json.dumps({"recipient": "Sam", "company": "X", "role": "Y", "last_touch_date": "March 3"}), encoding="utf-8")
    assert run(tmp_path, "decline", p)[0].returncode == 1
    assert run(tmp_path, "cover-letter", FX / "context-thank-you.json")[0].returncode == 2   # argparse choices
