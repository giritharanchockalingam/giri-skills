"""Tests for ai-platform/conversation-design/scripts/conversation_design.py (hand-computed TF-IDF)."""
from __future__ import annotations

import csv
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/conversation-design/scripts/conversation_design.py"
FIX = REPO_ROOT / "skills/ai-platform/conversation-design/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Conversation designer]"
HDR = "intent,description,examples,response_type,handoff,owner\n"


def _run(tmp_path, intents: str, utterances: str, *extra, persona: str | None = None):
    (tmp_path / "i.csv").write_text(intents, encoding="utf-8")
    (tmp_path / "u.csv").write_text(utterances, encoding="utf-8")
    args = ["--intents", str(tmp_path / "i.csv"), "--utterances", str(tmp_path / "u.csv"),
            "--out-dir", str(tmp_path / "out"), *extra]
    if persona is not None:
        (tmp_path / "p.csv").write_text(persona, encoding="utf-8")
        args += ["--persona", str(tmp_path / "p.csv")]
    res = run_script(SCRIPT, *args)
    out = tmp_path / "out"
    routing = list(csv.DictReader((out / "routing.csv").open(encoding="utf-8"))) if (out / "routing.csv").exists() else []
    return res, routing, out


TWO = HDR + "pay,pay bill,pay,action,no,Payments lead\nview,view bill,view,answer,no,Billing lead\n"


def test_tfidf_cosine_hand_computed(tmp_path):
    # docs: pay=[pay,bill,pay], view=[view,bill,view]; idf(pay)=ln(3/2)+1=1.405465, idf(bill)=ln(3/3)+1=1
    # pay vec (2.810930, 1) ; utterance "pay bill" (1.405465, 1)
    # cos = (2.810930*1.405465 + 1) / (2.983505 * 1.724915) = 4.950667 / 5.146303 = 0.962
    res, rows, _ = _run(tmp_path, TWO, "utterance,expected_intent\npay bill,pay\n")
    assert res.returncode == 0, res.stderr
    assert rows[0]["predicted_intent"] == "pay" and rows[0]["score"] == "0.962" and rows[0]["correct"] == "yes"


def test_threshold_routes_to_fallback_and_tie_breaks_by_name(tmp_path):
    # "bill" alone: idf 1 on both sides; cos = 1/2.983505 = 0.335 for both -> tie -> 'pay' (name order)
    # "cherry": no known term -> score 0 -> fallback, nearest by name order
    res, rows, _ = _run(tmp_path, TWO, "utterance,expected_intent\nbill,\ncherry,fallback\n")
    assert rows[0]["predicted_intent"] == "pay" and rows[0]["score"] == "0.335"
    assert rows[1]["predicted_intent"] == "fallback" and rows[1]["score"] == "0.000" and rows[1]["correct"] == "yes"


def test_precision_recall_and_accuracy(tmp_path):
    utt = "utterance,expected_intent\npay,pay\nview,view\nview bill,pay\nunrelated words,\n"
    res, rows, out = _run(tmp_path, TWO, utt)
    q = {r["intent"]: r for r in csv.DictReader((out / "intent-quality.csv").open(encoding="utf-8"))}
    # labelled 3: pay->pay ok, view->view ok, 'view bill' expected pay -> predicted view (wrong)
    assert q["pay"]["precision"] == "1.000" and q["pay"]["recall"] == "0.500"
    assert q["view"]["precision"] == "0.500" and q["view"]["recall"] == "1.000"
    spec = (out / "conversation-spec.md").read_text(encoding="utf-8")
    assert "Accuracy: 2/3 (66.7%)" in spec and "Coverage: 3/4 (75.0%)" in spec
    assert "| pay | view | 1 |" in spec


def test_confusable_pairs(tmp_path):
    intents = HDR + ("a,alpha,pay my bill|pay bill now,action,no,X\n"
                     "b,beta,pay my bill late|pay bill later,action,no,Y\n"
                     "c,gamma,usage graph,answer,no,Z\n")
    res, _, out = _run(tmp_path, intents, "utterance\npay bill\n")
    q = {r["intent"]: r for r in csv.DictReader((out / "intent-quality.csv").open(encoding="utf-8"))}
    assert q["a"]["confusable_with"] == "b" and q["b"]["confusable_with"] == "a"
    assert q["c"]["confusable_with"] == "none"


def test_gate_exit_1_and_no_labels_fails_gate(tmp_path):
    utt = "utterance,expected_intent\npay,pay\nview bill,pay\n"
    res, _, out = _run(tmp_path, TWO, utt, "--min-accuracy", "0.6")
    assert res.returncode == 1 and (out / "conversation-spec.md").exists()
    res2, _, _ = _run(tmp_path, TWO, utt, "--min-accuracy", "0.5")
    assert res2.returncode == 0
    res3, _, out3 = _run(tmp_path, TWO, "utterance\npay\n", "--min-accuracy", "0.5")
    assert res3.returncode == 1
    assert "no labels to measure it" in (out3 / "conversation-spec.md").read_text(encoding="utf-8")


