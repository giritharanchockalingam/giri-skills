#!/usr/bin/env python3
"""Install the observability starter kit into a Next.js repo — without overwriting anything.

    python3 -I scripts/install.py --target <repo> [--dry-run] [--project <name>] \
        --report-json install-report.json --report-md install-report.md

Copies the assets to their conventional paths:
  assets/logger.ts            -> lib/logger.ts
  assets/logger-context.ts    -> lib/logger/context.ts
  assets/health-route.ts      -> app/api/health/route.ts
  assets/health-deep-route.ts -> app/api/health/deep/route.ts
  assets/alert-rules.yaml     -> ops/alerts.yaml
  assets/slo-starter.md       -> docs/observability.md
and appends every `process.env.X` the assets read to .env.example when missing (created if absent).
An existing file is never overwritten: identical content -> skipped; different -> written beside it
as `<file>.proposed` and listed for a manual merge. --dry-run writes nothing and reports what would
happen. The reports list written / skipped / proposed / env_added. Exit 1 on bad input. Stdlib.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
MAPPING = [
    ("logger.ts", "lib/logger.ts"),
    ("logger-context.ts", "lib/logger/context.ts"),
    ("health-route.ts", "app/api/health/route.ts"),
    ("health-deep-route.ts", "app/api/health/deep/route.ts"),
    ("alert-rules.yaml", "ops/alerts.yaml"),
    ("slo-starter.md", "docs/observability.md"),
]
ENV_RE = re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)")
PLATFORM_VARS = {"NODE_ENV", "VERCEL_ENV", "VERCEL_GIT_COMMIT_SHA"}  # set by the platform, not by .env
ENV_DOC = {
    "LOG_LEVEL": "debug|info|warn|error (default: info in production, debug elsewhere)",
    "LOG_PRETTY": "1 to pretty-print logs in local development",
    "SERVICE_NAME": "service label on every log line (default: web)",
    "HEALTH_CHECK_TOKEN": "bearer token required by /api/health/deep (generate: openssl rand -hex 32)",
    "NEXT_PUBLIC_SUPABASE_URL": "Supabase project URL",
}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Install logger, health routes, alert rules and SLO starter")
    ap.add_argument("--target", required=True, help="repo root (created if absent)")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--project", default="", help="project name for docs/observability.md (default: target dir name)")
    ap.add_argument("--report-json", default="install-report.json")
    ap.add_argument("--report-md", default="install-report.md")
    a = ap.parse_args()
    target = Path(a.target)
    if target.exists() and not target.is_dir():
        die(f"target is not a directory: {target}")
    missing = [src for src, _ in MAPPING if not (ASSETS / src).is_file()]
    if missing:
        die(f"assets missing: {missing}")
    if not a.dry_run:
        target.mkdir(parents=True, exist_ok=True)
    project = a.project or target.name

    report = {"target": str(target), "dry_run": a.dry_run, "written": [], "skipped": [], "proposed": [], "env_added": []}
    env_vars: set[str] = set()
    for src, rel in MAPPING:
        content = (ASSETS / src).read_text(encoding="utf-8").replace("{{PROJECT}}", project)
        env_vars |= set(ENV_RE.findall(content))
        dest = target / rel
        if dest.exists():
            if dest.read_text(encoding="utf-8", errors="replace") == content:
                report["skipped"].append({"path": rel, "reason": "identical"})
                continue
            proposed = dest.with_name(dest.name + ".proposed")
            if not a.dry_run:
                proposed.write_text(content, encoding="utf-8")
            report["proposed"].append({"path": rel, "proposed": rel + ".proposed", "reason": "exists with different content — merge manually"})
            continue
        if not a.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        report["written"].append(rel)

    env_file = target / ".env.example"
    env_existed = env_file.exists()
    existing = env_file.read_text(encoding="utf-8", errors="replace") if env_existed else ""
    present = {m.group(1) for m in re.finditer(r"^\s*([A-Z][A-Z0-9_]*)\s*=", existing, re.M)}
    to_add = sorted(v for v in env_vars if v not in PLATFORM_VARS and v not in present)
    if to_add:
        block = ([""] if existing else []) + ["# observability (added by observability-setup/scripts/install.py)"]
        block += [f"{v}=  # {ENV_DOC.get(v, 'see docs/observability.md')}" for v in to_add]
        if not a.dry_run:
            sep = "" if not existing or existing.endswith("\n") else "\n"
            env_file.write_text(existing + sep + "\n".join(block) + "\n", encoding="utf-8")
        report["env_added"] = to_add
        if not env_existed:
            report["written"].append(".env.example")

    rj, rm = Path(a.report_json), Path(a.report_md)
    rj.parent.mkdir(parents=True, exist_ok=True)
    rm.parent.mkdir(parents=True, exist_ok=True)
    rj.write_text(json.dumps(report, indent=2), encoding="utf-8")
    verb = "would be " if a.dry_run else ""
    lines = [f"# Observability install — {project}", "",
             f"**{len(report['written'])} file(s) {verb}written, {len(report['skipped'])} skipped (identical), "
             f"{len(report['proposed'])} proposed for manual merge, {len(report['env_added'])} env var(s) {verb}added.**"
             + (" Dry run — nothing was written." if a.dry_run else ""), "",
             "## Written", ""] + [f"- `{p}`" for p in report["written"]] + (["- none"] if not report["written"] else [])
    lines += ["", "## Skipped (already identical)", ""] + [f"- `{s['path']}`" for s in report["skipped"]] + (["- none"] if not report["skipped"] else [])
    lines += ["", "## Proposed (exists with different content — merge by hand)", ""]
    lines += [f"- `{p['path']}` → review `{p['proposed']}`" for p in report["proposed"]] + (["- none"] if not report["proposed"] else [])
    lines += ["", "## Env vars added to .env.example", ""] + [f"- `{v}` — {ENV_DOC.get(v, '')}" for v in report["env_added"]] + (["- none"] if not report["env_added"] else [])
    lines += ["", "## Next steps", "",
              "1. Wire `requestId` in `middleware.ts` and set ESLint `no-console: error`.",
              "2. Replace `console.*` calls with `lib/logger` in minimal diffs.",
              "3. Set `HEALTH_CHECK_TOKEN` in Vercel; curl both health routes on preview.",
              "4. Fill owners and runbook links in `ops/alerts.yaml`; translate to the monitoring vendor.",
              "5. Fill the SLO table in `docs/observability.md` from the critical journeys in SPEC."]
    rm.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{'dry-run: ' if a.dry_run else ''}{len(report['written'])} written, {len(report['skipped'])} skipped, "
          f"{len(report['proposed'])} proposed, env +{len(report['env_added'])} -> {rj}, {rm}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
