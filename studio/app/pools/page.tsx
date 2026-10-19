import { requireWorkspace } from "@/lib/factory/db";
import { PageHead } from "@/components/PageHead";
import { TalentList } from "@/components/factory/TalentList";

export const metadata = { title: "Talent pools · Skills Factory" };
export const dynamic = "force-dynamic";

export default async function PoolsPage() {
  const ctx = await requireWorkspace();
  return (
    <>
      <PageHead eyebrow={`Talent pools · ${ctx.workspace.name}`} title="Teams, assembled from" em="roles" after="."
        lead="A talent pool is a team of tailored roles. It shows which ADLC stages the team covers, where the gaps are, and which member takes each step of its playbooks." />
      <TalentList kind="pool" />
    </>
  );
}
