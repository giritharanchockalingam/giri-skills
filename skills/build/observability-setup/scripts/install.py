#!/usr/bin/env python3
"""Install the observability starter kit into a Next.js repo — read before write, never overwrite.

    python3 -I scripts/install.py --target <repo> [--dry-run] [--project <name>] [--flavour ts|js] \
        --report-json install-report.json --report-md install-report.md

Flavour (read before write): tsconfig.json or any .ts/.tsx under app|lib|components -> TypeScript;
otherwise JavaScript (an empty/new target defaults to TypeScript). The matching asset variant is used:
  assets/logger.{ts,js}            -> lib/logger.{ext}
  assets/logger-context.{ts,js}    -> lib/logger/context.{ext}
  assets/health-route.{ts,js}      -> app/api/health/route.{ext}
  assets/health-deep-route.{ts,js} -> app/api/health/deep/route.{ext}
  assets/alert-rules.yaml          -> ops/alerts.yaml
  assets/slo-starter.md            -> docs/observability.md
Existing files (in ANY source extension: route.js next to a planned route.ts counts) are never
overwritten and never get a conflicting sibling: identical -> skipped; a health route -> "exists, kept"
with a static gap table (exports GET? force-dynamic? no-store? liveness free of dependency calls?);
any other file in the same flavour -> `<file>.proposed` twin for a manual merge; in the other flavour ->
"exists, kept" (merge by hand from the asset). Env vars (`process.env.X`) are appended to .env.example
only for files written in this run. The plan is computed before anything is written: a repo that already
holds a conflicting pair (route.js AND route.ts) makes the run write nothing, report why, and exit 1.
--dry-run writes nothing. The run also lists every `console.*` call in the app's source. Exit 0 when the
repo already has every piece (the report carries the gap table). Exit 1 on bad input or conflict. Stdlib.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
# (asset stem, destination without extension, kind); kind: route | module | static
PLAN = [
    ("logger", "lib/logger", "module"),
    ("logger-context", "lib/logger/context", "module"),
    ("health-route", "app/api/health/route", "route"),
    ("health-deep-route", "app/api/health/deep/route", "route"),
    ("alert-rules.yaml", "ops/alerts.yaml", "static"),
    ("slo-starter.md", "docs/observability.md", "static"),
]
SIBLING_EXT = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]   # any of these at the same stem is "the file"
TS_EXT = {".ts", ".tsx"}
FLAVOUR_DIRS = ("app", "lib", "components", "src")
ENV_RE = re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)")
CONSOLE_RE = re.compile(r"\bconsole\.(log|info|warn|error|debug)\s*\(")
SOURCE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
SKIP_DIRS = {"node_modules", ".next", ".git", "dist", "build", "out", "coverage", ".vercel"}
PLATFORM_VARS = {"NODE_ENV", "VERCEL_ENV", "VERCEL_GIT_COMMIT_SHA"}  # set by the platform, not by .env
ENV_DOC = {
    "LOG_LEVEL": "debug|info|warn|error (default: info in production, debug elsewhere)",
    "LOG_PRETTY": "1 to pretty-print logs in local development",
    "SERVICE_NAME": "service label on every log line (default: web)",
    "HEALTH_CHECK_TOKEN": "bearer token required by /api/health/deep (generate: openssl rand -hex 32)",
    "NEXT_PUBLIC_SUPABASE_URL": "Supabase project URL",
}
GET_EXPORT_RE = re.compile(r"export\s+(?:async\s+)?function\s+GET\b|export\s+const\s+GET\b|export\s*\{[^}]*\bGET\b[^}]*\}")
# dependency calls a liveness route must not make, most specific first; comments are stripped before matching
DEP_CALL_PATTERNS = [r"\bfetch\s*\(", r"\.rpc\s*\(", r"\.from\s*\(", r"createAdminClient", r"createClient",
                     r"\bsupabase\b", r"\bprisma\b", r"\bmongoose\b", r"\bpg\b", r"\bredis\b"]
LINE_COMMENT_RE = re.compile(r"^\s*//.*$", re.M)
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _skip(p: Path, target: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.relative_to(target).parts)


def detect_flavour(target: Path) -> tuple[str, str]:
    """('ts'|'js', evidence). tsconfig.json or any .ts/.tsx under app|lib|components|src -> ts; else js.
    An empty or missing target has nothing to read and defaults to ts (the greenfield happy path)."""
    if not target.is_dir() or not any(target.iterdir()):
        return "ts", "empty target — default"
    if (target / "tsconfig.json").is_file():
        return "ts", "tsconfig.json present"
    for d in FLAVOUR_DIRS:
        root = target / d
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in TS_EXT and not _skip(p, target):
                return "ts", f"{p.relative_to(target).as_posix()} is TypeScript"
    if (target / "jsconfig.json").is_file():
        return "js", "jsconfig.json present, no tsconfig.json or .ts/.tsx source"
    return "js", "no tsconfig.json or .ts/.tsx source under app|lib|components|src"


def siblings(target: Path, stem: str) -> list[Path]:
    """Existing files at <stem>.<ext> for every source extension (the route/module in either flavour)."""
    return [target / f"{stem}{ext}" for ext in SIBLING_EXT if (target / f"{stem}{ext}").is_file()]


def health_gap(text: str, deep: bool) -> list[dict]:
    """Static check of an existing health route against the standard (references/health-endpoints.md)."""
    rows = [{"check": "exports GET", "ok": bool(GET_EXPORT_RE.search(text)),
             "note": "route responds to GET" if GET_EXPORT_RE.search(text) else "no GET export — the route does not respond"}]
    rows.append({"check": "force-dynamic", "ok": "force-dynamic" in text,
                 "note": "" if "force-dynamic" in text else "add `export const dynamic = \"force-dynamic\"`"})
    rows.append({"check": "Cache-Control: no-store", "ok": "no-store" in text,
                 "note": "" if "no-store" in text else "respond with `Cache-Control: no-store`"})
    has_version = bool(re.search(r"\b(version|sha|commit)\b", text))
    rows.append({"check": "build info (version/sha)", "ok": has_version,
                 "note": "" if has_version else "include the deployed commit sha"})
    rows.append({"check": "timestamp (ts)", "ok": bool(re.search(r"\bts\b|toISOString", text)),
                 "note": "" if re.search(r"\bts\b|toISOString", text) else "include `ts`"})
    if deep:
        has_auth = "HEALTH_CHECK_TOKEN" in text or re.search(r"\bBearer\b", text) is not None
        rows.append({"check": "bearer-protected (HEALTH_CHECK_TOKEN)", "ok": bool(has_auth),
                     "note": "" if has_auth else "require `Authorization: Bearer ${HEALTH_CHECK_TOKEN}`"})
        has_timeout = bool(re.search(r"setTimeout|AbortController|timeout", text, re.I))
        rows.append({"check": "per-dependency timeout", "ok": has_timeout,
                     "note": "" if has_timeout else "time out each dependency check at ≤ 3 s"})
        rows.append({"check": "503 when a required dependency is down", "ok": "503" in text,
                     "note": "" if "503" in text else "return 503 on a required dependency failure"})
    else:
        code = LINE_COMMENT_RE.sub("", BLOCK_COMMENT_RE.sub("", text))
        touches = next((m for pat in DEP_CALL_PATTERNS for m in [re.search(pat, code, re.I)] if m), None)
        rows.append({"check": "liveness has no dependency calls", "ok": touches is None,
                     "note": "" if touches is None else
                     f"calls `{touches.group(0).strip()}` — a dependency outage makes the app look dead; move the check to /api/health/deep"})
    return rows


def console_calls(target: Path, ours: set[str]) -> list[dict]:
    """console.* calls in the repo's own source (files this script installs are excluded)."""
    found = []
    if not target.is_dir():
        return found
    for p in sorted(target.rglob("*")):
        rel = p.relative_to(target).as_posix()
        if not p.is_file() or p.suffix not in SOURCE_EXT or rel in ours or rel.endswith(".proposed") or _skip(p, target):
            continue
        for n, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = CONSOLE_RE.search(ln)
            if m:
                found.append({"path": rel, "line": n, "call": f"console.{m.group(1)}"})
    return found


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def build_plan(target: Path, flavour: str, project: str) -> list[dict]:
    """One decision per asset, computed before any write: written | skipped | proposed | kept | conflict."""
    ext = f".{flavour}"
    plan = []
    for stem, dest_stem, kind in PLAN:
        src = ASSETS / (stem if kind == "static" else f"{stem}{ext}")
        content = src.read_text(encoding="utf-8").replace("{{PROJECT}}", project)
        rel = dest_stem if kind == "static" else f"{dest_stem}{ext}"
        item = {"path": rel, "kind": kind, "content": content, "asset": f"assets/{src.name}",
                "env": sorted(set(ENV_RE.findall(content)) - PLATFORM_VARS)}
        existing = siblings(target, dest_stem) if kind != "static" else ([target / rel] if (target / rel).is_file() else [])
        if len(existing) > 1:
            item.update(action="conflict", existing=[p.relative_to(target).as_posix() for p in existing],
                        reason="more than one source file at this path (" + ", ".join(p.name for p in existing)
                        + ") — Next.js resolves one; fix the repo first")
        elif not existing:
            item["action"] = "written"
        else:
            cur = existing[0]
            cur_rel = cur.relative_to(target).as_posix()
            text = cur.read_text(encoding="utf-8", errors="replace")
            item["existing"] = cur_rel
            if cur_rel == rel and text == content:
                item.update(action="skipped", reason="identical")
            elif kind == "route":
                item.update(action="kept", reason="exists, kept — no sibling route created (a route.js/route.ts pair is a Next.js conflict)",
                            gap=health_gap(text, deep=stem == "health-deep-route"))
            elif cur_rel == rel:
                item.update(action="proposed", proposed=rel + ".proposed", reason="exists with different content — merge manually")
            else:
                item.update(action="kept", reason=f"exists, kept — {cur.suffix} file in a {flavour} install; merge by hand from {item['asset']}")
        plan.append(item)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description="Install logger, health routes, alert rules and SLO starter")
    ap.add_argument("--target", required=True, help="repo root (created if absent)")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--project", default="", help="project name for docs/observability.md (default: target dir name)")
    ap.add_argument("--flavour", choices=["ts", "js"], default="", help="override the detected language flavour")
    ap.add_argument("--report-json", default="install-report.json")
    ap.add_argument("--report-md", default="install-report.md")
    a = ap.parse_args()
    target = Path(a.target)
    if target.exists() and not target.is_dir():
        die(f"target is not a directory: {target}")
    missing = [f"{stem}.{e}" for stem, _, kind in PLAN if kind != "static" for e in ("ts", "js") if not (ASSETS / f"{stem}.{e}").is_file()]
    missing += [stem for stem, _, kind in PLAN if kind == "static" and not (ASSETS / stem).is_file()]
    if missing:
        die(f"assets missing: {missing}")
    project = a.project or target.name
    detected, evidence = detect_flavour(target)
    flavour = a.flavour or detected
    if a.flavour:
        evidence = f"--flavour {a.flavour} (detected: {detected}, {evidence})"

    plan = build_plan(target, flavour, project)
    conflicts = [i for i in plan if i["action"] == "conflict"]
    report = {"target": str(target), "dry_run": a.dry_run, "flavour": flavour, "flavour_evidence": evidence,
              "written": [], "skipped": [], "proposed": [], "kept": [], "conflicts": [], "env_added": [], "health_gaps": []}

    for i in plan:
        if i["action"] == "conflict":
            report["conflicts"].append({"path": i["path"], "existing": i["existing"], "reason": i["reason"]})
        elif i["action"] == "skipped":
            report["skipped"].append({"path": i["path"], "reason": "identical"})
        elif i["action"] == "proposed":
            report["proposed"].append({"path": i["path"], "proposed": i["proposed"], "reason": i["reason"]})
        elif i["action"] == "kept":
            report["kept"].append({"path": i["existing"], "planned": i["path"], "reason": i["reason"]})
            if "gap" in i:
                report["health_gaps"].append({"path": i["existing"], "responds": i["gap"][0]["ok"], "checks": i["gap"],
                                              "missing": [g["check"] for g in i["gap"] if not g["ok"]]})
        else:
            report["written"].append(i["path"])

    env_file = target / ".env.example"
    env_existed = env_file.exists()
    existing_env = env_file.read_text(encoding="utf-8", errors="replace") if env_existed else ""
    present = {m.group(1) for m in re.finditer(r"^\s*([A-Z][A-Z0-9_]*)\s*=", existing_env, re.M)}
    needed = {v for i in plan if i["action"] == "written" for v in i["env"]}   # only for files this run installs
    to_add = sorted(v for v in needed if v not in present)

    write = not a.dry_run and not conflicts
    if write:
        target.mkdir(parents=True, exist_ok=True)
        for i in plan:
            if i["action"] == "written":
                dest = target / i["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(i["content"], encoding="utf-8")
            elif i["action"] == "proposed":
                (target / i["proposed"]).write_text(i["content"], encoding="utf-8")
        if to_add:
            block = ([""] if existing_env else []) + ["# observability (added by observability-setup/scripts/install.py)"]
            block += [f"{v}=  # {ENV_DOC.get(v, 'see docs/observability.md')}" for v in to_add]
            sep = "" if not existing_env or existing_env.endswith("\n") else "\n"
            env_file.write_text(existing_env + sep + "\n".join(block) + "\n", encoding="utf-8")
    if to_add and not conflicts:
        report["env_added"] = to_add
        if not env_existed:
            report["written"].append(".env.example")
    if conflicts:   # nothing is written on a conflict — report the plan that would have run
        report.update(written=[], proposed=[], env_added=[])

    report["console_calls"] = console_calls(target, {i["path"] for i in plan})

    rj, rm = Path(a.report_json), Path(a.report_md)
    rj.parent.mkdir(parents=True, exist_ok=True)
    rm.parent.mkdir(parents=True, exist_ok=True)
    rj.write_text(json.dumps(report, indent=2), encoding="utf-8")
    verb = "would be " if a.dry_run else ""
    status = ("**Aborted — nothing written.** The repo already holds a conflicting pair; fix it and re-run." if conflicts else
              f"**{len(report['written'])} file(s) {verb}written, {len(report['skipped'])} skipped (identical), "
              f"{len(report['kept'])} kept (exists), {len(report['proposed'])} proposed for manual merge, "
              f"{len(report['env_added'])} env var(s) {verb}added.**" + (" Dry run — nothing was written." if a.dry_run else ""))
    lines = [f"# Observability install — {project}", "", status, "",
             f"Flavour: **{'TypeScript' if flavour == 'ts' else 'JavaScript'}** (`.{flavour}`) — {evidence}.", ""]
    if conflicts:
        lines += ["## Conflicts (fix before re-running)", ""] + [f"- `{c['path']}` — {c['reason']}" for c in conflicts] + [""]
    lines += ["## Written", ""] + [f"- `{p}`" for p in report["written"]] + (["- none"] if not report["written"] else [])
    lines += ["", "## Kept (exists, kept — no sibling created)", ""]
    lines += [f"- `{k['path']}` — {k['reason']}" for k in report["kept"]] + (["- none"] if not report["kept"] else [])
    if report["health_gaps"]:
        lines += ["", "## Existing health route vs the standard", ""]
        for g in report["health_gaps"]:
            lines += [f"`{g['path']}` — {'responds (exports GET)' if g['responds'] else 'DOES NOT RESPOND (no GET export)'}; "
                      f"missing versus the standard: {', '.join(g['missing']) if g['missing'] else 'nothing'}", "",
                      "| Check | Status | Note |", "|---|---|---|"]
            lines += [f"| {c['check']} | {'ok' if c['ok'] else 'MISSING'} | {c['note']} |" for c in g["checks"]]
            lines += [""]
    lines += ["", "## Skipped (already identical)", ""] + [f"- `{s['path']}`" for s in report["skipped"]] + (["- none"] if not report["skipped"] else [])
    lines += ["", "## Proposed (exists with different content — merge by hand)", ""]
    lines += [f"- `{p['path']}` → review `{p['proposed']}`" for p in report["proposed"]] + (["- none"] if not report["proposed"] else [])
    lines += ["", "## Env vars added to .env.example", "", "Only variables read by files written in this run are added.", ""]
    lines += [f"- `{v}` — {ENV_DOC.get(v, '')}" for v in report["env_added"]] + (["- none"] if not report["env_added"] else [])
    lines += ["", "## Console calls to replace with lib/logger", ""]
    lines += [f"- `{c['path']}:{c['line']}` — `{c['call']}`" for c in report["console_calls"]] or ["- none found"]
    lines += ["", "## Next steps", "",
              f"1. Wire `requestId` in `middleware.{flavour}` and set ESLint `no-console: error`.",
              "2. Replace `console.*` calls with `lib/logger` in minimal diffs.",
              "3. Set `HEALTH_CHECK_TOKEN` in the deploy platform's env; curl both health routes on preview.",
              "4. Fill owners and runbook links in `ops/alerts.yaml`; translate to the monitoring vendor.",
              "5. Fill the SLO table in `docs/observability.md` from the critical journeys in SPEC."]
    if report["health_gaps"]:
        lines.append("6. Close the gaps in the existing health route table above (keep the route file; edit in place).")
    rm.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if conflicts:
        print(f"error: conflicting files already in the repo — nothing written: "
              + "; ".join(f"{c['path']} ({', '.join(c['existing'])})" for c in conflicts) + f" -> {rm}", file=sys.stderr)
        return 1
    print(f"{'dry-run: ' if a.dry_run else ''}[{flavour}] {len(report['written'])} written, {len(report['skipped'])} skipped, "
          f"{len(report['kept'])} kept, {len(report['proposed'])} proposed, env +{len(report['env_added'])} -> {rj}, {rm}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
