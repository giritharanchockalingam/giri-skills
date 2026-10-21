/* The skill-count sentence (pure; see lib/counts.ts for where the numbers come from). */
export interface SkillCounts {
  library: number; reference: number; workspace: number; published: number; inProgress: number;
  /** library skills imported into this workspace (distinct), library skills not imported yet, and skills written here */
  imported?: number; notImported?: number; authored?: number;
}
export const countsSentence = (c: SkillCounts) =>
  `${c.library} skills in the library · ${c.workspace} in this workspace (${c.published} published, ${c.inProgress} in progress) · ${c.reference} reference skills`;

/** The bridge wherever two skill counts meet: "78 in the library = 61 in this workspace + 17 not imported yet". */
export const countsBridge = (c: SkillCounts) =>
  c.imported == null || c.notImported == null ? countsSentence(c)
    : `${c.library} in the library = ${c.imported} in this workspace + ${c.notImported} not imported yet${c.authored ? ` · plus ${c.authored} written in this workspace` : ""}`;
