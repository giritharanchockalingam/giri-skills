"""Tests for scripts/check_output.py — one test (or more) per check in the vocabulary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, run_script

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output as co  # noqa: E402

SCRIPT = "scripts/check_output.py"


def w(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def ok(spec, path=None, **kw):
    return co.run_check(spec, str(path) if path else None, **kw)["pass"]


def test_vocabulary_is_complete():
    expected = {"exists", "json", "csv", "csv_rows", "yaml", "sections", "no_unowned_tbd", "numbers_trace_to",
                "cites_source_ids", "mermaid_parses", "max_lines", "contains", "cmd", "exit", "needs_input"}
    assert co.VOCAB == expected


def test_parse_spec():
    assert co.parse_spec("exists") == ("exists", None)
    assert co.parse_spec("max_lines:40") == ("max_lines", "40")
    assert co.parse_spec('sections:["Bottom line","Risks"]') == ("sections", ["Bottom line", "Risks"])
    assert co.parse_spec('cmd:"python3 x.py --flag"') == ("cmd", "python3 x.py --flag")
    assert co.parse_spec("csv:[a,b]") == ("csv", ["a", "b"])


def test_exists(tmp_path):
    assert ok("exists", w(tmp_path, "a.txt", "x"))
    assert not ok("exists", tmp_path / "missing.txt")
    assert not ok("exists", w(tmp_path, "empty.txt", ""))


def test_json(tmp_path):
    assert ok("json", w(tmp_path, "a.json", '{"a": 1}'))
    assert not ok("json", w(tmp_path, "b.json", "{nope"))


def test_csv(tmp_path):
    p = w(tmp_path, "a.csv", "id,name,stage\n1,x,Applied\n")
    assert ok("csv:[id,stage]", p)
    r = co.run_check("csv:[id,missing]", str(p))
    assert not r["pass"] and "missing" in r["evidence"]


def test_csv_rows_not_empty(tmp_path):
    p = w(tmp_path, "d.csv", "id,acceptance\nD-01,Signed off\nD-02,[TO BE BASELINED — owner: ___]\n")
    assert ok("csv_rows:acceptance!empty", p, mode="real")
    gap = w(tmp_path, "g.csv", "id,acceptance\nD-01,Signed off\nD-02,\n")
    r = co.run_check("csv_rows:acceptance!empty", str(gap), mode="real")
    assert not r["pass"] and "1 of 2 rows empty" in r["evidence"] and "lines [3]" in r["evidence"]
    assert not ok("csv_rows:acceptance!empty", gap, mode="dry")   # partially filled: still evaluated
    r = co.run_check("csv_rows:nope!empty", str(p), mode="real")
    assert not r["pass"] and "not in header" in r["evidence"]
    assert not ok("csv_rows:acceptance!empty", w(tmp_path, "h.csv", "id,acceptance\n"), mode="real")


def test_csv_rows_regex(tmp_path):
    p = w(tmp_path, "s.csv", "slide,verdict\n1,[KEEP]\n2,[SHARPEN] + [TBD]\n")
    assert ok(r"csv_rows:verdict~\[(KEEP|SHARPEN|CUT|ADD|TBD)\]", p, mode="real")
    assert ok(r"csv_rows:slide~^\d+$", p, mode="real")
    r = co.run_check(r"csv_rows:verdict~^\[KEEP\]$", str(p), mode="real")
    assert not r["pass"] and "not matching" in r["evidence"]
    assert not ok("csv_rows:verdict~[", p, mode="real")          # bad regex fails, never raises
    assert not ok("csv_rows:verdict", p, mode="real")            # no predicate


def test_csv_rows_dry_mode_skips_unfilled_column(tmp_path):
    p = w(tmp_path, "l.csv", "slide,verdict\n1,\n2,\n")
    r = co.run_check("csv_rows:verdict!empty", str(p), mode="dry")
    assert r["pass"] and "skipped in dry mode" in r["evidence"]
    assert not ok("csv_rows:verdict!empty", p, mode="real")


def test_csv_rows_parse_spec_keeps_regex():
    assert co.parse_spec("csv_rows:owner!empty") == ("csv_rows", "owner!empty")
    assert co.parse_spec(r"csv_rows:when~^\d{4}-\d{2}") == ("csv_rows", r"when~^\d{4}-\d{2}")


def test_yaml(tmp_path):
    assert ok("yaml", w(tmp_path, "a.yml", "name: ci\non:\n  push: {}\njobs:\n  build:\n    runs-on: ubuntu\n"))
    assert not ok("yaml", w(tmp_path, "e.yml", "\n"))


def test_sections(tmp_path):
    p = w(tmp_path, "a.md", "# Memo\n\n## Bottom line\ntext\n\n## Risks to the estimate\n")
    assert ok('sections:["Bottom line","Risks"]', p)
    r = co.run_check('sections:["Bottom line","Staffing"]', str(p))
    assert not r["pass"] and "Staffing" in r["evidence"]


def test_no_unowned_tbd_modes(tmp_path):
    owned = w(tmp_path, "o.md", "Price: [TO BE BASELINED — owner: Priya]\n")
    blank = w(tmp_path, "b.md", "Price: [TO BE BASELINED — owner: ___]\n")
    bare = w(tmp_path, "n.md", "Count: [TO BE BASELINED]\n")
    assert ok("no_unowned_tbd", owned, mode="real")
    assert not ok("no_unowned_tbd", blank, mode="real")
    assert ok("no_unowned_tbd", blank, mode="dry")      # template placeholder is fine in dry mode
    assert not ok("no_unowned_tbd", bare, mode="dry")   # marker without owner segment never passes
    assert not ok("no_unowned_tbd", bare, mode="real")


def test_numbers_trace_to(tmp_path):
    ref = w(tmp_path, "ref.md", "P80 83.09 pd; P50 76.31; total 1,250,000 USD; 12 tasks\n")
    good = w(tmp_path, "good.md", "Quote 83.1 pd at P80 (P50 76.3). Price $1,250,000. 12 tasks, 3 phases.\n")
    bad = w(tmp_path, "bad.md", "Quote 95.5 pd at P80; margin 32%.\n")
    assert ok(f"numbers_trace_to:{ref}", good, mode="real")
    r = co.run_check(f"numbers_trace_to:{ref}", str(bad), mode="real")
    assert not r["pass"] and "95.5" in r["evidence"] and "32" in r["evidence"]
    assert ok(f"numbers_trace_to:{ref}", bad, mode="dry")  # skipped in dry mode
    # list of reference files, resolved against cwd
    ref2 = w(tmp_path, "ref2.md", "margin 32%\n")
    spec = f'numbers_trace_to:["{ref.name}","{ref2.name}"]'
    assert not ok(spec, bad, mode="real", cwd=str(tmp_path))
    assert ok(spec, w(tmp_path, "ok2.md", "P50 76.31 and margin 32%\n"), mode="real", cwd=str(tmp_path))


def test_cites_source_ids(tmp_path):
    ref = w(tmp_path, "skel.md", "## Sources\n| S1 | https://example.com |\n| S2 | report |\n")
    assert ok(f"cites_source_ids:{ref}", w(tmp_path, "b.md", "Revenue up [S1]; CIO quote [S2]\n"), mode="real")
    assert not ok(f"cites_source_ids:{ref}", w(tmp_path, "c.md", "Revenue up [S9]\n"), mode="real")
    assert not ok(f"cites_source_ids:{ref}", w(tmp_path, "d.md", "no citations at all\n"), mode="real")
    assert ok(f"cites_source_ids:{ref}", w(tmp_path, "e.md", "[S9]\n"), mode="dry")


def test_mermaid_parses(tmp_path):
    assert ok("mermaid_parses", w(tmp_path, "a.md", "```mermaid\ngraph TD\n A[Web] --> B[API]\n```\n"))
    assert not ok("mermaid_parses", w(tmp_path, "b.md", "```mermaid\ngraph TD\n A[Web --> B\n```\n"))
    assert not ok("mermaid_parses", w(tmp_path, "c.md", "no diagram\n"))


def test_max_lines(tmp_path):
    p = w(tmp_path, "a.md", "1\n2\n3\n")
    assert ok("max_lines:3", p)
    assert not ok("max_lines:2", p)


def test_contains(tmp_path):
    p = w(tmp_path, "a.md", "Price: [TO BE BASELINED — owner: ___]\n")
    assert ok('contains:"[TO BE BASELINED"', p)
    assert not ok('contains:"$1,000"', p)


def test_cmd(tmp_path):
    p = w(tmp_path, "a.json", '{"a": 1}')
    good = w(tmp_path, "good.py", "import sys, json; json.load(open(sys.argv[1])); sys.exit(0)\n")
    bad = w(tmp_path, "bad.py", "import sys; sys.exit(3)\n")
    assert ok(f'cmd:"python3 {good} {{path}}"', p)
    r = co.run_check(f'cmd:"python3 {bad}"', str(p))
    assert not r["pass"] and "exit 3" in r["evidence"]


def test_exit_and_needs_input(tmp_path):
    assert ok("exit:0", exit_code=0)
    assert not ok("exit:0", exit_code=2)
    assert ok("exit:2", exit_code=2)
    (tmp_path / "needs_input.json").write_text(json.dumps({"missing": [{"name": "rates"}]}), encoding="utf-8")
    assert ok("needs_input:rates", out_dir=str(tmp_path))
    assert not ok("needs_input:wbs", out_dir=str(tmp_path))
    assert not ok("needs_input:rates", out_dir=str(tmp_path / "nowhere"))


def test_unknown_check_fails():
    r = co.run_check("bogus", "x")
    assert not r["pass"] and "unknown check" in r["evidence"]


def test_result_shape(tmp_path):
    r = co.run_check("exists", str(w(tmp_path, "a.txt", "x")))
    assert set(r) == {"check", "pass", "evidence"}


def test_cli(tmp_path):
    p = w(tmp_path, "a.md", "## Bottom line\nx\n")
    r = run_script(SCRIPT, str(p), "exists", 'sections:["Bottom line"]', "--mode", "dry")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout
    r = run_script(SCRIPT, str(p), "json")
    assert r.returncode == 1
    assert "FAIL" in r.stdout
