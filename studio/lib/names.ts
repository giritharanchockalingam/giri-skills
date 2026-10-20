/** Display name for a skill or input slug: "ai-bom-license-check" → "AI BOM license check". Pure; client-safe. */
const ACRONYMS = /\b(ai|llm|rls|rag|mcp|slm|sow|rfp|pii|dpia|slo|slos|bom|eu|ab|raid|nextjs|tdd|ci|cd|gpu|coe|prd|jd|ui|ux|api|sql|nist|crm|kpi|finops|hitl)\b/gi;
export const humanName = (slug: string): string =>
  slug.replace(/-runner$/, "").replace(/[-_]/g, " ").replace(ACRONYMS, (m) => (m.toLowerCase() === "finops" ? "FinOps" : m.toLowerCase() === "nextjs" ? "Next.js" : m.toUpperCase()))
    .replace(/\bA\/?B\b/, "A/B").replace(/\blanggraph\b/gi, "LangGraph").replace(/\blangchain\b/gi, "LangChain").replace(/\bsupabase\b/gi, "Supabase")
    .replace(/\bvercel\b/gi, "Vercel").replace(/\bgithub\b/gi, "GitHub").replace(/\bsaas\b/gi, "SaaS").replace(/\bwebapp\b/gi, "Web app").replace(/^./, (c) => c.toUpperCase());

/** A stored skill or playbook name that is only a slug ("account-plan") reads as a title ("Account plan"); real titles pass through. */
export const skillTitle = (name: string): string => (/^[a-z0-9][a-z0-9-]*$/.test(name) ? humanName(name) : name);

/** "Produces a forward-only migration SQL with a rollback block, …" → "Forward-only migration SQL" (≤ maxWords). */
export function shortOutcome(youGet: string, maxWords = 12): string {
  let t = youGet.replace(/^(Produces|Builds|Creates|Writes|Generates|Returns|Runs)\s+(an?\s+|the\s+)?/i, "").replace(/\.$/, "");
  const cut = t.search(/\s(with|from|using|plus|so that|that|which|for each|per)\s|[;:—]|,\s(?=\w+\s+\w+)/i);
  const words = t.split(/\s+/);
  if (cut > 0 && t.slice(0, cut).split(/\s+/).length >= 3) t = t.slice(0, cut);
  else if (words.length > maxWords) t = words.slice(0, maxWords).join(" ") + "…";
  t = t.trim().replace(/[,\s]+$/, "");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** "What you get", in one sentence, from the skill's own description (its "Produces …" sentence). */
export function whatYouGet(description: string): string {
  let d = description;
  for (let i = 0; i < 3; i++) d = d.replace(/\s*\([^()]*\)/g, "");                       // drop parenthetical detail first
  d = d.replace(/\b(Art|e\.g|i\.e|vs|No|Reg)\.\s/g, "$1.\u00a0");                         // abbreviations do not end a sentence
  // the "Produces …" sentence; a sentence ends at a full stop followed by a space (not the dot in "report.md")
  let t = (d.match(/\b(Produces|Builds|Creates|Writes|Generates|Returns|Runs)\b.*?\.(?=\s|$)/) ?? [d.replace(/^Use (when|for) (the user )?/i, "")])[0];
  const seen = new Set<string>();
  t = t.replace(/\b([a-z0-9][a-z0-9-]*)\.(jsonl|json|csv|md|txt|yaml|yml|sql|py|html)\b/gi, (_m, base: string) => {   // report.md -> "report", once
    const w = base.replace(/-/g, " ").toLowerCase();
    if (seen.has(w)) return "";
    seen.add(w); return w;
  });
  t = t.replace(/(,\s*)+(?=,|\s+and\b|\s+from\b)/g, "").replace(/\band\s+(?=from\b|,|\.)/g, "").replace(/,\s*(?=and\b)/g, " ")
       .replace(/\b(ai|eu|llm|rls|nist|dpia|slo|pii|rag|mcp|csv|sql)\b/gi, (m) => m.toUpperCase()).replace(/\s+([,.])/g, "$1").replace(/\s+/g, " ").trim();
  t = t.replace(/\s+-\s+.*$/, ".")                                                       // " - detail…" is detail
       .replace(/^(\w+ )(.+?)( from\b)/, (m, verb: string, list: string, from: string) =>        // "a, b from" -> "a and b from"
         / and /.test(list) || !list.includes(",") ? m : verb + list.replace(/,\s*([^,]+)$/, " and $1") + from);
  return t.length > 200 ? t.slice(0, 197).replace(/\s+\S*$/, "") + "…" : t;
}


/** Skill descriptions name the marker some skills write for unsourced numbers ("[TO BE BASELINED — owner: ___]");
 *  shown raw it reads as unfinished work, so descriptions say it in words. The skill files are unchanged. */
export const displayDescription = (s: string) =>
  s.replace(/\[?\s*TO BE BASELINED\s*[—-]\s*owner:\s*_+\s*\]?/gi, "a “to be baselined” flag naming the owner")
   .replace(/\[\s*TBD\s*\]/g, "a “to be decided” flag");
