#!/usr/bin/env python3
"""scaffold.py — write the docs/ADR/CI skeleton, plus a minimal runnable application, into a target directory.

Idempotent: never overwrites an existing file. Re-running reports 0 writes.
Existing repo: every kept Markdown file is read and compared with its template's `##` sections; the
sections it lacks are reported as gaps (`gap    <file>: missing sections — A, B`) for a by-hand merge.

Application skeleton (--stack nextjs-js | nextjs-ts, default nextjs-js): written ONLY when the target has
no package.json — a repo that already has one keeps its application untouched and the skeleton is not
planned at all. The skeleton is the smallest app the rest of the factory can work on: package.json (next,
react, vitest; scripts dev/build/start/lint/typecheck/test), next.config.js with the security-header
baseline, jsconfig.json | tsconfig.json with the `@/*` alias, .eslintrc.json, vitest.config, app/layout,
app/page (placeholder), app/api/health/route ({ok: true} liveness, no dependency calls), lib/app-info,
tests/unit/health.test exercising the route, .gitignore. No network, no Supabase client — that is feature
work. After bootstrap, scripts/stack_profile.py reads framework=nextjs, flavour=js|ts, test_runner=vitest,
package_manager=npm.

--report writes JSON {target, stack, written[], kept[], gaps[{path, missing[]}], app_skeleton: written|kept}.
Stdlib only. Run offline:
  python3 -I scaffold.py --target <dir> --name "<project>" [--stack nextjs-js|nextjs-ts] [--multi-tenant] [--dry-run] [--report r.json]

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


STACKS = ("nextjs-js", "nextjs-ts")

# Pinned ranges — every one is a published release; `npm install` resolves them, nothing here runs it.
VERSIONS = {
    "next": "^14.2.15", "react": "^18.3.1", "react-dom": "^18.3.1",
    "vitest": "^2.1.8", "@vitest/coverage-v8": "^2.1.8",
    "eslint": "^8.57.1", "eslint-config-next": "^14.2.15",
    "typescript": "^5.6.3", "@types/node": "^20.17.6", "@types/react": "^18.3.12", "@types/react-dom": "^18.3.1",
}

NEXT_CONFIG = """// next.config.js — security-header baseline (shared/stack-conventions.md). Keep headers here, not in middleware.
// CSP is deliberately not set yet: a nonce-based policy belongs to the first feature that ships scripts
// [TO BE BASELINED — owner: Tech lead].
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "X-DNS-Prefetch-Control", value: "off" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

module.exports = nextConfig;
"""

GITIGNORE = """# dependencies
node_modules/
# next.js
.next/
out/
# tests
coverage/
# env — never commit secrets; .env.example is the contract
.env*
!.env.example
# misc
.DS_Store
*.log
.vercel
*.tsbuildinfo
"""

ESLINTRC = """{
  "extends": "next/core-web-vitals"
}
"""


def _pkg_name(name: str) -> str:
    """npm-safe package name: lower-case, [a-z0-9-], no leading dash."""
    slug = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    return slug or "app"


def app_skeleton(name: str, stack: str) -> list[tuple[str, str]]:
    """(destination relative to target, content) for the minimal runnable Next.js app of the given stack."""
    ts = stack == "nextjs-ts"
    ext, xext = ("ts", "tsx") if ts else ("js", "js")
    pkg_name = _pkg_name(name)
    dev_deps = {"vitest": VERSIONS["vitest"], "@vitest/coverage-v8": VERSIONS["@vitest/coverage-v8"],
                "eslint": VERSIONS["eslint"], "eslint-config-next": VERSIONS["eslint-config-next"]}
    if ts:
        dev_deps.update({k: VERSIONS[k] for k in ("typescript", "@types/node", "@types/react", "@types/react-dom")})
    package_json = {
        "name": pkg_name,
        "version": "0.1.0",
        "private": True,
        "packageManager": "npm@10.8.2",
        "engines": {"node": ">=20"},
        "scripts": {
            "dev": "next dev",
            "build": "next build",
            "start": "next start",
            "lint": "next lint",
            "typecheck": "tsc --noEmit" if ts else "node -e \"console.error('typecheck: JavaScript project, no tsc; bootstrap with --stack nextjs-ts for type checking')\"",
            "test": "vitest run",
            "test:watch": "vitest",
        },
        "dependencies": {"next": VERSIONS["next"], "react": VERSIONS["react"], "react-dom": VERSIONS["react-dom"]},
        "devDependencies": dict(sorted(dev_deps.items())),
    }
    if ts:
        lang_config = ("tsconfig.json", json.dumps({
            "compilerOptions": {
                "target": "ES2022", "lib": ["dom", "dom.iterable", "esnext"], "allowJs": True, "skipLibCheck": True,
                "strict": True, "noEmit": True, "esModuleInterop": True, "module": "esnext",
                "moduleResolution": "bundler", "resolveJsonModule": True, "isolatedModules": True, "jsx": "preserve",
                "incremental": True, "plugins": [{"name": "next"}], "baseUrl": ".", "paths": {"@/*": ["./*"]},
            },
            "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
            "exclude": ["node_modules"],
        }, indent=2) + "\n")
    else:
        lang_config = ("jsconfig.json", json.dumps({
            "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./*"]}},
        }, indent=2) + "\n")

    vitest_config = f"""// vitest.config.{ext} — unit tests under tests/unit; coverage summary feeds the CI gate (coverage-summary.json).
