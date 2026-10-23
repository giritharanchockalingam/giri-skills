/* WP0 — Port tenant inventory (Skills Factory × Port spec §4.0, §10 WP0).
 *
 * Reads the tenant with PORT_CLIENT_ID / PORT_CLIENT_SECRET (and PORT_API_URL for a US/EU base) from the shell
 * environment and writes a Markdown inventory. Read-only: nothing is created, changed or deleted in Port.
 * The output never contains credentials or tokens; only identifiers, titles, counts and property names.
 *
 *   cd studio && node --experimental-strip-types scripts/port-inventory.mts ../docs/PORT-TENANT-INVENTORY.md
 *
 * What it records (every item the spec's WP0 asks for):
 *   - organization details Port exposes (name, region/base URL; plan/limits only where the API states them)
 *   - every blueprint: identifier, title, system (`_`-prefixed) or custom, property count, relation count
 *   - whether a native "skill" blueprint exists (spec §4.0 → extend it instead of creating sf_skill)
 *   - whether the built-in `_mcp_server` blueprint exists (spec §4.0 → never create a second one)
 *   - the factory's existing `aiSkill` blueprint (studio/docs/PORT.md, verified live 2026-10-20) and its entity count
 *   - every self-service action / automation and every scorecard the API lists
 * Anything a route refuses (403/404) is written as "not available on this account", never guessed.
 */
import { writeFileSync } from "node:fs";
import { PortClient, portConfig } from "../lib/integrations/port/client.ts";
import { BLUEPRINT_ID } from "../lib/integrations/port/map.ts";

type J = Record<string, unknown>;
const out = process.argv[2];
if (!out) { console.error("usage: node --experimental-strip-types scripts/port-inventory.mts <out.md>"); process.exit(2); }

const cfg = portConfig(process.env);
if (!cfg.ok) { console.error(`Port is not configured in this shell: set ${cfg.missing.join(" and ")} (and PORT_API_URL for a non-default region).`); process.exit(2); }

const port = new PortClient(cfg);
const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : JSON.stringify(v));
const n = (o: unknown) => (o && typeof o === "object" ? Object.keys(o as J).length : 0);
const md = (s: string) => s.replace(/\|/g, "\\|").replace(/\r?\n/g, " ");

async function readList(path: string, key: string): Promise<{ note: string; items: J[] }> {
  const r = await port.read(path);
  if (r.status >= 400) return { note: `${path} → HTTP ${r.status}${r.json.message ? `: ${str(r.json.message)}` : ""} (not available on this account or API version)`, items: [] };
  const v = r.json[key];
  return { note: `${path} → HTTP ${r.status}`, items: Array.isArray(v) ? (v as J[]) : [] };
}

const when = new Date().toISOString();
const lines: string[] = [];
const h = (s: string) => lines.push("", s, "");

lines.push(`# Port tenant inventory (WP0)`, "", `Generated ${when} by \`studio/scripts/port-inventory.mts\` against \`${cfg.apiUrl}\`. Read-only; no credentials or tokens appear in this file.`);

// ── organization ──
h("## Organization");
{
  const r = await port.read("/v1/organization");
  if (r.status >= 400) lines.push(`- \`/v1/organization\` → HTTP ${r.status}; organization details not readable with these credentials.`);
  else {
    const org = (r.json.organization ?? r.json) as J;
    const known: [string, unknown][] = [["name", org.name], ["identifier", org.identifier ?? org.id], ["created", org.createdAt], ["region (API base)", cfg.apiUrl]];
    for (const [k, v] of known) if (v != null && v !== "") lines.push(`- ${k}: ${md(str(v))}`);
    const plan = org.plan ?? org.tier ?? org.subscription ?? org.billing;
    lines.push(plan != null ? `- plan (as the API states it): ${md(str(plan))}` : `- plan / limits: **not exposed by \`/v1/organization\`** — record from Port UI → Settings → Billing before WP1 (spec §11: blueprint/action counts are plan-gated).`);
    const limits = org.limits ?? org.quotas;
    if (limits != null) lines.push(`- limits (as the API states them): ${md(str(limits))}`);
  }
}

