/* Read what delivery metrics need from GitHub for one repository: pull requests into the default branch (closed in
 * the last 90 days, and open ones) and production deployments when the App may read them. Read-only. */
import { gh, GithubError, type GhRepo } from "./app";
import type { PrFact, DeployFact } from "@/lib/insights/delivery";

type Pull = { number: number; title: string; draft?: boolean; created_at: string; updated_at: string; merged_at: string | null; closed_at: string | null; head: { ref: string } };
const toFact = (p: Pull): PrFact => ({ number: p.number, title: p.title, head_ref: p.head.ref, created_at: p.created_at, merged_at: p.merged_at, closed_at: p.closed_at, draft: p.draft });

export async function deliveryFacts(token: string, repo: Pick<GhRepo, "full_name" | "default_branch">, days = 90, fetchImpl?: typeof fetch):
  Promise<{ prs: PrFact[]; deploys: DeployFact[] | null; deploysNote: string | null; truncated: boolean }> {
  const auth = `Bearer ${token}`, since = Date.now() - days * 86_400_000;
  const base = `/repos/${repo.full_name}/pulls?base=${encodeURIComponent(repo.default_branch)}&per_page=100`;
  const prs: PrFact[] = [];
  let url: string | null = `${base}&state=closed&sort=updated&direction=desc`, pages = 0, truncated = false;
  while (url) {
    const r: { data: Pull[]; next: string | null } = await gh<Pull[]>(url, auth, { fetchImpl });
    prs.push(...r.data.map(toFact));
    pages++;
    const oldest = r.data.at(-1);
    if (!r.next || !oldest || Date.parse(oldest.updated_at) < since) break;
    if (pages >= 5) { truncated = true; break; }
    url = r.next;
  }
  prs.push(...(await gh<Pull[]>(`${base}&state=open`, auth, { fetchImpl })).data.map(toFact));
  let deploys: DeployFact[] | null = null, deploysNote: string | null = null;
  try {
    const d = await gh<{ created_at: string; environment: string }[]>(`/repos/${repo.full_name}/deployments?per_page=100`, auth, { fetchImpl });
    deploys = d.data.map((x) => ({ created_at: x.created_at, environment: x.environment }));
  } catch (e) {
    if (e instanceof GithubError && (e.status === 403 || e.status === 404)) deploysNote = "The GitHub App cannot read deployments (grant Deployments: Read-only for true deployment counts); merges to the default branch are counted instead.";
    else throw e;
  }
  return { prs, deploys, deploysNote, truncated };
}
