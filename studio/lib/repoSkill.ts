/* Shared loader for the repository skill detail pages (/repo/<domain>/<name>/ and its tabs). Build-time data only. */
import { notFound } from "next/navigation";
import { skills, scoreFor, proposalFor, agentCasesFor, trigger, quality, type Skill } from "./data";

export type RepoParams = Promise<{ domain: string; name: string }>;

export const repoSkillParams = () => skills.map((s) => ({ domain: s.domain, name: s.name }));

export async function loadRepoSkill(params: RepoParams) {
  const { domain, name } = await params;
  const id = `${domain}/${name}`;
  const skill: Skill | undefined = skills.find((s) => s.id === id);
  if (!skill) notFound();
  return {
    id, domain, name, skill,
    score: scoreFor(id), proposal: proposalFor(id), agentCases: agentCasesFor(id),
    trigger: trigger.filter((t) => t.skill === id), quality: quality.filter((q) => q.skill === id),
    base: `/repo/${id}`,
  };
}

export const REPO_TABS = [
  { seg: "", label: "Overview" }, { seg: "test", label: "Test" }, { seg: "instructions", label: "Instructions" },
  { seg: "evals", label: "Evals" }, { seg: "files", label: "Files" },
] as const;