// ── blueprints ──
h("## Blueprints");
const bps = await readList("/v1/blueprints", "blueprints");
lines.push(`_${bps.note}_`, "");
if (bps.items.length) {
  lines.push("| identifier | title | kind | properties | relations | notes |", "|---|---|---|---|---|---|");
  for (const b of bps.items.sort((a, c) => str(a.identifier).localeCompare(str(c.identifier)))) {
    const id = str(b.identifier);
    const schema = (b.schema ?? {}) as J;
    const notes: string[] = [];
    if (id === "_mcp_server") notes.push("built-in MCP registry — register the factory MCP server as an entity here (§5.4)");
    if (id === BLUEPRINT_ID) notes.push("factory's existing AI Skill blueprint (studio/docs/PORT.md, live since 2026-10-20)");
    if (/skill/i.test(id) && id !== BLUEPRINT_ID) notes.push("name contains 'skill' — candidate native skill blueprint (§4.0: extend, don't duplicate)");
    if (/mcp/i.test(id) && id !== "_mcp_server") notes.push("name contains 'mcp'");
    lines.push(`| \`${md(id)}\` | ${md(str(b.title))} | ${id.startsWith("_") ? "system" : "custom"} | ${n(schema.properties)} | ${n(b.relations)} | ${md(notes.join("; "))} |`);
  }
}
const ids = new Set(bps.items.map((b) => str(b.identifier)));
h("### §4.0 checks");
lines.push(`- Built-in \`_mcp_server\` blueprint present: **${ids.has("_mcp_server") ? "yes" : "no"}**`);
const nativeSkill = [...ids].filter((i) => /skill/i.test(i) && i !== BLUEPRINT_ID);
lines.push(`- Native Port skill blueprint present: **${nativeSkill.length ? `candidate(s): ${nativeSkill.map((i) => `\`${i}\``).join(", ")} — confirm in Port UI whether Port-managed` : "no (only the factory's own, if listed)"}**`);
lines.push(`- Factory \`${BLUEPRINT_ID}\` blueprint present: **${ids.has(BLUEPRINT_ID) ? "yes" : "no"}**`);
lines.push(`- Custom blueprints in use: **${[...ids].filter((i) => !i.startsWith("_")).length}** (plan-gated — compare with the plan limit above).`);

// ── entity counts for the blueprints that matter ──
h("## Entity counts (skill / MCP / repository blueprints)");
for (const id of [...ids].filter((i) => i === BLUEPRINT_ID || i === "_mcp_server" || /skill|repository|service|mcp/i.test(i))) {
  try {
    const r = await port.listEntities(id);
    lines.push(`- \`${md(id)}\`: ${r.entities.length}${r.truncated ? "+ (truncated at 2,000)" : ""} entities`);
  } catch (e) { lines.push(`- \`${md(id)}\`: could not read — ${md((e as Error).message)}`); }
}

