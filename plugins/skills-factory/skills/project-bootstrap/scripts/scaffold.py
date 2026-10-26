#!/usr/bin/env python3
"""scaffold.py — write the docs/ADR/CI skeleton into a target directory.

Idempotent: never overwrites an existing file. Re-running reports 0 writes.
Existing repo: every kept Markdown file is read and compared with its template's `##` sections; the
sections it lacks are reported as gaps (`gap    <file>: missing sections — A, B`) for a by-hand merge.
--report writes the same as JSON {target, written[], kept[], gaps[{path, missing[]}]}.
Stdlib only. Run offline: python3 -I scaffold.py --target <dir> --name "<project>" [--multi-tenant] [--dry-run] [--report r.json]

Templates are read from ../assets relative to this script.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
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
| Deciders | [TO BE BASELINED — owner: Tech lead] |

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


def section_names(markdown: str) -> list[str]:
    """`##` headings with numbering and a trailing parenthetical removed: '## 1. Purpose (one paragraph)' -> 'Purpose'."""
    out = []
    for ln in markdown.splitlines():
        m = re.match(r"^##\s+(.*)$", ln)
        if not m:
            continue
        name = re.sub(r"^\d+(\.\d+)*\.?\s+", "", m.group(1)).strip()
        name = re.sub(r"\s*\(.*\)\s*$", "", name).strip()
        if name:
            out.append(name)
    return out


def missing_sections(existing: str, template: str) -> list[str]:
    """Template sections with no matching heading in the existing file (case-insensitive; a match is one name
    containing the other, so '## Users' covers 'Users and jobs to be done')."""
    heads = [h.lower() for h in section_names(existing)]
    return [s for s in section_names(template) if not any(s.lower() in h or (len(h) >= 4 and h in s.lower()) for h in heads)]


def render(text: str, name: str, tenancy: str) -> str:
    today = _dt.date.today().isoformat()
    return (
        text.replace("{{PROJECT_NAME}}", name)
        .replace("{{DATE}}", today)
        .replace("{{TENANCY}}", tenancy)
        .replace("{{PURPOSE}}", "[TO BE BASELINED — owner: Tech lead]")
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
    ap.add_argument("--report", default="", help="also write written/kept/gaps as JSON here")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        if args.dry_run:
            print(f"would create dir {target}")
        else:
            target.mkdir(parents=True)

    written = skipped = 0
    report = {"target": str(target), "dry_run": args.dry_run, "written": [], "kept": [], "gaps": []}
    for path, content in plan(target, args.name, args.multi_tenant):
        rel = path.relative_to(target).as_posix()
        if path.exists():
            skipped += 1
            report["kept"].append(rel)
            print(f"keep   {rel}")
            if path.suffix == ".md":
                miss = missing_sections(path.read_text(encoding="utf-8", errors="replace"), content)
                if miss:
                    report["gaps"].append({"path": rel, "missing": miss})
                    print(f"gap    {rel}: missing sections — {', '.join(miss)}")
            continue
        written += 1
        report["written"].append(rel)
        print(f"{'would write' if args.dry_run else 'write '} {path.relative_to(target)}")
        if not args.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    print(f"\n{'dry-run: ' if args.dry_run else ''}{written} written, {skipped} kept (never overwritten)"
          + (f", {len(report['gaps'])} kept file(s) with section gaps to merge by hand" if report["gaps"] else ""))
    if args.report:
        rp = Path(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
