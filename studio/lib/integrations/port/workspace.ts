/* Which workspace an operator route means when none is named: the one workspace that has published skills (that is
 * the only one Port mirrors). Several such workspaces → ambiguous, and the caller must say which. */
export type WorkspacePick = { ok: true; id: string } | { ok: false; status: number; code: string; message: string };

export function pickPublishingWorkspace(rows: { workspace_id: string }[]): WorkspacePick {
  const ids = [...new Set(rows.map((r) => r.workspace_id))];
  if (!ids.length) return { ok: false, status: 404, code: "NO_WORKSPACE", message: "no workspace has published skills" };
  if (ids.length > 1) return { ok: false, status: 400, code: "AMBIGUOUS", message: `${ids.length} workspaces have published skills: pass ?workspace=<uuid>` };
  return { ok: true, id: ids[0] };
}
