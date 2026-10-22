"""Tests for build/perf-review-runner/scripts/perf_review.py (PF1–PF10, baseline, gate, determinism)."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/perf-review-runner/scripts/perf_review.py"
FX = REPO_ROOT / "skills/build/perf-review-runner/evals/fixtures"
HEADER = "// fictional test file\n"


def review(tmp_path, target, *extra):
    f, r = tmp_path / "findings.csv", tmp_path / "report.md"
    res = run_script(SCRIPT, "--target", str(target), *extra, "--findings", str(f), "--report", str(r))
    rows = list(csv.DictReader(f.open(encoding="utf-8"))) if f.exists() else None
    return res, rows, (r.read_text(encoding="utf-8") if r.exists() else "")


def repo(tmp_path, files: dict[str, str]):
    root = tmp_path / "repo"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(HEADER + text, encoding="utf-8")
    return root


def rules(rows):
    return sorted({(r["rule"], r["file"], int(r["line"])) for r in rows})


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_clean_fixture_passes_with_no_findings(tmp_path):
    res, rows, md = review(tmp_path, FX / "repo-clean")
    assert res.returncode == 0, res.stderr
    assert rows == []
    assert "Gate: PASS" in md and "0 finding(s) in 6 file(s)" in md


def test_violations_fixture_fires_every_rule_and_fails_gate(tmp_path):
    res, rows, md = review(tmp_path, FX / "repo-violations")
    assert res.returncode == 1 and "gate: FAIL" in res.stderr
    assert {r["rule"] for r in rows} == {f"PF{i}" for i in range(1, 11)}
    assert sum(1 for r in rows if r["severity"] == "high") == 6
    assert {r["rule"] for r in rows if r["severity"] == "high"} == {"PF1", "PF3", "PF4"}
    assert all(r["file"] != "lib/format.ts" for r in rows)              # the clean helper
    assert "14 finding(s) in 5 file(s): 6 high, 8 medium" in md
    for section in ("## Summary", "## Findings", "## Rules"):
        assert section in md
    assert "Gate: FAIL" in md


def test_pf1_loop_and_callback_but_not_batched_in(tmp_path):
    root = repo(tmp_path, {"server/services/a.ts": (
        'export async function bad(ids: string[]) {\n'
        '  for (const id of ids) {\n'
        '    await supabase.from("items").select("id").eq("order_id", id).limit(10);\n'
        '  }\n'
        '  ids.forEach((id) => fetch(`/api/x/${id}`));\n'
        '}\n'
        'export async function good(ids: string[]) {\n'
        '  const { data } = await supabase.from("items").select("id, qty").in("order_id", ids).limit(1000);\n'
        '  return data;\n'
        '}\n')})
    res, rows, _ = review(tmp_path, root)
    assert res.returncode == 1
    assert rules(rows) == [("PF1", "server/services/a.ts", 4), ("PF1", "server/services/a.ts", 6)]   # no PF2 on the PF1 line


def test_pf2_await_in_loop_but_not_for_await_or_promise_all(tmp_path):
    root = repo(tmp_path, {"server/jobs/x.ts": (
        'export async function slow(ids: string[]) {\n'
        '  for (const id of ids) {\n'
        '    await send(id);\n'
        '  }\n'
        '}\n'
        'export async function stream(it: AsyncIterable<string>) {\n'
        '  for await (const chunk of it) {\n'
        '    await handle(chunk);\n'
        '  }\n'
        '}\n'
        'export async function fast(ids: string[]) {\n'
        '  await Promise.all(ids.map((id) => send(id)));\n'
        '}\n')})
    res, rows, _ = review(tmp_path, root)
    assert res.returncode == 0                                         # medium only
    assert rules(rows) == [("PF2", "server/jobs/x.ts", 4)]
    assert rows[0]["severity"] == "medium"


def test_pf3_pf4_select_star_and_bounds(tmp_path):
    root = repo(tmp_path, {"lib/db/q.ts": (
        'export const a = supabase.from("t").select("*").eq("x", 1);\n'                     # PF3 + PF4
        'export const b = supabase.from("t").select("id, rel(*)").limit(5);\n'              # PF3 only
        'export const c = supabase.from("t").select("id").order("id");\n'                   # PF4 only
        'export const d = supabase.from("t").select("id").range(0, 49);\n'                  # clean
        'export const e = supabase.from("t").select("id").eq("id", id).single();\n'         # clean
        'export const f = supabase.from("t").select("id", { count: "exact", head: true });\n'  # clean (count)
        'export const g = supabase.from("t").insert({ id: 1 }).select("*");\n'              # PF3 (write: no PF4)
        'export const h = supabase\n  .from("t")\n  .select("id")\n  .maybeSingle();\n')})   # clean, multi-line
    res, rows, _ = review(tmp_path, root)
    assert res.returncode == 1
    assert rules(rows) == [("PF3", "lib/db/q.ts", 2), ("PF3", "lib/db/q.ts", 3), ("PF3", "lib/db/q.ts", 8),
                           ("PF4", "lib/db/q.ts", 2), ("PF4", "lib/db/q.ts", 4)]


def test_pf5_pf6_client_only_and_memo_exempt(tmp_path):
    client = (
        '"use client";\n'
        'import { useEffect, useMemo, useState } from "react";\n'
        'export function Table({ rows, props2 }: { rows: Row[]; props2: Row[] }) {\n'
        '  const [q, setQ] = useState("");\n'
        '  useEffect(() => { fetch("/api/x").then(() => setQ("")); }, []);\n'
        '  useEffect(() => { document.title = q; }, [q]);\n'
        '  const memo = useMemo(() => rows.filter((r) => r.ok).sort(), [rows]);\n'
        '  const hot = props2.filter((r) => r.ok);\n'
        '  const local = [1, 2].sort();\n'
        '  return <div>{memo.length + hot.length + local.length}</div>;\n'
        '}\n')
    server = client.replace('"use client";\n', "")
    root = repo(tmp_path, {"components/Table.tsx": client, "components/ServerTable.tsx": server})
    res, rows, _ = review(tmp_path, root)
    assert res.returncode == 0
    assert rules(rows) == [("PF5", "components/Table.tsx", 6), ("PF6", "components/Table.tsx", 9)]


def test_pf7_pf8_pf9_pages_only(tmp_path):
    root = repo(tmp_path, {
        "app/shop/page.tsx": (
            'import { LineChart } from "recharts";\n'
            'import type { Foo } from "three";\n'
            'export default async function Page() {\n'
            '  const a = await fetch("https://x.test/a", { cache: "no-store" });\n'
            '  const b = await fetch("https://x.test/b", {\n    cache: "no-store",\n  });\n'
            '  return <img src="/a.png" alt="a" />;\n'
            '}\n'),
        "app/mixed/page.tsx": (
            'export default async function Page() {\n'
            '  const a = await fetch("https://x.test/a", { cache: "no-store" });\n'
            '  const b = await fetch("https://x.test/b", { next: { revalidate: 60 } });\n'
            '  return null;\n'
            '}\n'),
        "components/Chart.tsx": 'import { LineChart } from "recharts";\nexport const C = () => <img src="/b.png" alt="b" />;\n',
    })
    res, rows, _ = review(tmp_path, root)
    assert res.returncode == 0
    assert rules(rows) == [("PF7", "app/shop/page.tsx", 9), ("PF7", "components/Chart.tsx", 3),
                           ("PF8", "app/shop/page.tsx", 2),
                           ("PF9", "app/shop/page.tsx", 5), ("PF9", "app/shop/page.tsx", 6)]


def test_pf10_handler_body_only(tmp_path):
    root = repo(tmp_path, {
        "app/api/a/route.ts": (
            'import { readFileSync } from "node:fs";\n'
            'const cached = JSON.parse(readFileSync("data.json", "utf8"));\n'
            'export async function GET() {\n'
            '  const fresh = JSON.parse(readFileSync("data.json", "utf8"));\n'
            '  return Response.json({ n: cached.length + fresh.length });\n'
            '}\n'),
        "lib/load.ts": 'import { readFileSync } from "node:fs";\nexport const x = () => readFileSync("a", "utf8");\n',
    })
    res, rows, _ = review(tmp_path, root)
    assert res.returncode == 0
    assert rules(rows) == [("PF10", "app/api/a/route.ts", 5)]
    assert rows[0]["severity"] == "medium"


def test_baseline_marks_known_lists_resolved_and_passes(tmp_path):
    res, rows, md = review(tmp_path, FX / "repo-violations", "--baseline", str(FX / "baseline-findings.csv"))
    assert res.returncode == 0, res.stderr
    assert {r["status"] for r in rows if r["severity"] == "high"} == {"known"}
    assert {r["status"] for r in rows if r["severity"] == "medium"} == {"new"}
    assert "8 new, 6 known from the baseline, 1 resolved" in md
    assert "- PF4 `lib/legacy-report.ts`" in md and "## Baseline" in md
    assert "Gate: PASS (no new high-severity findings" in md


def test_baseline_new_high_still_fails_and_lines_may_move(tmp_path):
    root = repo(tmp_path, {"lib/db/q.ts": 'export const c = supabase.from("t").select("id").order("id");\n'})
    first = tmp_path / "first"
    first.mkdir()
    review(first, root)
    (root / "lib/db/q.ts").write_text(HEADER + "// moved\n" + 'export const c = supabase.from("t").select("id").order("id");\n'
                                      + 'export const z = supabase.from("u").select("*").limit(1);\n', encoding="utf-8")
    res, rows, md = review(tmp_path, root, "--baseline", str(first / "findings.csv"))
    assert res.returncode == 1 and "1 new high-severity" in res.stderr
    by = {(r["rule"], r["line"]): r["status"] for r in rows}
    assert by[("PF4", "3")] == "known" and by[("PF3", "4")] == "new"
    assert "Gate: FAIL (new high-severity findings)" in md


def test_deterministic_outputs(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    review(a, FX / "repo-violations")
    review(b, FX / "repo-violations")
    assert (a / "findings.csv").read_bytes() == (b / "findings.csv").read_bytes()
    assert (a / "report.md").read_bytes() == (b / "report.md").read_bytes()


def test_bad_inputs_give_clear_errors(tmp_path):
    res = run_script(SCRIPT, "--target", str(tmp_path / "missing"))
    assert res.returncode == 1 and "not a directory" in res.stderr
    empty = tmp_path / "empty"
    empty.mkdir()
    res = run_script(SCRIPT, "--target", str(empty), "--findings", str(tmp_path / "f.csv"), "--report", str(tmp_path / "r.md"))
    assert res.returncode == 1 and "no .ts/.tsx" in res.stderr
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    res, _, _ = review(tmp_path, FX / "repo-clean", "--baseline", str(bad))
    assert res.returncode == 1 and "baseline lacks column" in res.stderr
    res, _, _ = review(tmp_path, FX / "repo-clean", "--baseline", str(tmp_path / "none.csv"))
    assert res.returncode == 1 and "baseline not found" in res.stderr


def test_quiet_and_generated_dirs_skipped(tmp_path):
    root = repo(tmp_path, {"app/page.tsx": "export default function P() { return null }\n",
                           ".next/server/chunk.js": 'fetch("x"); for (;;) { await fetch("y"); }\n',
                           "node_modules/x/index.js": '<img src="a" />\n'})
    res = run_script(SCRIPT, "--target", str(root), "--findings", str(tmp_path / "f.csv"),
                     "--report", str(tmp_path / "r.md"), "--quiet")
    assert res.returncode == 0 and res.stdout.count("\n") == 1
    assert "in 1 file(s)" in (tmp_path / "r.md").read_text(encoding="utf-8")
