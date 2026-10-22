"""Tests for build/tech-debt-audit-runner/scripts/audit_debt.py (TD1–TD8, baseline, owners, gate, verify)."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/tech-debt-audit-runner"
SCRIPT = SK / "scripts/audit_debt.py"
FX = SK / "evals/fixtures"
TBD = "[TO BE BASELINED — owner: tech lead]"


def audit(tmp_path, target, *extra):
    f, r, p = tmp_path / "findings.csv", tmp_path / "report.md", tmp_path / "refactor-plan.md"
    res = run_script(SCRIPT, "--target", str(target), *extra, "--findings", str(f), "--report", str(r), "--plan", str(p))
    rows = list(csv.DictReader(f.open(encoding="utf-8"))) if f.exists() else []
    return res, rows, (r.read_text(encoding="utf-8") if r.exists() else ""), (p.read_text(encoding="utf-8") if p.exists() else "")


def by_rule(rows):
    out = {}
    for r in rows:
        out.setdefault(r["rule"], []).append(r)
    return out


def write(repo, rel: str, text: str):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_clean_repo_no_findings_gate_passes(tmp_path):
    res, rows, md, plan = audit(tmp_path, FX / "repo-clean")
    assert res.returncode == 0, res.stderr
    assert rows == []
    assert "Gate: PASS." in md and "## Summary" in md and "## Findings" in md and "## Rules" in md
    for section in ("## Summary", "## Architecture map", "## Priorities", "## Sequencing"):
        assert section in plan
    assert "| `lib/` | 3 | — | components, server, tests |" in plan   # foundation: imports nothing internal
    assert "| `app/` | 1 | components, server | — |" in plan


def test_violations_every_rule_fires_and_gate_fails(tmp_path):
    res, rows, md, plan = audit(tmp_path, FX / "repo-violations")
    assert res.returncode == 1 and "gate: FAIL" in res.stderr
    r = by_rule(rows)
    assert set(r) == {"TD1", "TD2", "TD3", "TD4", "TD5", "TD6", "TD7", "TD8"}
    assert r["TD1"][0]["file"] == "server/services/quote-service.ts" and "computeTotals() in lib/pricing.ts" in r["TD1"][0]["snippet"]
    assert {x["file"] for x in r["TD2"]} == {"components/legacy/ReportGrid.tsx", "lib/utils.ts"}
    assert all(x["severity"] == "medium" for x in r["TD2"])            # 413 lines / 14 exports: medium, not high
    assert r["TD3"][0]["file"] == "server/services/invoice-service.ts" and r["TD3"][0]["line"] == "2"
    assert "payment-service.ts -> server/services/invoice-service.ts" in r["TD3"][0]["snippet"]
    assert {(x["file"], x["line"]) for x in r["TD4"]} == {("app/reports/page.tsx", "2"), ("lib/analytics.ts", "2")}
    assert [x["snippet"] for x in r["TD5"]] == ["export mapLegacyBatch is never imported"]
    assert r["TD6"][0]["snippet"].startswith("2 TODO/FIXME/HACK") and r["TD6"][0]["severity"] == "low"
    assert r["TD7"][0]["snippet"] == "7 `any` usages (max 5)"
    assert {x["file"] for x in r["TD8"]} == {"lib/analytics.ts", "lib/legacy-mapper.ts", "lib/pricing.ts"}
    assert "Gate: FAIL (high-severity findings)" in md
    assert TBD in plan and "### Phase 1 — restore the dependency direction (3 item(s))" in plan


def test_framework_exports_and_namespace_imports_are_not_dead(tmp_path):
    _, rows, _, _ = audit(tmp_path, FX / "repo-violations")
    dead = {(r["file"], r["snippet"]) for r in rows if r["rule"] == "TD5"}
    assert not any(f.startswith("app/api/settle/route.ts") for f, _ in dead)     # POST / runtime are framework exports
    assert not any(f == "lib/utils.ts" for f, _ in dead)                           # tests import * as utils


def test_god_file_high_above_800_lines(tmp_path):
    repo = tmp_path / "repo"
    write(repo, "lib/huge.ts", "export const a = 1;\n" + "// filler\n" * 820)
    write(repo, "app/page.tsx", 'import { a } from "@/lib/huge";\nexport default function P() { return <p>{a}</p>; }\n')
    write(repo, "tests/huge.test.ts", 'import { a } from "@/lib/huge";\n')
    res, rows, md, _ = audit(tmp_path, repo)
    assert res.returncode == 1
    td2 = [r for r in rows if r["rule"] == "TD2"]
    assert len(td2) == 1 and td2[0]["severity"] == "high" and td2[0]["snippet"].startswith("821 lines")


def test_app_sibling_vs_ancestor_imports(tmp_path):
    repo = tmp_path / "repo"
    write(repo, "app/_shared/nav.tsx", "export function Nav() { return <nav />; }\n")
    write(repo, "app/a/page.tsx", 'import { Nav } from "../_shared/nav";\nimport { Local } from "./local";\nexport default function A() { return <Nav />; }\n')
    write(repo, "app/a/local.tsx", "export function Local() { return <i />; }\n")
    write(repo, "app/b/page.tsx", 'import { Local } from "../a/local";\nexport default function B() { return <Local />; }\n')
    res, rows, _, _ = audit(tmp_path, repo)
    td4 = [(r["file"], r["snippet"]) for r in rows if r["rule"] == "TD4"]
    assert td4 == [("app/b/page.tsx", "app/ imports a sibling route folder: ../a/local")]   # ancestor _shared and own folder are fine


def test_duplicate_needs_six_lines_and_two_files(tmp_path):
    repo = tmp_path / "repo"
    short = "export function f(x: number) {\n  const a = x + 1;\n  const b = a * 2;\n  return b;\n}\n"
    write(repo, "lib/one.ts", short)
    write(repo, "lib/two.ts", short.replace("function f", "function g"))
    write(repo, "tests/one.test.ts", 'import { f } from "@/lib/one";\nimport { g } from "@/lib/two";\n')
    write(repo, "tests/two.test.ts", "")
    _, rows, _, _ = audit(tmp_path, repo)
    assert not [r for r in rows if r["rule"] == "TD1"]
    long = "export function f(x: number) {\n" + "".join(f"  const v{i} = x + {i};\n" for i in range(6)) + "  return v5;\n}\n"
    write(repo, "lib/one.ts", long)
    write(repo, "lib/two.ts", long.replace("function f", "function   g").replace("  const", "    const"))   # whitespace differs
    _, rows, _, _ = audit(tmp_path, repo)
    td1 = [r for r in rows if r["rule"] == "TD1"]
    assert len(td1) == 1 and td1[0]["file"] == "lib/two.ts" and "g() duplicates f() in lib/one.ts (2 copies)" == td1[0]["snippet"]


def test_any_threshold_and_strings_comments_ignored(tmp_path):
    repo = tmp_path / "repo"
    body = "export function m(a: any, b: any, c: any, d: any, e: any): string {\n  // any any any in a comment\n  return 'any any' + String(a) + String(b) + String(c) + String(d) + String(e);\n}\n"
    write(repo, "lib/m.ts", body)
    write(repo, "tests/m.test.ts", 'import { m } from "@/lib/m";\n')
    _, rows, _, _ = audit(tmp_path, repo)
    assert not [r for r in rows if r["rule"] == "TD7"]                      # exactly 5: not over the threshold
    write(repo, "lib/m.ts", body.replace("): string", ", f: any): string"))
    _, rows, _, _ = audit(tmp_path, repo)
    assert [r["snippet"] for r in rows if r["rule"] == "TD7"] == ["6 `any` usages (max 5)"]


def test_baseline_known_new_resolved_and_file_level_match(tmp_path):
    res, rows, md, plan = audit(tmp_path, FX / "repo-violations", "--baseline", str(FX / "baseline-findings.csv"), "--owners", str(FX / "owners.csv"))
    assert res.returncode == 0, res.stderr
    status = {(r["rule"], r["file"]): r["status"] for r in rows}
    assert status[("TD3", "server/services/invoice-service.ts")] == "known"
    assert status[("TD2", "lib/utils.ts")] == "known"                      # snippet changed (61 -> 67 lines) but file-level rule matches
    assert status[("TD2", "components/legacy/ReportGrid.tsx")] == "new"
    assert status[("TD5", "lib/legacy-mapper.ts")] == "new"
    assert "7 new, 5 known from the baseline, 1 resolved" in md
    assert "- TD4 `lib/old-widget.ts` — lib/ imports components/: @/components/OldWidget" in md
    assert "Gate: PASS (no new high-severity findings; known debt listed below)" in md
    assert "| payments team lead |" in plan and "| platform team lead |" in plan
    assert "| `app/reports/page.tsx:2` | S | high | known | " + TBD + " |" in plan   # no owner prefix for app/


def test_baseline_new_high_still_fails(tmp_path):
    base = tmp_path / "base.csv"
    base.write_text("rule,file,line,snippet,severity,status\nTD4,lib/analytics.ts,2,lib/ imports components/: @/components/Chart,high,new\n", encoding="utf-8")
    res, rows, md, _ = audit(tmp_path, FX / "repo-violations", "--baseline", str(base))
    assert res.returncode == 1 and "2 new high-severity" in res.stderr
    assert "Gate: FAIL (new high-severity findings)" in md


def test_deterministic_two_runs_identical(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    audit(a, FX / "repo-violations", "--baseline", str(FX / "baseline-findings.csv"))
    audit(b, FX / "repo-violations", "--baseline", str(FX / "baseline-findings.csv"))
    for name in ("findings.csv", "report.md", "refactor-plan.md"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_malformed_inputs_clear_errors(tmp_path):
    res = run_script(SCRIPT, "--target", str(tmp_path / "nope"))
    assert res.returncode == 2 and "not a directory" in res.stderr
    empty = tmp_path / "empty"
    empty.mkdir()
    res = run_script(SCRIPT, "--target", str(empty))
    assert res.returncode == 2 and "no .ts/.tsx" in res.stderr
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    res = run_script(SCRIPT, "--target", str(FX / "repo-clean"), "--baseline", str(bad))
    assert res.returncode == 2 and "baseline lacks column(s)" in res.stderr
    res = run_script(SCRIPT, "--target", str(FX / "repo-clean"), "--owners", str(bad))
    assert res.returncode == 2 and "path_prefix,owner" in res.stderr


def test_verify_mode(tmp_path):
    _, _, _, _ = audit(tmp_path, FX / "repo-violations")
    assert run_script(SCRIPT, "--verify", str(tmp_path / "findings.csv")).returncode == 0
    broken = tmp_path / "broken.csv"
    broken.write_text("rule,file,line,snippet,severity,status\nTD3,x.ts,1,cycle,medium,new\n", encoding="utf-8")
    res = run_script(SCRIPT, "--verify", str(broken))
    assert res.returncode == 1 and "severity medium does not match TD3" in res.stderr


def test_plan_sections_and_phase_assignment(tmp_path):
    _, _, _, plan = audit(tmp_path, FX / "repo-violations")
    p1 = plan.split("### Phase 1")[1].split("### Phase 2")[0]
    p2 = plan.split("### Phase 2")[1].split("### Phase 3")[0]
    p4 = plan.split("### Phase 4")[1]
    assert "TD3 `server/services/invoice-service.ts:2`" in p1 and "TD4 `lib/analytics.ts:2`" in p1
    assert "TD2 `lib/utils.ts:1`" in p2
    assert "TD5 `lib/legacy-mapper.ts:10`" in p4 and "TD7 `lib/legacy-mapper.ts:2`" in p4 and "TD6 `server/services/payment-service.ts:4`" in p4
    assert plan.index("| high | new |") < plan.index("| low | new |")          # severity ordering in Priorities


# ---------------------------------------------------------------- brownfield: JavaScript Next.js, special files (TD5 regression)

def test_nextjs_special_files_js_not_dead_exports(tmp_path):
    """Regression: app/** special files (manifest/robots/sitemap/opengraph-image/twitter-image/icon/apple-icon/…), root
    middleware/instrumentation/*.config.* and evals/ produced TD5 on a JavaScript repo. Only the genuine dead export fires."""
    res, rows, md, plan = audit(tmp_path, FX / "repo-nextjs-special")
    assert res.returncode == 0, res.stderr
    assert [(r["rule"], r["file"], r["line"], r["snippet"]) for r in rows] == \
        [("TD5", "lib/legacy.js", "6", "export oldHelper is never imported")]
    assert "1 finding(s) in 26 audited file(s): 0 high, 1 medium, 0 low" in md and "Gate: PASS." in md
    assert "| `app/` | 17 | components, lib | — |" in plan                # every special file was scanned, none flagged
    assert "| `evals/` | 2 |" in plan                                      # evals/ is in the graph but not audited


def test_special_file_exclusion_list_is_exhaustive(tmp_path):
    """Each special-file stem, in .js/.jsx/.ts/.tsx, alone in app/ with a default export and the metadata exports:
    zero TD5. A non-special sibling with the same exports still fires."""
    stems = ["page", "layout", "template", "loading", "error", "global-error", "not-found", "default", "route",
             "manifest", "robots", "sitemap", "opengraph-image", "twitter-image", "icon", "apple-icon"]
    body = "export const alt = 'x';\nexport const size = { width: 1, height: 1 };\nexport const contentType = 'image/png';\n" \
           "export const metadata = {};\nexport async function generateStaticParams() { return []; }\n" \
           "export async function generateSitemaps() { return []; }\nexport default function X() { return null; }\n"
    repo = tmp_path / "repo"
    for i, (stem, ext) in enumerate((s, e) for s in stems for e in (".js", ".jsx", ".ts", ".tsx")):
        write(repo, f"app/r{i}/{stem}{ext}", body if stem != "route" else "export async function GET() { return null; }\n")
    write(repo, "app/r0/helpers.js", "export default function helper() { return 1; }\nexport const alt = 2;\n")
    write(repo, "middleware.js", "export function middleware() {}\nexport const config = { matcher: [] };\n")
    write(repo, "instrumentation.js", "export async function register() {}\nexport function onRequestError() {}\n")
    write(repo, "instrumentation-client.js", "export const onRouterTransitionStart = () => {};\n")
    write(repo, "next.config.mjs", "export default { reactStrictMode: true };\n")
    write(repo, "sentry.edge.config.js", "export const dsn = '';\n")
    write(repo, "tailwind.config.ts", "export default { content: [] };\n")
    write(repo, "evals/corpus.mjs", "export const CASES = [];\nexport default CASES;\n")
    write(repo, "tests/unit/dummy.test.js", "import { CASES } from '../../evals/corpus.mjs';\n")
    _, rows, _, _ = audit(tmp_path, repo)
    td5 = [(r["file"], r["snippet"]) for r in rows if r["rule"] == "TD5"]
    assert td5 == [("app/r0/helpers.js", "export default is never imported"), ("app/r0/helpers.js", "export alt is never imported")]


def test_js_and_jsx_audited_like_ts(tmp_path):
    """TD1/TD2/TD3/TD4/TD5/TD6/TD8 fire on .js/.jsx exactly as on .ts/.tsx; TD7 (`any`) is TypeScript-only by design."""
    repo = tmp_path / "repo"
    dup = "export function compute(x) {\n" + "".join(f"  const v{i} = x + {i};\n" for i in range(6)) + "  return v5;\n}\n"
    write(repo, "lib/pricing.js", dup)
    write(repo, "server/quote.js", dup.replace("compute", "quote") + 'import { b } from "./billing";\n')
    write(repo, "server/billing.js", 'import { quote } from "./quote";\nexport const b = 1;\nexport function unused() {}\n')
    write(repo, "lib/widget.jsx", 'import { Chart } from "@/components/Chart";\n// TODO: remove\nexport function W() { return <Chart />; }\n')
    write(repo, "components/Chart.jsx", "export function Chart() { return <svg />; }\n")
    write(repo, "lib/big.js", "export const a = 1;\n" + "// filler\n" * 420 + "const n = 1; /* any any any any any any any */\n")
    write(repo, "app/page.jsx", 'import { compute } from "@/lib/pricing";\nimport { W } from "@/lib/widget";\nimport { a } from "@/lib/big";\n'
                                'import { quote } from "@/server/quote";\nexport default function P() { return <W>{compute(a) + quote(1)}</W>; }\n')
    write(repo, "tests/unit/pricing.test.js", 'import { compute } from "../../lib/pricing";\n')
    res, rows, _, _ = audit(tmp_path, repo)
    assert res.returncode == 1
    r = by_rule(rows)
    assert r["TD1"][0]["file"] == "server/quote.js" and "compute() in lib/pricing.js" in r["TD1"][0]["snippet"]
    assert [x["file"] for x in r["TD2"]] == ["lib/big.js"]
    assert "server/billing.js -> server/quote.js" in r["TD3"][0]["snippet"]
    assert [(x["file"], x["snippet"]) for x in r["TD4"]] == [("lib/widget.jsx", "lib/ imports components/: @/components/Chart")]
    assert [(x["file"], x["snippet"]) for x in r["TD5"]] == [("server/billing.js", "export unused is never imported")]
    assert r["TD6"][0]["file"] == "lib/widget.jsx"
    assert "TD7" not in r
    assert {x["file"] for x in r["TD8"]} == {"lib/big.js", "lib/widget.jsx"}       # pricing.js has tests/unit/pricing.test.js


