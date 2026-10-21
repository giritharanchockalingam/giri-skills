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
      <PageHead eyebrow={`Admin · Job roles · ${ctx.workspace.name}`} title="Job roles, defined by" em="skills" after="."
        lead="A job role is the set of skills it brings plus the playbooks it runs. Start from a template, then add or remove skills to tailor it. When “Restrict skills by job role” is on (Administration), the job roles assigned to people and API keys decide what they may run." />
      <nav className="flex gap-2 mb-4" aria-label="Roles and teams"><Link href="/roles" className="chip chip-on" aria-current="page">Roles</Link><Link href="/teams" className="chip" aria-current={undefined}>Teams</Link></nav>
      <TalentList kind="role" />
    </>
  );
}