def test_persona_missing_is_tbd_with_owner(tmp_path):
    res, _, out = _run(tmp_path, TWO, "utterance\npay\n", persona="key,value,source,notes\ntone,Friendly,guide,\n")
    spec = (out / "conversation-spec.md").read_text(encoding="utf-8")
    assert f"| escalation_channel | {TBD} | — |" in spec
    assert "| tone | Friendly | guide |" in spec
    assert "No intent hands off to a person" in spec
    assert "[TO BE BASELINED]" not in spec


def test_utterances_truncated_to_80_and_leak_check(tmp_path):
    long = "x" * 50 + " pay my bill " + "y" * 60
    res, rows, out = _run(tmp_path, TWO, f"utterance\n{long}\n")
    assert rows[0]["utterance"] == long[:80] + "…"
    for f in ("routing.csv", "conversation-spec.md"):
        chk = run_script(SCRIPT, "--leak-check", str(out / f), "--utterances", str(tmp_path / "u.csv"))
        assert chk.returncode == 0, chk.stdout
    bad = tmp_path / "bad.md"
    bad.write_text(long, encoding="utf-8")
    assert run_script(SCRIPT, "--leak-check", str(bad), "--utterances", str(tmp_path / "u.csv")).returncode == 1


def test_invalid_inputs_exit_2(tmp_path):
    cases = [
        (HDR + "a,d,x,reply,no,O\n", "utterance\nx\n", "response_type"),
        (HDR + "a,d,x,answer,maybe,O\n", "utterance\nx\n", "handoff"),
        (HDR + "fallback,d,x,answer,no,O\n", "utterance\nx\n", "reserved"),
        (HDR + "a,d,x,answer,no,O\na,d,y,answer,no,O\n", "utterance\nx\n", "duplicate"),
        ("intent,description\na,d\n", "utterance\nx\n", "missing column"),
        (TWO, "utterance,expected_intent\nx,nope\n", "nope"),
        (TWO, "utterance\n", "no non-empty"),
        (TWO, "text\nhello\n", "'utterance' column"),
    ]
    for intents, utt, msg in cases:
        res, _, _ = _run(tmp_path, intents, utt)
        assert res.returncode == 2 and msg in res.stderr, (msg, res.stderr)
    res, _, _ = _run(tmp_path, TWO, "utterance\npay\n", "--min-accuracy", "1.5")
    assert res.returncode == 2
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2


def test_fixture_determinism_and_verify(tmp_path):
    outs = []
    for name in ("a", "b"):
        out = tmp_path / name
        res = run_script(SCRIPT, "--intents", str(FIX / "intents.csv"), "--utterances", str(FIX / "utterances.csv"),
                         "--persona", str(FIX / "persona.csv"), "--min-accuracy", "0.8", "--out-dir", str(out))
        assert res.returncode == 0, res.stderr
        outs.append({f: (out / f).read_bytes() for f in ("routing.csv", "intent-quality.csv", "conversation-spec.md")})
    assert outs[0] == outs[1]
    ok = run_script(SCRIPT, "--verify", str(tmp_path / "a" / "routing.csv"),
                    "--intents", str(FIX / "intents.csv"), "--utterances", str(FIX / "utterances.csv"))
    assert ok.returncode == 0, ok.stdout
    tampered = tmp_path / "a" / "routing.csv"
    tampered.write_text(tampered.read_text(encoding="utf-8").replace("0.610", "0.910"), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(tampered),
                     "--intents", str(FIX / "intents.csv"), "--utterances", str(FIX / "utterances.csv"))
    assert bad.returncode == 1


def test_mermaid_has_fallback_and_handoff(tmp_path):
    out = tmp_path / "o"
    run_script(SCRIPT, "--intents", str(FIX / "intents.csv"), "--utterances", str(FIX / "utterances.csv"),
               "--persona", str(FIX / "persona.csv"), "--out-dir", str(out))
    spec = (out / "conversation-spec.md").read_text(encoding="utf-8")
    block = spec.split("```mermaid", 1)[1].split("```", 1)[0]
    assert "flowchart TD" in block and "FB -->|still unmatched| H" in block and "HANDOFF --> H" in block
    assert block.count("[") == block.count("]") and block.count("(") == block.count(")")
    chk = REPO_ROOT / "scripts" / "check_output.py"
    assert run_script(chk, str(out / "conversation-spec.md"), "mermaid_parses").returncode == 0


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src
