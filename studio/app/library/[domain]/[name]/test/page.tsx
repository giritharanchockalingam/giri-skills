import { loadRepoSkill, repoSkillParams, type RepoParams } from "@/lib/repoSkill";
import { RunPanel } from "@/components/RunPanel";
import { CopyButton } from "@/components/CopyButton";

export function generateStaticParams() { return repoSkillParams(); }
export const dynamicParams = false;

/** Test: the in-browser run form only; the CLI equivalents sit in a collapsed "Command line" block underneath. */
export default async function RepoSkillTest({ params }: { params: RepoParams }) {
  const d = await loadRepoSkill(params);
  const { skill, id, name } = d;
  if (!skill.agent) {
    return <div className="card card-pad"><p className="none">Not wired yet — this SKILL.md has no <code>metadata.agent</code> block, so <code>run_skill.py</code> cannot run it.</p></div>;
  }
  const demoCmd = `python3 scripts/run_skill.py --demo ${id}`;
  // Required inputs plainly; optional ones in [brackets] (usage syntax) so the pasted command stays valid.
  const inputCmd = [`python3 scripts/run_skill.py ${id}`, ...skill.agent.inputs.map((i) => `  ${i.required ? "" : "["}--input ${i.name}=<${i.type || "value"}>${i.required ? "" : "]"}`), "  --out runs/" + name].join(" \\\n");
  return (
    <>
      <RunPanel skillId={id} agent={skill.agent} defaultOpen />
      <details className="disclosure cmdline">
        <summary>Command line</summary>
        <p className="caption mt-2">On its own happy-path fixtures, from the repo root:</p>
        <div className="codeblock"><CopyButton text={demoCmd} />{demoCmd}</div>
        <p className="caption mt-3">With your own inputs (bracketed ones are optional):</p>
        <div className="codeblock"><CopyButton text={inputCmd} />{inputCmd}</div>
      </details>
    </>
  );
}
