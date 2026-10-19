import skillsJson from "@/data/skills.json";
import scorecardJson from "@/data/scorecard.json";
import triggerJson from "@/data/trigger.json";
import qualityJson from "@/data/quality.json";
import agentJson from "@/data/agent.json";
import findingsJson from "@/data/findings.json";
import metaJson from "@/data/meta.json";
import upstreamJson from "@/data/upstream.json";
import stagesJson from "@/data/stages.json";

export type Verdict = "OK" | "DESC" | "BODY" | "BOTH";
export type AgentVerdict = "Works" | "Partial" | "Broken";

export interface AgentInput { name: string; type: string; required: boolean; from: string; default: string | null; flag: string | null }
export interface AgentStep { step: string; kind: string }
export interface AgentOutput { path: string; checks: string[] }
/** The happy-path eval case `run_skill.py --demo` uses: input values (fixture paths relative to the skill dir) and assumptions. */
export interface AgentDemo { caseId: string; inputs: Record<string, string>; assume: Record<string, string> }
/** The `metadata.agent` block of SKILL.md: what run_skill.py needs, runs and checks. */
/** A starting point: "new" (greenfield, from scratch) or "existing" (brownfield, improve what exists), with its example. */
export type StartMode = "new" | "existing";
export interface AgentMode extends AgentDemo { bring: string }
export interface AgentSpec { inputs: AgentInput[]; steps: AgentStep[]; outputs: AgentOutput[]; demo: AgentDemo | null; modes?: Partial<Record<StartMode, AgentMode>> }

export interface EvalCase { id: string; prompt: string; expected: string[] }
export interface Skill {
  id: string; domain: string; stage: string | null; name: string; description: string; license: string | null;
  metadata: Record<string, string>; agent: AgentSpec | null; bodyHtml: string;
  files: { references: string[]; assets: string[]; scripts: string[] };
  cases: EvalCase[];
}
export interface ScoreRow {
  skill: string; domain: string; name: string;
  /** Behavioural (model-graded) results; null when the skill has not been through a behavioural eval run yet. */
  triggerAcc: number | null; fpRate: number | null; without: number | null; with: number | null; lift: number | null; verdict: Verdict | null;
  /** Share of agent checks passed (0–1), null when the skill has no agent cases. */
  agentPass: number | null; agentVerdict: AgentVerdict | null;
}
export interface AgentRow { skill: string; caseId: string; check: string; pass: boolean; evidence: string }
export interface TriggerRow { skill: string; caseId: string; run: number; selected: string; correct: number | null }
export interface QualityRow {
  skill: string; caseId: string; run: number; mode: "without" | "with"; expectedIdx: number; pass: boolean; evidence: string;
}
export interface Proposal {
  number: number; skill: string; name: string; domain: string; verdict: Verdict; stats: string; evidence: string;
  descriptionProposal: string | null; bodyProposal: string | null;
}
export interface Findings {
  intro: string; caveatsHtml: string;
  verdictCounts: { domain: string; OK: number; DESC: number; BODY: number; BOTH: number }[];
  verdictNotesHtml: string; proposals: Proposal[];
}
export interface Meta {
  provider: string | null; model: string | null; runs: number | null; seed: number | null; date: string | null;
  spend: string | null; resultsDir: string; agentResultsDir: string;
  counts: { skills: number; scorecard: number; trigger: number; quality: number; findings: number; agent: number; agentWorks: number; upstream: number };
  domains: string[]; verdicts: Verdict[]; agentVerdicts: AgentVerdict[];
}

export const skills = skillsJson as unknown as Skill[]; // demo.inputs is a per-skill map; JSON inference makes it a union of literal shapes
export const scorecard = scorecardJson as ScoreRow[];
export const trigger = triggerJson as TriggerRow[];
export const quality = qualityJson as QualityRow[];
export const agent = agentJson as AgentRow[];
export const findings = findingsJson as Findings;
export const meta = metaJson as Meta;

export const DOMAINS = meta.domains;
export const VERDICTS = meta.verdicts;

const scoreById = new Map(scorecard.map((r) => [r.skill, r]));
const proposalById = new Map(findings.proposals.map((p) => [p.skill, p]));

