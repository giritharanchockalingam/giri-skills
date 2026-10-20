/* Data for "Who can run which skills" on the Administration page. Runs as the signed-in user (RLS applies). */
import type { SupabaseClient } from "@supabase/supabase-js";
import { skillTitle } from "@/lib/names";
import type { Assignment, JobRole, PublishedSkill } from "@/lib/access";

export interface AccessData { enabled: boolean; roles: JobRole[]; skills: PublishedSkill[]; assignments: Assignment[] }

export async function loadAccessData(sb: SupabaseClient, ws: string): Promise<AccessData> {
  const [pol, roleVersions, skills, assignments] = await Promise.all([
    sb.from("sf_policies").select("skills_by_role").eq("workspace_id", ws).maybeSingle(),
    sb.from("sf_talent_versions").select("spec, sf_talent!inner(id, slug, name, kind, workspace_id)").eq("status", "published").eq("sf_talent.kind", "role").eq("sf_talent.workspace_id", ws),
    sb.from("sf_skills").select("slug, name, latest_version_id").eq("workspace_id", ws).eq("status", "published"),
    sb.from("sf_role_assignments").select("id, talent_id, user_id, api_key_id").eq("workspace_id", ws),
  ]);
  const vids = ((skills.data ?? []) as { latest_version_id: string | null }[]).map((s) => s.latest_version_id).filter((x): x is string => !!x);
  const { data: versions } = vids.length ? await sb.from("sf_skill_versions").select("id, source").in("id", vids) : { data: [] };
  const src = new Map(((versions ?? []) as { id: string; source: { kind?: string; repo_skill?: string } }[]).map((v) => [v.id, v.source]));
  type RV = { spec: { skills?: string[]; playbooks?: string[] }; sf_talent: { id: string; slug: string; name: string } };
  return {
    enabled: !!(pol.data as { skills_by_role?: boolean } | null)?.skills_by_role,
    roles: ((roleVersions.data ?? []) as unknown as RV[]).map((r) => ({ id: r.sf_talent.id, slug: r.sf_talent.slug, name: r.sf_talent.name, skills: r.spec.skills ?? [], playbooks: r.spec.playbooks ?? [] }))
      .sort((a, b) => a.name.localeCompare(b.name)),
    skills: ((skills.data ?? []) as { slug: string; name: string; latest_version_id: string | null }[]).map((s) => {
      const so = s.latest_version_id ? src.get(s.latest_version_id) : undefined;
      return { slug: s.slug, title: skillTitle(s.name), repoSkill: so?.kind === "repo" ? so.repo_skill ?? null : null };
    }).sort((a, b) => a.title.localeCompare(b.title)),
    assignments: (assignments.data ?? []) as Assignment[],
  };
}
