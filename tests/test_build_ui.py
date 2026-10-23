"""build/ui-component-quality — ui_lint.py: every rule fires on the violation fixture and not on the clean one,
baseline marks known debt, exit codes, determinism, malformed input, report sections."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/ui-component-quality"
SCRIPT = SK / "scripts/ui_lint.py"
FX = SK / "evals/fixtures"
ALL_RULES = {f"UI{i}" for i in range(1, 12)}


def lint(tmp_path, target, *extra):
    f, r, c = tmp_path / "findings.csv", tmp_path / "report.md", tmp_path / "a11y-checklist.md"
    res = run_script(SCRIPT, "--target", str(target), *extra, "--findings", str(f), "--report", str(r), "--checklist", str(c))
    rows = list(csv.DictReader(f.open(encoding="utf-8"))) if f.exists() else []
    return res, rows, (r.read_text(encoding="utf-8") if r.exists() else ""), (c.read_text(encoding="utf-8") if c.exists() else "")


def repo(tmp_path, name: str, src: str):
    d = tmp_path / "repo" / "components"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(src, encoding="utf-8")
    return tmp_path / "repo"


def test_clean_fixture_has_no_findings(tmp_path):
    res, rows, md, cl = lint(tmp_path, FX / "repo-clean")
    assert res.returncode == 0, res.stderr
    assert rows == [] and "Gate: PASS." in md and "0 finding(s) in 5 component file(s)" in md
    assert "| no findings |" in cl


def test_every_rule_fires_on_violations_and_gate_fails(tmp_path):
    res, rows, md, _ = lint(tmp_path, FX / "repo-violations")
    assert res.returncode == 1 and "6 high-severity" in res.stderr
    assert {r["rule"] for r in rows} == ALL_RULES
    assert all(r["status"] == "new" for r in rows)
    assert "14 finding(s) in 4 component file(s): 6 high, 5 medium, 3 low" in md and "Gate: FAIL" in md


def test_exact_locations_hand_verified(tmp_path):
    _, rows, _, _ = lint(tmp_path, FX / "repo-violations")
    where = {(r["rule"], r["file"], r["line"]) for r in rows}
    assert ("UI1", "components/features/orders/OrderTable.tsx", "19") in where
    assert ("UI2", "components/features/orders/OrderTable.tsx", "29") in where
    assert ("UI3", "app/(app)/orders/page.tsx", "9") in where
    assert ("UI4", "components/features/orders/OrderTable.tsx", "20") in where
    assert ("UI5", "components/features/orders/OrderDetail.tsx", "8") in where
    assert ("UI6", "components/features/orders/OrderTable.tsx", "23") in where
    assert ("UI7", "components/features/orders/OrderDetail.tsx", "10") in where
    assert ("UI8", "components/features/orders/OrderDetail.tsx", "12") in where
    assert ("UI9", "components/features/orders/OrderCard.tsx", "2") in where
    assert ("UI10", "components/features/orders/OrderTable.tsx", "24") in where
    assert ("UI11", "components/features/orders/OrderTable.tsx", "26") in where
    assert {r["severity"] for r in rows if r["rule"] in ("UI1", "UI2", "UI3", "UI4", "UI8")} == {"high"}
    assert {r["severity"] for r in rows if r["rule"] in ("UI9", "UI10", "UI11")} == {"low"}


def test_img_alt_and_spread_props(tmp_path):
    src = ('export function A() { return (<div>\n'
           '  <img src="/a.png" alt="" />\n'
           '  <img src="/b.png" />\n'
           '  <img {...imgProps} />\n'
           '  <Image src="/c.png" width={1} height={1} />\n'
           '</div>); }\n')
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "A.tsx", src))
    assert [(r["rule"], r["line"]) for r in rows] == [("UI1", "3"), ("UI1", "5")]


def test_icon_button_variants(tmp_path):
    src = ('export function B() { return (<div>\n'
           '  <button type="button"><Icon /></button>\n'
           '  <button type="button" aria-label="Save"><Icon /></button>\n'
           '  <button type="button"><Icon /><span className="sr-only">Save</span></button>\n'
           '  <button type="button">{t("save")}</button>\n'
           '  <button type="button">Save</button>\n'
           '</div>); }\n')
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "B.tsx", src))
    assert [(r["rule"], r["line"]) for r in rows] == [("UI2", "2")]


def test_clickable_div_requires_role_tabindex_and_key_handler(tmp_path):
    src = ('export function C() { return (<div>\n'
           '  <div onClick={go} role="button" tabIndex={0} onKeyDown={go}>ok</div>\n'
           '  <div onClick={go} role="button" tabIndex={0}>no key handler</div>\n'
           '  <span onClick={go}>bare</span>\n'
           '  <button onClick={go}>real button</button>\n'
           '</div>); }\n')
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "C.tsx", src))
    assert [(r["rule"], r["line"]) for r in rows] == [("UI3", "3"), ("UI3", "4")]


def test_input_label_association_forms(tmp_path):
    src = ('export function D() { return (<form>\n'
           '  <label htmlFor="a">A</label><input id="a" />\n'
           '  <label>B <input name="b" /></label>\n'
           '  <input aria-label="C" />\n'
           '  <input type="hidden" name="csrf" />\n'
           '  <select id="e"><option>1</option></select>\n'
           '  <textarea name="f" />\n'
           '  <input id={ids.g} /><label htmlFor={ids.g}>G</label>\n'
           '</form>); }\n')
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "D.tsx", src))
    assert [(r["rule"], r["line"]) for r in rows] == [("UI4", "6"), ("UI4", "7")]


def test_loading_and_empty_state_heuristics(tmp_path):
    with_states = ('"use client";\nimport { useEffect, useState } from "react";\n'
                   'export function E({ items }: { items: string[] }) {\n'
                   '  const [loading, setLoading] = useState(true);\n'
                   '  useEffect(() => { fetch("/api/x").then(() => setLoading(false)); }, []);\n'
                   '  if (loading) return <p aria-busy="true">Loading</p>;\n'
                   '  if (!items.length) return <p>Nothing here</p>;\n'
                   '  return <ul>{items.map((i) => <li key={i}>{i}</li>)}</ul>;\n}\n')
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "E.tsx", with_states))
    assert rows == []
    without = ('"use client";\nimport { useEffect, useState } from "react";\n'
               'export function F({ items }: { items: string[] }) {\n'
               '  const [data, setData] = useState([]);\n'
               '  useEffect(() => { fetch("/api/x").then((r) => r.json()).then(setData); }, []);\n'
               '  return <ul>{items.map((i) => <li key={i}>{i}</li>)}{NAV.map((n) => <li key={n}>{n}</li>)}</ul>;\n}\n')
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "F.tsx", without))
    assert sorted((r["rule"], r["line"]) for r in rows) == [("UI5", "5"), ("UI6", "6")]


def test_fixed_width_threshold_and_responsive_variants(tmp_path):
    src = ('export function G() { return (<div>\n'
           '  <div className="w-[600px]" />\n'
           '  <div className="w-[601px]" />\n'
           '  <div className="w-full lg:w-[900px]" />\n'
           '  <div className="min-w-[800px] max-w-full" />\n'
           '  <div style={{ width: 700, maxWidth: "100%" }} />\n'
           '  <div style={{ minWidth: 700 }} />\n'
           '  <div style={{ width: "640px" }} />\n'
           '</div>); }\n')
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "G.tsx", src))
    assert [(r["rule"], r["line"]) for r in rows] == [("UI7", "3"), ("UI7", "7"), ("UI7", "8")]


def test_prop_sprawl_counts_members_and_exempts_composition(tmp_path):
    nine = "".join(f"  p{i}: string;\n" for i in range(9))
    src = (f"interface BigProps {{\n{nine}}}\n"
           f"interface OkProps extends Shared {{\n{nine}}}\n"
           f"type AlsoOkProps = {{\n{nine}}} & Shared;\n"
           f"interface EightProps {{\n{''.join(f'  p{i}: string;' + chr(10) for i in range(8))}}}\n"
           "export function H(p: BigProps) { return <div>{p.p0}</div>; }\n")
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "H.tsx", src))
    assert [(r["rule"], r["line"]) for r in rows] == [("UI9", "1")]


def test_color_only_state_is_conservative(tmp_path):
    src = ('export function I({ ok, n }: { ok: boolean; n: number }) { return (<table><tbody><tr>\n'
           '  <td className={ok ? "text-green-600" : "text-red-600"}>{n}</td>\n'
           '  <td className={ok ? "text-green-600" : "text-red-600"}>{ok ? "Paid" : "Overdue"}</td>\n'
           '  <td className={ok ? "text-green-600" : "text-red-600"}><CheckIcon aria-label="Paid" />{n}</td>\n'
           '  <td className="text-green-600">{n}</td>\n'
           '</tr></tbody></table>); }\n')
    _, rows, _, _ = lint(tmp_path, repo(tmp_path, "I.tsx", src))
    assert [(r["rule"], r["line"]) for r in rows] == [("UI11", "2")]


def test_baseline_marks_known_resolved_and_gates_only_new_high(tmp_path):
    res, rows, md, _ = lint(tmp_path, FX / "repo-violations", "--baseline", str(FX / "baseline-findings.csv"))
    assert res.returncode == 0, res.stderr
    assert sum(r["status"] == "known" for r in rows) == 6 and sum(r["status"] == "new" for r in rows) == 8
    assert {r["severity"] for r in rows if r["status"] == "new"} == {"medium", "low"}
    assert "8 new, 6 known from the baseline, 1 resolved" in md
    assert "- UI1 `components/features/orders/CustomerAvatar.tsx`" in md
    assert "Gate: PASS (no new high-severity findings" in md
    base = tmp_path / "partial.csv"
    base.write_text('rule,file,line,snippet,severity\nUI1,components/features/orders/OrderTable.tsx,19,"<img src=""/logo.png"" />",high\n',
                    encoding="utf-8")
    res, rows, md, _ = lint(tmp_path, FX / "repo-violations", "--baseline", str(base))
    assert res.returncode == 1 and "5 new high-severity" in res.stderr and "Gate: FAIL (new high-severity findings)" in md


def test_deterministic_byte_identical(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    for d in (a, b):
        lint(d, FX / "repo-violations", "--baseline", str(FX / "baseline-findings.csv"))
    for name in ("findings.csv", "report.md", "a11y-checklist.md"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_malformed_input_clear_errors(tmp_path):
    res, _, _, _ = lint(tmp_path, tmp_path / "missing")
    assert res.returncode == 1 and "target is not a directory" in res.stderr
    empty = tmp_path / "empty"; empty.mkdir()
    (empty / "readme.md").write_text("x", encoding="utf-8")
    res, _, _, _ = lint(tmp_path, empty)
    assert res.returncode == 1 and "no React component files" in res.stderr
    bad = tmp_path / "bad.csv"; bad.write_text("a,b\n1,2\n", encoding="utf-8")
    res, _, _, _ = lint(tmp_path, FX / "repo-clean", "--baseline", str(bad))
    assert res.returncode == 1 and "baseline lacks column" in res.stderr
    res, _, _, _ = lint(tmp_path, FX / "repo-clean", "--baseline", str(tmp_path / "none.csv"))
    assert res.returncode == 1 and "baseline not found" in res.stderr


def test_report_and_checklist_sections(tmp_path):
    _, _, md, cl = lint(tmp_path, FX / "repo-violations")
    for h in ("## Summary", "## Findings", "## Rules"):
        assert h in md
    assert "## Baseline" not in md
    assert "## Covered by the rules (static)" in cl and "## Not checkable statically" in cl
    assert "| 2.5.8 | Target Size (Minimum) | AA |" in cl and "| 1.1.1 | Non-text Content | A | UI1 |" in cl
    assert "1 finding(s)" in cl.split("| 1.1.1 |")[1].split("\n")[0]


def test_skips_tests_stories_and_build_output(tmp_path):
    root = tmp_path / "repo"
    for rel in ("components/A.test.tsx", "components/A.stories.tsx", "node_modules/x/B.tsx", ".next/C.tsx", "__tests__/D.tsx"):
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('export const X = () => <img src="/x.png" />;\n', encoding="utf-8")
    (root / "components/Ok.tsx").write_text('export const Ok = () => <img src="/x.png" alt="ok" />;\n', encoding="utf-8")
    res, rows, md, _ = lint(tmp_path, root)
    assert res.returncode == 0 and rows == [] and "in 1 component file(s)" in md


# --- brownfield: JavaScript Next.js repos write JSX inside .js files (regression for "no .tsx/.jsx component files") ---

def test_js_fixture_scans_jsx_js_files_and_skips_plain_js(tmp_path):
    res, rows, md, cl = lint(tmp_path, FX / "repo-js")
    assert res.returncode == 1 and "6 high-severity" in res.stderr, res.stderr
    assert "no React component files" not in res.stderr
    assert {r["rule"] for r in rows} == ALL_RULES - {"UI9"}  # UI9 needs a Props type; plain JS has none
    assert "12 finding(s) in 4 component file(s): 6 high, 4 medium, 2 low" in md and "Gate: FAIL" in md
    files = {r["file"] for r in rows}
    assert files == {"components/features/orders/OrderTable.js", "components/features/orders/OrderDetail.js",
                     "app/(app)/orders/page.js"}
    # the plain .js utility, the route handler, middleware and config are never scanned
    assert not any(f.startswith(("lib/", "app/api/")) or f in ("middleware.js", "next.config.js") for f in files)
    where = {(r["rule"], r["file"], r["line"]) for r in rows}
    assert ("UI1", "components/features/orders/OrderTable.js", "11") in where
    assert ("UI2", "components/features/orders/OrderTable.js", "21") in where
    assert ("UI3", "app/(app)/orders/page.js", "9") in where
    assert ("UI4", "components/features/orders/OrderTable.js", "12") in where
    assert ("UI5", "components/features/orders/OrderDetail.js", "9") in where
    assert ("UI8", "components/features/orders/OrderDetail.js", "14") in where
    assert "6 finding(s)" not in cl.split("| 1.1.1 |")[1].split("\n")[0]


def test_js_detection_is_conservative(tmp_path):
    root = tmp_path / "repo"
    cases = {
        # scanned: JSX evidence
        "components/A.js": 'export function A() {\n  return (\n    <img src="/a.png" />\n  );\n}\n',
        "components/B.js": 'export const B = () => <img src="/b.png" />;\n',
        "components/C.js": 'import { useState } from "react";\nexport function C() {\n  const el = <img src="/c.png" />;\n  return el;\n}\n',
        "app/loading.js": 'export default function L() {\n  return (<><img src="/l.png" /></>);\n}\n',
        "components/D.ts": 'export function D() {\n  return <img src="/d.png" />;\n}\n',
        # not scanned: no JSX — comparisons, HTML strings, hooks-only, next imports, route handlers, tests, configs
        "lib/util.js": 'export const lt = (a, b) => a < b;\nexport const html = `<img src="/x.png"><input placeholder="x">`;\n',
        "lib/hook.js": 'import { useEffect } from "react";\nexport function useX() { useEffect(() => {}, []); return null; }\n',
        "app/api/x/route.js": 'import { NextResponse } from "next/server";\nexport function GET() { return NextResponse.json({ img: "<img src=\'/x.png\'>" }); }\n',
        "middleware.js": 'import { NextResponse } from "next/server";\nexport function middleware() { return NextResponse.next(); }\n',
        "components/A.test.js": 'export function T() { return <img src="/t.png" />; }\n',
        "components/A.spec.js": 'export function T() { return <img src="/t.png" />; }\n',
        "types.d.ts": 'declare module "x";\n',
        "next.config.js": 'module.exports = { reactStrictMode: true };\n',
    }
    for rel, src in cases.items():
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")
    res, rows, md, _ = lint(tmp_path, root)
    assert res.returncode == 1
    assert sorted(r["file"] for r in rows) == ["app/loading.js", "components/A.js", "components/B.js",
                                                "components/C.js", "components/D.ts"]
    assert {r["rule"] for r in rows} == {"UI1"} and "in 5 component file(s)" in md


def test_js_only_repo_without_jsx_reports_clear_error(tmp_path):
    root = tmp_path / "repo"
    (root / "lib").mkdir(parents=True)
    (root / "lib/a.js").write_text("export const a = 1;\n", encoding="utf-8")
    (root / "api.ts").write_text("export const b = (x: number) => x < 2;\n", encoding="utf-8")
    res, _, _, _ = lint(tmp_path, root)
    assert res.returncode == 1 and "no React component files" in res.stderr and ".js/.ts files containing JSX" in res.stderr


def test_snippet_cut_at_width_with_trailing_space_still_matches_unchanged_file(tmp_path):
    """Regression: the snippet is cut to 120 chars after stripping, so it can end in a space; the baseline CSV
    round-trip strips it. An unchanged file must come back fully `known` (both sides normalised the same way)."""
    line = 'return <img src="/a.png" className="'.ljust(119, "x") + ' h-4" />;'   # char 120 is a space
    root = repo(tmp_path, "Logo.tsx", f"export function Logo() {{\n  {line}\n}}\n")
    first = tmp_path / "first"
    first.mkdir()
    res, rows, _, _ = lint(first, root)
    assert res.returncode == 1 and [r["rule"] for r in rows] == ["UI1"] and rows[0]["snippet"].endswith(" ")
    res, rows, md, _ = lint(tmp_path, root, "--baseline", str(first / "findings.csv"))
    assert res.returncode == 0, res.stderr
    assert [r["status"] for r in rows] == ["known"] and "0 new, 1 known from the baseline, 0 resolved" in md
