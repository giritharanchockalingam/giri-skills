import type { Verdict, AgentVerdict } from "./data";

export type Tone = "sage" | "hold" | "deep" | "rust" | "none";

export interface VerdictInfo {
  code: Verdict;
  /** Human label shown in pills, legends and filters. */
  label: string;
  /** Short imperative used in sentences ("need a better description"). */
  tone: Tone;
  /** Lower is worse. Used as the default sort of every scorecard/list. */
  severity: number;
  /** One plain sentence; the rule behind the code, shown as a tooltip. */
  explanation: string;
}

export const VERDICT_INFO: Record<Verdict, VerdictInfo> = {
  BOTH: { code: "BOTH", label: "Fix both", tone: "rust", severity: 0, explanation: "Trigger below 0.8 and lift below +0.2 — the description misroutes and the instructions do not help." },
  DESC: { code: "DESC", label: "Fix description", tone: "hold", severity: 1, explanation: "Trigger below 0.8 — the router does not reliably pick this skill for its own prompts." },
  BODY: { code: "BODY", label: "Fix instructions", tone: "deep", severity: 2, explanation: "Lift below +0.2 — loading the SKILL.md barely changes the output." },
  OK: { code: "OK", label: "Healthy", tone: "sage", severity: 3, explanation: "Trigger at or above 0.8 and lift at or above +0.2." },
};

export const NO_VERDICT: VerdictInfo = { code: "OK", label: "Not evaluated", tone: "none", severity: 4, explanation: "No scorecard row for this skill." };

export const verdictInfo = (v: Verdict | null | undefined): VerdictInfo => (v ? VERDICT_INFO[v] : NO_VERDICT);
export const verdictLabel = (v: Verdict | null | undefined) => verdictInfo(v).label;
export const verdictSeverity = (v: Verdict | null | undefined) => verdictInfo(v).severity;

/** Verdicts ordered worst first. */
export const VERDICTS_BY_SEVERITY: Verdict[] = ["BOTH", "DESC", "BODY", "OK"];
/** Verdicts ordered for a legend (good → bad). */
export const VERDICTS_FOR_LEGEND: Verdict[] = ["OK", "DESC", "BODY", "BOTH"];

/** Filter keys for verdict selects. Composite keys map to several codes. */
export type VerdictFilter = "all" | "needs-work" | "needs-desc" | "needs-body" | Verdict;

export const VERDICT_FILTERS: { key: VerdictFilter; label: string; codes: Verdict[] | null }[] = [
  { key: "all", label: "All verdicts", codes: null },
  { key: "needs-work", label: "Needs work", codes: ["BOTH", "DESC", "BODY"] },
  { key: "needs-desc", label: "Needs a better description", codes: ["BOTH", "DESC"] },
  { key: "needs-body", label: "Needs stronger instructions", codes: ["BOTH", "BODY"] },
  { key: "OK", label: "Healthy", codes: ["OK"] },
  { key: "DESC", label: "Fix description", codes: ["DESC"] },
  { key: "BODY", label: "Fix instructions", codes: ["BODY"] },
  { key: "BOTH", label: "Fix both", codes: ["BOTH"] },
];

export const isVerdictFilter = (s: string | null | undefined): s is VerdictFilter => !!s && VERDICT_FILTERS.some((f) => f.key === s);

export const matchesVerdictFilter = (filter: VerdictFilter, v: Verdict | null | undefined): boolean => {
  const codes = VERDICT_FILTERS.find((f) => f.key === filter)?.codes ?? null;
  if (codes === null) return true;
  return !!v && codes.includes(v);
};

/** Headline numbers for a set of verdicts: N need work, D need a better description, B need stronger instructions. */
export interface VerdictSummary { total: number; healthy: number; needsWork: number; needsDesc: number; needsBody: number; counts: Record<Verdict, number> }

