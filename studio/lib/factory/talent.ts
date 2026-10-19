/* Roles and talent pools: pure core (no I/O), shared by the server, the UI and the tests.
 *
 *  skill  — one executable capability (SKILL.md)
 *  role   — a named set of skills (template defaults, tailored by adding/removing) plus playbooks (agents it runs)
 *  pool   — a team of roles; its playbooks are agents whose every skill step is owned by some member
 *
 * A role answers a free-form task by routing it to the best of ITS skills (lexical BM25 over each skill's
 * description and "When to use" section; deterministic and explainable). Nothing here invents capability: a role
 * can only route to, and a pool can only staff, skills that exist in the catalog. */

export interface RoleSpec {
  name: string;               // slug
  title: string;              // "AI Solution Architect"
  description: string;        // what this role is accountable for
  skills: string[];           // skill ids, e.g. "ai-platform/model-selection"
  playbooks: string[];        // agent slugs this role runs end to end
  based_on?: string | null;   // template it was tailored from
}

export interface PoolMember { role: string; label?: string; seats?: number }
export interface PoolSpec {
  name: string; title: string; description: string;
  members: PoolMember[];
  playbooks: string[];        // agent slugs the team runs together (each step staffed by a member)
  based_on?: string | null;
}

export interface SkillInfo { id: string; name: string; stage: string | null; description: string; bodyMd?: string }
export interface PlaybookInfo { name: string; skills: string[] }   // the skill ids an agent's steps use, in order
export interface StageInfo { id: string; name: string; n?: number }

const SLUG = /^[a-z0-9][a-z0-9-]{0,78}$/;

// ---------- validation ----------

export function validateRoleSpec(spec: RoleSpec, skills: Map<string, SkillInfo>, playbooks: Map<string, PlaybookInfo>): string[] {
  const p: string[] = [];
  if (!SLUG.test(spec.name ?? "")) p.push("name must be a lowercase slug");
  if (!spec.title?.trim()) p.push("missing 'title'");
  if (!spec.description?.trim()) p.push("missing 'description'");
  if (!Array.isArray(spec.skills) || spec.skills.length === 0) p.push("the role has no skills");
  const seen = new Set<string>();
  for (const s of spec.skills ?? []) {
    if (seen.has(s)) p.push(`skill ${s} listed twice`);
    seen.add(s);
    if (!skills.has(s)) p.push(`skill ${s} does not exist`);
  }
  for (const pb of spec.playbooks ?? []) {
    const info = playbooks.get(pb);
    if (!info) { p.push(`playbook ${pb} does not exist`); continue; }
    const missing = info.skills.filter((s) => !seen.has(s));
    if (missing.length) p.push(`playbook ${pb} uses skills this role does not have: ${[...new Set(missing)].join(", ")}`);
  }
  return p;
}

/** Which member staffs each skill step of a playbook: among members that have the skill, the specialist — the one
 *  with the most skills in that skill's stage — wins; ties go to team order. `stageOf` maps skill → stage. */
export function staffPlaybook(pb: PlaybookInfo, members: { key: string; skills: string[] }[], stageOf: (skill: string) => string | null | undefined = () => null): { skill: string; member: string | null }[] {
  return pb.skills.map((s) => {
    const st = stageOf(s);
    let best: { key: string; depth: number } | null = null;
    for (const m of members) {
      if (!m.skills.includes(s)) continue;
      const depth = st ? m.skills.filter((x) => stageOf(x) === st).length : 0;
      if (!best || depth > best.depth) best = { key: m.key, depth };
    }
    return { skill: s, member: best?.key ?? null };
  });
}

/** A member's name in the team: its label, else its role (role#2, #3… when the role repeats unlabelled). */
export function memberKey(m: PoolMember, i: number, members: PoolMember[] = []) {
  if (m.label?.trim()) return m.label.trim();
  const before = members.slice(0, i).filter((x) => x.role === m.role && !x.label?.trim()).length;
  return before ? `${m.role}#${before + 1}` : m.role;
}

export function validatePoolSpec(spec: PoolSpec, roles: Map<string, RoleSpec>, playbooks: Map<string, PlaybookInfo>, stageOf?: (skill: string) => string | null | undefined): string[] {
  const p: string[] = [];
  if (!SLUG.test(spec.name ?? "")) p.push("name must be a lowercase slug");
  if (!spec.title?.trim()) p.push("missing 'title'");
  if (!spec.description?.trim()) p.push("missing 'description'");
  if (!Array.isArray(spec.members) || spec.members.length === 0) p.push("the pool has no members");
  const keys = new Set<string>();
  for (const [i, m] of (spec.members ?? []).entries()) {
    if (!roles.has(m.role)) p.push(`member ${i + 1}: role ${m.role} does not exist`);
    if (m.seats != null && (!Number.isInteger(m.seats) || m.seats < 1 || m.seats > 50)) p.push(`member ${i + 1}: seats must be 1–50`);
    const k = memberKey(m, i, spec.members);
    if (keys.has(k)) p.push(`member ${k} listed twice (give it a label)`);
    keys.add(k);
  }
  const members = (spec.members ?? []).map((m, i) => ({ key: memberKey(m, i, spec.members), skills: roles.get(m.role)?.skills ?? [] }));
  for (const pb of spec.playbooks ?? []) {
    const info = playbooks.get(pb);
    if (!info) { p.push(`playbook ${pb} does not exist`); continue; }
    const gaps = staffPlaybook(info, members, stageOf).filter((x) => !x.member).map((x) => x.skill);
    if (gaps.length) p.push(`playbook ${pb} has steps no member can staff: ${[...new Set(gaps)].join(", ")}`);
  }
  return p;
}

