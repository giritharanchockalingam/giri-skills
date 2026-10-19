/* Library search: case- and punctuation-insensitive, every word must appear somewhere ("red team" finds "red-team",
 * "rls supabase" finds "supabase-schema-rls"). Pure; used by every list filter. */
export const normText = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
export function matches(query: string, ...fields: (string | null | undefined)[]): boolean {
  const words = normText(query).split(" ").filter(Boolean);
  if (!words.length) return true;
  const hay = ` ${normText(fields.filter(Boolean).join(" "))} `;
  const squashed = hay.replace(/ /g, "");
  return words.every((w) => hay.includes(w) || squashed.includes(w));
}
