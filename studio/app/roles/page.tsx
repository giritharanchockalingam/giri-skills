import Link from "next/link";
import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { TalentList } from "@/components/factory/TalentList";

export const metadata = { title: "Roles · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function RolesPage() {
  const ctx = await requireWorkspace();
  return (
    <>
      <PageHead eyebrow={`Roles · ${ctx.workspace.name}`} title="Roles, defined by" em="skills" after="."
        lead="A role is the set of skills it brings plus the playbooks it runs. Start from a template, then add or remove skills to tailor it. Give it a task and it picks the right skill." />
      <nav className="flex gap-2 mb-4" aria-label="Roles and teams"><Link href="/roles" className="chip chip-on" aria-current="page">Roles</Link><Link href="/pools" className="chip" aria-current={undefined}>Teams</Link></nav>
      <TalentList kind="role" />
    </>
  );
}
