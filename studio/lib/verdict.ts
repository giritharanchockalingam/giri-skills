import type { Verdict } from "./data";

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
export const conclusionSentence = (s: VerdictSummary) =>
  `${s.needsWork} of ${s.total} skills need work — ${s.needsDesc} need a better description, ${s.needsBody} need stronger instructions.`;
