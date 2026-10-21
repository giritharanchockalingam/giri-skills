/* The front door: what a person can get done, organised by role and task — not by the factory's internals.
 * Every example is a skill's own happy-path eval case: the prompt shown is the one whose fixture inputs the
 * "Try it" run uses, so what you click is what runs. Server only. */
import { skills as repoSkillsData } from "@/lib/data";
import { ROLE_TEMPLATES } from "@/lib/factory/talentData";
import { STAGES, SHELVES } from "@/lib/data";
import { humanName } from "@/lib/names";
import type { StartMode } from "@/lib/data";

type RepoRow = { id: string; name: string; stage?: string | null; description: string; agent?: { demo?: { caseId: string } | null } | null; cases?: { id: string; prompt?: string }[] };
const REPO = repoSkillsData as unknown as RepoRow[];
const BY_ID = new Map(REPO.map((s) => [s.id, s]));

export { whatYouGet } from "@/lib/names";
import { whatYouGet } from "@/lib/names";

export interface Example { skill: string; name: string; prompt: string }

/** The prompt of the eval case the skill's demo runs (null when the skill has no runnable example). */
export function exampleFor(id: string): Example | null {
  const s = BY_ID.get(id);
  const caseId = s?.agent?.demo?.caseId;
  if (!s || !caseId) return null;
  const c = (s.cases ?? []).find((x) => x.id === caseId);
  if (!c?.prompt) return null;
  return { skill: id, name: s.name, prompt: c.prompt.length > 160 ? c.prompt.slice(0, 157).replace(/\s+\S*$/, "") + "…" : c.prompt };
}

export const tryHref = (skillId: string, task?: string) =>
  `/repo/${skillId}/test?example=1${task ? `&task=${encodeURIComponent(task.slice(0, 300))}` : ""}`;
export const ownHref = (skillId: string, task?: string) =>
  `/repo/${skillId}/test${task ? `?task=${encodeURIComponent(task.slice(0, 300))}` : ""}`;

const GROUPS: { title: string; roles: string[] }[] = [
  { title: "Build and ship", roles: ["full-stack-engineer", "llm-agent-engineer", "ai-solution-architect", "ai-data-engineer", "ai-product-manager", "conversation-ux-designer"] },
  { title: "Test, secure and govern", roles: ["ai-quality-red-team", "data-scientist", "ai-security-engineer", "responsible-ai-lead", "ai-privacy-compliance-officer", "ai-risk-release-lead"] },
  { title: "Run and improve", roles: ["ai-ops-sre", "mlops-platform-engineer", "ai-finops-analyst", "annotation-data-ops-lead", "ai-program-manager", "ai-change-adoption-lead", "ai-strategist"] },
  { title: "Business", roles: ["presales-solution-architect", "bid-proposal-lead", "client-partner", "career-coach"] },
];

export interface RoleCard { slug: string; title: string; description: string; skills: number; examples: Example[] }

export function roleGroups(): { title: string; cards: RoleCard[] }[] {
  const tpl = new Map(ROLE_TEMPLATES.map((r) => [r.name, r]));
  const placed = new Set(GROUPS.flatMap((g) => g.roles));
  const groups = GROUPS.map((g) => ({ title: g.title, roles: g.roles }));
  const rest = ROLE_TEMPLATES.map((r) => r.name).filter((n) => !placed.has(n));
  if (rest.length) groups.push({ title: "More roles", roles: rest });
  return groups.map((g) => ({
    title: g.title,
    cards: g.roles.map((n) => tpl.get(n)).filter(Boolean).map((r) => ({
      slug: r!.name, title: r!.title, description: r!.description, skills: r!.skills.length,
      examples: r!.skills.map(exampleFor).filter((e): e is Example => !!e).slice(0, 3),
    })),
  }));
}

/** Which role templates bring a skill (for "who does this"). */
export function ownersOf(skillId: string): string[] {
  return ROLE_TEMPLATES.filter((r) => r.skills.includes(skillId)).map((r) => r.title);
}