// ── schemas of the blueprints WP1 designs against ──
h("## Blueprint schemas (skill / MCP / repository / service)");
for (const b of bps.items.filter((x) => { const i = str(x.identifier); return i === BLUEPRINT_ID || i === "_mcp_server" || /^skill$|skill/i.test(i) || i === "githubRepository" || i === "service"; })) {
  const id = str(b.identifier), schema = (b.schema ?? {}) as J, props = (schema.properties ?? {}) as J, rels = (b.relations ?? {}) as J;
  lines.push(`### \`${md(id)}\``, "", `- created: ${md(str(b.createdAt))} by ${md(str(b.createdBy))}; updated: ${md(str(b.updatedAt))} by ${md(str(b.updatedBy))}`, `- required: ${md(str(schema.required ?? []))}`, "");
  lines.push("| property | type | format | enum | title |", "|---|---|---|---|---|");
  for (const [k, v] of Object.entries(props)) { const p = (v ?? {}) as J; lines.push(`| \`${md(k)}\` | ${md(str(p.type))} | ${md(str(p.format ?? ""))} | ${md(Array.isArray(p.enum) ? (p.enum as unknown[]).join(", ") : "")} | ${md(str(p.title ?? ""))} |`); }
  if (Object.keys(rels).length) { lines.push("", "| relation | target | required | many |", "|---|---|---|---|"); for (const [k, v] of Object.entries(rels)) { const r = (v ?? {}) as J; lines.push(`| \`${md(k)}\` | \`${md(str(r.target))}\` | ${md(str(r.required ?? false))} | ${md(str(r.many ?? false))} |`); } }
  if (id !== "_mcp_server") try {
    const r = await port.listEntities(id, 3);
    lines.push("", `Sample identifiers (first 3): ${r.entities.map((e) => `\`${md(str(e.identifier))}\``).join(", ") || "none"}`);
    const first = r.entities[0] as J | undefined;
    if (first) lines.push(`First entity: created ${md(str(first.createdAt))} by ${md(str(first.createdBy))}; property keys present: ${Object.keys((first.properties ?? {}) as J).map((k) => `\`${md(k)}\``).join(", ")}`);
  } catch (e) { lines.push("", `Entities not readable: ${md((e as Error).message)}`); }
  lines.push("");
}

// ── actions / automations ──
h("## Self-service actions and automations");
const acts = await readList("/v1/actions", "actions");
lines.push(`_${acts.note}_`, "");
if (acts.items.length) {
  lines.push("| identifier | title | trigger | blueprint | invocation | notes |", "|---|---|---|---|---|---|");
  for (const a of acts.items) {
    const trig = (a.trigger ?? {}) as J, inv = (a.invocationMethod ?? {}) as J;
    const notes: string[] = [];
    if (/^run_(ai_)?skill|run_sf_skill/.test(str(a.identifier))) notes.push("factory run action (classic) — §5.3 target to extend/replace");
    lines.push(`| \`${md(str(a.identifier))}\` | ${md(str(a.title))} | ${md(str(trig.type))}${trig.operation ? `/${md(str(trig.operation))}` : ""} | ${md(str(trig.blueprintIdentifier ?? ""))} | ${md(str(inv.type))} | ${md(notes.join("; "))} |`);
  }
}
lines.push("", "_Port Workflows (the newer builder) are not listed by `/v1/actions`; record any existing workflow (e.g. the 2026-10-20 \"Run governed skill\" workflow) from the Port UI below._", "", "- Workflows seen in UI: _to be recorded by owner_");

// ── scorecards ──
h("## Scorecards");
const sc = await readList("/v1/scorecards", "scorecards");
lines.push(`_${sc.note}_`, "");
if (sc.items.length) {
  lines.push("| blueprint | identifier | title | levels | rules |", "|---|---|---|---|---|");
  for (const s of sc.items) {
    const levels = Array.isArray(s.levels) ? (s.levels as J[]).map((l) => str(l.title)).join(" → ") : "";
    lines.push(`| \`${md(str(s.blueprint))}\` | \`${md(str(s.identifier))}\` | ${md(str(s.title))} | ${md(levels)} | ${Array.isArray(s.rules) ? s.rules.length : 0} |`);
  }
} else lines.push("- none listed");

// ── credentials & secrets ──
h("## Credentials and secrets (locations only)");
lines.push(
  "- `PORT_CLIENT_ID`, `PORT_CLIENT_SECRET`: Vercel project `giri-skills-studio`, production, type *sensitive* (not readable after creation).",
  "- `PORT_SF_API_KEY`: same place — the factory workspace key Port's webhook runs under.",
  "- `PORT_API_URL`: set only for a non-default region.",
  "- Port-side secret `SF_API_KEY` (Settings → Secrets): the workspace key the MCP connector and workflow use.",
  "- Spec §11 (token single-flight): confirm these Port credentials are **dedicated to the factory** and not shared with any other integration — _owner to confirm_.",
);

writeFileSync(out, lines.join("\n") + "\n");
console.log(`wrote ${out}: ${bps.items.length} blueprints, ${acts.items.length} actions, ${sc.items.length} scorecards`);
