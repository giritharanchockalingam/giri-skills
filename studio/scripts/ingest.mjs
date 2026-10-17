// ingest.mjs — reads the giri-skills repo (skills/, evals/results/<dir>/, docs/EVAL-FINDINGS.md)
// and writes studio/data/*.json. Zero dependencies. Run: npm run ingest
// Env: RESULTS_DIR (default evals/results/full-openai), relative to the repo root or absolute.

import { readFileSync, writeFileSync, readdirSync, existsSync, statSync, mkdirSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const STUDIO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = resolve(STUDIO, "..");
const RESULTS_DIR = resolve(ROOT, process.env.RESULTS_DIR || "evals/results/full-openai");
const OUT = join(STUDIO, "data");
mkdirSync(OUT, { recursive: true });

const DOMAIN_ORDER = ["presales", "build", "ai-platform", "career"];
const VERDICTS = ["OK", "DESC", "BODY", "BOTH"];

// ---------- helpers ----------
const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

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
    const nested = raw.match(/^\s+([\w-]+):\s*(.*)$/);
    const top = raw.match(/^([\w-]+):\s*(.*)$/);
    if (top) {
      const [, k, v] = top;
      if (v === "" ) { fm[k] = {}; current = k; }
      else { fm[k] = unquote(v); current = null; }
    } else if (nested && current) {
      fm[current][nested[1]] = unquote(nested[2]);
    }
  }
  return { fm, body: m[2] };
}
const unquote = (v) => {
  v = v.trim();
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) return v.slice(1, -1);
  return v;
};

