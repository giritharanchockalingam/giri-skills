"""Tests for build/supabase-schema-rls/scripts/rls_lint.py."""
from __future__ import annotations

from pathlib import Path

from conftest import run_script

SCRIPT = "skills/build/supabase-schema-rls/scripts/rls_lint.py"

GOOD_SQL = """-- rollback: drop policy "owners_read_own" on public.orders;
create table public.orders (id bigint primary key, owner_id uuid);
alter table public.orders enable row level security;
create policy "owners_read_own" on public.orders for select to authenticated using (auth.uid() = owner_id);
"""

# Missing the required `-- rollback:` block -> RLS007 (error level).
BAD_SQL = "create table public.orders (id bigint primary key);\n"


def _migrations(tmp_path: Path, files: dict[str, str]) -> Path:
    d = tmp_path / "migrations"
    d.mkdir()
    for name, sql in files.items():
        (d / name).write_text(sql, encoding="utf-8")
    return d


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_clean_migration(tmp_path):
    d = _migrations(tmp_path, {"001_orders.sql": GOOD_SQL})
    r = run_script(SCRIPT, str(d))
    assert r.returncode == 0, r.stdout
    assert "0 errors" in r.stdout


def test_missing_rollback_is_error(tmp_path):
    d = _migrations(tmp_path, {"001_orders.sql": BAD_SQL})
    r = run_script(SCRIPT, str(d))
    assert r.returncode == 1
    assert "RLS007" in r.stdout


def test_warn_only_downgrades_errors(tmp_path):
    d = _migrations(tmp_path, {"001_orders.sql": BAD_SQL})
    r = run_script(SCRIPT, "--warn-only", str(d))
    assert r.returncode == 0


def test_not_a_directory(tmp_path):
    f = tmp_path / "not-a-dir.sql"
    f.write_text("select 1;\n", encoding="utf-8")
    r = run_script(SCRIPT, str(f))
    assert r.returncode == 2
