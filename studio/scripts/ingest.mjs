// ingest.mjs — reads the giri-skills repo (skills/, evals/results/<dir>/, docs/EVAL-FINDINGS.md)
// and writes studio/data/*.json. Zero dependencies. Run: npm run ingest
// Env: RESULTS_DIR (default evals/results/full-openai) for trigger/quality/scorecard,
//      AGENT_RESULTS_DIR (default evals/results/agent-dry) for agent.csv + the agent columns of its scorecard.md.
//      Both relative to the repo root or absolute.

import { readFileSync, writeFileSync, readdirSync, existsSync, statSync, mkdirSync, rmSync, copyFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { esc, mdToHtml } from "../lib/markdown.mjs";

const STUDIO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = resolve(STUDIO, "..");
const RESULTS_DIR = resolve(ROOT, process.env.RESULTS_DIR || "evals/results/full-openai");
const AGENT_RESULTS_DIR = resolve(ROOT, process.env.AGENT_RESULTS_DIR || "evals/results/agent-dry");
const OUT = join(STUDIO, "data");
mkdirSync(OUT, { recursive: true });

const DOMAIN_ORDER = ["presales", "build", "ai-platform", "career"];
const VERDICTS = ["OK", "DESC", "BODY", "BOTH"];

// ---------- helpers ----------

function listFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => !f.startsWith(".") && f !== "__pycache__" && !f.endsWith(".pyc"))
    .flatMap((f) => {
      const p = join(dir, f);
      return statSync(p).isDirectory() ? listFiles(p).map((x) => `${f}/${x}`) : [f];
    })
    .sort();
}

// RFC-4180-ish CSV parser: handles quoted fields, escaped quotes (""), commas and newlines inside quotes.
function parseCsv(text) {
  const rows = [];
  let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false;
      } else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  const header = rows.shift().map((h) => h.trim());
  return rows
    .filter((r) => r.length > 1 || (r.length === 1 && r[0] !== ""))
    .map((r) => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ""])));
}

// ---------- minimal YAML frontmatter (flat keys + one nested map level) ----------
function parseFrontmatter(md) {
  const m = md.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return { fm: {}, body: md };
  const fm = {};
  let current = null;
  for (const raw of m[1].split(/\r?\n/)) {
    if (!raw.trim()) continue;
    const nested = raw.match(/^  ([\w-]+):\s*(.*)$/);
    const top = raw.match(/^([\w-]+):\s*(.*)$/);
    if (top) {
      const [, k, v] = top;
      if (v === "" ) { fm[k] = {}; current = k; }
      else { fm[k] = unquote(v); current = null; }
    } else if (nested && current && nested[2] !== "") {
      fm[current][nested[1]] = unquote(nested[2]);
    }
  }
  return { fm, body: m[2], raw: m[1] };
}

