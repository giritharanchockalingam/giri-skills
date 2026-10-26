#!/usr/bin/env python3
"""Install the GitHub Actions workflows this skill ships, read-before-write, and validate their structure.

    python3 -I scripts/install_ci.py --target <repo> [--deploy auto|vercel|skip] \
        --report-json ci-report.json --report-md ci-report.md

Read before write — nothing is written until everything below has been computed:
  1. Language flavour: tsconfig.json or any .ts/.tsx source -> TypeScript; jsconfig.json or .js/.jsx/.mjs
     app sources -> JavaScript; neither -> unknown (treated as TypeScript, the skill's stack). A JavaScript
     repo gets the secrets-scan grep widened to *.js/*.jsx in anything this script writes.
  2. Deploy target, from existing workflows (comment lines stripped), package.json scripts and config:
       Vercel  .vercel/project.json link, `vercel deploy|pull|build|link`, VERCEL_TOKEN/ORG_ID/PROJECT_ID,
               a vercel-action; vercel.json alone is a weak signal (it does not beat another provider)
       AWS     aws-actions/, amazon-ecr, ecs, cdk, sam, aws cli;  Azure azure/;  GCP google-github-actions;
               Fly fly.io/flyctl;  Railway railway
     preview.yml and prod.yml (the Vercel deploy workflows) are written only when the effective target is
     Vercel: detected Vercel, or no deploy signal at all (greenfield), or `--deploy vercel` passed explicitly.
     `--deploy skip` never writes them. Any other detected provider -> they are skipped and the report says
     so with the detected target; the CI-only pieces (ci.yml) are still offered.
  3. Existing workflows (ci.yml/.yaml, preview.yml/.yaml, prod.yml/.yaml) are kept, never overwritten, and
     validated job by job: a top-level `on:` and `jobs:` block and the standard job names
       ci.yml       lint-typecheck-test, rls-lint, secrets-scan
       preview.yml  deploy-preview, e2e
       prod.yml     verify-tag, migrate-staging, migrate-prod, deploy-prod
     A kept workflow missing standard jobs never fails the run: the missing jobs are proposed as
     `.github/<name>-additions.yml` (e.g. ci-additions.yml — outside workflows/ so Actions ignores it) for the
     team to merge by hand, every job is reported present/missing in a table, and the exit code is 0.
  4. Every `npm run <script>` a workflow calls is checked against package.json "scripts" (warning only).
All writes are atomic: if any planned file conflicts (a kept workflow is structurally malformed, or an
additions file already exists with different content) nothing is written, the report says why, exit 1.
Exit 1 also on bad input. `ok` in the report is true only when every standard job is present.
Writes ci-report.json and ci-report.md. Stdlib, offline, deterministic.
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
DEPLOY_WORKFLOWS = ("preview.yml", "prod.yml")
TOP_KEY = re.compile(r"^([A-Za-z_][\w-]*):", re.M)
NPM_RUN = re.compile(r"\bnpm run ([A-Za-z0-9:_.-]+)")
COMMENT_LINE = re.compile(r"^\s*#.*$", re.M)
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "coverage", "out", ".vercel", "vendor"}
SRC_DIRS = ("app", "pages", "src", "lib", "components", "server", "scripts")

# strong Vercel signals: a CLI/action/secret, never a bare hostname (*.vercel.app in an uptime check is not a deploy)
VERCEL_STRONG = re.compile(r"\bvercel\s+(?:deploy|pull|build|link|promote|rollback)\b|\bnpx\s+vercel\b"
                           r"|VERCEL_(?:TOKEN|ORG_ID|PROJECT_ID)\b|vercel-action|uses:\s*vercel/", re.I)
PROVIDERS = {
    "aws": re.compile(r"aws-actions/|amazon-ecr|\becs\b|\bcdk\b|\bsam\s+(?:build|deploy|package)\b|\baws\s+(?:ecs|ecr|s3|lambda|cloudformation|cloudfront)\b", re.I),
    "azure": re.compile(r"uses:\s*azure/|\baz\s+(?:webapp|containerapp|aks|functionapp)\b", re.I),
    "gcp": re.compile(r"google-github-actions|\bgcloud\s+run\b", re.I),
    "fly.io": re.compile(r"\bfly\.io\b|superfly/flyctl|\bflyctl\b", re.I),
    "railway": re.compile(r"\brailway\b", re.I),
}
PROVIDER_LABEL = {"aws": "AWS", "azure": "Azure", "gcp": "Google Cloud", "fly.io": "Fly.io", "railway": "Railway"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------ read


def package_scripts(target: Path) -> dict[str, str] | None:
    """The "scripts" map in <target>/package.json, or None when there is no package.json."""
    pj = target / "package.json"
    if not pj.is_file():
        return None
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except ValueError as e:
        die(f"package.json is not valid JSON: {e}")
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in scripts.items()} if isinstance(scripts, dict) else {}


def walk_sources(target: Path, max_files: int = 4000):
    """Source files under the usual app dirs (and the root), skipping build/vendor dirs; bounded."""
    n = 0
    roots = [target] + [target / d for d in SRC_DIRS if (target / d).is_dir()]
    seen = set()
    for root in roots:
        for p in sorted(root.rglob("*") if root != target else root.glob("*")):
            if p in seen:
                continue
            seen.add(p)
            if any(part in SKIP_DIRS for part in p.relative_to(target).parts):
                continue
            if p.is_file():
                n += 1
                yield p
                if n >= max_files:
                    return


def detect_flavour(target: Path) -> dict:
    """typescript | javascript | unknown, with the evidence that decided it."""
    if (target / "tsconfig.json").is_file():
        return {"flavour": "typescript", "evidence": "tsconfig.json"}
    ts, js = [], []
    for p in walk_sources(target):
        if p.suffix in (".ts", ".tsx", ".mts", ".cts") and not p.name.endswith(".d.ts"):
            ts.append(p)
        elif p.suffix in (".js", ".jsx", ".mjs", ".cjs"):
            js.append(p)
    if ts:
        return {"flavour": "typescript", "evidence": f"{len(ts)} .ts/.tsx source file(s)"}
    if (target / "jsconfig.json").is_file():
        return {"flavour": "javascript", "evidence": "jsconfig.json, no tsconfig.json"}
    if js:
        return {"flavour": "javascript", "evidence": f"{len(js)} .js/.jsx source file(s), no tsconfig.json"}
    return {"flavour": "unknown", "evidence": "no tsconfig.json and no sources yet (treated as TypeScript)"}


def strip_comments(text: str) -> str:
    return COMMENT_LINE.sub("", text)


def detect_deploy(target: Path, scripts: dict[str, str] | None) -> dict:
    """Which platform the repo deploys to today, from workflows (comments stripped), scripts and config."""
    signals: dict[str, list[str]] = {}

    def add(key: str, where: str) -> None:
        signals.setdefault(key, [])
        if where not in signals[key]:
            signals[key].append(where)

    wf_dir = target / ".github" / "workflows"
    for wf in sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []:
        body = strip_comments(wf.read_text(encoding="utf-8", errors="replace"))
        rel = f".github/workflows/{wf.name}"
        if VERCEL_STRONG.search(body):
            add("vercel", rel)
        for key, rx in PROVIDERS.items():
            if rx.search(body):
                add(key, rel)
    for name, cmd in sorted((scripts or {}).items()):
        if re.search(r"\bvercel\b", cmd):
            add("vercel", f"package.json scripts.{name}")
        for key, rx in PROVIDERS.items():
            if rx.search(cmd):
                add(key, f"package.json scripts.{name}")
    if (target / ".vercel" / "project.json").is_file():
        add("vercel", ".vercel/project.json (linked project)")
    weak = (target / "vercel.json").is_file()

    others = [k for k in PROVIDERS if k in signals]
    if "vercel" in signals:
        detected = "vercel"
    elif others:
        detected = others[0] if len(others) == 1 else "multiple"
    elif weak:
        detected = "vercel"
        add("vercel", "vercel.json (weak: config only, no link or deploy step)")
    else:
        detected = "none"
    labels = {**PROVIDER_LABEL, "vercel": "Vercel", "none": "none",
              "multiple": "multiple providers (" + ", ".join(PROVIDER_LABEL[k] for k in others) + ")"}
    return {"detected": detected, "others": others, "signals": signals, "label": labels[detected]}


def find_existing(wf_dir: Path, name: str) -> Path | None:
    """The existing workflow for <name>, accepting the .yaml sibling so we never create ci.yml beside ci.yaml."""
    for cand in (wf_dir / name, wf_dir / (Path(name).stem + ".yaml")):
        if cand.exists():
            return cand
    return None


# ------------------------------------------------------------------ validate


def job_blocks(text: str) -> dict[str, str]:
    """Each top-level job under `jobs:` mapped to its full text block (name line through its last line)."""
    m = re.search(r"^jobs:\s*$", text, re.M)
    if not m:
        return {}
    blocks: dict[str, str] = {}
    cur, buf = None, []
    for ln in text[m.end():].splitlines(keepends=True):
        if ln.strip() and not ln.startswith((" ", "\t", "#")):
            break  # next top-level key
        jm = re.match(r"^  ([A-Za-z_][\w-]*):\s*(?:#.*)?$", ln)
        if jm:
            if cur:
                blocks[cur] = "".join(buf).rstrip("\n") + "\n"
            cur, buf = jm.group(1), [ln]
        elif cur:
            buf.append(ln)
    if cur:
        blocks[cur] = "".join(buf).rstrip("\n") + "\n"
    return blocks


def validate(text: str, required: list[str]) -> dict:
    top = TOP_KEY.findall(text)
    has_on = bool(re.search(r"^(?:\"on\"|'on'|on):", text, re.M))
    has_jobs = "jobs" in top
    jobs = list(job_blocks(text))
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


# ------------------------------------------------------------------ plan


def adapt_flavour(text: str, flavour: str) -> str:
    """JavaScript repos: the secrets scan must also look at .js/.jsx files."""
    if flavour != "javascript":
        return text
    return text.replace("--include='*.ts' --include='*.tsx'",
                        "--include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx'")


def additions_text(name: str, missing: list[str], asset_text: str, flavour: str) -> str:
    blocks = job_blocks(adapt_flavour(asset_text, flavour))
    head = [f"# {Path(name).stem}-additions.yml — jobs the standard {name} has and yours lacks: {', '.join(missing)}.",
            "# NOT a workflow (it lives outside .github/workflows/ so Actions ignores it). Merge each job under",
            f"# `jobs:` in .github/workflows/{name} by hand, keep your customised steps, then delete this file.",
            "# Branch protection expects these check names: "
            + ", ".join(f"{Path(name).stem} / {j}" for j in missing) + ".",
            "# Anything these jobs reference at workflow level (env.NODE_VERSION, secrets, permissions) must exist in",
            "# your workflow too — see assets/workflows/" + name + " for the top-level blocks.",
            "jobs:"]
    return "\n".join(head) + "\n" + "\n".join(blocks[j] for j in missing if j in blocks)


def plan(target: Path, deploy_mode: str) -> dict:
    scripts = package_scripts(target)
    flavour = detect_flavour(target)
    deploy = detect_deploy(target, scripts)
    deploy["override"] = deploy_mode if deploy_mode != "auto" else ""
    if deploy_mode == "vercel":
        effective, reason = "vercel", "`--deploy vercel` passed explicitly"
    elif deploy_mode == "skip":
        effective, reason = "skip", "`--deploy skip` passed explicitly"
    elif deploy["detected"] == "vercel":
        effective, reason = "vercel", "Vercel detected"
    elif deploy["detected"] == "none":
        effective, reason = "vercel", "no deploy signal in the repo (greenfield) — the skill's default target is Vercel"
    else:
        effective = "skip"
        reason = (f"repo deploys to {deploy['label']} ({', '.join(sum(deploy['signals'].values(), []))}); "
                  "the Vercel deploy workflows do not apply — pass `--deploy vercel` to force them")
    deploy["effective"] = effective
    deploy["reason"] = reason
    deploy["deploy_workflows"] = "write" if effective == "vercel" else "skipped"

    wf_dir = target / ".github" / "workflows"
    rows, writes, conflicts = [], [], []
    for name, required in REQUIRED.items():
        asset_text = (ASSETS / name).read_text(encoding="utf-8")
        existing = find_existing(wf_dir, name) if wf_dir.is_dir() else None
        row: dict = {"workflow": name, "additions_path": ""}
        extra_text = ""
        if existing is not None:
            text = existing.read_text(encoding="utf-8", errors="replace")
            row.update(action="kept", path=existing.relative_to(target).as_posix(), **validate(text, required))
            if not row["valid"]:
                conflicts.append(f"{row['path']} is kept but structurally malformed ({'; '.join(row['problems'])}) — fix it by hand before installing")
            elif row["missing_jobs"]:
                add_path = target / ".github" / f"{Path(name).stem}-additions.yml"
                content = additions_text(name, row["missing_jobs"], asset_text, flavour["flavour"])
                row["additions_path"] = add_path.relative_to(target).as_posix()
                extra_text = content
                if add_path.exists():
                    if add_path.read_text(encoding="utf-8", errors="replace") != content:
                        conflicts.append(f"{row['additions_path']} already exists with different content — merge or delete it first")
                    else:
                        row["additions_action"] = "kept"
                else:
                    writes.append((add_path, content))
                    row["additions_action"] = "written"
        elif name in DEPLOY_WORKFLOWS and effective != "vercel":
            text = ""
            row.update(action="skipped", path=f".github/workflows/{name}", valid=True, problems=[],
                       jobs_found=[], missing_jobs=[], warnings=[], skip_reason=reason)
        else:
            text = adapt_flavour(asset_text, flavour["flavour"])
            writes.append((wf_dir / name, text))
            row.update(action="written", path=f".github/workflows/{name}", **validate(text, required))
        called = sorted(set(NPM_RUN.findall(text + "\n" + extra_text)))
        row["npm_scripts_missing"] = [] if scripts is None else [c for c in called if c not in scripts]
        rows.append(row)

    incomplete = [r for r in rows if r.get("action") != "skipped" and (not r["valid"] or r["missing_jobs"])]
    required_checks = ["ci / lint-typecheck-test", "ci / rls-lint"]
    if effective == "vercel" or any(r["workflow"] == "preview.yml" and r["action"] == "kept" for r in rows):
        required_checks.append("preview / e2e")
    gate = "ABORTED" if conflicts else ("PASS" if not incomplete else "NEEDS-MERGE")
    return {"target": str(target), "ok": gate == "PASS", "gate": gate, "conflicts": conflicts,
            "flavour": flavour, "deploy": deploy, "workflows": rows,
            "package_json": "absent" if scripts is None else "checked",
            "writes": [p.relative_to(target).as_posix() for p, _ in writes],
            "required_checks": required_checks, "_writes": writes}


# ------------------------------------------------------------------ report


def render_md(rep: dict) -> str:
    target = Path(rep["target"])
    rows, dep, fl = rep["workflows"], rep["deploy"], rep["flavour"]
    n_w = sum(r["action"] == "written" for r in rows) + sum(r.get("additions_action") == "written" for r in rows)
    n_k = sum(r["action"] == "kept" for r in rows)
    n_s = sum(r["action"] == "skipped" for r in rows)
    summary = {"PASS": "gate: PASS — every standard job present.",
               "NEEDS-MERGE": "gate: NEEDS-MERGE — a kept workflow lacks standard jobs; proposed in the additions file below, nothing overwritten.",
               "ABORTED": "gate: ABORTED — nothing written; see Conflicts."}[rep["gate"]]
    lines = [f"# CI install — {target.name}", "",
             f"**{n_w} file(s) written, {n_k} workflow(s) kept as-is, {n_s} deploy workflow(s) skipped; {summary}**", ""]
    if rep["conflicts"]:
        lines += ["## Conflicts (nothing was written)", ""] + [f"- {c}" for c in rep["conflicts"]] + [""]
    lines += ["## Read before write", "", "| Fact | Value | Evidence |", "|---|---|---|",
              f"| Language flavour | {fl['flavour']} | {fl['evidence']} |",
              f"| Deploy target detected | {dep['label']} | "
              + ("; ".join(f"{k}: {', '.join(v)}" for k, v in dep["signals"].items()) or "no deploy signals") + " |",
              f"| Deploy workflows (preview.yml, prod.yml) | {'written' if dep['deploy_workflows'] == 'write' else 'NOT written'} | {dep['reason']} |", ""]
    if dep["deploy_workflows"] != "write":
        lines += [f"The Vercel deploy workflows were **not** written: this repo deploys to **{dep['label']}**"
                  if dep["effective"] != "skip" or not dep["override"] else "The Vercel deploy workflows were **not** written (`--deploy skip`)",
                  "and `preview.yml`/`prod.yml` assume `vercel deploy`. What still applies here is the CI-only piece: `ci.yml` "
                  "(lint → typecheck → unit → build, RLS lint, secrets scan) and its branch-protection check names. "
                  "To force the Vercel workflows anyway, re-run with `--deploy vercel`.", ""]
    lines += ["## Workflows", "", "| Workflow | Action | Valid | Jobs found | Missing jobs | Warnings |", "|---|---|---|---|---|---|"]
    for r in rows:
        valid = "—" if r["action"] == "skipped" else ("yes" if r["valid"] else "no: " + "; ".join(r["problems"]))
        lines.append(f"| `{r['path']}` | {r['action']} | {valid} | {', '.join(r['jobs_found']) or '—'} | "
                     f"{', '.join(r['missing_jobs']) or '—'} | {'; '.join(r['warnings']) or '—'} |")
    lines += ["", "## Standard jobs", "", "| Workflow | Job | Status | Required check |", "|---|---|---|---|"]
    for r in rows:
        for j in REQUIRED[r["workflow"]]:
            status = ("skipped" if r["action"] == "skipped" else
                      "present" if j in r["jobs_found"] else f"missing → `{r['additions_path']}`" if r["additions_path"] else "missing")
            lines.append(f"| `{r['path']}` | `{j}` | {status} | `{Path(r['workflow']).stem} / {j}` |")
    adds = [r for r in rows if r["additions_path"]]
    if adds:
        lines += ["", "## Additions to merge by hand", ""]
        for r in adds:
            lines.append(f"- `{r['additions_path']}` ({r.get('additions_action', 'planned')}): jobs {', '.join(r['missing_jobs'])} "
                         f"for `{r['path']}` — copy each job under `jobs:`, keep your steps, delete the file. Not overwritten: `{r['path']}`.")
    lines += ["", "## package.json scripts", ""]
    if rep["package_json"] == "absent":
        lines.append("No package.json in the target yet — not checked; every `npm run` the workflows call must exist once it is added.")
    else:
        gaps = [(r["path"], s_) for r in rows for s_ in r["npm_scripts_missing"]]
        lines += [f"- `{p_}` calls `npm run {s_}` — not in package.json scripts" for p_, s_ in gaps] or \
                 ["Every `npm run` the workflows call exists in package.json."]
        if fl["flavour"] == "javascript" and any(s_ == "typecheck" for _, s_ in gaps):
            lines.append("- JavaScript repo: add a `typecheck` script (e.g. `tsc --noEmit --allowJs --checkJs` with a jsconfig/tsconfig) or drop that step when merging.")
    lines += ["", "## Branch protection (required checks)", ""] + [f"- `{c}`" for c in rep["required_checks"]]
    steps = ["Confirm every `npm run <script>` the workflows call exists in package.json."]
    if adds:
        steps.append("Merge the additions file(s) above into the kept workflow(s) by hand, then delete them.")
    if dep["deploy_workflows"] == "write":
        steps += ["`gh secret set` for VERCEL_TOKEN, VERCEL_ORG_ID, VERCEL_PROJECT_ID, SUPABASE_ACCESS_TOKEN, SUPABASE_DB_PASSWORD (values never in chat).",
                  "Create GitHub Environments `staging` and `production` (required reviewers on production)."]
    else:
        steps.append(f"Keep your {dep['label']} deploy workflows as they are; wire the `ci / *` checks above into branch protection.")
    steps += ["Push a `chore/ci` branch and watch the run; check names must match branch protection.",
              "Kept workflows: diff against `assets/workflows/` and merge missing stages by hand."]
    lines += ["", "## Next steps", ""] + [f"{i}. {s}" for i, s in enumerate(steps, 1)]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser(description="Install and validate ci/preview/prod GitHub Actions workflows (read before write)")
    ap.add_argument("--target", required=True, help="repo root (created if absent)")
    ap.add_argument("--deploy", default="auto", choices=["auto", "vercel", "skip"],
                    help="auto: write preview.yml/prod.yml only when the repo deploys to Vercel (or has no deploy yet); "
                         "vercel: force them; skip: never write them")
    ap.add_argument("--report-json", default="ci-report.json")
    ap.add_argument("--report-md", default="ci-report.md")
    a = ap.parse_args()
    target = Path(a.target)
    if target.exists() and not target.is_dir():
        die(f"target is not a directory: {target}")
    missing_assets = [n for n in REQUIRED if not (ASSETS / n).is_file()]
    if missing_assets:
        die(f"workflow assets missing: {missing_assets}")

    rep = plan(target, a.deploy)
    writes = rep.pop("_writes")
    if not rep["conflicts"]:
        for p, content in writes:           # atomic: every conflict was ruled out above
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    else:
        rep["writes"] = []

    rj, rm = Path(a.report_json), Path(a.report_md)
    rj.parent.mkdir(parents=True, exist_ok=True)
    rm.parent.mkdir(parents=True, exist_ok=True)
    rj.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    rm.write_text(render_md(rep), encoding="utf-8")

    print(f"flavour={rep['flavour']['flavour']} deploy={rep['deploy']['label']} deploy_workflows={rep['deploy']['deploy_workflows']}")
    for r in rep["workflows"]:
        extra = f" additions={r['additions_path']}" if r["additions_path"] else ""
        print(f"{r['workflow']:12} {r['action']:8} jobs={r['jobs_found']} missing={r['missing_jobs']}{extra}")
    print(f"gate: {rep['gate']} -> {rj}, {rm}")
    if rep["conflicts"]:
        for c in rep["conflicts"]:
            print(f"error: {c}", file=sys.stderr)
        print("error: nothing written (atomic install); fix the conflicts and re-run", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
