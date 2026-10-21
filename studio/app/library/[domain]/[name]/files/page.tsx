import { FilePreview } from "@/components/FilePreview";
import { loadRepoSkill, repoSkillParams, type RepoParams } from "@/lib/repoSkill";

export function generateStaticParams() { return repoSkillParams(); }
export const dynamicParams = false;

/** Files: the inventory of references, assets and scripts packaged with the skill. */
export default async function RepoSkillFiles({ params }: { params: RepoParams }) {
  const { skill, id } = await loadRepoSkill(params);
  const fileCount = skill.files.references.length + skill.files.assets.length + skill.files.scripts.length;
  return (
    <div className="card card-pad">
      <div className="h3 mb-1">Files <span className="muted font-normal">({fileCount})</span></div>
      <p className="caption mb-4">Select a file to preview it. <code>skills/{id}/</code>{skill.license && <> · License {skill.license}</>}</p>
      <div className="agent-cols">
        {(["scripts", "assets", "references"] as const).map((k) => (
          <div key={k}>
            <div className="caption capitalize">{k} ({skill.files[k].length})</div>
            {skill.files[k].length === 0 ? <div className="none text-[14px]">none</div> : <ul className="file-list mt-1">{skill.files[k].map((f) => <FilePreview key={f} href={`/runtime/repo/skills/${id}/${k}/${f}`} label={`${k}/${f}`} />)}</ul>}
          </div>
        ))}
      </div>
    </div>
  );
}
