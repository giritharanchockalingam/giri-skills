"""Tests for ai-platform/annotation-agreement/scripts/agreement.py against published worked examples."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/annotation-agreement/scripts/agreement.py"
FIX = REPO_ROOT / "skills/ai-platform/annotation-agreement/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Annotation lead]"


def _write(tmp_path: Path, rows: list[tuple[str, str, str]], name: str = "labels.csv") -> Path:
    p = tmp_path / name
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "annotator", "label"])
        w.writerows(rows)
    return p


def _run(tmp_path, labels: Path, *extra, name: str = "o"):
    res = run_script(SCRIPT, "--labels", str(labels), "--out-dir", str(tmp_path / name), *extra)
    j = tmp_path / name / "agreement.json"
    return res, (json.loads(j.read_text(encoding="utf-8")) if j.exists() else {})


def _matrix(observers: dict[str, str]) -> list[tuple[str, str, str]]:
    rows = []
    for obs, vals in observers.items():
        for i, v in enumerate(vals.split(), start=1):
            if v != ".":
                rows.append((f"u{i:02d}", obs, v))
    return rows


def test_krippendorff_alpha_published_example_with_missing_data(tmp_path):
    # Krippendorff (2011), "Computing Krippendorff's Alpha-Reliability": nominal alpha = 0.743
    rows = _matrix({"A": "1 2 3 3 2 1 4 1 2 . . .", "B": "1 2 3 3 2 2 4 1 2 5 . 3",
                    "C": ". 3 3 3 2 3 4 2 2 5 1 .", "D": "1 2 3 3 2 4 4 1 2 5 1 ."})
    res, d = _run(tmp_path, _write(tmp_path, rows))
    assert res.returncode == 0, res.stderr
    assert round(d["krippendorff_alpha"], 3) == 0.743
    assert d["single_rated_items"] == ["u12"]            # unit 12 has one value: not pairable
    assert d["fleiss"]["kappa"] is None                  # 2-4 ratings per item


def test_krippendorff_alpha_binary_two_observer_example(tmp_path):
    # Same source, Meg/Owen binary data: alpha = 0.095
    rows = _matrix({"Meg": "0 1 0 0 0 0 0 0 1 0", "Owen": "1 1 1 0 0 1 0 0 0 0"})
    _, d = _run(tmp_path, _write(tmp_path, rows))
    assert round(d["krippendorff_alpha"], 3) == 0.095


def test_fleiss_kappa_wikipedia_worked_example(tmp_path):
    # Fleiss' kappa page: 10 subjects x 14 raters x 5 categories -> P-bar 0.378, Pe 0.213, kappa 0.210
    table = [[0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
             [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7]]
    rows = []
    for s, counts in enumerate(table, start=1):
        r = 0
        for c, n in enumerate(counts, start=1):
            for _ in range(n):
                r += 1
                rows.append((f"s{s:02d}", f"r{r:02d}", f"c{c}"))
    _, d = _run(tmp_path, _write(tmp_path, rows))
    fl = d["fleiss"]
    assert round(fl["kappa"], 3) == 0.210 and round(fl["p_bar"], 3) == 0.378 and round(fl["p_e"], 3) == 0.213
    assert fl["raters_per_item"] == 14 and fl["band"] == "fair"


def test_cohen_kappa_and_specific_agreement_wikipedia_example(tmp_path):
    # Cohen's kappa page: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> p_o .70, p_e .50, kappa .40
    rows, i = [], 0
    for a, b, n in (("yes", "yes", 20), ("yes", "no", 5), ("no", "yes", 10), ("no", "no", 15)):
        for _ in range(n):
            i += 1
            rows += [(f"g{i:02d}", "A", a), (f"g{i:02d}", "B", b)]
    _, d = _run(tmp_path, _write(tmp_path, rows))
    p = d["pairs"][0]
    assert (p["observed"], p["expected"], p["kappa"], p["band"]) == (0.7, 0.5, 0.4, "fair")
    lab = {r["label"]: r for r in csv.DictReader((tmp_path / "o" / "label-agreement.csv").open(encoding="utf-8"))}
    assert lab["yes"]["agreement"] == f"{2 * 20 / (2 * 20 + 5 + 10):.3f}"   # 2a/(2a+b+c) = 0.727
    assert lab["no"]["agreement"] == f"{2 * 15 / (2 * 15 + 5 + 10):.3f}"    # 0.667
    assert d["percent_agreement"] == 0.7


def test_fixture_pair_kappa_disputed_and_guideline_gaps(tmp_path):
    res, d = _run(tmp_path, FIX / "labels.csv", "--guidelines", str(FIX / "guidelines.md"))
    assert res.returncode == 0, res.stderr
    ab = next(p for p in d["pairs"] if p["pair"] == "ann_a|ann_b")
    # hand count: 9/15 agree; marginals give p_e = 45/225 = 0.2 -> kappa 0.5
    assert ab["n_items"] == 15 and ab["observed"] == 0.6 and ab["expected"] == 0.2 and ab["kappa"] == 0.5
    disputed = list(csv.DictReader((tmp_path / "o" / "disputed-items.csv").open(encoding="utf-8")))
    assert disputed[0] == {"item_id": "NW-011", "labels": "billing_dispute:1;other:1;plan_change:1",
                           "majority": "tie", "agreement": "0.000"}
    assert [r["item_id"] for r in disputed[1:]] == ["NW-002", "NW-004", "NW-006", "NW-009", "NW-014", "NW-015"]
    assert d["guideline_gaps"] == ["plan_change"] and d["labels_not_in_guidelines"] == ["plan_change", "refund_request"]
    assert d["confusion_pairs"][0] == {"label_a": "billing_dispute", "label_b": "refund_request", "count": 6}


def test_min_agreement_gate(tmp_path):
    res, d = _run(tmp_path, FIX / "labels.csv", "--min-agreement", "0.5", name="pass")
    assert res.returncode == 0 and d["gate"]["passed"] is True
    res2, d2 = _run(tmp_path, FIX / "labels.csv", "--min-agreement", "0.667", name="fail")
    assert res2.returncode == 1 and d2["gate"]["passed"] is False and "below minimum" in res2.stderr
    assert (tmp_path / "fail" / "agreement-report.md").exists()          # outputs still written
    assert run_script(SCRIPT, "--labels", str(FIX / "labels.csv"), "--min-agreement", "high",
                      "--out-dir", str(tmp_path / "x")).returncode == 2


def test_single_annotator_per_item_exits_1_without_score(tmp_path):
    res, d = _run(tmp_path, FIX / "labels-single.csv")
    assert res.returncode == 1 and "no item has ratings from 2 or more annotators" in res.stderr
    assert d["status"] == "insufficient" and "krippendorff_alpha" not in d and "pairs" not in d
    md = (tmp_path / "o" / "agreement-report.md").read_text(encoding="utf-8")
    assert "**No agreement score:" in md and "0.000" not in md


def test_no_guidelines_is_tbd_with_owner(tmp_path):
    res, d = _run(tmp_path, FIX / "labels.csv")
    rows = list(csv.DictReader((tmp_path / "o" / "label-agreement.csv").open(encoding="utf-8")))
    assert all(r["defined_in_guidelines"] == TBD for r in rows)
    md = (tmp_path / "o" / "agreement-report.md").read_text(encoding="utf-8")
    assert f"No guidelines supplied: {TBD}" in md
    for line in md.splitlines():
        if "[TO BE BASELINED" in line:
            assert "— owner: Annotation lead]" in line


def test_guideline_matching_spaces_and_hyphens(tmp_path):
    rows = [("i1", "a", "refund_request"), ("i1", "b", "plan-change"), ("i2", "a", "refund_request"),
            ("i2", "b", "refund_request"), ("i3", "a", "plan-change"), ("i3", "b", "plan-change")]
    g = tmp_path / "g.md"
    g.write_text("# Guide\n\nA Refund Request asks for money back.\n\nprepaid_plan-changes are out of scope.\n")
    _, d = _run(tmp_path, _write(tmp_path, rows), "--guidelines", str(g))
    assert d["defined"] == {"plan-change": False, "refund_request": True}


def test_malformed_inputs_exit_2(tmp_path):
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "x")).returncode == 2
    (tmp_path / "bad.csv").write_text("item,rater,label\n1,a,x\n", encoding="utf-8")
    res = run_script(SCRIPT, "--labels", str(tmp_path / "bad.csv"), "--out-dir", str(tmp_path / "x"))
    assert res.returncode == 2 and "item_id" in res.stderr
    dup = _write(tmp_path, [("i1", "a", "x"), ("i1", "a", "y"), ("i1", "b", "x")], "dup.csv")
    res2 = run_script(SCRIPT, "--labels", str(dup), "--out-dir", str(tmp_path / "x"))
    assert res2.returncode == 2 and "twice" in res2.stderr
    res3 = run_script(SCRIPT, "--labels", str(FIX / "labels.csv"), "--guidelines", str(tmp_path / "nope.md"),
                      "--out-dir", str(tmp_path / "x"))
    assert res3.returncode == 2


def test_deterministic_and_verify_mode(tmp_path):
    args = ("--guidelines", str(FIX / "guidelines.md"), "--min-agreement", "0.5")
    _run(tmp_path, FIX / "labels.csv", *args, name="a")
    _run(tmp_path, FIX / "labels.csv", *args, name="b")
    for f in ("agreement.json", "disputed-items.csv", "label-agreement.csv", "agreement-report.md"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
        ok = run_script(SCRIPT, "--verify", str(tmp_path / "a" / f), "--labels", str(FIX / "labels.csv"))
        assert ok.returncode == 0, ok.stdout
    p = tmp_path / "a" / "label-agreement.csv"
    p.write_text(p.read_text().replace("plan_change,6,0.500,no", "plan_change,6,0.900,yes"), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(p), "--labels", str(FIX / "labels.csv"))
    assert bad.returncode == 1


def test_no_network_imports():
    src = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for bad in ("import socket", "import urllib", "import requests", "import subprocess", "urlopen("):
        assert bad not in src