import {{ defineConfig }} from "vitest/config";
import {{ fileURLToPath }} from "node:url";

export default defineConfig({{
  resolve: {{ alias: {{ "@": fileURLToPath(new URL("./", import.meta.url)) }} }},
  test: {{
    environment: "node",
    include: ["tests/unit/**/*.test.{{js,jsx,ts,tsx}}"],
    coverage: {{
      provider: "v8",
      reporter: ["text", "json-summary"],
      include: ["app/api/**", "lib/**"],
    }},
  }},
}});
"""

    app_info = f"""// lib/app-info.{ext} — build facts for the health route and pages. No I/O, no dependencies.
export function appInfo() {{
  return {{
    name: {json.dumps(pkg_name)},
    version: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "local",
    env: process.env.VERCEL_ENV ?? process.env.NODE_ENV ?? "development",
  }};
}}
"""

    health_route = f"""// app/api/health/route.{ext} — liveness. No dependency calls (that is /api/health/deep). Never cached.
import {{ NextResponse }} from "next/server";
import {{ appInfo }} from "@/lib/app-info";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET() {{
  return NextResponse.json(
    {{ ok: true, status: "ok", ...appInfo(), ts: new Date().toISOString() }},
    {{ headers: {{ "Cache-Control": "no-store" }} }},
  );
}}
"""

    children = "{ children }: { children: React.ReactNode }" if ts else "{ children }"
    type_import = 'import type { Metadata } from "next";\n\n' if ts else ""
    layout = f"""// app/layout.{xext} — root layout. Fonts, providers and navigation are feature work.
{type_import}export const metadata{": Metadata" if ts else ""} = {{
  title: {json.dumps(name)},
  description: "[TO BE BASELINED — owner: Product]",
}};

export default function RootLayout({children}) {{
  return (
    <html lang="en">
      <body>{{children}}</body>
    </html>
  );
}}
"""

    page = f"""// app/page.{xext} — placeholder until the first feature lands (spec-to-plan). Server component; no data access here.
import {{ appInfo }} from "@/lib/app-info";

export default function HomePage() {{
  const info = appInfo();
  return (
    <main>
      <h1>{name}</h1>
      <p>Bootstrapped. Replace this page with the first feature.</p>
      <p>
        <code>{{info.name}}</code> · {{info.env}} · {{info.version}} · <a href="/api/health">/api/health</a>
      </p>
    </main>
  );
}}
"""

    health_test = f"""// tests/unit/health.test.{ext} — the liveness route answers {{ ok: true }} and is never cached.
import {{ describe, it, expect }} from "vitest";
import {{ GET }} from "@/app/api/health/route";
import {{ appInfo }} from "@/lib/app-info";

describe("GET /api/health", () => {{
  it("returns ok: true with build facts and a timestamp", async () => {{
    const res = GET();
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.status).toBe("ok");
    expect(body.name).toBe(appInfo().name);
    expect(typeof body.version).toBe("string");
    expect(Number.isNaN(Date.parse(body.ts))).toBe(false);
  }});
}});

describe("appInfo", () => {{
  it("names the app and falls back to local/development without Vercel env", () => {{
    const info = appInfo();
    expect(info.name).toBe({json.dumps(pkg_name)});
    expect(info.version.length).toBeGreaterThan(0);
    expect(info.env.length).toBeGreaterThan(0);
  }});
}});
"""

    files: list[tuple[str, str]] = [
        ("package.json", json.dumps(package_json, indent=2) + "\n"),
        ("next.config.js", NEXT_CONFIG),
        lang_config,
        (".eslintrc.json", ESLINTRC),
        (f"vitest.config.{ext}", vitest_config),
        (f"app/layout.{xext}", layout),
        (f"app/page.{xext}", page),
        (f"app/api/health/route.{ext}", health_route),
        (f"lib/app-info.{ext}", app_info),
        (f"tests/unit/health.test.{ext}", health_test),
        (".gitignore", GITIGNORE),
    ]
    return files


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


def plan(target: Path, name: str, multi_tenant: bool, stack: str = "nextjs-js") -> list[tuple[Path, str]]:
    """Docs/ADR/CI files always; the application skeleton only when the target has no package.json yet."""
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
    if not (target / "package.json").is_file():
        out += [(target / rel, content) for rel, content in app_skeleton(name, stack)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Idempotent project scaffold (docs/ADR/CI + minimal runnable app).")
    ap.add_argument("--target", required=True, help="target project directory")
    ap.add_argument("--name", required=True, help="project name")
    ap.add_argument("--stack", default="nextjs-js", choices=STACKS,
                    help="application skeleton to write when the target has no package.json (default: nextjs-js)")
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
    has_app = (target / "package.json").is_file()
    report = {"target": str(target), "dry_run": args.dry_run, "stack": args.stack,
              "app_skeleton": "kept" if has_app else "written",
              "written": [], "kept": [], "gaps": []}
    if has_app:
        skipped += 1
        report["kept"].append("package.json")
        print(f"keep   package.json (application present; no {args.stack} skeleton written)")
    for path, content in plan(target, args.name, args.multi_tenant, args.stack):
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
