#!/usr/bin/env python3
"""Install the three GitHub Actions workflows and validate their structure.

    python3 -I scripts/install_ci.py --target <repo> --report-json ci-report.json --report-md ci-report.md

For ci.yml, preview.yml and prod.yml: write the asset to .github/workflows/<name>.yml when absent
(action=written); never overwrite an existing one (action=kept). Then validate every workflow with
a minimal structural check (no YAML library): a top-level `on:` and `jobs:` block, and the required
job names per workflow:
  ci.yml       lint-typecheck-test, rls-lint, secrets-scan
  preview.yml  deploy-preview, e2e
  prod.yml     verify-tag, migrate-staging, migrate-prod, deploy-prod
A `concurrency:` block is recommended and reported as a warning when absent. Writes ci-report.json
(per workflow: workflow, action, path, valid, jobs_found, missing_jobs, warnings) and ci-report.md.
Exit 1 on bad input or when any required job is missing / a workflow is structurally invalid —
the branch-protection check names depend on those job names. Stdlib, offline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets" / "workflows"
REQUIRED = {
    "ci.yml": ["lint-typecheck-test", "rls-lint", "secrets-scan"],
    "preview.yml": ["deploy-preview", "e2e"],
    "prod.yml": ["verify-tag", "migrate-staging", "migrate-prod", "deploy-prod"],
}
TOP_KEY = re.compile(r"^([A-Za-z_][\w-]*):", re.M)


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def validate(text: str, required: list[str]) -> dict:
    top = TOP_KEY.findall(text)
    has_on = bool(re.search(r"^(?:\"on\"|'on'|on):", text, re.M))
    has_jobs = "jobs" in top
    jobs = []
    m = re.search(r"^jobs:\s*$", text, re.M)
    if m:
        for ln in text[m.end():].splitlines():
            if ln and not ln.startswith((" ", "\t", "#")):
                break  # next top-level key
            jm = re.match(r"^  ([A-Za-z_][\w-]*):\s*(?:#.*)?$", ln)
            if jm:
                jobs.append(jm.group(1))
    missing = [j for j in required if j not in jobs]
    warnings = []
    if "concurrency:" not in text:
        warnings.append("no concurrency block")
    if "timeout-minutes" not in text:
        warnings.append("no timeout-minutes on jobs")
    problems = []
    if not has_on:
        problems.append("missing top-level on:")
    if not has_jobs:
        problems.append("missing top-level jobs:")
    return {"valid": not problems, "problems": problems, "jobs_found": jobs, "missing_jobs": missing, "warnings": warnings}


def main() -> int:
    ap = argparse.ArgumentParser(description="Install and validate ci/preview/prod GitHub Actions workflows")
    ap.add_argument("--target", required=True, help="repo root (created if absent)")
    ap.add_argument("--report-json", default="ci-report.json")
    ap.add_argument("--report-md", default="ci-report.md")
    a = ap.parse_args()
    target = Path(a.target)
    if target.exists() and not target.is_dir():
        die(f"target is not a directory: {target}")
    missing_assets = [n for n in REQUIRED if not (ASSETS / n).is_file()]
    if missing_assets:
        die(f"workflow assets missing: {missing_assets}")
    wf_dir = target / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for name, required in REQUIRED.items():
        dest = wf_dir / name
        if dest.exists():
            action = "kept"
        else:
            dest.write_text((ASSETS / name).read_text(encoding="utf-8"), encoding="utf-8")
            action = "written"
        res = validate(dest.read_text(encoding="utf-8", errors="replace"), required)
        rows.append({"workflow": name, "action": action, "path": f".github/workflows/{name}", **res})

    failed = [r for r in rows if not r["valid"] or r["missing_jobs"]]
    report = {"target": str(target), "ok": not failed, "workflows": rows,
              "required_checks": ["ci / lint-typecheck-test", "ci / rls-lint", "preview / e2e"]}
    rj, rm = Path(a.report_json), Path(a.report_md)
    rj.parent.mkdir(parents=True, exist_ok=True)
    rm.parent.mkdir(parents=True, exist_ok=True)
    rj.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [f"# CI install — {target.name}", "",
             f"**{sum(r['action'] == 'written' for r in rows)} workflow(s) written, "
             f"{sum(r['action'] == 'kept' for r in rows)} kept as-is; "
             + ("gate: PASS — every required job present." if not failed else
                f"gate: FAIL — {len(failed)} workflow(s) missing required jobs or malformed.") + "**", "",
             "## Workflows", "", "| Workflow | Action | Valid | Jobs found | Missing jobs | Warnings |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['path']}` | {r['action']} | {'yes' if r['valid'] else 'no: ' + '; '.join(r['problems'])} | "
                     f"{', '.join(r['jobs_found']) or '—'} | {', '.join(r['missing_jobs']) or '—'} | {'; '.join(r['warnings']) or '—'} |")
    lines += ["", "## Branch protection (required checks)", ""] + [f"- `{c}`" for c in report["required_checks"]]
    lines += ["", "## Next steps", "",
              "1. Confirm every `npm run <script>` the workflows call exists in package.json.",
              "2. `gh secret set` for VERCEL_TOKEN, VERCEL_ORG_ID, VERCEL_PROJECT_ID, SUPABASE_ACCESS_TOKEN, SUPABASE_DB_PASSWORD (values never in chat).",
              "3. Create GitHub Environments `staging` and `production` (required reviewers on production).",
              "4. Push a `chore/ci` branch and watch the run; check names must match branch protection.",
              "5. Kept workflows: diff against `assets/workflows/` and merge missing stages by hand."]
    rm.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for r in rows:
        print(f"{r['workflow']:12} {r['action']:8} jobs={r['jobs_found']} missing={r['missing_jobs']}")
    print(f"{'gate: PASS' if not failed else 'gate: FAIL'} -> {rj}, {rm}")
    if failed:
        for r in failed:
            print(f"  {r['workflow']}: missing {r['missing_jobs']} {r['problems']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
