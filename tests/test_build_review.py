"""Tests for build/code-review-runner/scripts/review.py."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/code-review-runner/scripts/review.py"
FX = REPO_ROOT / "skills/build/code-review-runner/evals/fixtures"


def run(tmp_path, diff, *extra):
    j, m = tmp_path / "review.json", tmp_path / "review.md"
    res = run_script(SCRIPT, "--diff", str(diff), *extra, "--json", str(j), "--md", str(m))
    data = json.loads(j.read_text(encoding="utf-8")) if j.exists() else None
    return res, data, (m.read_text(encoding="utf-8") if m.exists() else "")


def keyed(d):
    return {(f["rule"], f["file"], f["line"]) for f in d["findings"]}


def write_patch(tmp_path, path, added, name="x.patch"):
    body = "".join(f"+{ln}\n" for ln in added)
    p = tmp_path / name
    p.write_text(f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(added)} @@\n{body}", encoding="utf-8")
    return p


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_ok_diff_passes_with_non_blocking(tmp_path):
    res, d, md = run(tmp_path, FX / "change-ok.patch")
    assert res.returncode == 0, res.stderr
    assert keyed(d) == {("CR-DEBUG", "src/cart/coupon.ts", 15), ("CR-TODO", "src/cart/coupon.ts", 16)}
    s = d["stats"]
    # hand count: coupon.ts +6/-1 (1 hunk), coupon.test.ts +5/-0 (1 hunk)
    assert (s["files"], s["hunks"], s["added"], s["removed"]) == (2, 2, 11, 1)
    assert d["tests"]["verdict"] == "tests changed" and d["verdict"] == "PASS"
    assert d["counts"] == {"blocking": 0, "warning": 1, "info": 1}
    for sec in ("## Summary", "## Blocking", "## Non-blocking", "## Tests", "## Files"):
        assert sec in md
    assert "Verdict: **PASS**" in md


def test_risky_diff_blocks_and_redacts(tmp_path):
    res, d, md = run(tmp_path, FX / "change-risky.patch")
    assert res.returncode == 1                                   # blocking -> exit 1, files still written
    k = keyed(d)
    f = "app/reports/export.py"
    for rule, line in (("CR-SECRET", 3), ("CR-SECRET", 4), ("CR-SQL-CONCAT", 8), ("CR-TLS", 11),
                       ("CR-SWALLOW", 12), ("CR-DEBUG", 14), ("CR-TODO", 19), ("CR-EVAL", 20)):
        assert (rule, f, line) in k, (rule, line)
    assert ("CR-NO-TESTS", f, 1) in k
    assert not any(x["file"] == "app/settings.py" for x in d["findings"])   # ${DB_PASSWORD} is a placeholder
    assert d["counts"] == {"blocking": 5, "warning": 3, "info": 1}
    assert [x["severity"] for x in d["findings"]][:5] == ["blocking"] * 5    # sorted worst first
    assert d["findings"][0]["id"] == "F01"
    assert "FAKEFAKEFAKE1234" not in md and "AKIA[redacted]" in md
    assert "app/settings.py" in d["stats"]["risky_paths"]
    assert d["tests"]["verdict"] == "MISSING"


def test_gate(tmp_path):
    run(tmp_path, FX / "change-risky.patch")
    r = run_script(SCRIPT, "--gate", str(tmp_path / "review.json"))
    assert r.returncode == 1 and "BLOCK" in r.stderr
    run(tmp_path, FX / "change-ok.patch")
    assert run_script(SCRIPT, "--gate", str(tmp_path / "review.json")).returncode == 0
    assert run_script(SCRIPT, "--gate", str(tmp_path / "missing.json")).returncode == 1


def test_only_added_lines_scanned(tmp_path):
    p = tmp_path / "ctx.patch"
    p.write_text("--- a/a.py\n+++ b/a.py\n@@ -1,3 +1,3 @@\n x = eval(y)\n-print('old')\n+total = 1\n", encoding="utf-8")
    res, d, _ = run(tmp_path, p)
    assert res.returncode == 0
    assert {x["rule"] for x in d["findings"]} == {"CR-NO-TESTS"}


def test_todo_with_owner_not_flagged(tmp_path):
    p = write_patch(tmp_path, "tests/test_a.py", ["# TODO(priya): later", "# TODO [ABC-12] later",
                                                 "# TODO @sam later", "# FIXME broken"])
    _, d, _ = run(tmp_path, p)
    assert [(x["rule"], x["line"]) for x in d["findings"]] == [("CR-TODO", 4)]


def test_sql_variants(tmp_path):
    p = write_patch(tmp_path, "tests/test_q.py", [
        'q = f"SELECT id FROM users WHERE name = {name}"',
        'q = "DELETE FROM t WHERE id = %s" % uid',
        'q = "SELECT id FROM users WHERE id = %s"',          # parameterised: not flagged
        'cur.execute("UPDATE t SET a = {}".format(v))',
    ])
    _, d, _ = run(tmp_path, p)
    assert sorted(x["line"] for x in d["findings"] if x["rule"] == "CR-SQL-CONCAT") == [1, 2, 4]


def test_swallow_and_js_rules(tmp_path):
    p = write_patch(tmp_path, "src/a.ts", ["try { go(); } catch (e) {}", "debugger;", "const f = new Function(src);",
                                          "https.request({ rejectUnauthorized: false });", "re.exec(text);"])
    _, d, _ = run(tmp_path, p)
    got = {(x["rule"], x["line"]) for x in d["findings"]}
    assert {("CR-SWALLOW", 1), ("CR-DEBUG", 2), ("CR-EVAL", 3), ("CR-TLS", 4)} <= got
    assert ("CR-EVAL", 5) not in got                         # .exec() method call is not eval


def test_duplicate_block(tmp_path):
    block = ["total = order.subtotal * rate", "total = round(total, 2)", "log_total(order.id, total)"]
    p = write_patch(tmp_path, "tests/test_dup.py", block + ["x = 1"] + block)
    _, d, _ = run(tmp_path, p)
    dups = [x for x in d["findings"] if x["rule"] == "CR-DUP"]
    assert len(dups) == 1 and dups[0]["line"] == 5


def test_rules_csv_overrides_and_custom(tmp_path):
    res, d, _ = run(tmp_path, FX / "change-risky.patch", "--rules", str(FX / "rules.csv"))
    assert res.returncode == 1
    sev = {x["rule"]: x["severity"] for x in d["findings"]}
    assert sev["CR-NO-TESTS"] == "blocking" and sev["CR-TODO"] == "warning"
    assert d["rules"]["custom"] == ["TEAM-NO-ANY"]
    p = write_patch(tmp_path, "src/b.ts", ["let v: any = 1;"])
    _, d2, _ = run(tmp_path, p, "--rules", str(FX / "rules.csv"))
    assert ("TEAM-NO-ANY", "src/b.ts", 1) in keyed(d2)


def test_rules_off_and_bad_rules(tmp_path):
    rules = tmp_path / "r.csv"
    rules.write_text("rule_id,pattern,severity,message,file_glob\nCR-EVAL,,off,,\n", encoding="utf-8")
    p = write_patch(tmp_path, "tests/test_e.py", ["eval(x)"])
    _, d, _ = run(tmp_path, p, "--rules", str(rules))
    assert d["findings"] == []
    rules.write_text("rule_id,pattern,severity,message,file_glob\nX,(,blocking,m,\n", encoding="utf-8")
    res, _, _ = run(tmp_path, p, "--rules", str(rules))
    assert res.returncode == 2 and "bad regex" in res.stderr


def test_entropy_threshold_is_a_parameter(tmp_path):
    p = write_patch(tmp_path, "tests/test_k.py", ['k = "Zx81QmTr4LpW0cVb7NsY"'])
    _, d, _ = run(tmp_path, p)
    assert any(x["rule"] == "CR-SECRET" for x in d["findings"])
    _, d2, _ = run(tmp_path, p, "--entropy", "6.0")
    assert not any(x["rule"] == "CR-SECRET" for x in d2["findings"])


def test_missing_or_empty_input_exit_2(tmp_path):
    assert run_script(SCRIPT, "--json", str(tmp_path / "r.json")).returncode == 2
    assert run_script(SCRIPT, "--diff", str(tmp_path / "nope"), "--json", str(tmp_path / "r.json")).returncode == 2
    empty = tmp_path / "e.patch"
    empty.write_text("nothing here\n", encoding="utf-8")
    res, d, _ = run(tmp_path, empty)
    assert res.returncode == 2 and d is None


def test_placeholder_credentials_in_tests_are_not_secrets(tmp_path):
    """Stand-in values a test or doc uses are not leaked credentials (found on the first real delivery run)."""
    p = write_patch(tmp_path, "tests/unit/alerts.test.js", [
        '  RESEND_API_KEY: "placeholder",',
        '  WHATSAPP_TOKEN: "test-token",',
        '  expect(out).toEqual({ token: "[redacted]", authorization: "[redacted]", password: "p" });',
        '  const headers = { apikey: "k" };',
    ])
    _, data, _ = run(tmp_path, p)
    assert not [f for f in data["findings"] if f["rule"] == "CR-SECRET"], data["findings"]
    # a real-looking literal is still caught
    q = write_patch(tmp_path, "lib/pay.js", ['const STRIPE_SECRET = "sk_live_51H8x9ABCDEFGH123456";'], name="y.patch")
    _, data, _ = run(tmp_path, q)
    assert [f for f in data["findings"] if f["rule"] == "CR-SECRET"]
