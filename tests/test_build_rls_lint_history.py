"""Brownfield ("existing") path of build/supabase-schema-rls: history replay and --applied-through."""
from __future__ import annotations

from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/supabase-schema-rls/scripts/rls_lint.py"
REPO = REPO_ROOT / "skills/build/supabase-schema-rls/evals/fixtures/repo-existing"
RB = "-- rollback: n/a (test)\n"


def mig(tmp_path: Path, files: dict[str, str]) -> Path:
    d = tmp_path / "migrations"
    d.mkdir()
    for name, sql in files.items():
        (d / name).write_text(sql, encoding="utf-8")
    return d


def lint(path, *extra):
    return run_script(SCRIPT, str(path), *extra)


def test_fixture_history_is_clean_once_applied_marked(tmp_path):
    r = lint(REPO / "supabase/migrations", "--client-dirs", "app", "components", "--root", str(REPO),
             "--applied-through", "0002_tenancy.sql")
    assert r.returncode == 0, r.stdout
    assert "0 findings, 0 errors" in r.stdout


def test_without_applied_through_the_legacy_rollback_gap_is_reported(tmp_path):
    r = lint(REPO / "supabase/migrations")
    assert r.returncode == 1 and "0001_init.sql:1: ERROR RLS007" in r.stdout


def test_applied_through_only_covers_older_files(tmp_path):
    d = mig(tmp_path, {"0001.sql": "create table public.t (id int);\nalter table public.t enable row level security;\n"
                                   "create policy p on public.t for select to authenticated using (id > 0);\n",
                       "0002.sql": "select 1;\n"})
    r = lint(d, "--applied-through", "0001.sql")
    assert "0001.sql:1: ERROR RLS007" not in r.stdout and "0002.sql:1: ERROR RLS007" in r.stdout


def test_dropped_policy_findings_are_withdrawn(tmp_path):
    d = mig(tmp_path, {
        "0001.sql": RB + "create table public.t (id int);\nalter table public.t enable row level security;\n"
                         "create policy open on public.t for all using (true);\n",
        "0002.sql": RB + "drop policy if exists open on public.t;\n"
                         "create policy reader on public.t for select to authenticated using (id > 0);\n"})
    r = lint(d)
    assert r.returncode == 0, r.stdout


def test_still_reported_when_not_dropped(tmp_path):
    d = mig(tmp_path, {"0001.sql": RB + "create table public.t (id int);\nalter table public.t enable row level security;\n"
                                        "create policy open on public.t for all using (true);\n"})
    r = lint(d)
    assert r.returncode == 1 and "RLS005" in r.stdout and "RLS004" in r.stdout


def test_dropping_the_only_policy_leaves_rls002(tmp_path):
    d = mig(tmp_path, {
        "0001.sql": RB + "create table public.t (id int);\nalter table public.t enable row level security;\n"
                         "create policy reader on public.t for select to authenticated using (id > 0);\n",
        "0002.sql": RB + "drop policy reader on public.t;\n"})
    r = lint(d)
    assert r.returncode == 1 and "RLS002" in r.stdout


def test_dropped_table_is_not_linted(tmp_path):
    d = mig(tmp_path, {"0001.sql": RB + "create table public.scratch (id int);\n",
                       "0002.sql": RB + "drop table if exists public.scratch;\n"})
    r = lint(d)
    assert r.returncode == 0, r.stdout


def test_recreated_table_does_not_inherit_old_policies(tmp_path):
    d = mig(tmp_path, {
        "0001.sql": RB + "create table public.t (id int);\nalter table public.t enable row level security;\n"
                         "create policy reader on public.t for select to authenticated using (id > 0);\n",
        "0002.sql": RB + "drop table public.t;\ncreate table public.t (id int);\n"
                         "alter table public.t enable row level security;\n"})
    r = lint(d)
    assert r.returncode == 1 and "RLS002" in r.stdout