export const summarize = (verdicts: (Verdict | null | undefined)[]): VerdictSummary => {
  const counts: Record<Verdict, number> = { OK: 0, DESC: 0, BODY: 0, BOTH: 0 };
  for (const v of verdicts) if (v) counts[v]++;
  const total = verdicts.length;
  return {
    total, counts,
    healthy: counts.OK,
    needsWork: counts.DESC + counts.BODY + counts.BOTH,
    needsDesc: counts.DESC + counts.BOTH,
    needsBody: counts.BODY + counts.BOTH,
  };
};

/** The one-sentence conclusion every eval view opens with. */
export const conclusionSentence = (s: VerdictSummary, a?: AgentSummary) =>
  `${s.needsWork} of ${s.total} skills need work — ${s.needsDesc} need a better description, ${s.needsBody} need stronger instructions.` +
  (a ? ` ${agentClause(a)}` : "");

/* ───────────── Agent run verdicts (deterministic: scripts ran, outputs passed their checks) ───────────── */

export interface AgentVerdictInfo { code: AgentVerdict; label: string; tone: Tone; severity: number; explanation: string }

export const AGENT_VERDICT_INFO: Record<AgentVerdict, AgentVerdictInfo> = {
  Broken: { code: "Broken", label: "Broken", tone: "rust", severity: 0, explanation: "Fewer than half of the output checks passed — the scripts fail or the deliverables are missing." },
  Partial: { code: "Partial", label: "Partial", tone: "hold", severity: 1, explanation: "Between 50% and 90% of the output checks passed — it runs, but some deliverables fail their checks." },
  Works: { code: "Works", label: "Works", tone: "sage", severity: 2, explanation: "At least 90% of the output checks passed — the scripts produce every deliverable and the checks hold." },
};
export const NO_AGENT_VERDICT: AgentVerdictInfo = { code: "Works", label: "Not wired", tone: "none", severity: 3, explanation: "No agent cases ran for this skill." };

/** Column tooltip for every "Runs" column. */
export const AGENT_COL_TIP = "Deterministic: did the skill's scripts produce the deliverables and pass their output checks (dry provider)";

export const agentVerdictInfo = (v: AgentVerdict | null | undefined): AgentVerdictInfo => (v ? AGENT_VERDICT_INFO[v] : NO_AGENT_VERDICT);
export const agentVerdictSeverity = (v: AgentVerdict | null | undefined) => agentVerdictInfo(v).severity;

export type AgentFilter = "all" | AgentVerdict | "none";
export const AGENT_FILTERS: { key: AgentFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "Works", label: "Works" },
  { key: "Partial", label: "Partial" },
  { key: "Broken", label: "Broken" },
  { key: "none", label: "Not wired" },
];
export const isAgentFilter = (s: string | null | undefined): s is AgentFilter => !!s && AGENT_FILTERS.some((f) => f.key === s);
export const matchesAgentFilter = (filter: AgentFilter, v: AgentVerdict | null | undefined): boolean =>
  filter === "all" ? true : filter === "none" ? !v : v === filter;

export interface AgentSummary { total: number; ran: number; works: number; partial: number; broken: number }
export const summarizeAgent = (verdicts: (AgentVerdict | null | undefined)[]): AgentSummary => {
  const c = { Works: 0, Partial: 0, Broken: 0 };
  for (const v of verdicts) if (v) c[v]++;
  return { total: verdicts.length, ran: c.Works + c.Partial + c.Broken, works: c.Works, partial: c.Partial, broken: c.Broken };
};

/** Second clause of the conclusion: "All 40 run end-to-end as agents (40 Works)" or the real counts. */
export const agentClause = (a: AgentSummary) => {
  const parts = [`${a.works} Works`];
  if (a.partial) parts.push(`${a.partial} Partial`);
  if (a.broken) parts.push(`${a.broken} Broken`);
  const head = a.works === a.total ? `All ${a.total} run end-to-end as agents` : `${a.works} of ${a.total} run end-to-end as agents`;
  return `${head} (${parts.join(", ")}).`;
};
