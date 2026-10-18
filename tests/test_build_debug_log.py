"""Tests for build/systematic-debugging-runner/scripts/debug_log.py."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/systematic-debugging-runner/scripts/debug_log.py"
FX = REPO_ROOT / "skills/build/systematic-debugging-runner/evals/fixtures"


def run(tmp_path, log, *extra):
    j, m = tmp_path / "debug.json", tmp_path / "debug-log.md"
    res = run_script(SCRIPT, "--log", str(log), *extra, "--json", str(j), "--md", str(m))
    data = json.loads(j.read_text(encoding="utf-8")) if j.exists() else None
    md = m.read_text(encoding="utf-8") if m.exists() else ""
    return res, data, md


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_python_with_diff_is_regression(tmp_path):
    res, d, md = run(tmp_path, FX / "pytest-failure.txt", "--diff", str(FX / "recent.patch"),
                     "--repro", str(FX / "repro.md"))
    assert res.returncode == 0, res.stderr
    assert d["format"] == "python"
    assert d["symptom"]["error_type"] == "KeyError" and d["symptom"]["message"] == "'EU'"
    assert len(d["frames"]) == 4
    # innermost first: the site-packages frame is depth 0 and is not in-repo
    assert d["frames"][0]["in_repo"] is False and "site-packages" in d["frames"][0]["file"]
    im = d["innermost_in_repo_frame"]
    assert im["file"].endswith("billing/tax.py") and im["line"] == 17 and im["func"] == "tax_rate_for"
    assert d["classification"] == "regression-likely"
    # hunk @@ +10,9 covers new lines 10-18; the changed line is 12
    assert im["line_touched"] is True and im["hunk"] == [10, 18] and im["changed_lines"] == [12]
    assert d["frames"][2]["file_touched"] is False          # invoice.py is not in the diff
    h = d["hypotheses"]
    assert h[0]["id"] == "H1" and h[0]["evidence_score"] == 3 and h[0]["kind"] == "regression-line"
    assert h[1]["kind"] == "missing-key-or-index"
    assert [x["evidence_score"] for x in h] == sorted((x["evidence_score"] for x in h), reverse=True)
    assert all(x["falsifying_test"] and x["status"] == "untested" for x in h)
    assert d["gate"]["fix_allowed"] is False
    assert d["symptom"]["repro_steps"][1].startswith("Run: pytest")
    assert d["next_experiments"][0]["experiment"].startswith("H1:")     # repro given -> straight to H1
    for sec in ("## Symptom", "## Evidence", "## Hypotheses", "## Next experiment", "## Fix gate"):
        assert sec in md
    assert "Fix allowed: NO" in md


def test_js_without_diff(tmp_path):
    res, d, md = run(tmp_path, FX / "jest-failure.txt")
    assert res.returncode == 0, res.stderr
    assert d["format"] == "js" and d["symptom"]["error_type"] == "TypeError"
    assert [f["file"] for f in d["frames"]] == ["src/cart/coupon.ts", "src/cart/__tests__/cart.test.ts",
                                              "node_modules/jest-circus/build/utils.js"]
    assert [f["in_repo"] for f in d["frames"]] == [True, True, False]
    assert d["classification"] == "no-diff"
    assert d["hypotheses"][0]["kind"] == "null-value"          # "undefined" in the message
    assert d["hypotheses"][-1]["kind"] == "environment"
    assert d["next_experiments"][0]["experiment"].startswith("Establish a reliable reproduction")
    assert "[TO BE BASELINED — owner: Reporting engineer]" in md


def test_java_caused_by_is_root(tmp_path):
    res, d, _ = run(tmp_path, FX / "java-failure.txt")
    assert res.returncode == 0, res.stderr
    assert d["format"] == "java"
    assert d["symptom"]["error_type"] == "java.lang.NullPointerException"
    assert [f["func"] for f in d["frames"]] == ["com.acme.orders.ShippingCalculator.quote",
                                              "com.acme.orders.OrderService.process",
                                              "java.util.ArrayList.forEach"]
    assert d["frames"][0]["file"] == "com/acme/orders/ShippingCalculator.java"
    assert d["frames"][2]["in_repo"] is False


def test_java_frame_matches_diff_by_package_path(tmp_path):
    patch = tmp_path / "j.patch"
    patch.write_text("--- a/src/main/java/com/acme/orders/ShippingCalculator.java\n"
                     "+++ b/src/main/java/com/acme/orders/ShippingCalculator.java\n"
                     "@@ -30,3 +30,4 @@\n ctx\n ctx\n+    Address addr = order.address();\n ctx\n", encoding="utf-8")
    res, d, _ = run(tmp_path, FX / "java-failure.txt", "--diff", str(patch))
    assert res.returncode == 0, res.stderr
    f0 = d["frames"][0]
    assert f0["file_touched"] and f0["line_touched"] and f0["changed_lines"] == [32]
    assert d["classification"] == "regression-likely"


def test_diff_without_overlap(tmp_path):
    patch = tmp_path / "x.patch"
    patch.write_text("--- a/docs/x.md\n+++ b/docs/x.md\n@@ -1,1 +1,2 @@\n a\n+b\n", encoding="utf-8")
    res, d, _ = run(tmp_path, FX / "pytest-failure.txt", "--diff", str(patch))
    assert res.returncode == 0
    assert d["classification"] == "no-overlap"
    assert d["hypotheses"][-1]["kind"] == "environment"


def test_no_parsable_error_exits_2(tmp_path):
    res, d, _ = run(tmp_path, FX / "no-error.txt")
    assert res.returncode == 2 and d is None
    assert "no parsable error" in res.stderr


def test_missing_inputs_exit_2(tmp_path):
    assert run_script(SCRIPT, "--json", str(tmp_path / "d.json")).returncode == 2
    assert run_script(SCRIPT, "--log", str(tmp_path / "nope.txt"), "--json", str(tmp_path / "d.json")).returncode == 2
    assert run_script(SCRIPT, "--log", str(FX / "jest-failure.txt"), "--diff", str(tmp_path / "nope"),
                      "--json", str(tmp_path / "d.json")).returncode == 2


def test_validate_rejects_open_gate(tmp_path):
    _, d, _ = run(tmp_path, FX / "jest-failure.txt")
    good = tmp_path / "debug.json"
    assert run_script(SCRIPT, "--validate", str(good)).returncode == 0
    d["gate"]["fix_allowed"] = True
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(d), encoding="utf-8")
    r = run_script(SCRIPT, "--validate", str(bad))
    assert r.returncode == 1 and "fix gate open" in r.stderr
    d["gate"]["fix_allowed"] = False
    d["hypotheses"][0]["falsifying_test"] = ""
    bad.write_text(json.dumps(d), encoding="utf-8")
    assert run_script(SCRIPT, "--validate", str(bad)).returncode == 1
