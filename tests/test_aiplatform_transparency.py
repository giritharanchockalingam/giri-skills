"""Tests for ai-platform/ai-transparency-notice/scripts/transparency_notice.py (hand-computed grades)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-transparency-notice/scripts/transparency_notice.py"
FIX = REPO_ROOT / "skills/ai-platform/ai-transparency-notice/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Product owner]"
OUTS = ("notice.md", "system-card.md", "disclosure-checklist.csv", "transparency.json")


def _facts(tmp_path, rows: dict[str, str]) -> Path:
    p = tmp_path / "facts.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "value", "source", "notes"])
        for k, v in rows.items():
            w.writerow([k, v, "test source", ""])
    return p


def _run(tmp_path, facts: Path, *extra):
    out = tmp_path / "out"
    res = run_script(SCRIPT, "--facts", str(facts), "--out-dir", str(out), *extra)
    tj = json.loads((out / "transparency.json").read_text(encoding="utf-8")) if (out / "transparency.json").exists() else {}
    rows = {r["article"] + "|" + r["duty"]: r for r in csv.DictReader((out / "disclosure-checklist.csv").open(encoding="utf-8"))} \
        if (out / "disclosure-checklist.csv").exists() else {}
    return res, out, tj, rows


def _row(rows, article, start):
    return next(r for k, r in rows.items() if k.startswith(article + "|" + start))


def test_flesch_kincaid_hand_computed_via_verify(tmp_path):
    # "Please read the notice before you begin." -> 7 words, 1 sentence,
    # syllables please1 read1 the1 notice2 before2 you1 begin2 = 10
    # grade = 0.39*7 + 11.8*10/7 - 15.59 = 2.73 + 16.857 - 15.59 = 3.997 -> 4.0
    d = tmp_path / "v"
    d.mkdir()
    (d / "notice.md").write_text("# About this AI assistant\n\nPlease read the notice before you begin.\n", encoding="utf-8")
    good = {"grade": 4.0, "word_count": 7, "sentence_count": 1, "syllable_count": 10, "max_grade": 8.0, "grade_ok": True}
    (d / "transparency.json").write_text(json.dumps(good), encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(d / "notice.md")).returncode == 0
    (d / "transparency.json").write_text(json.dumps({**good, "grade": 3.0}), encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(d / "notice.md")).returncode == 1
    (d / "transparency.json").write_text(json.dumps({**good, "max_grade": 3.5}), encoding="utf-8")
    assert run_script(SCRIPT, "--verify", str(d / "notice.md")).returncode == 1  # grade_ok inconsistent


def test_fixture_happy_path_and_determinism(tmp_path):
    blobs = []
    for name in ("a", "b"):
        out = tmp_path / name
        res = run_script(SCRIPT, "--facts", str(FIX / "facts.csv"), "--classification", str(FIX / "classification.json"),
                         "--out-dir", str(out))
        assert res.returncode == 0, res.stderr
        blobs.append({f: (out / f).read_bytes() for f in OUTS})
    assert blobs[0] == blobs[1]
    tj = json.loads(blobs[0]["transparency.json"])
    # 94 words, 12 sentences, 131 syllables: 0.39*94/12 + 11.8*131/94 - 15.59 = 3.055 + 16.445 - 15.59 = 3.91
    assert (tj["grade"], tj["word_count"], tj["sentence_count"], tj["syllable_count"]) == (3.9, 94, 12, 131)
    assert tj["missing_facts"] == [] and tj["checklist"]["missing"] == 0
    assert run_script(SCRIPT, "--verify", str(tmp_path / "a" / "notice.md")).returncode == 0


def test_grade_gate_boundary(tmp_path):
    res, out, tj, _ = _run(tmp_path, FIX / "facts.csv", "--max-grade", "3.9")
    assert res.returncode == 0 and tj["grade_ok"] is True
    res2, out2, tj2, rows2 = _run(tmp_path, FIX / "facts.csv", "--max-grade", "3.8")
    assert res2.returncode == 1 and tj2["grade_ok"] is False
    assert all((out2 / f).exists() for f in OUTS)
    assert _row(rows2, "Art. 50(5)", "Give")["provided"] == "no"


def test_missing_facts_tbd_and_strict(tmp_path):
    f = _facts(tmp_path, {"system_name": "Test Bot", "provider": "Acme (fictional)"})
    res, out, tj, _ = _run(tmp_path, f)
    assert res.returncode == 0
    notice = (out / "notice.md").read_text(encoding="utf-8")
    assert f"It is here to {TBD}." in notice and "You are chatting with Test Bot." in notice
    card = (out / "system-card.md").read_text(encoding="utf-8")
    assert f"| Model | {TBD} | — |" in card and "[TO BE BASELINED — owner: Compliance lead]" in card
    assert "purpose" in tj["notice_missing_facts"] and "model" in tj["missing_facts"]
    res2, _, _, _ = _run(tmp_path, f, "--strict")
    assert res2.returncode == 1 and "purpose" in res2.stderr


def test_conditional_sentences_and_checklist(tmp_path):
    base = {k: "x" for k in ("system_name", "provider", "purpose", "data_sources", "not_intended_for",
                             "known_limitations", "human_oversight", "contact", "last_updated")}
    f = _facts(tmp_path, {**base, "interacts_directly": "yes", "emotion_recognition": "yes",
                          "biometric_categorisation": "no", "generates_synthetic_content": "yes", "deep_fake": "yes",
                          "public_interest_text": "no", "notice_placement": "before first message"})
    res, out, tj, rows = _run(tmp_path, f)
    notice = (out / "notice.md").read_text(encoding="utf-8")
    assert "It tries to recognise emotions from what you share." in notice
    assert "may look real, but they are made by AI." in notice
    assert "biometric" not in notice
    assert _row(rows, "Art. 50(3)", "Inform people exposed to an emotion")["status"] == "provided"
    assert _row(rows, "Art. 50(3)", "Inform people exposed to a biometric")["status"] == "not applicable"
    assert _row(rows, "Art. 50(2)", "Mark")["status"] == "missing"          # no content_marking
    assert _row(rows, "Art. 50(4)", "Disclose that deep")["status"] == "missing"  # no deep_fake_label
    assert _row(rows, "Art. 50(4)", "Disclose AI-generated")["provided"] == "n/a"
    assert _row(rows, "Art. 50(5)", "Give")["status"] == "partial"
    assert "public_interest_text_label" not in tj["missing_facts"] and "deep_fake_label" in tj["missing_facts"]


def test_applies_tbd_and_all_no(tmp_path):
    f = _facts(tmp_path, {"system_name": "Bot"})
    res, out, tj, rows = _run(tmp_path, f)
    assert _row(rows, "Art. 50(1)", "Inform")["applies"] == TBD and tj["checklist"]["to confirm"] == 7
    no = {k: "no" for k in ("interacts_directly", "generates_synthetic_content", "emotion_recognition",
                            "biometric_categorisation", "deep_fake", "public_interest_text")}
    res2, out2, tj2, rows2 = _run(tmp_path, _facts(tmp_path, {"system_name": "Bot", **no}))
    assert tj2["checklist"]["not applicable"] == 7


def test_classification_alternative_keys_and_absent_fields(tmp_path):
    c = tmp_path / "c.json"
    c.write_text(json.dumps({"risk_tier": "minimal", "reasons": ["r1", "r2"]}), encoding="utf-8")
    res, out, tj, _ = _run(tmp_path, FIX / "facts.csv", "--classification", str(c))
    assert res.returncode == 0 and "tier minimal; basis: r1; r2." in (out / "system-card.md").read_text(encoding="utf-8")
    c.write_text(json.dumps({"something_else": 1}), encoding="utf-8")
    res2, out2, _, _ = _run(tmp_path, FIX / "facts.csv", "--classification", str(c))
    assert res2.returncode == 0 and "tier not stated in file" in (out2 / "system-card.md").read_text(encoding="utf-8")


def test_invalid_inputs_exit_2(tmp_path):
    assert _run(tmp_path, _facts(tmp_path, {"system_name": "Bot", "emotion_recognition": "maybe"}))[0].returncode == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("name,val\na,b\n", encoding="utf-8")
    assert _run(tmp_path, bad)[0].returncode == 2
    empty = tmp_path / "empty.csv"
    empty.write_text("key,value\n", encoding="utf-8")
    assert _run(tmp_path, empty)[0].returncode == 2
    c = tmp_path / "c.json"
    c.write_text("{not json", encoding="utf-8")
    assert _run(tmp_path, FIX / "facts.csv", "--classification", str(c))[0].returncode == 2
    assert _run(tmp_path, FIX / "facts.csv", "--classification", str(tmp_path / "nope.json"))[0].returncode == 2
    assert _run(tmp_path, FIX / "facts.csv", "--max-grade", "abc")[0].returncode == 2
    assert run_script(SCRIPT, "--facts", str(tmp_path / "nope.csv"), "--out-dir", str(tmp_path / "o")).returncode == 2
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2


def test_never_claims_compliance_and_tbds_owned(tmp_path):
    res, out, _, _ = _run(tmp_path, FIX / "facts-partial.csv")
    text = "".join((out / f).read_text(encoding="utf-8") for f in OUTS).lower()
    assert "is compliant" not in text and "compliant with" not in text
    assert "does not claim compliance" in text
    raw = "".join((out / f).read_text(encoding="utf-8") for f in OUTS)
    assert raw.count("[TO BE BASELINED") == raw.count("[TO BE BASELINED — owner: ")


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src
