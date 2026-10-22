/* The composition catalog as the portal ships it: request kinds (data/request-kinds.json, from shared/), roles
 * (data/role-templates.json, from roles/) and every library skill's `metadata.fits` (data/skills.json) — all written
 * by scripts/ingest.mjs. lib/delivery/compose.ts stays pure; this module binds it to the data. */
import requestKindsJson from "@/data/request-kinds.json";
import roleTemplatesJson from "@/data/role-templates.json";
import { skills } from "@/lib/data";
import { compose, type ComposeCatalog, type ComposeInput, type ComposeResult, type RequestKinds, type SkillFits } from "./compose";

export const REQUEST_KINDS = requestKindsJson as unknown as RequestKinds;
/** The kinds a person can pick (aliases hidden). */
export const REQUEST_KIND_OPTIONS = REQUEST_KINDS.kinds.filter((k) => !k.alias_of).map((k) => ({ id: k.id, description: k.description, mode: k.mode ?? "brownfield", stages: k.stages ?? [] }));

let cached: ComposeCatalog | null = null;
export function composeCatalog(): ComposeCatalog {
  if (cached) return cached;
  const roles = (roleTemplatesJson as unknown as { name: string; stages?: string[]; skills?: string[] }[]).map((r) => ({ name: r.name, stages: r.stages ?? [], skills: r.skills ?? [] }));
  const fits: Record<string, SkillFits | null> = {};
  for (const s of skills as unknown as { id: string; metadata?: { fits?: SkillFits } }[]) fits[s.id] = s.metadata?.fits ?? null;
  return (cached = { roles, fits });
}

export const composeWithData = (input: ComposeInput): ComposeResult => compose(input, composeCatalog(), REQUEST_KINDS);