// ---------- metadata.agent (inputs / run / outputs as `- {flow maps}`) ----------
function splitTop(s, sep) {
  const parts = []; let depth = 0, quote = null, buf = "";
  for (const ch of s) {
    if (quote) { buf += ch; if (ch === quote) quote = null; continue; }
    if (ch === '"' || ch === "'") { quote = ch; buf += ch; }
    else if (ch === "[" || ch === "{") { depth++; buf += ch; }
    else if (ch === "]" || ch === "}") { depth--; buf += ch; }
    else if (ch === sep && depth === 0) { parts.push(buf); buf = ""; }
    else buf += ch;
  }
  if (buf.trim() || parts.length) parts.push(buf);
  return parts.map((p) => p.trim()).filter(Boolean);
}
function scalar(v) {
  v = unquote(v);
  return v === "true" ? true : v === "false" ? false : v;
}
function parseFlow(s) {
  s = s.trim();
  if (s.startsWith("{") && s.endsWith("}")) {
    const o = {};
    for (const item of splitTop(s.slice(1, -1), ",")) {
      const k = item.match(/^([\w-]+):\s*([\s\S]*)$/);
      if (k) o[k[1]] = parseFlow(k[2]);
    }
    return o;
  }
  if (s.startsWith("[") && s.endsWith("]")) return splitTop(s.slice(1, -1), ",").map((x) => (/^[\[{]/.test(x) ? parseFlow(x) : unquote(x)));
  return scalar(s);
}
function parseAgent(rawFm) {
  const lines = rawFm.split(/\r?\n/);
  const start = lines.findIndex((l) => /^  agent:\s*$/.test(l));
  if (start < 0) return null;
  const agent = { inputs: [], steps: [], run: [], outputs: [], demo: null };
  let section = null;
  for (let i = start + 1; i < lines.length; i++) {
    const l = lines[i];
    if (/^\S/.test(l) || /^  [\w-]+:/.test(l)) break;
    const sec = l.match(/^    (inputs|run|outputs):\s*$/);
    if (sec) { section = sec[1] === "run" ? "steps" : sec[1]; continue; }
    const item = l.match(/^      - (\{[\s\S]*\})\s*$/);
    if (item && section) {
      const o = parseFlow(item[1]);
      if (section === "inputs") agent.inputs.push({ name: o.name ?? "", type: o.type ?? "", required: o.required === true, from: o.from ?? "", default: o.default ?? null, flag: o.flag ?? null, copy: o.copy === true });
      else if (section === "steps") { agent.steps.push({ step: o.step ?? "", kind: o.kind ?? "" }); agent.run.push(o); } // run: the full step spec (cmd/template/context/out/…) for the factory manifest
      else agent.outputs.push({ path: o.path ?? "", checks: (Array.isArray(o.checks) ? o.checks : []).map((c) => (typeof c === "string" ? c : JSON.stringify(c))) });
    }
  }
  return agent.inputs.length || agent.steps.length || agent.outputs.length ? agent : null;
}
const unquote = (v) => {
  v = v.trim();
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) return v.slice(1, -1);
  return v;
};

// ---------- skills ----------
const skills = [];
for (const domain of readdirSync(join(ROOT, "skills")).sort()) {
  const ddir = join(ROOT, "skills", domain);
  if (!statSync(ddir).isDirectory()) continue;
  for (const name of readdirSync(ddir).sort()) {
    const sdir = join(ddir, name);
    const skillMd = join(sdir, "SKILL.md");
    if (!existsSync(skillMd)) continue;
    const { fm, body, raw } = parseFrontmatter(readFileSync(skillMd, "utf8"));
    let evals = { skill: name, cases: [] };
    const evalPath = join(sdir, "evals", "evals.json");
    if (existsSync(evalPath)) {
      try { evals = JSON.parse(readFileSync(evalPath, "utf8")); } catch (e) { console.warn(`bad evals.json: ${evalPath}: ${e.message}`); }
    }
    const agent = parseAgent(raw || "");
    if (agent) {
      // the happy-path eval case the runner's --demo uses (same pick as run_skill.demo_args): fixture paths kept relative to the skill dir
      const withInputs = (evals.cases || []).filter((c) => c.inputs && Object.keys(c.inputs).length);
      const demoCase = withInputs.find((c) => String(c.id || "").includes("happy")) || withInputs[0] || null;
      agent.demo = demoCase
        ? { caseId: demoCase.id, inputs: Object.fromEntries(Object.entries(demoCase.inputs).map(([k, v]) => [k, String(v)])), assume: Object.fromEntries(Object.entries(demoCase.assume || {}).map(([k, v]) => [k, String(v)])) }
        : null;
    }
    skills.push({
      id: `${domain}/${name}`,
      domain,
      stage: (typeof fm.metadata === "object" && fm.metadata.adlc_stage) || null,
      name: fm.name || name,
      description: fm.description || "",
      license: fm.license || null,
      metadata: typeof fm.metadata === "object" ? fm.metadata : {},
      agent,
      bodyHtml: mdToHtml(body),
      files: {
        references: listFiles(join(sdir, "references")),
        assets: listFiles(join(sdir, "assets")),
        scripts: listFiles(join(sdir, "scripts")),
      },
      cases: (evals.cases || []).map((c) => ({ id: c.id, prompt: c.prompt, expected: c.expected || [] })),
      // agent cases (inputs + deterministic checks) become evaluation cases when the skill is imported into the factory
      agentCases: (evals.cases || []).filter((c) => c.inputs || c.checks).map((c) => ({
        id: c.id, prompt: c.prompt || "", inputs: Object.fromEntries(Object.entries(c.inputs || {}).map(([k, v]) => [k, String(v)])),
        assume: Object.fromEntries(Object.entries(c.assume || {}).map(([k, v]) => [k, String(v)])), checks: c.checks || [], expected: c.expected || [],
      })),
      bodyMd: body,
    });
  }
}

// ---------- scorecard ----------
const scorecardMd = readFileSync(join(RESULTS_DIR, "scorecard.md"), "utf8");
const meta = { provider: null, model: null, runs: null, seed: null, date: null, spend: null, resultsDir: RESULTS_DIR.replace(ROOT + "/", ""), agentResultsDir: AGENT_RESULTS_DIR.replace(ROOT + "/", "") };
for (const l of scorecardMd.split("\n")) {
  for (const k of ["provider", "model", "runs", "seed", "date"]) {
    const m = l.match(new RegExp(`${k}=([^\\s_]+)`));
    if (m) meta[k] = k === "runs" || k === "seed" ? Number(m[1]) : m[1];
  }
  const sp = l.match(/spend:\s*\$?([\d.,]+)/i);
  if (sp) meta.spend = `$${sp[1]}`;
}
const scorecardCells = (md) => md.split("\n")
  .filter((l) => l.startsWith("|"))
  .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()))
  .filter((cells) => cells.length >= 7 && cells[0] !== "skill" && !/^-+$/.test(cells[0]));
