// Roles, pools and the task router (lib/factory/talent.ts). Same rules as scripts/talent.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { validateRoleSpec, validatePoolSpec, staffPlaybook, memberKey, coverage, tailor, diffFromTemplate, Router, tokens,
  type RoleSpec, type PoolSpec, type SkillInfo, type PlaybookInfo } from "../lib/factory/talent.ts";

const load = (f: string) => JSON.parse(readFileSync(new URL(`../data/${f}`, import.meta.url), "utf8"));
const SKILLS: (SkillInfo & { cases?: { prompt?: string }[] })[] = load("skills.json");
const skillMap = new Map(SKILLS.map((s) => [s.id, s]));
const playbooks = new Map<string, PlaybookInfo>((load("agent-templates.json") as { name: string; spec: { steps: { skill?: string }[] } }[])
  .map((t) => [t.name, { name: t.name, skills: t.spec.steps.filter((s) => s.skill).map((s) => s.skill!) }]));
const ROLES: RoleSpec[] = load("role-templates.json");
const POOLS: PoolSpec[] = load("pool-templates.json");
const roleMap = new Map(ROLES.map((r) => [r.name, r]));
const STAGES = load("stages.json").stages as { id: string; name: string }[];

test("talent: every shipped role and pool validates; every skill belongs to a role", () => {
  for (const r of ROLES) assert.deepEqual(validateRoleSpec(r, skillMap, playbooks), [], r.name);
  for (const p of POOLS) assert.deepEqual(validatePoolSpec(p, roleMap, playbooks), [], p.name);
  const owned = new Set(ROLES.flatMap((r) => r.skills));
  assert.deepEqual(SKILLS.map((s) => s.id).filter((id) => !owned.has(id)), []);
});

test("talent: tailoring a role is reflected in its playbooks and in the pools that staff it", () => {
  const sa = roleMap.get("presales-solution-architect")!;
  const cut = tailor(sa, ["presales/rfp-compliance-matrix"], ["presales/effort-estimator"]);
  assert.deepEqual(diffFromTemplate(cut, sa), { added: ["presales/rfp-compliance-matrix"], removed: ["presales/effort-estimator"] });
  assert.match(validateRoleSpec(cut, skillMap, playbooks).join("\n"), /estimate-and-value uses skills this role does not have: presales\/effort-estimator/);
  const roles = new Map(roleMap); roles.set(cut.name, cut);
  assert.match(validatePoolSpec(POOLS.find((p) => p.name === "presales-bid-team")!, roles, playbooks).join("\n"), /no member can staff: presales\/effort-estimator/);
  assert.match(validateRoleSpec({ ...sa, skills: [...sa.skills, "nope/x"] }, skillMap, playbooks).join(), /nope\/x does not exist/);
});

test("talent: staffing follows team order; repeated roles get distinct names", () => {
  const ms = [{ role: "ai-strategist" }, { role: "ai-strategist" }, { role: "ai-risk-release-lead", label: "Risk" }];
  assert.deepEqual(ms.map((m, i) => memberKey(m, i, ms)), ["ai-strategist", "ai-strategist#2", "Risk"]);
  const keyed = ms.map((m, i) => ({ key: memberKey(m, i, ms), skills: roleMap.get(m.role)!.skills }));
  assert.deepEqual(staffPlaybook({ name: "x", skills: ["ai-platform/ai-governance-risk", "ai-platform/ai-release-plan", "nope/x"] }, keyed),
    [{ skill: "ai-platform/ai-governance-risk", member: "ai-strategist" }, { skill: "ai-platform/ai-release-plan", member: "Risk" }, { skill: "nope/x", member: null }]);
  const stageOf = (id: string) => skillMap.get(id)?.stage;
  assert.equal(staffPlaybook({ name: "x", skills: ["ai-platform/ai-governance-risk"] }, keyed, stageOf)[0].member, "Risk", "the specialist wins");
});

test("talent: coverage shows real gaps that adding a role closes", () => {
  const pod = POOLS.find((p) => p.name === "ai-delivery-pod")!;
  const mem = (p: PoolSpec) => p.members.map((m, i) => ({ key: memberKey(m, i, p.members), skills: roleMap.get(m.role)!.skills }));
  assert.ok(coverage(mem(pod), skillMap, STAGES).gaps.includes("operate"));
  const more = { ...pod, members: [...pod.members, { role: "ai-ops-sre" }] };
  assert.ok(!coverage(mem(more), skillMap, STAGES).gaps.includes("operate"));
});

test("router: deterministic, restricted to the role's skills, explains its match", () => {
  const r = new Router(SKILLS);
  const sa = roleMap.get("ai-solution-architect")!;
  const hits = r.route("How many GPUs do we need to serve a 70B model at 50 requests per second?", sa.skills);
  assert.equal(hits[0].skill, "ai-platform/infra-gpu-sizing");
  assert.ok(hits.every((h) => sa.skills.includes(h.skill)));
  assert.ok(hits[0].matched.includes(tokens("GPUs")[0]));
  assert.deepEqual(r.route("How many GPUs do we need", sa.skills), r.route("How many GPUs do we need", sa.skills));
  assert.deepEqual(r.route("", sa.skills), []);
});

test("router: accuracy on the library's own eval prompts (measured, with a floor so it cannot silently regress)", () => {
  const r = new Router(SKILLS);
  let n = 0, top1 = 0, inRole = 0, roleN = 0;
  for (const s of SKILLS) for (const c of s.cases ?? []) {
    if (!c.prompt) continue;
    n++; if (r.route(c.prompt, undefined, 1)[0]?.skill === s.id) top1++;
    for (const role of ROLES.filter((x) => x.skills.includes(s.id))) { roleN++; if (r.route(c.prompt, role.skills, 1)[0]?.skill === s.id) inRole++; }
  }
  const all = top1 / n, scoped = inRole / roleN;
  console.log(`router: ${n} prompts · top-1 across all ${SKILLS.length} skills ${(all * 100).toFixed(1)}% · within the owning role ${(scoped * 100).toFixed(1)}%`);
  assert.ok(n > 300);
  assert.ok(all >= 0.75, `library-wide top-1 ${all}`);
  assert.ok(scoped >= 0.85, `within-role top-1 ${scoped}`);
});
