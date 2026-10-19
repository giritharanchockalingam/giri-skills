import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { TalentList } from "@/components/factory/TalentList";

export const metadata = { title: "Teams · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function PoolsPage() {
  const ctx = await requireWorkspace();
  return (
    <>
      <PageHead eyebrow={`Teams · ${ctx.workspace.name}`} title="Teams, assembled from" em="roles" after="."
        lead="A team is a set of tailored roles. It shows which stages of the AI development lifecycle (ADLC) the team covers, where the gaps are, and which member takes each step of its playbooks." />
      <nav className="flex gap-2 mb-4" aria-label="Roles and teams"><Link href="/roles" className="chip" aria-current={undefined}>Roles</Link><Link href="/pools" className="chip chip-on" aria-current="page">Teams</Link></nav>
      <TalentList kind="pool" />
    </>
  );
}