const scorecard = [];
for (const cells of scorecardCells(scorecardMd)) {
  const [id, trig, fp, without, with_, lift, verdict] = cells;
  const [domain, name] = id.split("/");
  scorecard.push({
    skill: id, domain, name,
    triggerAcc: Number(trig), fpRate: Number(fp), without: Number(without), with: Number(with_), lift: Number(lift),
    verdict: verdict.toUpperCase(), agentPass: null, agentVerdict: null,
  });
}

// ---------- agent results (deterministic run_skill.py checks; separate results dir) ----------
const AGENT_VERDICTS = ["Works", "Partial", "Broken"];
let agent = [];
const agentCsv = join(AGENT_RESULTS_DIR, "agent.csv");
if (existsSync(agentCsv)) {
  agent = parseCsv(readFileSync(agentCsv, "utf8")).map((r) => ({
    skill: r.skill, caseId: r.case_id, check: r.check, pass: r.pass === "1" || r.pass.toUpperCase() === "PASS", evidence: r.evidence,
  }));
  const byId = new Map(scorecard.map((r) => [r.skill, r]));
  // pass share from the rows; verdict from the agent scorecard columns when present, else from the pass share (>= .9 Works, >= .5 Partial)
  const passes = new Map();
  for (const a of agent) { const p = passes.get(a.skill) ?? { n: 0, ok: 0 }; p.n++; if (a.pass) p.ok++; passes.set(a.skill, p); }
  for (const [id, p] of passes) {
    const row = byId.get(id);
    if (!row) { console.warn(`agent.csv skill not in scorecard: ${id}`); continue; }
    row.agentPass = Number((p.ok / p.n).toFixed(4));
    row.agentVerdict = row.agentPass >= 0.9 ? "Works" : row.agentPass >= 0.5 ? "Partial" : "Broken";
  }
  const agentScorecard = join(AGENT_RESULTS_DIR, "scorecard.md");
  if (existsSync(agentScorecard)) {
    for (const cells of scorecardCells(readFileSync(agentScorecard, "utf8"))) {
      const row = byId.get(cells[0]);
      if (!row || cells.length < 9) continue;
      const v = AGENT_VERDICTS.find((x) => x.toLowerCase() === cells[8].toLowerCase());
      if (cells[7] !== "" && !Number.isNaN(Number(cells[7]))) row.agentPass = Number(cells[7]);
      if (v) row.agentVerdict = v;
    }
  }
} else {
  console.warn(`no agent results at ${agentCsv} (set AGENT_RESULTS_DIR)`);
}
const agentWorks = scorecard.filter((r) => r.agentVerdict === "Works").length;

