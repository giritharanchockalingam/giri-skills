import skillsJson from "@/data/skills.json";
import scorecardJson from "@/data/scorecard.json";
import triggerJson from "@/data/trigger.json";
import qualityJson from "@/data/quality.json";
import findingsJson from "@/data/findings.json";
import metaJson from "@/data/meta.json";

export type Verdict = "OK" | "DESC" | "BODY" | "BOTH";

export interface EvalCase { id: string; prompt: string; expected: string[] }
export interface Skill {
  id: string; domain: string; name: string; description: string; license: string | null;
  metadata: Record<string, string>; bodyHtml: string;
  files: { references: string[]; assets: string[]; scripts: string[] };
  cases: EvalCase[];
}
export interface ScoreRow {
  skill: string; domain: string; name: string;
  triggerAcc: number; fpRate: number; without: number; with: number; lift: number; verdict: Verdict;
}
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
  spend: string | null; resultsDir: string;
  counts: { skills: number; scorecard: number; trigger: number; quality: number; findings: number };
  domains: string[]; verdicts: Verdict[];
}

export const skills = skillsJson as Skill[];
export const scorecard = scorecardJson as ScoreRow[];
export const trigger = triggerJson as TriggerRow[];
export const quality = qualityJson as QualityRow[];
export const findings = findingsJson as Findings;
export const meta = metaJson as Meta;

export const DOMAINS = meta.domains;
export const VERDICTS = meta.verdicts;

const scoreById = new Map(scorecard.map((r) => [r.skill, r]));
const proposalById = new Map(findings.proposals.map((p) => [p.skill, p]));

export const scoreFor = (id: string) => scoreById.get(id) ?? null;
export const proposalFor = (id: string) => proposalById.get(id) ?? null;
export const skillFor = (id: string) => skills.find((s) => s.id === id) ?? null;

export const skillHref = (id: string) => `/skills/${id}/`;

/** Catalog row: skill + score merged. */
export interface CatalogRow {
  id: string; name: string; domain: string; description: string; verdict: Verdict | null;
  triggerAcc: number | null; lift: number | null; cases: number; scripts: number;
}
export const catalogRows = (): CatalogRow[] =>
  skills.map((s) => {
    const sc = scoreFor(s.id);
    return {
      id: s.id, name: s.name, domain: s.domain, description: s.description, verdict: sc?.verdict ?? null,
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

export const fmt = (n: number | null | undefined, digits = 2) => (n == null || Number.isNaN(n) ? "—" : n.toFixed(digits));
export const fmtLift = (n: number | null | undefined) => (n == null ? "—" : (n > 0 ? "+" : "") + n.toFixed(2));