// ---------- lifecycle view ----------

type ModeRow = { bring: string; caseId: string };
type LifeRow = RepoRow & { card?: string; agent?: { demo?: { caseId: string } | null; modes?: Partial<Record<StartMode, ModeRow>> } | null };
const LIFE = REPO as LifeRow[];

export const PHASES: { id: string; title: string; stages: string[] }[] = [
  { id: "plan", title: "Plan", stages: ["strategy", "use-case", "data", "requirements"] },
  { id: "build", title: "Build", stages: ["architecture", "build", "evaluate"] },
  { id: "ship", title: "Ship", stages: ["govern", "deploy"] },
  { id: "run", title: "Run", stages: ["operate", "improve"] },
  { id: "business", title: "Business", stages: ["opportunity", "career"] },
];

export interface StageTab { id: string; n: number | null; name: string; question: string; count: number; why: string | null /* set when this starting point does not apply to the stage */ }
export interface SkillRowView { id: string; name: string; outcome: string; bring: string | null; runnable: boolean; owners: string[] }

const roleSkills = (role?: string | null) => {
  const r = role ? ROLE_TEMPLATES.find((x) => x.name === role) : null;
  return r ? new Set(r.skills) : null;
};
const inStage = (s: LifeRow, stage: string) => (Array.isArray(s.stage) ? s.stage.includes(stage) : s.stage === stage);
/** Skills that serve a starting point: those that declare it; skills that declare no modes yet show under both. */
const serves = (s: LifeRow, mode: StartMode) => { const m = s.agent?.modes; return !m || !Object.keys(m).length || !!m[mode]; };

export function lifecycle(mode: StartMode, role?: string | null): { id: string; title: string; stages: StageTab[] }[] {
  const only = roleSkills(role);
  const meta = new Map([...STAGES, ...SHELVES].map((s) => [s.id, s as { id: string; n?: number; name: string; question: string; modes?: StartMode[]; modes_why?: string }]));
  return PHASES.map((p) => ({
    id: p.id, title: p.title,
    stages: p.stages.map((id) => {
      const m = meta.get(id)!;
      const count = LIFE.filter((s) => inStage(s, id) && serves(s, mode) && (!only || only.has(s.id))).length;
      const why = m.modes && !m.modes.includes(mode) ? m.modes_why ?? "This starting point does not apply here." : null;
      return { id, n: m.n ?? null, name: m.name.replace(/^Business · /, ""), question: m.question, count: why ? 0 : count, why };
    }),
  }));
}

export function stageSkills(stage: string, mode: StartMode, role?: string | null): { rows: SkillRowView[]; otherMode: number } {
  const only = roleSkills(role);
  const all = LIFE.filter((s) => inStage(s, stage) && (!only || only.has(s.id)));
  const rows = all.filter((s) => serves(s, mode)).map((s) => ({
    id: s.id, name: humanName(s.id.split("/")[1]), outcome: s.card || whatYouGet(s.description),
    bring: s.agent?.modes?.[mode]?.bring ?? null, runnable: !!(s.agent?.modes?.[mode] || s.agent?.demo), owners: ownersOf(s.id),
  }));
  return { rows, otherMode: all.length - rows.length };
}

export const roleOptions = () => ROLE_TEMPLATES.map((r) => ({ slug: r.name, title: r.title })).sort((a, b) => a.title.localeCompare(b.title));
export const modeHref = (skillId: string, mode: StartMode, example: boolean) =>
  `/repo/${skillId}/test?mode=${mode}${example ? "&example=1" : ""}`;

/** How many distinct skills the lifecycle shows for a starting point (a skill can sit in more than one stage, so the
 *  stage counts may add up to more than this), out of how many in scope. */
export function modeCoverage(mode: StartMode, role?: string | null): { shown: number; total: number } {
  const only = roleSkills(role);
  const all = LIFE.filter((s) => !only || only.has(s.id));
  return { shown: all.filter((s) => serves(s, mode)).length, total: all.length };
}