export const scoreFor = (id: string) => scoreById.get(id) ?? null;
export const proposalFor = (id: string) => proposalById.get(id) ?? null;
export const skillFor = (id: string) => skills.find((s) => s.id === id) ?? null;

export const skillHref = (id: string) => `/repo/${id}/`;

/** Catalog row: skill + score merged. */
export interface CatalogRow {
  id: string; name: string; domain: string; description: string; verdict: Verdict | null; agentVerdict: AgentVerdict | null;
  triggerAcc: number | null; lift: number | null; cases: number; scripts: number;
}
export const catalogRows = (): CatalogRow[] =>
  skills.map((s) => {
    const sc = scoreFor(s.id);
    return {
      id: s.id, name: s.name, domain: s.domain, description: s.description, verdict: sc?.verdict ?? null, agentVerdict: sc?.agentVerdict ?? null,
      triggerAcc: sc?.triggerAcc ?? null, lift: sc?.lift ?? null, cases: s.cases.length, scripts: s.files.scripts.length,
    };
  });

/** Misrouted trigger rows for a skill (selected != expected name). */
export interface Misroute { caseId: string; prompt: string; run: number; selected: string }
export const misroutesFor = (id: string): Misroute[] => {
  const s = skillFor(id);
  return trigger
    .filter((t) => t.skill === id && t.correct === 0)
    .map((t) => ({ caseId: t.caseId, prompt: s?.cases.find((c) => c.id === t.caseId)?.prompt ?? "", run: t.run, selected: t.selected }))
    .sort((a, b) => a.caseId.localeCompare(b.caseId) || a.run - b.run);
};

/** Most-failed expected items in with-mode for a skill. */
export interface FailedItem { caseId: string; expectedIdx: number; expected: string; fails: number; total: number; evidence: string }
export const failedWithItemsFor = (id: string, limit = 5): FailedItem[] => {
  const s = skillFor(id);
  const map = new Map<string, FailedItem>();
  for (const q of quality) {
    if (q.skill !== id || q.mode !== "with") continue;
    const key = `${q.caseId}#${q.expectedIdx}`;
    const it = map.get(key) ?? {
      caseId: q.caseId, expectedIdx: q.expectedIdx,
      expected: s?.cases.find((c) => c.id === q.caseId)?.expected[q.expectedIdx] ?? `expected[${q.expectedIdx}]`,
      fails: 0, total: 0, evidence: "",
    };
    it.total++;
    if (!q.pass) { it.fails++; if (!it.evidence) it.evidence = q.evidence; }
    map.set(key, it);
  }
  return [...map.values()].filter((i) => i.fails > 0).sort((a, b) => b.fails - a.fails || a.caseId.localeCompare(b.caseId)).slice(0, limit);
};

/** Agent eval cases for a skill: case_id → its checks with pass/evidence, in file order. */
export interface AgentCase { caseId: string; checks: AgentRow[]; passed: number; total: number }
export const agentCasesFor = (id: string): AgentCase[] => {
  const out: AgentCase[] = [];
  for (const a of agent) {
    if (a.skill !== id) continue;
    let c = out.find((x) => x.caseId === a.caseId);
    if (!c) { c = { caseId: a.caseId, checks: [], passed: 0, total: 0 }; out.push(c); }
    c.checks.push(a); c.total++; if (a.pass) c.passed++;
  }
  return out;
};

export const fmt = (n: number | null | undefined, digits = 2) => (n == null || Number.isNaN(n) ? "—" : n.toFixed(digits));
export const fmtLift = (n: number | null | undefined) => (n == null ? "—" : (n > 0 ? "+" : "") + n.toFixed(2));

