/* Immutable versions for library skills. A repo-sourced version past draft (in review, approved, published, superseded)
 * runs on the exact files it was reviewed with, frozen in sf_version_snapshots, so improving the library never stops a
 * live version from running. Files are taken from the Python runtime of the same deployment, and only while that
 * deployment still holds the version's pinned files (pin == version.content_sha). Server only. */
import "server-only";
import { createHash } from "node:crypto";
import { adminConfigured, createAdminSupabase } from "@/lib/supabase/server-admin";
import { currentPin } from "./pins";
import { runtimeConfig, runtimeHeadersForServer } from "./runtime";

export interface SnapshotFile { path: string; content: string }
export interface Snapshot { files: SnapshotFile[]; sha256: string }

/** sha256 over a skill's own files sorted by path — the same algorithm as api/py/run.py snapshot_sha(). */
export function snapshotSha(files: SnapshotFile[]): string {
  const h = createHash("sha256");
  for (const f of [...files].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0))) {
    h.update(Buffer.from(f.path, "utf8")); h.update(Buffer.from([0]));
    h.update(Buffer.from(f.content, "utf8")); h.update(Buffer.from([0]));
  }
  return h.digest("hex");
}

/** The frozen files of a version, verified against their recorded hash; null when none exist (or snapshots are off). */
export async function loadSnapshot(versionId: string): Promise<Snapshot | null> {
  if (!adminConfigured()) return null;
  const { data } = await createAdminSupabase().from("sf_version_snapshots").select("files, sha256").eq("version_id", versionId).maybeSingle();
  if (!data) return null;
  const files = data.files as SnapshotFile[];
  if (snapshotSha(files) !== data.sha256) throw new Error(`frozen files of version ${versionId} do not match their recorded hash`);
  return { files, sha256: data.sha256 as string };
}

/** Freeze a repo version's files if it has none yet and this deployment still holds exactly the files it was pinned to.
 *  Returns the snapshot, or null when it cannot be taken (authored skill, unpinned, files already changed, no service key). */
export async function ensureSnapshot(versionId: string): Promise<Snapshot | null> {
  if (!adminConfigured()) return null;
  const existing = await loadSnapshot(versionId);
  if (existing) return existing;
  const admin = createAdminSupabase();
  const { data: v } = await admin.from("sf_skill_versions").select("id, source, sf_skills!sf_skill_versions_skill_id_fkey(workspace_id)").eq("id", versionId).maybeSingle();
  const source = (v?.source ?? null) as { kind?: string; repo_skill?: string; content_sha?: string } | null;
  if (!v || source?.kind !== "repo" || !source.repo_skill || !source.content_sha) return null;
  if (currentPin(source.repo_skill) !== source.content_sha) return null;   // the reviewed files are no longer deployed
  const cfg = runtimeConfig();
  if (!cfg.ok || !cfg.url) return null;
  const res = await fetch(cfg.url, { method: "POST", headers: runtimeHeadersForServer(), body: JSON.stringify({ export: source.repo_skill }), cache: "no-store", signal: AbortSignal.timeout(30_000) });
  const body = (await res.json().catch(() => null)) as { files?: SnapshotFile[]; sha256?: string; error?: string } | null;
  if (!res.ok || !body?.files?.length || !body.sha256) throw new Error(`could not read ${source.repo_skill} from the runtime: ${body?.error ?? `HTTP ${res.status}`}`);
  if (snapshotSha(body.files) !== body.sha256) throw new Error(`runtime returned files for ${source.repo_skill} that do not match their hash`);
  const workspaceId = (v.sf_skills as unknown as { workspace_id: string }).workspace_id;
  const bytes = body.files.reduce((n, f) => n + Buffer.byteLength(f.path, "utf8") + Buffer.byteLength(f.content, "utf8"), 0);
  const { error } = await admin.from("sf_version_snapshots").insert({
    version_id: versionId, workspace_id: workspaceId, repo_skill: source.repo_skill, content_sha: source.content_sha, sha256: body.sha256, files: body.files, bytes,
  });
  if (error && !/duplicate key/.test(error.message)) throw new Error(`could not freeze ${source.repo_skill}: ${error.message}`);
  return error ? await loadSnapshot(versionId) : { files: body.files, sha256: body.sha256 };
}
