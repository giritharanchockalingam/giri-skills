/* The front door: what a person can get done, organised by role and task — not by the factory's internals.
 * Every example is a skill's own happy-path eval case: the prompt shown is the one whose fixture inputs the
 * "Try it" run uses, so what you click is what runs. Server only. */
import { skills as repoSkillsData } from "@/lib/data";
import { ROLE_TEMPLATES } from "@/lib/factory/talentData";

type RepoRow = { id: string; name: string; stage?: string | null; description: string; agent?: { demo?: { caseId: string } | null } | null; cases?: { id: string; prompt?: string }[] };
const REPO = repoSkillsData as unknown as RepoRow[];
const BY_ID = new Map(REPO.map((s) => [s.id, s]));

/** "What you get", in one sentence, from the skill's own description (its "Produces …" sentence). */
export function whatYouGet(description: string): string {
  let d = description;
  for (let i = 0; i < 3; i++) d = d.replace(/\s*\([^()]*\)/g, "");                       // drop parenthetical detail first
  d = d.replace(/\b(Art|e\.g|i\.e|vs|No|Reg)\.\s/g, "$1.\u00a0");                         // abbreviations do not end a sentence
  // the "Produces …" sentence; a sentence ends at a full stop followed by a space (not the dot in "report.md")
  let t = (d.match(/\b(Produces|Builds|Creates|Writes|Generates|Returns|Runs)\b.*?\.(?=\s|$)/) ?? [d.replace(/^Use (when|for) (the user )?/i, "")])[0];
  const seen = new Set<string>();
  t = t.replace(/\b([a-z0-9][a-z0-9-]*)\.(jsonl|json|csv|md|txt|yaml|yml|sql|py|html)\b/gi, (_m, base: string) => {   // report.md -> "report", once
    const w = base.replace(/-/g, " ").toLowerCase();
    if (seen.has(w)) return "";
    seen.add(w); return w;
  });
  t = t.replace(/(,\s*)+(?=,|\s+and\b|\s+from\b)/g, "").replace(/\band\s+(?=from\b|,|\.)/g, "").replace(/,\s*(?=and\b)/g, " ")
       .replace(/\b(ai|eu|llm|rls|nist|dpia|slo|pii|rag|mcp|csv|sql)\b/gi, (m) => m.toUpperCase()).replace(/\s+([,.])/g, "$1").replace(/\s+/g, " ").trim();
  t = t.replace(/\s+-\s+.*$/, ".")                                                       // " - detail…" is detail
       .replace(/^(\w+ )(.+?)( from\b)/, (m, verb: string, list: string, from: string) =>        // "a, b from" -> "a and b from"
         / and /.test(list) || !list.includes(",") ? m : verb + list.replace(/,\s*([^,]+)$/, " and $1") + from);
  return t.length > 200 ? t.slice(0, 197).replace(/\s+\S*$/, "") + "…" : t;
}

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