// ---------- trigger / quality ----------
const trigger = parseCsv(readFileSync(join(RESULTS_DIR, "trigger.csv"), "utf8")).map((r) => ({
  skill: r.skill, caseId: r.case_id, run: Number(r.run), selected: r.selected,
  correct: r.correct === "" ? null : Number(r.correct),
}));
const quality = parseCsv(readFileSync(join(RESULTS_DIR, "quality.csv"), "utf8")).map((r) => ({
  skill: r.skill, caseId: r.case_id, run: Number(r.run), mode: r.mode,
  expectedIdx: Number(r.expected_idx), pass: r.pass === "PASS", evidence: r.evidence,
}));

// ---------- findings ----------
function parseFindings(md) {
  const lines = md.split("\n");
  const section = (title) => {
    const s = lines.findIndex((l) => l.trim() === title);
    if (s < 0) return [];
    let e = s + 1;
    while (e < lines.length && !/^## /.test(lines[e])) e++;
    return lines.slice(s + 1, e);
  };
  const caveatsLines = section("## Caveats (read before acting on any proposal)");
  const caveatsHtml = mdToHtml(caveatsLines.join("\n"));
  const intro = lines.slice(0, lines.findIndex((l) => /^## /.test(l))).filter((l) => l.startsWith(">")).map((l) => l.replace(/^>\s?/, "")).join(" ");

  const vcLines = section("## Verdict counts");
  const verdictCounts = [];
  for (const l of vcLines) {
    if (!l.startsWith("|")) continue;
    const c = l.split("|").slice(1, -1).map((x) => x.trim().replace(/\*\*/g, ""));
    if (c[0] === "Domain" || /^-+$/.test(c[0])) continue;
    const dm = c[0].match(/^([\w-]+(?: \(\d+\))?)/);
    verdictCounts.push({ domain: dm ? dm[1] : c[0], OK: +c[1], DESC: +c[2], BODY: +c[3], BOTH: +c[4] });
  }
  const notes = mdToHtml(vcLines.filter((l) => !l.startsWith("|")).join("\n"));

  // proposals
  const rp = lines.findIndex((l) => l.trim() === "## Ranked proposals");
  let end = lines.findIndex((l, k) => k > rp && /^## /.test(l));
  if (end < 0) end = lines.length;
  // join proposal headers that wrap across lines ("**N. skill — VERDICT (stats\ncontinued).**")
  const block = [];
  for (let q = rp + 1; q < end; q++) {
    let l = lines[q];
    if (/^\*\*\d+\.\s/.test(l)) {
      while (!/\)\.\*\*/.test(l) && q + 1 < end && lines[q + 1].trim()) l += " " + lines[++q].trim();
    }
    block.push(l);
  }
  const proposals = [];
  let domain = null;
  let cur = null;
  let k = 0;
  const flush = () => { if (cur) { finalize(cur); proposals.push(cur); cur = null; } };
  while (k < block.length) {
    const l = block[k];
    const dh = l.match(/^### (.+)$/);
    if (dh) { flush(); domain = dh[1].trim(); k++; continue; }
    const start = l.match(/^\*\*(\d+)\.\s+([\w-]+)\s+—\s+(\w+)\s*\(([^)]*)\)\.\*\*\s*(.*)$/);
    if (start) {
      flush();
      cur = { number: +start[1], skill: `${domain}/${start[2]}`, name: start[2], domain, verdict: start[3].toUpperCase(), stats: start[4].trim(), evidence: start[5].trim(), descriptionProposal: null, bodyProposal: null, _raw: [] };
      k++; continue;
    }
    if (cur) cur._raw.push(l);
    k++;
  }
  flush();
  function finalize(p) {
    const raw = p._raw;
    delete p._raw;
    let j = 0;
    // evidence continues until a blank line or "Description"/"Body:" marker
    const evid = [];
    while (j < raw.length && raw[j].trim() && !/^Description\s*\(paste-ready\):/i.test(raw[j]) && !/^Body:/i.test(raw[j])) evid.push(raw[j++].trim());
    p.evidence = [p.evidence, ...evid].join(" ").replace(/\s+/g, " ").trim();
    while (j < raw.length) {
      const l = raw[j];
      if (/^Description\s*\(paste-ready\):/i.test(l)) {
        j++;
        while (j < raw.length && !raw[j].startsWith("```")) j++;
        j++;
        const buf = [];
        while (j < raw.length && !raw[j].startsWith("```")) buf.push(raw[j++]);
        j++;
        p.descriptionProposal = buf.join("\n").trim();
        continue;
      }
      const b = l.match(/^Body:\s*(.*)$/i);
      if (b) {
        const buf = [b[1]];
        j++;
        while (j < raw.length && raw[j].trim()) buf.push(raw[j++].trim());
        p.bodyProposal = buf.join(" ").replace(/\s+/g, " ").trim();
        continue;
      }
      j++;
    }
  }
  return { intro, caveatsHtml, verdictCounts, verdictNotesHtml: notes, proposals };
}
const findings = parseFindings(readFileSync(join(ROOT, "docs", "EVAL-FINDINGS.md"), "utf8"));

// ---------- upstream (vendored top-50: catalog/top-50.json + vendor/pins.json + vendor/<name>/SKILL.md) ----------
// The upstream SKILL.md frontmatter is not ours: `description` may be a plain, quoted, folded (>, >-) or literal (|, |-)
// scalar spanning several indented lines. Read the scalar by hand instead of trusting parseFrontmatter's one-line keys.
function fmScalar(rawFm, key) {
  const lines = rawFm.split(/\r?\n/);
  const start = lines.findIndex((l) => new RegExp(`^${key}:`).test(l));
  if (start < 0) return "";
  let first = lines[start].slice(key.length + 1).trim();
  const rest = [];
  for (let i = start + 1; i < lines.length; i++) {
    if (/^\s+\S/.test(lines[i]) || (rest.length && !lines[i].trim() && /^\s/.test(lines[i + 1] ?? ""))) rest.push(lines[i].trim());
    else break;
  }
  const block = first.match(/^([>|])[-+]?\s*$/);
  if (block) return rest.join(block[1] === ">" ? " " : "\n").replace(/\s+/g, " ").trim();
  const joined = [first, ...rest].join(" ").trim();
  return unquote(joined).replace(/\s+/g, " ").trim();
}
const VENDOR_ORGS = ["anthropics", "vercel-labs", "supabase", "stripe", "cloudflare", "microsoft", "google", "getsentry", "langchain-ai", "shadcn"];
const upstream = [];
const top50Path = join(ROOT, "catalog", "top-50.json");
const pinsPath = join(ROOT, "vendor", "pins.json");
if (existsSync(top50Path) && existsSync(pinsPath)) {
  const top50 = JSON.parse(readFileSync(top50Path, "utf8"));
  const pins = JSON.parse(readFileSync(pinsPath, "utf8"));
  for (const t of [...top50].sort((a, b) => a.rank - b.rank)) {
    const pin = pins[t.name];
    const vdir = join(ROOT, "vendor", t.name);
    const skillMd = join(vdir, "SKILL.md");
    if (!pin || !existsSync(skillMd)) { console.warn(`upstream: no pin or SKILL.md for ${t.name}`); continue; }
    const { fm, body, raw } = parseFrontmatter(readFileSync(skillMd, "utf8"));
    const license = pin.license || t.license || "";
    const sha = pin.sha || "";
    const path = pin.path || t.path;
    const repo = pin.repo || t.repo;
    upstream.push({
      rank: t.rank,
      name: t.name,
      repo, path, sha, shortSha: sha.slice(0, 7),
      category: t.category,
      license,
      licenseKind: /Anthropic source-available/i.test(license) ? "source-available" : "oss",
      origin: VENDOR_ORGS.includes(repo.split("/")[0]) ? "vendor" : "community",
      evidence: t.evidence || "",
      why: t.why || "",
      fetched: pin.fetched || null,
      description: fmScalar(raw || "", "description") || fm.description || "",
      bodyHtml: mdToHtml(body),
      // the vendored upstream files; UPSTREAM.md is our provenance note, not theirs
      fileCount: listFiles(vdir).filter((f) => f !== "UPSTREAM.md").length,
      url: `https://github.com/${repo}/tree/${sha}/${path}`,
    });
  }
} else {
  console.warn(`no upstream catalog at ${top50Path} / ${pinsPath}`);
}

// ---------- runtime bundle for the in-browser Run view (public/runtime/) ----------
// The runner (scripts/*.py), shared/*.md and, per wired skill, SKILL.md + scripts/ + assets/ + references/ + evals/fixtures/,
// copied with their repo-relative paths so run_skill.py finds everything under /repo in Pyodide's virtual FS.
// Excluded: evals/results, docs, vendor, tests, __pycache__.
const RUNTIME = join(STUDIO, "public", "runtime");
rmSync(RUNTIME, { recursive: true, force: true });
const runtimeFiles = [];
// never ship what the repo keeps local (.gitignore: personal inputs such as the real master résumé or rate card)
const ignoreGlobs = existsSync(join(ROOT, ".gitignore"))
  ? readFileSync(join(ROOT, ".gitignore"), "utf8").split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith("#"))
  : [];
const globRe = (g) => new RegExp("^" + g.replace(/^\//, "").replace(/\/$/, "").replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, "[^/]*") + "(/|$)");
const ignored = (rel) => ignoreGlobs.some((g) => (g.includes("/") ? globRe(g).test(rel) : rel.split("/").some((seg) => globRe(g).test(seg))));
const copyRel = (rel) => {
  const src = join(ROOT, rel);
  if (!existsSync(src) || ignored(rel)) return;
  if (statSync(src).isDirectory()) { for (const f of listFiles(src)) copyRel(`${rel}/${f}`); return; }
  const dest = join(RUNTIME, "repo", rel);
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(src, dest);
  runtimeFiles.push({ path: rel, size: statSync(src).size });
};
for (const f of ["run_skill.py", "check_output.py", "skillmeta.py", "behavioral_evals.py"]) copyRel(`scripts/${f}`);
for (const f of listFiles(join(ROOT, "shared")).filter((f) => f.endsWith(".md"))) copyRel(`shared/${f}`);
for (const s of skills) {
  if (!s.agent) continue;
  copyRel(`skills/${s.id}/SKILL.md`);
  for (const sub of ["scripts", "assets", "references", "evals/fixtures", "evals/evals.json"]) copyRel(`skills/${s.id}/${sub}`);
  // files a step reads from outside the skill (e.g. a wrapped upstream skill's ../../../vendor/<name>/SKILL.md)
  const rawMd = readFileSync(join(ROOT, "skills", s.id, "SKILL.md"), "utf8");
  for (const m of rawMd.matchAll(/\.\.\/\.\.\/\.\.\/(vendor\/[A-Za-z0-9._-]+\/[A-Za-z0-9._\/-]+)/g)) copyRel(m[1]);
}
const runtimeBytes = runtimeFiles.reduce((a, f) => a + f.size, 0);
// one fetch instead of 450: every runtime file's text keyed by its repo-relative path (all are UTF-8 text; the build fails otherwise)
const bundle = {};
for (const f of runtimeFiles) {
  const buf = readFileSync(join(RUNTIME, "repo", f.path));
  try { bundle[f.path] = new TextDecoder("utf-8", { fatal: true }).decode(buf); } catch { throw new Error(`runtime bundle: ${f.path} is not UTF-8 text`); }
}
writeFileSync(join(RUNTIME, "bundle.json"), JSON.stringify(bundle));
// Content pin per repo skill: sha256 over its own files + the shared runner (scripts/*.py) and prompts (shared/*.md),
// sorted by path. A version records the pin when it leaves draft; the server refuses to run it on different files.
{
  const { createHash } = await import("node:crypto");
  const paths = Object.keys(bundle).sort();
  const common = paths.filter((p) => p.startsWith("scripts/") || p.startsWith("shared/"));
  const pins = {};
  const vendorRefs = (id) => [...readFileSync(join(ROOT, "skills", id, "SKILL.md"), "utf8").matchAll(/\.\.\/\.\.\/\.\.\/(vendor\/[A-Za-z0-9._-]+\/[A-Za-z0-9._\/-]+)/g)].map((m) => m[1]).sort();
  for (const s of skills) {
    if (!s.agent) continue;
    const h = createHash("sha256");
    for (const p of [...common, ...paths.filter((x) => x.startsWith(`skills/${s.id}/`)), ...vendorRefs(s.id).filter((x) => x in bundle)]) h.update(p + "\0" + bundle[p] + "\0");
    pins[s.id] = h.digest("hex");
  }
  writeFileSync(join(OUT, "content-pins.json"), JSON.stringify(pins, null, 1) + "\n");
}
// the Vercel Python runtime (api/py/run.py) reads the same bundle from its own folder; committed so the function has it whatever the build order
writeFileSync(join(STUDIO, "api", "py", "bundle.json"), JSON.stringify(bundle));
writeFileSync(join(RUNTIME, "manifest.json"), JSON.stringify({
  generated: new Date().toISOString(), root: "/repo", files: runtimeFiles, bytes: runtimeBytes,
  pyodide: { version: "0.27.7", url: "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js" },
}, null, 1) + "\n");

// ---------- write ----------
const w = (f, d) => writeFileSync(join(OUT, f), JSON.stringify(d, null, 1) + "\n");
w("upstream.json", upstream);
w("skills.json", skills);
w("stages.json", JSON.parse(readFileSync(join(ROOT, "shared", "adlc-stages.json"), "utf8")));
w("scorecard.json", scorecard);
w("trigger.json", trigger);
w("quality.json", quality);
w("agent.json", agent);
w("findings.json", findings);
w("meta.json", { ...meta, counts: { skills: skills.length, scorecard: scorecard.length, trigger: trigger.length, quality: quality.length, findings: findings.proposals.length, agent: agent.length, agentWorks, upstream: upstream.length }, domains: DOMAIN_ORDER, verdicts: VERDICTS, agentVerdicts: AGENT_VERDICTS });

console.log(`ingest: runtime bundle: ${runtimeFiles.length} files, ${(runtimeBytes / 1024).toFixed(0)} KB -> public/runtime/`);
console.log(`ingest: skills=${skills.length} scorecard=${scorecard.length} trigger=${trigger.length} quality=${quality.length} findings=${findings.proposals.length} agent=${agent.length} agentWorks=${agentWorks} wired=${skills.filter((s) => s.agent).length} upstream=${upstream.length} (results: ${meta.resultsDir}; agent: ${meta.agentResultsDir})`);