// ---------- markdown -> safe HTML ----------
function inline(s) {
  // s is already HTML-escaped. Code spans first (protect their content).
  const codes = [];
  s = s.replace(/`([^`]+)`/g, (_, c) => { codes.push(`<code>${c}</code>`); return `\u0000${codes.length - 1}\u0000`; });
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, u) => {
    const safe = /^(https?:|mailto:|\/|#|\.)/.test(u) ? u : "#";
    return `<a href="${safe}"${safe.startsWith("http") ? ' target="_blank" rel="noopener"' : ""}>${t}</a>`;
  });
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/__([^_]+)__/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, "$1<em>$2</em>").replace(/(^|[^_\w])_([^_\n]+)_(?!\w)/g, "$1<em>$2</em>");
  s = s.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => codes[+i]);
}

function mdToHtml(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;
  const isTableSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
  const splitRow = (l) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    // fenced code
    const fence = line.match(/^\s*(```+|~~~+)\s*([\w.+-]*)/);
    if (fence) {
      const close = fence[1];
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].startsWith(close)) buf.push(lines[i++]);
      i++;
      out.push(`<pre><code${fence[2] ? ` class="lang-${esc(fence[2])}"` : ""}>${esc(buf.join("\n"))}</code></pre>`);
      continue;
    }
    // heading
    const h = line.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (h) {
      const lvl = h[1].length;
      const id = h[2].toLowerCase().replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-");
      out.push(`<h${lvl} id="${esc(id)}">${inline(esc(h[2]))}</h${lvl}>`);
      i++; continue;
    }
    // hr
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { out.push("<hr>"); i++; continue; }
    // table
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = splitRow(line);
      const aligns = splitRow(lines[i + 1]).map((c) => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : c.startsWith(":") ? "left" : ""));
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(splitRow(lines[i++]));
      const al = (k) => (aligns[k] ? ` style="text-align:${aligns[k]}"` : "");
      out.push(
        `<table><thead><tr>${head.map((c, k) => `<th${al(k)}>${inline(esc(c))}</th>`).join("")}</tr></thead><tbody>` +
          rows.map((r) => `<tr>${head.map((_, k) => `<td${al(k)}>${inline(esc(r[k] ?? ""))}</td>`).join("")}</tr>`).join("") +
          `</tbody></table>`,
      );
      continue;
    }
    // blockquote
    if (/^\s*>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push(`<blockquote>${mdToHtml(buf.join("\n"))}</blockquote>`);
      continue;
    }
    // lists (with nesting by indentation)
    const li = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (li) {
      out.push(renderList(lines, i, li[1].length));
      i = renderList.end;
      continue;
    }
    // paragraph
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*(```|~~~)|\s*>|\s*([-*+]|\d+[.)])\s)/.test(lines[i]) &&
      !(lines[i].includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))) buf.push(lines[i++].trim());
    out.push(`<p>${inline(esc(buf.join(" ")))}</p>`);
  }
  return out.join("\n");
}

function renderList(lines, start, indent) {
  let i = start;
  const first = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+/);
  const ordered = /\d/.test(first[2]);
  const items = [];
  while (i < lines.length) {
    const m = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (m && m[1].length === indent && /\d/.test(m[2]) === ordered) {
      items.push({ text: m[3], children: [] });
      i++;
      continue;
    }
    if (m && m[1].length > indent && items.length) {
      const sub = renderList(lines, i, m[1].length);
      items[items.length - 1].children.push(sub);
      i = renderList.end;
      continue;
    }
    // continuation line (indented, non-empty, not a list marker)
    if (!m && lines[i].trim() && /^\s+/.test(lines[i]) && items.length) {
      items[items.length - 1].text += " " + lines[i].trim();
      i++;
      continue;
    }
    break;
  }
  renderList.end = i;
  const tag = ordered ? "ol" : "ul";
  return `<${tag}>${items.map((it) => `<li>${inline(esc(it.text))}${it.children.join("")}</li>`).join("")}</${tag}>`;
}

// ---------- skills ----------
const skills = [];
for (const domain of readdirSync(join(ROOT, "skills")).sort()) {
  const ddir = join(ROOT, "skills", domain);
  if (!statSync(ddir).isDirectory()) continue;
  for (const name of readdirSync(ddir).sort()) {
    const sdir = join(ddir, name);
    const skillMd = join(sdir, "SKILL.md");
    if (!existsSync(skillMd)) continue;
    const { fm, body } = parseFrontmatter(readFileSync(skillMd, "utf8"));
    let evals = { skill: name, cases: [] };
    const evalPath = join(sdir, "evals", "evals.json");
    if (existsSync(evalPath)) {
      try { evals = JSON.parse(readFileSync(evalPath, "utf8")); } catch (e) { console.warn(`bad evals.json: ${evalPath}: ${e.message}`); }
    }
    skills.push({
      id: `${domain}/${name}`,
      domain,
      name: fm.name || name,
      description: fm.description || "",
      license: fm.license || null,
      metadata: typeof fm.metadata === "object" ? fm.metadata : {},
      bodyHtml: mdToHtml(body),
      files: {
        references: listFiles(join(sdir, "references")),
        assets: listFiles(join(sdir, "assets")),
        scripts: listFiles(join(sdir, "scripts")),
      },
      cases: (evals.cases || []).map((c) => ({ id: c.id, prompt: c.prompt, expected: c.expected || [] })),
    });
  }
}

// ---------- scorecard ----------
const scorecardMd = readFileSync(join(RESULTS_DIR, "scorecard.md"), "utf8");
const meta = { provider: null, model: null, runs: null, seed: null, date: null, spend: null, resultsDir: RESULTS_DIR.replace(ROOT + "/", "") };
for (const l of scorecardMd.split("\n")) {
  for (const k of ["provider", "model", "runs", "seed", "date"]) {
    const m = l.match(new RegExp(`${k}=([^\\s_]+)`));
    if (m) meta[k] = k === "runs" || k === "seed" ? Number(m[1]) : m[1];
  }
  const sp = l.match(/spend:\s*\$?([\d.,]+)/i);
  if (sp) meta.spend = `$${sp[1]}`;
}
const scorecard = [];
for (const l of scorecardMd.split("\n")) {
  if (!l.startsWith("|")) continue;
  const cells = l.split("|").slice(1, -1).map((c) => c.trim());
  if (cells.length < 7 || cells[0] === "skill" || /^-+$/.test(cells[0])) continue;
  const [id, trig, fp, without, with_, lift, verdict] = cells;
  const [domain, name] = id.split("/");
  scorecard.push({
    skill: id, domain, name,
    triggerAcc: Number(trig), fpRate: Number(fp), without: Number(without), with: Number(with_), lift: Number(lift),
    verdict: verdict.toUpperCase(),
  });
}

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

// ---------- write ----------
const w = (f, d) => writeFileSync(join(OUT, f), JSON.stringify(d, null, 1) + "\n");
w("skills.json", skills);
w("scorecard.json", scorecard);
w("trigger.json", trigger);
w("quality.json", quality);
w("findings.json", findings);
w("meta.json", { ...meta, counts: { skills: skills.length, scorecard: scorecard.length, trigger: trigger.length, quality: quality.length, findings: findings.proposals.length }, domains: DOMAIN_ORDER, verdicts: VERDICTS });

console.log(`ingest: skills=${skills.length} scorecard=${scorecard.length} trigger=${trigger.length} quality=${quality.length} findings=${findings.proposals.length} (results: ${meta.resultsDir})`);