// ---------- tailoring ----------

/** Add/remove skills from a role; returns the tailored spec plus what changed versus its template. */
export function tailor(spec: RoleSpec, add: string[], remove: string[]): RoleSpec {
  const rm = new Set(remove);
  const skills = spec.skills.filter((s) => !rm.has(s));
  for (const a of add) if (!skills.includes(a)) skills.push(a);
  return { ...spec, skills };
}

export function diffFromTemplate(spec: RoleSpec, template: RoleSpec | undefined): { added: string[]; removed: string[] } {
  if (!template) return { added: [], removed: [] };
  return { added: spec.skills.filter((s) => !template.skills.includes(s)), removed: template.skills.filter((s) => !spec.skills.includes(s)) };
}

// ---------- coverage ----------

/** Stage → which members (or roles) bring a skill for it. Gaps are stages nobody covers. */
export function coverage(members: { key: string; skills: string[] }[], skills: Map<string, SkillInfo>, stages: StageInfo[]) {
  const rows = stages.map((st) => {
    const by = members.map((m) => ({ key: m.key, skills: m.skills.filter((s) => skills.get(s)?.stage === st.id) }));
    return { stage: st, by, covered: by.some((b) => b.skills.length > 0) };
  });
  return { rows, gaps: rows.filter((r) => !r.covered).map((r) => r.stage.id), covered: rows.filter((r) => r.covered).length };
}

// ---------- routing ----------

const STOP = new Set(("a an and are as at be by can do does for from has have how i in into is it its me my of on or our please should so that the their them then there these this to us use using was we what when where which who why will with would you your " +
  "user asks ask asked produces produce output outputs skill not").split(" "));

export function tokens(text: string): string[] {
  return text.toLowerCase().replace(/[`"'“”‘’()[\]{}<>|*_#:;,.!?/\\]+/g, " ").split(/\s+/)
    .map((t) => t.replace(/^-+|-+$/g, "")).filter((t) => t.length > 1 && !STOP.has(t) && !/^\d+$/.test(t))
    .map(stemWord);
}
function stemWord(w: string): string {
  for (const suf of ["ations", "ation", "ings", "ing", "ies", "ers", "er", "es", "ed", "s"]) {
    if (w.length > suf.length + 3 && w.endsWith(suf)) return suf === "ies" ? w.slice(0, -3) + "y" : w.slice(0, -suf.length);
  }
  return w;
}

/** The routing text of a skill: name (weighted), its description without the "Not for…" clause, and its
 *  "When to use" bullets (without the NOT-for bullet). */
export function routingText(s: SkillInfo): string {
  const desc = s.description.split(/\b(?:Not for|NOT for|Do not use|Don't use)\b/)[0];
  const when = (s.bodyMd ?? "").match(/## When to use\n([\s\S]*?)(?:\n## |$)/)?.[1] ?? "";
  const whenKeep = when.split("\n").filter((l) => !/\bNOT for\b/i.test(l)).join("\n");
  const name = s.name.replace(/-/g, " ");
  return `${name} ${name} ${name} ${desc} ${whenKeep}`;
}

export interface RouteHit { skill: string; score: number; matched: string[] }

export class Router {
  private docs: { id: string; tf: Map<string, number>; len: number }[];
  private df = new Map<string, number>();
  private avg: number;
  constructor(skills: SkillInfo[]) {
    this.docs = skills.map((s) => {
      const tf = new Map<string, number>();
      const toks = tokens(routingText(s));
      for (const t of toks) tf.set(t, (tf.get(t) ?? 0) + 1);
      return { id: s.id, tf, len: toks.length };
    });
    for (const d of this.docs) for (const t of d.tf.keys()) this.df.set(t, (this.df.get(t) ?? 0) + 1);
    this.avg = this.docs.reduce((a, d) => a + d.len, 0) / Math.max(1, this.docs.length);
  }
  /** BM25 (k1 1.2, b 0.75) of the task against the allowed skills; ties break on skill id for determinism. */
  route(task: string, allowed?: Iterable<string>, k = 3): RouteHit[] {
    const allow = allowed ? new Set(allowed) : null;
    const q = [...new Set(tokens(task))];
    const N = this.docs.length;
    const hits: RouteHit[] = [];
    for (const d of this.docs) {
      if (allow && !allow.has(d.id)) continue;
      let score = 0; const matched: string[] = [];
      for (const t of q) {
        const f = d.tf.get(t); if (!f) continue;
        const n = this.df.get(t) ?? 0;
        const idf = Math.log(1 + (N - n + 0.5) / (n + 0.5));
        score += idf * (f * 2.2) / (f + 1.2 * (1 - 0.75 + 0.75 * d.len / this.avg));
        matched.push(t);
      }
      if (score > 0) hits.push({ skill: d.id, score: Math.round(score * 1000) / 1000, matched });
    }
    return hits.sort((a, b) => b.score - a.score || a.skill.localeCompare(b.skill)).slice(0, k);
  }
}
