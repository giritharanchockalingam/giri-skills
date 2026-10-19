/* Delivery metrics (DORA-style) for one repository, computed from GitHub records. Pure.
 * What each number is — and is not — travels with it, so nothing is presented as more than it measures:
 *  - Deployment frequency: production deployments GitHub recorded (e.g. Vercel's) when the App can read them;
 *    otherwise merges to the default branch (each one deploys when the repo auto-deploys from it).
 *  - Lead time: pull request opened → merged (median and p75). DORA's change lead time runs commit → production,
 *    so this approximates it.
 *  - Change failure rate: share of merges that revert or hotfix a change (title/branch), a proxy — no incident data.
 * Bands: DORA 2024 performance clusters for deployment frequency and lead time only (the 2024 change-failure bands
 * are not monotonic, so no band is given for it). */

export interface PrFact { number: number; title: string; head_ref: string; created_at: string; merged_at: string | null; closed_at: string | null; draft?: boolean }
export interface DeployFact { created_at: string; environment: string }
export type Band = "elite" | "high" | "medium" | "low";
export interface Delivery {
  window_days: number;
  deploys: { count: number; per_week: number; source: "deployments" | "merges"; band: Band | null };
  lead_time: { median_hours: number | null; p75_hours: number | null; samples: number; band: Band | null };
  change_failure: { rate: number | null; failures: number; of: number; examples: string[] };
  open_prs: { count: number; oldest_days: number | null };
  merges: number;
}

const HOUR = 3_600_000, DAY = 24 * HOUR;
const FAIL = /^(revert\b|hotfix\b|fix\(prod\)|rollback\b)|^revert-|(^|\/)hotfix[/-]/i;

export function percentile(xs: number[], p: number): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const i = (s.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}
const r1 = (n: number | null) => (n == null ? null : Math.round(n * 10) / 10);

/** DORA 2024: on demand (≥ once a day) · daily–weekly · weekly–monthly · less than monthly. */
export function frequencyBand(perWeek: number): Band { return perWeek >= 7 ? "elite" : perWeek >= 1 ? "high" : perWeek >= 12 / 52 ? "medium" : "low"; }
/** DORA 2024: < 1 day · 1 day–1 week · 1 week–1 month · longer. */
export function leadTimeBand(hours: number): Band { return hours < 24 ? "elite" : hours < 24 * 7 ? "high" : hours < 24 * 30 ? "medium" : "low"; }

export function computeDelivery(prs: PrFact[], deploys: DeployFact[] | null, windowDays: number, now = Date.now()): Delivery {
  const since = now - windowDays * DAY;
  const merged = prs.filter((p) => p.merged_at && Date.parse(p.merged_at) >= since && Date.parse(p.merged_at) <= now);
  const weeks = windowDays / 7;
  const prodDeploys = deploys?.filter((d) => /^prod/i.test(d.environment) && Date.parse(d.created_at) >= since) ?? null;
  const count = prodDeploys && prodDeploys.length > 0 ? prodDeploys.length : merged.length;
  const source = prodDeploys && prodDeploys.length > 0 ? "deployments" as const : "merges" as const;
  const perWeek = Math.round((count / weeks) * 10) / 10;
  const leads = merged.map((p) => (Date.parse(p.merged_at!) - Date.parse(p.created_at)) / HOUR).filter((h) => h >= 0);
  const med = percentile(leads, 0.5);
  const fails = merged.filter((p) => FAIL.test(p.title) || FAIL.test(p.head_ref));
  const open = prs.filter((p) => !p.closed_at && !p.merged_at && !p.draft);
  const oldest = open.length ? Math.max(...open.map((p) => (now - Date.parse(p.created_at)) / DAY)) : null;
  return {
    window_days: windowDays,
    deploys: { count, per_week: perWeek, source, band: count ? frequencyBand(perWeek) : null },
    lead_time: { median_hours: r1(med), p75_hours: r1(percentile(leads, 0.75)), samples: leads.length, band: med == null ? null : leadTimeBand(med) },
    change_failure: { rate: merged.length ? Math.round((fails.length / merged.length) * 1000) / 10 : null, failures: fails.length, of: merged.length, examples: fails.slice(0, 3).map((p) => `#${p.number} ${p.title}`.slice(0, 120)) },
    open_prs: { count: open.length, oldest_days: oldest == null ? null : Math.floor(oldest) },
    merges: merged.length,
  };
}

export const BAND_LABEL: Record<Band, string> = { elite: "Elite", high: "High", medium: "Medium", low: "Low" };
export const fmtHours = (h: number | null) => (h == null ? "—" : h < 1 ? `${Math.round(h * 60)} min` : h < 48 ? `${r1(h)} h` : `${r1(h / 24)} days`);
