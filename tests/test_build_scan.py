"""Tests for build/security-review/scripts/scan.py."""
from __future__ import annotations

import csv

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/security-review/scripts/scan.py"
FX = REPO_ROOT / "skills/build/security-review/evals/fixtures"


def run(tmp_path, *args):
    f, r = tmp_path / "findings.csv", tmp_path / "review.md"
    res = run_script(SCRIPT, *args, "--findings", str(f), "--report", str(r))
    rows = list(csv.DictReader(f.open(encoding="utf-8"))) if f.exists() else None
    return res, rows, r


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_risky_diff_findings(tmp_path):
    res, rows, report = run(tmp_path, "--diff", str(FX / "change-risky.patch"))
    assert res.returncode == 0, res.stderr          # scan writes; the gate is a separate call
    cats = {(r["category"], r["file"], r["line"]) for r in rows}
    assert ("secrets", "app/api/admin/route.ts", "3") in cats
    assert ("rls-bypass", "app/api/admin/route.ts", "6") in cats
    assert ("injection", "server/actions/export-invoices.ts", "5") in cats
    assert ("authz", "server/actions/export-invoices.ts", "4") in cats
    assert ("ssrf", "server/actions/export-invoices.ts", "10") in cats
    assert ("xss", "components/Preview.tsx", "2") in cats
    secret = next(r for r in rows if r["category"] == "secrets")
    assert "[redacted]" in secret["evidence"] and "FAKEFAKE" not in secret["evidence"]
    assert rows[0]["id"] == "F01" and rows[0]["severity"] == "critical"   # sorted worst first
    assert all(r["recommendation"] for r in rows)
    text = report.read_text(encoding="utf-8")
    assert "Scanner verdict: BLOCK" in text and "## Findings" in text and "## Method and limits" in text


def test_clean_diff_no_findings(tmp_path):
    res, rows, report = run(tmp_path, "--diff", str(FX / "change-clean.patch"))
    assert res.returncode == 0, res.stderr
    assert rows == []
    assert "Scanner verdict: MERGE" in report.read_text(encoding="utf-8")


def test_gate(tmp_path):
    run(tmp_path, "--diff", str(FX / "change-risky.patch"))
    r = run_script(SCRIPT, "--gate", str(tmp_path / "findings.csv"))
    assert r.returncode == 1 and "BLOCK" in r.stderr
    run(tmp_path, "--diff", str(FX / "change-clean.patch"))
    assert run_script(SCRIPT, "--gate", str(tmp_path / "findings.csv")).returncode == 0
    assert run_script(SCRIPT, "--gate", str(tmp_path / "nope.csv")).returncode == 1


def test_target_mode_scans_repo(tmp_path):
    repo = tmp_path / "repo" / "server" / "actions"
    repo.mkdir(parents=True)
    (repo / "a.ts").write_text('"use server";\nexport async function go(url: string) { return fetch(url); }\n', encoding="utf-8")
    (repo / "ok.ts").write_text('"use server";\nimport { requireUser } from "@/lib/auth";\n'
                                'export async function fine() { await requireUser(); return fetch("https://api.example.com/x"); }\n', encoding="utf-8")
    res, rows, _ = run(tmp_path, "--target", str(tmp_path / "repo"))
    assert res.returncode == 0, res.stderr
    assert sorted((r["category"], r["file"]) for r in rows) == [("authz", "server/actions/a.ts"), ("ssrf", "server/actions/a.ts")]


def test_bad_input_exits_1(tmp_path):
    assert run_script(SCRIPT, "--findings", str(tmp_path / "f.csv")).returncode == 1
    assert run_script(SCRIPT, "--diff", str(tmp_path / "missing.patch")).returncode == 1
    bad = tmp_path / "bad.patch"
    bad.write_text("not a diff\n", encoding="utf-8")
    assert run_script(SCRIPT, "--diff", str(bad), "--findings", str(tmp_path / "f.csv")).returncode == 1


def test_rls_allow_marker_is_a_reasoned_exception_to_rls_bypass(tmp_path):
    """The observability kit's deep health route calls createAdminClient() in a handler, read-only, with the marker
    rls_lint.py honours (`// rls-lint: allow — <reason>`); the scan accepts the marked line and flags an unmarked one."""
    repo = tmp_path / "repo"
    (repo / "app/api/health/deep").mkdir(parents=True)
    (repo / "app/api/admin").mkdir(parents=True)
    (repo / "app/api/health/deep/route.ts").write_text(
        'import { createAdminClient } from "@/lib/supabase/admin";\n'
        'export async function GET() {\n'
        '  const admin = createAdminClient(); // rls-lint: allow — health check only, read-only\n'
        '  return Response.json({ ok: !(await admin.rpc("health_ping")).error });\n}\n', encoding="utf-8")
    (repo / "app/api/admin/route.ts").write_text(
        'import { createAdminClient } from "@/lib/supabase/admin";\n'
        'export async function GET() {\n  const admin = createAdminClient();\n  return Response.json(await admin.from("users").select("*"));\n}\n', encoding="utf-8")
    res, rows, _ = run(tmp_path, "--target", str(repo))
    assert res.returncode == 0, res.stderr
    bypass = {(r["file"], r["line"]) for r in rows if r["category"] == "rls-bypass"}
    assert bypass == {("app/api/admin/route.ts", "3")}
