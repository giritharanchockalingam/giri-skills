"""merge_eval_results: a partial run replaces only its skills; mismatched settings are refused."""
import csv, importlib.util, sys
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("m", Path(__file__).parents[1] / "scripts" / "merge_eval_results.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def write(d: Path, date, spend, rows, model="gpt-4.1-mini"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "scorecard.md").write_text(f"# Behavioral eval scorecard\n_provider=openai model={model} runs=2 seed=42 date={date}_\n_estimated spend: ${spend}_\n\n"
        "| skill | trigger acc | verdict |\n|---|---|---|\n" + "".join(f"| {s} | 1.00 | {v} |\n" for s, v in rows), encoding="utf-8")
    for name, cols in (("trigger.csv", ["skill", "case_id", "run", "selected", "correct"]), ("quality.csv", ["skill", "case_id", "run", "mode", "expected_idx", "pass", "evidence"])):
        with (d / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
            for s, v in rows: w.writerow({c: (s if c == "skill" else v) for c in cols})

def test_partial_run_replaces_only_its_skills(tmp_path):
    write(tmp_path / "dst", "2026-10-17", "11.84", [("a/one", "OK"), ("a/two", "BODY")])
    write(tmp_path / "src", "2026-10-20", "25.13", [("a/two", "OK"), ("b/new", "DESC")])
    r = m.merge(tmp_path / "src", tmp_path / "dst")
    assert (r["added"], r["replaced"], r["total"]) == (1, 1, 3)
    sc = (tmp_path / "dst" / "scorecard.md").read_text()
    assert "date=2026-10-17–2026-10-20_" in sc and "$36.97" in sc
    assert "| a/one | 1.00 | OK |" in sc and "| a/two | 1.00 | OK |" in sc and "BODY" not in sc
    q = list(csv.DictReader((tmp_path / "dst" / "quality.csv").open()))
    assert sorted(x["skill"] for x in q) == ["a/one", "a/two", "b/new"]

def test_refuses_a_different_model(tmp_path):
    write(tmp_path / "dst", "2026-10-17", "1", [("a/one", "OK")])
    write(tmp_path / "src", "2026-10-20", "1", [("a/one", "OK")], model="gpt-4.1")
    with pytest.raises(SystemExit):
        m.merge(tmp_path / "src", tmp_path / "dst")
