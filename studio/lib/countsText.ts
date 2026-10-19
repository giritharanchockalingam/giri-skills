/* The skill-count sentence (pure; see lib/counts.ts for where the numbers come from). */
export interface SkillCounts { library: number; reference: number; workspace: number; published: number; inProgress: number }
export const countsSentence = (c: SkillCounts) =>
  `${c.library} skills in the library · ${c.workspace} in this workspace (${c.published} published, ${c.inProgress} in progress) · ${c.reference} reference skills`;
