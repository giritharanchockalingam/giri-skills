"""Brownfield ("existing") path of build/webapp-testing-runner: --existing suite, only gaps generated."""
from __future__ import annotations

import ast
import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/webapp-testing-runner/scripts/gen_tests.py"
FX = REPO_ROOT / "skills/build/webapp-testing-runner/evals/fixtures"


def gen(tmp_path, flows, existing):
    t, r, j = tmp_path / "test_flows.py", tmp_path / "flows-report.md", tmp_path / "out.json"
    res = run_script(SCRIPT, "--flows", str(flows), "--existing", str(existing), "--test-out", str(t),
                     "--report", str(r), "--json", str(j))
    return res, t, (r.read_text(encoding="utf-8") if r.exists() else ""), \
        (json.loads(j.read_text(encoding="utf-8")) if j.exists() else None)


def test_covered_flow_not_regenerated(tmp_path):
    res, t, md, data = gen(tmp_path, FX / "flows.json", FX / "existing-e2e")
    assert res.returncode == 0, res.stderr
    names = [n.name for n in ast.parse(t.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)]
    assert "test_add_item_to_cart" in names and "test_sign_in" not in names
    assert data["existing"]["tests"] == 2
    assert data["existing"]["flows"][0] == {"flow": "Sign in", "file": "auth.spec.ts",
                                            "test": "sign in with email and password"}
    assert "| Add item to cart | — | generated |" in md
    assert len(data["coverage"]) == 2                     # every flow is still validated and reported


def test_python_suite_and_all_covered(tmp_path):
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "test_shop.py").write_text("def test_sign_in(page):\n    pass\n\n"
                                        "async def test_add_item_to_cart_from_listing(page):\n    pass\n", encoding="utf-8")
    res, t, md, data = gen(tmp_path, FX / "flows.json", suite)
    assert res.returncode == 0, res.stderr
    src = t.read_text(encoding="utf-8")
    assert "GENERATED, NOT EXECUTED" in src and "def test_" not in src.split("_require_base_url", 1)[1]
    assert run_script(SCRIPT, "--verify-compiles", str(t)).returncode == 0
    assert "(0 test function(s)" in md


def test_unrelated_suite_covers_nothing(tmp_path):
    suite = tmp_path / "s.spec.ts"
    suite.write_text('test("export invoices as csv", async () => {});\n', encoding="utf-8")
    res, t, md, data = gen(tmp_path, FX / "flows.json", suite)
    assert res.returncode == 0
    assert all("test" not in r for r in data["existing"]["flows"])
    assert "(2 test function(s)" in md


def test_missing_existing_path_exits_2(tmp_path):
    res, _, _, _ = gen(tmp_path, FX / "flows.json", tmp_path / "nope")
    assert res.returncode == 2 and "--existing not found" in res.stderr
