"""Tests for build_dataset.py --existing-dir (extend a current dataset without reshuffling it)."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/finetune-dataset-builder/scripts/build_dataset.py"
FIX = REPO_ROOT / "skills/ai-platform/finetune-dataset-builder/evals/fixtures"
SPLITS = ("train", "val", "test")


def records(folder, split):
    return [json.loads(ln)["messages"] for ln in (folder / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
            if ln.strip()]


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps({"messages": [{"role": "user", "content": p}, {"role": "assistant", "content": c}]})
                            + "\n" for p, c in rows), encoding="utf-8")


def test_current_dataset_fixture_is_real_output_of_v1(tmp_path):
    r = run_script(SCRIPT, "--examples", str(FIX / "helpdesk-examples-v1.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    for s in SPLITS:
        assert records(tmp_path, s) == records(FIX / "current-dataset", s)


def test_existing_records_keep_their_split(tmp_path):
    r = run_script(SCRIPT, "--examples", str(FIX / "helpdesk-examples.csv"), "--existing-dir",
                   str(FIX / "current-dataset"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    for s in SPLITS:
        new = records(tmp_path, s)
        assert all(rec in new for rec in records(FIX / "current-dataset", s)), s
    st = json.loads((tmp_path / "dataset-stats.json").read_text(encoding="utf-8"))
    assert st["existing"]["kept"] == {"train": 8, "val": 1, "test": 1}
    assert st["existing"]["new_added"] == {"train": 3, "val": 1, "test": 1}
    assert st["existing"]["new_already_in_dataset"] == 11 and st["leakage_prompts_across_splits"] == 0
    for s in SPLITS:
        assert run_script(SCRIPT, "--validate-jsonl", str(tmp_path / f"{s}.jsonl")).returncode == 0


def test_new_completion_joins_pinned_prompt_split(tmp_path):
    cur = tmp_path / "cur"
    cur.mkdir()
    write_jsonl(cur / "train.jsonl", [(f"train question {i}", f"answer {i}") for i in range(8)])
    write_jsonl(cur / "test.jsonl", [("How do I reset my token?", "Use the portal.")])
    new = tmp_path / "new.csv"
    new.write_text("prompt,completion\nHow do I reset my token?,Call the service desk.\n", encoding="utf-8")
    r = run_script(SCRIPT, "--examples", str(new), "--existing-dir", str(cur), "--out-dir", str(tmp_path / "out"))
    assert r.returncode == 0, r.stderr
    test = records(tmp_path / "out", "test")
    assert len(test) == 2 and {m[1]["content"] for m in test} == {"Use the portal.", "Call the service desk."}


def test_existing_leakage_and_duplicates_repaired(tmp_path):
    cur = tmp_path / "cur"
    cur.mkdir()
    write_jsonl(cur / "train.jsonl", [(f"q{i}", f"a{i}") for i in range(9)] + [("q0", "a0")])
    write_jsonl(cur / "val.jsonl", [("Q1 ", "another answer")])  # same prompt as a train group
    new = tmp_path / "new.csv"
    new.write_text("prompt,completion\nq9,a9\n", encoding="utf-8")
    r = run_script(SCRIPT, "--examples", str(new), "--existing-dir", str(cur), "--out-dir", str(tmp_path / "out"))
    assert r.returncode == 0, r.stderr
    st = json.loads((tmp_path / "out" / "dataset-stats.json").read_text(encoding="utf-8"))
    ex = st["existing"]
    assert ex["duplicates_removed"] == 1 and ex["leakage_groups_repaired"] == 1
    assert ex["records_moved_to_repair_leakage"] == 1 and st["leakage_prompts_across_splits"] == 0
    assert "1 leaking prompt group(s) repaired" in (tmp_path / "out" / "data-card.md").read_text(encoding="utf-8")


def test_without_existing_output_unchanged(tmp_path):
    r = run_script(SCRIPT, "--examples", str(FIX / "helpdesk-examples.csv"), "--out-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    st = json.loads((tmp_path / "dataset-stats.json").read_text(encoding="utf-8"))
    assert "existing" not in st and st["splits"] == {"train": 11, "val": 2, "test": 2}


def test_bad_existing_dir_exits_2(tmp_path):
    r = run_script(SCRIPT, "--examples", str(FIX / "helpdesk-examples.csv"), "--existing-dir", str(tmp_path / "nope"),
                   "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 2 and "folder not found" in r.stderr
    (tmp_path / "empty").mkdir()
    r = run_script(SCRIPT, "--examples", str(FIX / "helpdesk-examples.csv"), "--existing-dir", str(tmp_path / "empty"),
                   "--out-dir", str(tmp_path / "o"))
    assert r.returncode == 2 and "needs train.jsonl" in r.stderr
