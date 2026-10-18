// markdown.mjs — the studio's hand-rolled, dependency-free Markdown → safe HTML renderer.
// Used at build time by scripts/ingest.mjs (SKILL.md bodies, findings) and in the browser by the Run view
// (rendering .md outputs a run produced). Every text node is HTML-escaped first; links only keep http(s)/mailto/relative hrefs.

export const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function inline(s) {
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

export function mdToHtml(md) {
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

