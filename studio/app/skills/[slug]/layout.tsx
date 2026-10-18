import Link from "next/link";
import { loadSkillPage } from "@/lib/factory/skillPage";
import { SkillPill } from "@/components/factory/Pills";
import { SkillSubNav } from "@/components/factory/SkillSubNav";

export const dynamic = "force-dynamic";

export default async function SkillLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const d = await loadSkillPage(slug, null);
  return (
    <>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <nav className="caption" aria-label="Breadcrumb"><Link href="/" className="link">Skills</Link> <span aria-hidden="true">›</span> {d.skill.slug}</nav>
        <h1 className="h1" style={{ margin: "8px 0 10px" }}>{d.skill.name}</h1>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <SkillPill status={d.skill.status} />
          <span className="caption">{d.published ? <>Published <b>v{d.published.version}</b></> : "Not published yet"} · {d.versions.length} version{d.versions.length === 1 ? "" : "s"} · owner {d.skill.owner_id === d.ctx.user.id ? "you" : d.skill.owner_id.slice(0, 8)}</span>
        </div>
        <SkillSubNav slug={slug} />
      </div>
      {children}
    </>
  );
}
