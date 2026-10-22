/* Scorecard checks: which library skill scores which kind of repository, which files it needs, and how its real
 * output becomes a verdict. Pure (no I/O): the engine (run.ts) fetches the files and runs the skill on the runtime.
 * A verdict is always read from the skill's own report — never computed separately — so the scorecard says
 * exactly what the skill said. */

export type Verdict = "pass" | "warn" | "fail" | "error" | "skipped";
export interface TreeFile { path: string; sha: string; size: number }
export interface EntityFacts { stackIds: string[]; counts: { migrations: number; files: number } }
export interface CheckOutput { path: string; content_text: string | null }
export interface Scored { verdict: Verdict; summary: string; findings: number | null }

export const MAX_FILES = 200;
export const MAX_BYTES = 2 * 1024 * 1024;
const SKIP = /(^|\/)(node_modules|\.next|dist|build|vendor|\.venv|__pycache__|coverage|fixtures|__fixtures__)\//;   // fixtures: sample repos inside a repo

export interface CheckDef {
  id: string;
  title: string;                 // what a person reads in the scorecard
  skill: string;                 // library skill that does the work
  applies: (e: EntityFacts) => boolean;
  /** Repository files the check needs, as input name → files (each becomes a folder input) */
  select: (files: TreeFile[]) => { input: string; files: TreeFile[]; strip: string }[];
  values?: Record<string, string>;           // fixed scalar inputs
  primary: string;                           // the output whose content is the evidence shown
  score: (outs: CheckOutput[], status: string) => Scored;
}

const out = (outs: CheckOutput[], p: string) => outs.find((o) => o.path === p)?.content_text ?? null;
const keep = (files: TreeFile[], re: RegExp) => files.filter((f) => re.test(f.path) && !SKIP.test(f.path));
/** The directory a set of files shares (stripped so the skill sees the folder's own layout). */
export function commonDir(paths: string[]): string {
  if (!paths.length) return "";
  const parts = paths[0].split("/").slice(0, -1);
  let n = parts.length;
  for (const p of paths) { const q = p.split("/"); while (n && q.slice(0, n).join("/") !== parts.slice(0, n).join("/")) n--; }
  return parts.slice(0, n).join("/");
}
const bold = (md: string | null) => md?.match(/\*\*([^*]+)\*\*/)?.[1]?.trim() ?? null;

