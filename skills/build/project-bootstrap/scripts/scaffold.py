#!/usr/bin/env python3
"""scaffold.py — write the docs/ADR/CI skeleton into a target directory.

Idempotent: never overwrites an existing file. Re-running reports 0 writes.
Stdlib only. Run offline: python3 -I scaffold.py --target <dir> --name "<project>" [--multi-tenant] [--dry-run]

Templates are read from ../assets relative to this script.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# (template relative to assets/, destination relative to target)
FILES: list[tuple[str, str]] = [
    ("SPEC.md", "docs/SPEC.md"),
    ("CLAUDE.md", "CLAUDE.md"),
    ("HANDOFF.md", "docs/HANDOFF.md"),
    ("adr-template.md", "docs/adr/0000-template.md"),
    ("env.example", ".env.example"),
    ("CODEOWNERS", ".github/CODEOWNERS"),
    ("pull_request_template.md", ".github/pull_request_template.md"),
    ("workflows/ci.yml", ".github/workflows/ci.yml"),
    ("workflows/preview.yml", ".github/workflows/preview.yml"),
    ("workflows/prod.yml", ".github/workflows/prod.yml"),
]

STACK_ADR = """# ADR-0001: Default stack — Next.js App Router, Supabase, Vercel, GitHub Actions

| Field | Value |
|---|---|
| Status | Accepted |
| Date | {date} |
| Deciders | [TO BE BASELINED — owner: ___] |

## Context
{name} needs a web application with authenticated users, relational data{tenancy_ctx}, preview environments per change, and a release gate before production. The team standard (shared/stack-conventions.md) is Next.js + Supabase + Vercel + GitHub Actions.

## Decision
Adopt the standard stack without deviation unless listed below.

| Deviation | Reason | Owner |
|---|---|---|
| none | | |

## Options considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Standard stack (chosen) | team fluency, RLS-based isolation, preview per PR, zero-ops hosting | vendor coupling to Supabase/Vercel | chosen |
| Custom Node API + managed Postgres | full control | ops burden, no RLS by default, slower to first release | rejected |
| Serverless on GCP (Cloud Run + Cloud SQL) | enterprise cloud alignment | more infra code, slower preview envs | rejected for v1; revisit if GCP services are required |

## Consequences
| Type | Consequence | Mitigation (owner) |
|---|---|---|
| Positive | Preview per PR, RLS enforced isolation, tag-gated prod | — |
| Negative | Supabase/Vercel lock-in | Keep data access behind `lib/db`; migrations in repo |
| Neutral | Python for scripts/agents only | ruff + pytest in CI |

## Compliance / verification
- `rls_lint.py` in CI; `.env.example` contract parsed by `lib/env.ts`; prod deploys only via `prod.yml` on tag.
"""


def render(text: str, name: str, tenancy: str) -> str:
    today = _dt.date.today().isoformat()
    return (
        text.replace("{{PROJECT_NAME}}", name)
        .replace("{{DATE}}", today)
        .replace("{{TENANCY}}", tenancy)
        .replace("{{PURPOSE}}", "[TO BE BASELINED — owner: ___]")
        .replace("{{NUMBER}}", "NNNN")
        .replace("{{TITLE}}", "Title")
    )


def plan(target: Path, name: str, multi_tenant: bool) -> list[tuple[Path, str]]:
    tenancy = "multi-tenant (tenant_id on every scoped table; RLS)" if multi_tenant else "single-tenant"
    out: list[tuple[Path, str]] = []
    for src, dst in FILES:
        tpl = ASSETS / src
        if not tpl.exists():
            print(f"error: template missing: {tpl}", file=sys.stderr)
            sys.exit(2)
        out.append((target / dst, render(tpl.read_text(encoding="utf-8"), name, tenancy)))
    adr = STACK_ADR.format(
        date=_dt.date.today().isoformat(),
        name=name,
        tenancy_ctx=" with tenant isolation" if multi_tenant else "",
    )
    out.append((target / "docs/adr/0001-stack.md", adr))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Idempotent project scaffold (docs/ADR/CI).")
    ap.add_argument("--target", required=True, help="target project directory")
    ap.add_argument("--name", required=True, help="project name")
    ap.add_argument("--multi-tenant", action="store_true", help="mark tenancy as multi-tenant in SPEC/ADR")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        if args.dry_run:
            print(f"would create dir {target}")
        else:
            target.mkdir(parents=True)

    written = skipped = 0
    for path, content in plan(target, args.name, args.multi_tenant):
        if path.exists():
            skipped += 1
            print(f"keep   {path.relative_to(target)}")
            continue
        written += 1
        print(f"{'would write' if args.dry_run else 'write '} {path.relative_to(target)}")
        if not args.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    print(f"\n{'dry-run: ' if args.dry_run else ''}{written} written, {skipped} kept (never overwritten)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
