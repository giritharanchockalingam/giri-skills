/* The Library as an employee reads it: what each skill gives you, whether your workspace has approved it for use, and
 * what its evaluation says, in words. Pure (no JSON, no I/O) so it is unit-tested; scores stay on each skill's page. */

export type LibVerdict = "OK" | "DESC" | "BODY" | "BOTH" | null;
export type Evidence = "proven" | "improving" | "untested";

export interface LibraryInput {
  id: string; title: string; outcome: string; stage: string; domain: string;
  verdict: LibVerdict;
  /** Published version in this workspace (approved for use), else null. */
  published: number | null;
}
export interface LibraryRow extends LibraryInput { evidence: Evidence; evidenceLabel: string; evidenceNote: string }

const NOTE: Record<Exclude<LibVerdict, null>, string> = {
  OK: "Evaluated: chosen for the right requests, and the answer is clearly better with it than without it.",
  DESC: "Runs well, but an assistant may not choose it for every request it should handle. Being improved.",
  BODY: "Runs, but the answer is only a little better than without it. Being improved.",
  BOTH: "Runs, but it is not reliably chosen and adds little over no skill yet. Being improved.",
};

export function evidenceOf(v: LibVerdict): { evidence: Evidence; label: string; note: string } {
  if (!v) return { evidence: "untested", label: "Not evaluated", note: "Not evaluated yet." };
  return v === "OK" ? { evidence: "proven", label: "Proven", note: NOTE.OK } : { evidence: "improving", label: "Being improved", note: NOTE[v] };
}

const RANK: Record<Evidence, number> = { proven: 0, improving: 1, untested: 2 };

/** Approved for use first, then proven, then by title. */
export function libraryRows(inputs: LibraryInput[]): LibraryRow[] {
  return inputs
    .map((i) => { const e = evidenceOf(i.verdict); return { ...i, evidence: e.evidence, evidenceLabel: e.label, evidenceNote: e.note }; })
    .sort((a, b) => Number(b.published != null) - Number(a.published != null) || RANK[a.evidence] - RANK[b.evidence] || a.title.localeCompare(b.title));
}

export type LibraryFilter = "all" | "approved" | "proven";
export const matchesLibraryFilter = (f: LibraryFilter, r: LibraryRow) => f === "all" || (f === "approved" ? r.published != null : r.evidence === "proven");

export function librarySummary(rows: LibraryRow[]) {
  return { total: rows.length, approved: rows.filter((r) => r.published != null).length, proven: rows.filter((r) => r.evidence === "proven").length };
}

/** Library skill id → highest published version in this workspace. */
export function publishedByLibrarySkill(versions: { status: string; version: number; source: { kind: string; repo_skill?: string | null } }[]): Map<string, number> {
  const out = new Map<string, number>();
  for (const v of versions) {
    const id = v.source.repo_skill;
    if (v.status !== "published" || v.source.kind !== "repo" || !id) continue;
    out.set(id, Math.max(out.get(id) ?? 0, v.version));
  }
  return out;
}