def test_baseline_snippet_whitespace_is_normalised_on_both_sides(tmp_path):
    """Regression (same defect as the lint scripts): a baseline snippet with a trailing space or doubled spaces
    still matches the live line-level finding, so an unchanged repo comes back fully `known`."""
    repo = tmp_path / "repo"
    write(repo, "lib/orders.ts", "import { x } from \"../app/orders/page\";\nexport const y = x;\n")
    write(repo, "app/orders/page.tsx", "export const x = 1;\nexport default function Page() { return null; }\n")
    first = tmp_path / "first"
    first.mkdir()
    res, rows, _, _ = audit(first, repo)
    td4 = [r for r in rows if r["rule"] == "TD4"]
    assert res.returncode == 1 and len(td4) == 1, res.stderr
    base = tmp_path / "base.csv"
    padded = td4[0]["snippet"].replace(" ", "  ") + " "
    base.write_text("rule,file,line,snippet,severity,status\n", encoding="utf-8")
    with base.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(["TD4", td4[0]["file"], td4[0]["line"], padded, "high", "new"])
    res, rows, md, _ = audit(tmp_path, repo, "--baseline", str(base))
    assert res.returncode == 0, res.stderr
    assert all(r["status"] == "known" for r in rows if r["rule"] == "TD4")
    assert "0 resolved" in md
