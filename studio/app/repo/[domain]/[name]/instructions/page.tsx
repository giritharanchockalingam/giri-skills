import { loadRepoSkill, repoSkillParams, type RepoParams } from "@/lib/repoSkill";

export function generateStaticParams() { return repoSkillParams(); }
export const dynamicParams = false;

/** Instructions: the rendered SKILL.md prose (pre-rendered, sanitised at ingest). */
export default async function RepoSkillInstructions({ params }: { params: RepoParams }) {
  const { skill } = await loadRepoSkill(params);
  return (
    <div className="card card-pad">
      <div className="eyebrow mb-4">SKILL.md</div>
      <div className="prose" dangerouslySetInnerHTML={{ __html: skill.bodyHtml }} />
    </div>
  );
}
