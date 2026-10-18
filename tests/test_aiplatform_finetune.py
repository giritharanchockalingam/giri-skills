"""Tests for ai-platform/finetune-dataset-builder/scripts/build_dataset.py (hand-checked counts)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/finetune-dataset-builder/scripts/build_dataset.py"
FIX = REPO_ROOT / "skills/ai-platform/finetune-dataset-builder/evals/fixtures"


def _csv(p: Path, rows: list[tuple[str, str]]) -> Path:
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["prompt", "completion", "notes"])
        for a, b in rows:
            w.writerow([a, b, "fictional"])
    return p


def _uniq(n: int) -> list[tuple[str, str]]:
    return [(f"Fictional question number {i}?", f"Fictional answer number {i}.") for i in range(n)]


def _build(tmp_path, src: Path, *extra):
    out = tmp_path / "out"
    res = run_script(SCRIPT, "--examples", str(src), "--out-dir", str(out), *extra)
    stats = json.loads((out / "dataset-stats.json").read_text()) if (out / "dataset-stats.json").exists() else None
    return res, stats, out


def _lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def test_default_split_sizes_and_defaults_stated(tmp_path):
    res, st, out = _build(tmp_path, _csv(tmp_path / "e.csv", _uniq(20)))
    assert res.returncode == 0, res.stderr
    assert st["splits"] == {"train": 16, "val": 2, "test": 2}  # 20 - round(2) - round(2)
    assert st["parameters"]["seed"] == {"value": 42, "default": True}
    card = (out / "data-card.md").read_text()
    assert "split 0.8,0.1,0.1 (default); seed 42 (default); min_rows 10 (default)" in card
    for s in ("## Source", "## Cleaning", "## Splits", "## Length stats", "## Known limits"):
        assert s in card


def test_dedupe_exact_and_normalised(tmp_path):
    rows = _uniq(10) + [_uniq(10)[0], ("  FICTIONAL question   number 1? ", "fictional answer number 1.")]
    res, st, _ = _build(tmp_path, _csv(tmp_path / "e.csv", rows))
    c = st["cleaning"]
    assert c["exact_duplicates_removed"] == 1 and c["normalised_duplicates_removed"] == 1 and c["usable"] == 10


def test_same_prompt_two_completions_no_leakage(tmp_path):
    rows = _uniq(12) + [(f"Fictional question number {i}?", f"Alternative answer {i}.") for i in range(6)]
    res, st, out = _build(tmp_path, _csv(tmp_path / "e.csv", rows), "--split", "0.5,0.25,0.25")
    assert res.returncode == 0
    assert st["cleaning"]["prompts_with_multiple_completions"] == 6
    assert st["leakage_prompts_across_splits"] == 0
    seen = {}
    for s in ("train", "val", "test"):
        for r in _lines(out / f"{s}.jsonl"):
            p = r["messages"][0]["content"]
            assert seen.setdefault(p, s) == s


def test_deterministic_with_seed(tmp_path):
    src = _csv(tmp_path / "e.csv", _uniq(30))
    a = run_script(SCRIPT, "--examples", str(src), "--out-dir", str(tmp_path / "a"), "--seed", "7")
    b = run_script(SCRIPT, "--examples", str(src), "--out-dir", str(tmp_path / "b"), "--seed", "7")
    c = run_script(SCRIPT, "--examples", str(src), "--out-dir", str(tmp_path / "c"), "--seed", "8")
    assert a.returncode == b.returncode == c.returncode == 0
    assert (tmp_path / "a/train.jsonl").read_bytes() == (tmp_path / "b/train.jsonl").read_bytes()
    assert (tmp_path / "a/test.jsonl").read_bytes() != (tmp_path / "c/test.jsonl").read_bytes()


def test_whitespace_normalised_and_chat_format(tmp_path):
    rows = _uniq(10) + [("Line one   with\tspaces  \r\n\r\n\r\n\r\nline two", "ok  answer")]
    res, st, out = _build(tmp_path, _csv(tmp_path / "e.csv", rows), "--split", "1,0,0")
    recs = _lines(out / "train.jsonl")
    target = [r for r in recs if r["messages"][0]["content"].startswith("Line one")][0]
    assert target["messages"] == [{"role": "user", "content": "Line one with spaces\n\nline two"},
                                  {"role": "assistant", "content": "ok answer"}]
    assert st["cleaning"]["whitespace_normalised"] == 1
    assert (out / "val.jsonl").read_text() == ""


def test_token_estimate(tmp_path):
    rows = [("abcd", "abcdefgh")] * 1 + [(f"q{i:02d}", f"a{i:02d}") for i in range(9)]
    res, st, _ = _build(tmp_path, _csv(tmp_path / "e.csv", rows), "--split", "1,0,0")
    t = st["length_tokens_estimate"]["train"]
    # "abcd"+"abcdefgh" = 12 chars -> 3; each "qNN"+"aNN" = 6 chars -> 2
    assert t["max"] == 3 and t["min"] == 2 and t["total"] == 3 + 9 * 2 and t["examples"] == 10


def test_validation_rejects_and_max_chars(tmp_path):
    rows = _uniq(10) + [("empty completion", ""), ("x" * 50, "y" * 60)]
    res, st, _ = _build(tmp_path, _csv(tmp_path / "e.csv", rows), "--max-chars", "100")
    assert st["cleaning"]["rejected"] == {"empty prompt or completion": 1, "over max_chars": 1}
    assert st["parameters"]["max_chars"] == {"value": 100, "default": False}


def test_jsonl_messages_and_system_kept(tmp_path):
    src = tmp_path / "e.jsonl"
    recs = [{"messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": f"Q{i}"},
                          {"role": "assistant", "content": f"A{i}"}]} for i in range(10)]
    recs.append({"messages": [{"role": "user", "content": "no answer"}]})
    recs.append({"prompt": "P", "completion": "C"})
    src.write_text("\n".join(json.dumps(r) for r in recs) + "\nnot json\n")
    res, st, out = _build(tmp_path, src, "--split", "1,0,0")
    assert res.returncode == 0
    assert st["cleaning"]["usable"] == 11
    assert st["cleaning"]["rejected"] == {"invalid JSON": 1, "last turn is not assistant": 1}
    assert _lines(out / "train.jsonl")[0]["messages"][0]["role"] in ("system", "user")


def test_too_few_rows_exit_1(tmp_path):
    res, st, out = _build(tmp_path, _csv(tmp_path / "e.csv", _uniq(9)))
    assert res.returncode == 1 and st["verdict"] == "too few usable rows"
    assert "Not built: 9 usable examples is below min_rows 10." in (out / "data-card.md").read_text()
    res2, st2, _ = _build(tmp_path, _csv(tmp_path / "e.csv", _uniq(9)), "--min-rows", "5")
    assert res2.returncode == 0


def test_fixture_counts(tmp_path):
    res, st, _ = _build(tmp_path, FIX / "helpdesk-examples.csv")
    assert res.returncode == 0
    c = st["cleaning"]
    assert (c["rejected_total"], c["exact_duplicates_removed"], c["normalised_duplicates_removed"], c["usable"]) == (1, 1, 1, 15)
    assert st["splits"] == {"train": 11, "val": 2, "test": 2}


def test_bad_inputs_exit_2(tmp_path):
    src = _csv(tmp_path / "e.csv", _uniq(12))
    assert _build(tmp_path, src, "--split", "0.8,0.3,0.1")[0].returncode == 2
    assert _build(tmp_path, src, "--split", "a,b,c")[0].returncode == 2
    bad = tmp_path / "b.csv"
    bad.write_text("question,answer\nq,a\n")
    assert _build(tmp_path, bad)[0].returncode == 2
    txt = tmp_path / "e.txt"
    txt.write_text("x")
    assert _build(tmp_path, txt)[0].returncode == 2
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2


def test_validate_jsonl(tmp_path):
    good = tmp_path / "g.jsonl"
    good.write_text(json.dumps({"messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]}) + "\n")
    bad = tmp_path / "b.jsonl"
    bad.write_text(json.dumps({"prompt": "q", "completion": "a"}) + "\n")
    empty = tmp_path / "e.jsonl"
    empty.write_text("")
    assert run_script(SCRIPT, "--validate-jsonl", str(good)).returncode == 0
    assert run_script(SCRIPT, "--validate-jsonl", str(bad)).returncode == 1
    assert run_script(SCRIPT, "--validate-jsonl", str(empty)).returncode == 0


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src
