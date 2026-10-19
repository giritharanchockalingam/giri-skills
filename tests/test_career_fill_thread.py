"""career/outreach-and-followup: --thread (existing conversation) and --draft-only final."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/career/outreach-and-followup"
SCRIPT = SK / "scripts/fill.py"
FX = SK / "evals/fixtures"


def fill(tmp_path, msg_type, context, *extra):
    m, c, f = tmp_path / "m.md", tmp_path / "c.csv", tmp_path / "f.md"
    r = run_script(SCRIPT, "--type", msg_type, "--context", str(context), "--templates", str(SK / "assets/message-templates.md"),
                   "--cadence-ref", str(SK / "references/cadence.md"), "--message", str(m), "--cadence", str(c),
                   "--final", str(f), *extra)
    rows = list(csv.DictReader(c.open(encoding="utf-8"))) if c.exists() else []
    return r, (m.read_text(encoding="utf-8") if m.exists() else ""), rows, (f.read_text(encoding="utf-8") if f.exists() else None)


def thread(tmp_path, text):
    p = tmp_path / "thread.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_follow_up_counts_sent_and_marks_used_facts(tmp_path):
    r, msg, rows, final = fill(tmp_path, "referral-ask", FX / "context-referral-followup.json",
                               "--thread", str(FX / "thread-referral.md"), "--draft-only")
    assert r.returncode == 0, r.stderr
    assert [x["touch"] for x in rows] == ["Touch 2", "Touch 3"]
    assert rows[0]["date"] == "2026-10-08" and rows[1]["date"] == "2026-10-19"
    assert "shared history: we ran the claims cutover together at Lakeshore Health Plans — already used" in msg
    assert "shared history" not in final.split("## Facts used")[1]


def test_exhausted_cadence_reports_stop(tmp_path):
    t = thread(tmp_path, "## 2026-10-01 — sent\nhi\n## 2026-10-08 — sent\nnudge\n## 2026-10-19 — sent (email)\nlast\n")
    r, msg, rows, final = fill(tmp_path, "referral-ask", FX / "context-referral-followup.json", "--thread", str(t), "--draft-only")
    assert r.returncode == 0, r.stderr
    assert "Cadence exhausted after 3 touch(es) — stop rule: Stop after 3; thank and move on" in msg
    assert rows[0]["touch"] == "Stop" and "Do not send another" in final


def test_reply_is_flagged(tmp_path):
    t = thread(tmp_path, "## 2026-10-01 — sent\nhi\n## 2026-10-03 — received\nHappy to chat next week.\n")
    r, msg, _, _ = fill(tmp_path, "referral-ask", FX / "context-referral-followup.json", "--thread", str(t))
    assert r.returncode == 0 and "1 reply(ies), last 2026-10-03 — answer it before following up." in msg


def test_thread_without_sent_message_fails(tmp_path):
    t = thread(tmp_path, "## 2026-10-03 — received\nhello\n")
    r, *_ = fill(tmp_path, "referral-ask", FX / "context-referral-followup.json", "--thread", str(t))
    assert r.returncode == 1 and "no '## YYYY-MM-DD — sent' message" in r.stderr


def test_draft_only_new_message(tmp_path):
    r, msg, rows, final = fill(tmp_path, "thank-you", FX / "context-thank-you.json", "--draft-only")
    assert r.returncode == 0, r.stderr
    for h in ("## Message", "## Alternate variant", "## Facts used", "## Cadence"):
        assert h in final
    assert "## Thread so far" not in msg and rows[0]["touch"] == "Touch 1"


def test_final_not_written_without_draft_only(tmp_path):
    r, _, _, final = fill(tmp_path, "thank-you", FX / "context-thank-you.json")
    assert r.returncode == 0 and final is None