export const CHECKS: CheckDef[] = [
  {
    id: "rls", title: "Database security (row-level security)", skill: "build/supabase-schema-rls",
    applies: (e) => e.counts.migrations > 0,
    select: (files) => { const m = keep(files, /(^|\/)supabase\/migrations\/[^/]+\.sql$/); return [{ input: "migrations", files: m, strip: commonDir(m.map((f) => f.path)) }]; },
    primary: "rls-lint.txt",
    score: (outs) => {
      const t = out(outs, "rls-lint.txt");
      const m = t?.match(/rls_lint:\s*(\d+)\s+findings?,\s*(\d+)\s+errors?/);
      if (!m) return { verdict: "error", summary: "no lint summary in the output", findings: null };
      const [findings, errors] = [Number(m[1]), Number(m[2])];
      return { verdict: errors > 0 ? "fail" : findings > 0 ? "warn" : "pass", summary: `${errors} error(s), ${findings - errors} warning(s) in the migrations`, findings };
    },
  },
  {
    id: "tenancy", title: "Tenant isolation", skill: "build/multi-tenant-saas-patterns",
    applies: (e) => e.counts.migrations > 0,
    select: (files) => { const m = keep(files, /(^|\/)supabase\/migrations\/[^/]+\.sql$/); return [{ input: "migrations", files: m, strip: commonDir(m.map((f) => f.path)) }]; },
    values: { tenant_column: "auto" },
    primary: "audit.md",
    score: (outs) => {
      const md = out(outs, "audit.md");
      const m = md?.match(/(\d+) table\(s\) in \d+ migration file\(s\): (\d+) with findings/);
      if (!m) return { verdict: "error", summary: "no audit summary in the output", findings: null };
      const key = md?.match(/Tenancy key: `([^`]+)`/)?.[1];
      const bad = Number(m[2]);
      return { verdict: bad > 0 ? "fail" : "pass", summary: `${bad} of ${m[1]} tables need tenancy fixes${key ? ` (key: ${key})` : ""}`, findings: bad };
    },
  },
  {
    id: "nextjs", title: "Next.js conventions", skill: "build/nextjs-enterprise-conventions",
    applies: (e) => e.stackIds.includes("nextjs"),
    select: (files) => {
      const src = keep(files, /^(?:(?:[^/]+\/)?)(app|components|lib|server|src)\/.+\.(tsx?|jsx?|mjs)$/).filter((f) => !/\.(test|spec)\.|\.d\.ts$/.test(f.path));
      // a monorepo: score the Next.js app folder (the one holding next.config.*)
      const cfg = keep(files, /(^|\/)next\.config\.(js|mjs|ts|cjs)$/)[0];
      const root = cfg ? cfg.path.split("/").slice(0, -1).join("/") : "";
      const scoped = root ? src.filter((f) => f.path.startsWith(root + "/")) : src.filter((f) => !f.path.includes("/") || /^(app|components|lib|server|src)\//.test(f.path));
      return [{ input: "target", files: scoped, strip: root }];
    },
    primary: "report.md",
    score: (outs) => {
      const s = bold(out(outs, "report.md"));
      const m = s?.match(/(\d+) finding\(s\) in (\d+) file\(s\): (\d+) high, (\d+) medium/);
      if (!m) return { verdict: "error", summary: "no lint summary in the output", findings: null };
      const [n, f, high, med] = m.slice(1).map(Number);
      return { verdict: high > 0 ? "fail" : med > 0 ? "warn" : "pass", summary: `${high} high, ${med} medium finding(s) in ${f} file(s)`, findings: n };
    },
  },
  {
    id: "observability", title: "Observability (logging, health, alerts)", skill: "build/observability-setup",
    applies: (e) => e.stackIds.includes("nextjs"),
    select: (files) => {
      const cfg = keep(files, /(^|\/)next\.config\.(js|mjs|ts|cjs)$/)[0];
      const root = cfg ? cfg.path.split("/").slice(0, -1).join("/") : "";
      const pre = root ? root + "/" : "";
      const re = new RegExp(`^${pre.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(package\\.json|\\.env\\.example|lib/logger(\\.ts|/.+)|app/api/health/.+|ops/alerts\\.ya?ml|docs/observability\\.md)$`);
      return [{ input: "seed", files: keep(files, re), strip: root }];
    },
    values: { dry_run: "true" },
    primary: "install-report.md",
    score: (outs) => {
      const raw = out(outs, "install-report.json");
      if (!raw) return { verdict: "error", summary: "no install report in the output", findings: null };
      let j: { written?: string[]; proposed?: string[]; env_added?: string[] };
      try { j = JSON.parse(raw); } catch { return { verdict: "error", summary: "install report is not valid JSON", findings: null }; }
      // the check is about PRESENCE: a piece that exists with the team's own content is in place (reported, not failed)
      const missing = (j.written ?? []).length, custom = (j.proposed ?? []).length;
      return { verdict: missing >= 3 ? "fail" : missing > 0 ? "warn" : "pass",
        summary: missing ? `${missing} piece(s) missing: ${(j.written ?? []).slice(0, 3).join(", ")}${missing > 3 ? "…" : ""}`
          : `logging, health checks, alerts and runbook in place${custom ? ` (${custom} customised from the standard)` : ""}`, findings: missing };
    },
  },
];

/** Bound a file set to the runtime's folder limits; says when it had to cut (the scorecard shows it). */
export function bound(files: TreeFile[]): { files: TreeFile[]; partial: boolean } {
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));
  const outF: TreeFile[] = [];
  let bytes = 0;
  for (const f of sorted) {
    if (outF.length >= MAX_FILES || bytes + f.size > MAX_BYTES || f.size > 512 * 1024) continue;
    outF.push(f); bytes += f.size;
  }
  return { files: outF, partial: outF.length < files.length };
}

export const checksFor = (e: EntityFacts) => CHECKS.filter((c) => c.applies(e));

export const stripPaths = (t: string) => t.replace(/\/tmp\/sf\/[^\s/]+\/(inputs|out)\/?/g, "");
/** The last "error: …" / "gate: …" line a skill printed (its own explanation), without runtime paths. */
export function errorLine(logs: string | null | undefined): string | null {
  const lines = stripPaths(logs ?? "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const hit = [...lines].reverse().find((l) => /^(error|fatal)[:\s]|traceback|exception/i.test(l));
  return hit ? hit.replace(/^error:\s*/i, "").slice(0, 240) : null;
}
