"""tenancy_audit --tenant-column: a schema keyed by workspace_id (or org_id …) is audited by its real key."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "skills/build/multi-tenant-saas-patterns/scripts/tenancy_audit.py"
SCHEMA = """-- fictional example schema (test)
create table public.workspaces (id uuid primary key, name text);
alter table public.workspaces enable row level security;
create policy w on public.workspaces for select using (true);
create table public.projects (id uuid primary key, workspace_id uuid not null references public.workspaces(id), name text);
create index projects_ws on public.projects (workspace_id, name);
alter table public.projects enable row level security;
create policy p on public.projects for select using (true);
create table public.settings (workspace_id uuid primary key references public.workspaces(id), theme text);
alter table public.settings enable row level security;
create policy s on public.settings for select using (true);
create table public.notes (id uuid primary key, body text);
alter table public.notes enable row level security;
create policy n on public.notes for select using (true);
"""


def run(tmp_path: Path, *args: str) -> tuple[int, str]:
    (tmp_path / "m").mkdir(exist_ok=True)
    (tmp_path / "m" / "0001.sql").write_text(SCHEMA)
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--migrations", str(tmp_path / "m"), "--out", str(tmp_path / "a.csv"),
                        "--report", str(tmp_path / "a.md"), *args], capture_output=True, text=True)
    return r.returncode, (tmp_path / "a.md").read_text() if (tmp_path / "a.md").exists() else r.stderr


def test_auto_detects_workspace_id_and_audits_by_it(tmp_path):
    code, md = run(tmp_path, "--tenant-column", "auto")
    assert "Tenancy key: `workspace_id` (detected from the schema)." in md
    assert code == 1                                                   # notes has no workspace_id: a real finding
    assert "| `notes` | no | yes | no | 1 | no | missing workspace_id; no index leading with workspace_id |" in md
    assert "| `projects` | yes | yes | yes | 1 | no | — |" in md        # composite index leading with the key
    assert "| `settings` | yes | yes | yes | 1 | no | — |" in md        # inline `workspace_id … primary key` counts
    assert "| `workspaces` | no | yes | no | 1 | yes | — |" in md       # the tenant root is exempt by definition


def test_default_is_unchanged_tenant_id(tmp_path):
    code, md = run(tmp_path)
    assert code == 1 and "Tenancy key: `tenant_id`." in md and "missing tenant_id" in md


def test_bad_column_name_is_refused(tmp_path):
    code, err = run(tmp_path, "--tenant-column", "x; drop")
    assert code == 1 and "bad --tenant-column" in err