/** Per-domain roll-up of the scorecard (verdict counts, average trigger and lift). */
export interface DomainSummary {
  domain: string; n: number; counts: Record<Verdict, number>; needsWork: number; avgTrigger: number; avgLift: number;
  /** Skills whose agent run verdict is Works. */
  runs: number;
}
const rollup = (domain: string, rows: ScoreRow[]): DomainSummary => {
  const counts: Record<Verdict, number> = { OK: 0, DESC: 0, BODY: 0, BOTH: 0 };
  for (const r of rows) if (r.verdict) counts[r.verdict]++;
  // averages over skills that have been through a behavioural run (new skills are excluded, not counted as 0)
  const avg = (k: "triggerAcc" | "lift") => { const v = rows.map((r) => r[k]).filter((x): x is number => x != null); return v.length ? v.reduce((a, x) => a + x, 0) / v.length : 0; };
  return {
    domain, n: rows.length, counts, needsWork: rows.filter((r) => r.verdict && r.verdict !== "OK").length, avgTrigger: avg("triggerAcc"), avgLift: avg("lift"),
    runs: rows.filter((r) => r.agentVerdict === "Works").length,
  };
};
export const domainSummaries = (): { rows: DomainSummary[]; total: DomainSummary } => ({
  rows: DOMAINS.map((d) => rollup(d, scorecard.filter((r) => r.domain === d))),
  total: rollup("All domains", scorecard),
});

/* ───────────── Upstream: the 50 vendored public skills (catalog/top-50.json + vendor/pins.json + vendor/<name>/) ───────────── */

export type LicenseKind = "oss" | "source-available";
export type UpstreamOrigin = "vendor" | "community";
export interface UpstreamSkill {
  rank: number; name: string; repo: string; path: string; sha: string; shortSha: string;
  category: string; license: string; licenseKind: LicenseKind; origin: UpstreamOrigin;
  evidence: string; why: string; fetched: string | null; description: string; bodyHtml: string; fileCount: number;
  /** Pinned tree on GitHub: https://github.com/<repo>/tree/<sha>/<path> */
  url: string;
}

export const upstream = upstreamJson as UpstreamSkill[];

export const upstreamFor = (name: string) => upstream.find((u) => u.name === name) ?? null;
export const upstreamHref = (name: string) => `/upstream/${name}/`;

/** Catalog categories in display order (the four buckets of catalog/top-50.json), with human labels. */
export const UPSTREAM_CATEGORY_LABELS: Record<string, string> = {
  "engineering-workflow": "Engineering workflow",
  "framework-vendor": "Framework / vendor",
  "ai-agents-mcp-rag": "AI agents · MCP · RAG",
  "documents-productivity-business": "Documents · business",
};
export const UPSTREAM_CATEGORIES: string[] = [
  ...Object.keys(UPSTREAM_CATEGORY_LABELS).filter((c) => upstream.some((u) => u.category === c)),
  ...[...new Set(upstream.map((u) => u.category))].filter((c) => !(c in UPSTREAM_CATEGORY_LABELS)).sort(),
];
export const categoryLabel = (c: string) => UPSTREAM_CATEGORY_LABELS[c] ?? c;

/** Short license label for pills: MIT / Apache-2.0 / Source-available. The full text stays in `license`. */
export const licenseLabel = (u: Pick<UpstreamSkill, "license" | "licenseKind">) =>
  u.licenseKind === "source-available" ? "Source-available" : /^Apache/i.test(u.license) ? "Apache-2.0" : /^MIT/i.test(u.license) ? "MIT" : u.license;

export type LicenseFilter = "all" | "oss" | "source-available";
export const LICENSE_FILTERS: { key: LicenseFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "oss", label: "Open source" },
  { key: "source-available", label: "Source-available" },
];

export interface UpstreamSummary { total: number; vendor: number; community: number; oss: number; sourceAvailable: number }
export const upstreamSummary = (): UpstreamSummary => ({
  total: upstream.length,
  vendor: upstream.filter((u) => u.origin === "vendor").length,
  community: upstream.filter((u) => u.origin === "community").length,
  oss: upstream.filter((u) => u.licenseKind === "oss").length,
  sourceAvailable: upstream.filter((u) => u.licenseKind === "source-available").length,
});

/* ADLC stages (shared/adlc-stages.json) — the portal's primary organising axis. */
export interface Stage { id: string; n?: number; name: string; question: string }
export const STAGES = (stagesJson as { stages: Stage[]; shelves: Stage[] }).stages;
export const SHELVES = (stagesJson as { stages: Stage[]; shelves: Stage[] }).shelves;
export const stageName = (id: string | null | undefined) => [...STAGES, ...SHELVES].find((s) => s.id === id)?.name ?? "Unassigned";
export const stageOfRepoSkill = (id: string | null | undefined) => (id ? skills.find((s) => s.id === id)?.stage ?? null : null);
