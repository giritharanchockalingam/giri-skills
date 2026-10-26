#!/usr/bin/env python3
"""The partner-grade parts of the architecture document, all derived from components.json and nothing else.

  bottom_line      the recommendation in one paragraph: what the system is, the decisions taken, the waves
  drivers          goals and constraints, each with its source
  options          per decision: weighted option scores (computed), the choice, and a flag when the choice is not
                   the top score
  adr_files        one Architecture Decision Record per decision (Nygard format)
  risks            likelihood x impact, sorted, with owner and mitigation
  waves            goal, entry, exit and rollback per wave
  security         controls by area, each with its source
  open_items       every gap the document carries, with the section it comes from
  sources          every source the document cites
  to_html          the whole document as one self-contained, printable HTML page with the diagrams inline

Any value the input does not give is [TO BE BASELINED — owner: Solution architect]; a computed value (a weighted
score, a risk rating) shows how it was computed. Stdlib only.
"""
from __future__ import annotations

import re
from html import escape

TBD = "[TO BE BASELINED — owner: Solution architect]"
LEVEL = {"low": 1, "medium": 3, "high": 5}          # stated convention for word ratings; numbers 1-5 pass through


def _v(x) -> str:
    s = str(x if x is not None else "").strip()
    return s or TBD


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "decision"


# ───────────────────────── decisions ─────────────────────────

def weighted(decision: dict) -> list[dict]:
    """Options with their weighted score (sum of weight × score ÷ sum of weights, 1–5 scale), best first."""
    crit = decision.get("criteria") or []
    total = sum(float(c.get("weight") or 0) for c in crit)
    out = []
    for o in decision.get("options") or []:
        sc = o.get("scores") or {}
        missing = [c["name"] for c in crit if c["name"] not in sc]
        score = None if (missing or not total) else round(sum(float(c["weight"]) * float(sc[c["name"]]) for c in crit) / total, 2)
        out.append({"name": o["name"], "scores": sc, "score": score, "missing": missing})
    return sorted(out, key=lambda r: (r["score"] is None, -(r["score"] or 0)))


def decisions_with_ids(d: dict) -> list[dict]:
    out = []
    for k, dec in enumerate(d.get("decisions") or [], 1):
        dd = dict(dec)
        dd["id"] = dec.get("id") or f"ADR-{k:03d}"
        dd["ranked"] = weighted(dec)
        top = next((r for r in dd["ranked"] if r["score"] is not None), None)
        dd["top"] = top["name"] if top else None
        dd["off_top"] = bool(dec.get("chosen") and top and dec["chosen"] != top["name"])
        out.append(dd)
    return out


def options_section(decs: list[dict]) -> list[str]:
    if not decs:
        return []
    L = ["## Options and decisions", "",
         "Each option is scored 1 (poor) to 5 (strong) per criterion; the weighted score is Σ(weight × score) ÷ Σweights. "
         "Scores and weights are the workshop's, as recorded in the source."]
    for dec in decs:
        crit = dec.get("criteria") or []
        L += ["", f"### {dec['id']} — {dec['title']}", "", f"**Context.** {_v(dec.get('context'))}", ""]
        L += ["| Option | " + " | ".join(f"{c['name']} ({c['weight']})" for c in crit) + " | Weighted score |",
              "|---|" + "---|" * len(crit) + "---|"]
        for r in dec["ranked"]:
            mark = " **(chosen)**" if r["name"] == dec.get("chosen") else ""
            cells = [str(r["scores"].get(c["name"], TBD)) for c in crit]
            L.append(f"| {r['name']}{mark} | " + " | ".join(cells) + f" | {r['score'] if r['score'] is not None else TBD} |")
        L += ["", f"**Decision.** {_v(dec.get('chosen'))} — {_v(dec.get('rationale'))}"]
        if dec["off_top"]:
            L.append(f"**Note.** The chosen option is not the top weighted score ({dec['top']}); the rationale must carry that choice.")
        cons = dec.get("consequences") or []
        if cons:
            L += ["", "**Consequences.**"] + [f"- {c}" for c in cons]
        L += ["", f"Owner: {_v(dec.get('owner'))} · Status: {dec.get('status') or 'proposed'} · Source: {_v(dec.get('source'))}"]
    return L


def adr_log(decs: list[dict]) -> list[str]:
    L = ["| ADR | Decision | Chosen | Status | Owner |", "|---|---|---|---|---|"]
    L += [f"| {d['id']} | {d['title']} | {_v(d.get('chosen'))} | {d.get('status') or 'proposed'} | {_v(d.get('owner'))} |" for d in decs]
    return L


def adr_files(decs: list[dict], system: str) -> dict[str, str]:
    files = {}
    for d in decs:
        crit = d.get("criteria") or []
        body = [f"# {d['id']}: {d['title']}", "", f"- **System:** {system}", f"- **Status:** {d.get('status') or 'proposed'}",
                f"- **Owner:** {_v(d.get('owner'))}", f"- **Source:** {_v(d.get('source'))}", "",
                "## Context", _v(d.get("context")), "", "## Options considered",
                "| Option | " + " | ".join(f"{c['name']} ({c['weight']})" for c in crit) + " | Weighted |", "|---|" + "---|" * len(crit) + "---|"]
        for r in d["ranked"]:
            body.append(f"| {r['name']} | " + " | ".join(str(r["scores"].get(c["name"], TBD)) for c in crit) + f" | {r['score'] if r['score'] is not None else TBD} |")
        body += ["", "## Decision", f"{_v(d.get('chosen'))}. {_v(d.get('rationale'))}"]
        if d["off_top"]:
            body.append(f"\nThe chosen option is not the top weighted score ({d['top']}).")
        body += ["", "## Consequences"] + ([f"- {c}" for c in d.get("consequences") or []] or [f"- {TBD}"])
        files[f"{d['id']}-{slug(d['title'])}.md"] = "\n".join(body) + "\n"
    return files


# ───────────────────────── context sections ─────────────────────────

def drivers_section(d: dict) -> list[str]:
    drv = d.get("drivers") or []
    if not drv:
        return []
    L = ["## Drivers and constraints", "", "| Type | Statement | Source |", "|---|---|---|"]
    L += [f"| {x.get('type', 'goal')} | {_v(x.get('statement'))} | {_v(x.get('source'))} |" for x in drv]
    return L


def _level(x) -> int | None:
    if isinstance(x, (int, float)) and 1 <= x <= 5:
        return int(x)
    return LEVEL.get(str(x or "").strip().lower())


def rated_risks(d: dict) -> list[dict]:
    out = []
    for r in d.get("risks") or []:
        l, i = _level(r.get("likelihood")), _level(r.get("impact"))
        score = l * i if l and i else None
        band = None if score is None else ("high" if score >= 15 else "medium" if score >= 8 else "low")
        out.append({**r, "l": l, "i": i, "score": score, "band": band})
    return sorted(out, key=lambda r: -(r["score"] or 0))


def risks_section(d: dict) -> list[str]:
    rs = rated_risks(d)
    if not rs:
        return []
    L = ["## Risks", "", "Rating = likelihood × impact (each 1–5; low/medium/high read as 1/3/5): 15 and above high, 8–14 medium, below 8 low.", "",
         "| Risk | Likelihood | Impact | Rating | Mitigation | Owner |", "|---|---|---|---|---|---|"]
    for r in rs:
        rating = f"{r['score']} ({r['band']})" if r["score"] is not None else TBD
        L.append(f"| {_v(r.get('risk'))} | {r['l'] or TBD} | {r['i'] or TBD} | {rating} | {_v(r.get('mitigation'))} | {_v(r.get('owner'))} |")
    return L


def waves_section(d: dict) -> list[str]:
    """One table: each wave's goal, the integrations it delivers, and how it starts, ends and rolls back.
    Integrations with no wave are listed in a last row so they cannot be missed."""
    ws = d.get("waves") or []
    if not ws:
        return []
    ints = d.get("integrations") or []
    by = lambda w: ", ".join(it["id"] for it in ints if str(it.get("wave")) == str(w)) or "—"
    L = ["## Migration waves", "", "| Wave | Goal | Integrations | Entry criteria | Exit criteria | Rollback |", "|---|---|---|---|---|---|"]
    L += [f"| {w.get('wave', TBD)} | {_v(w.get('goal'))} | {by(w.get('wave'))} | {_v(w.get('entry'))} | {_v(w.get('exit'))} | {_v(w.get('rollback'))} |" for w in ws]
    known = {str(w.get("wave")) for w in ws}
    loose = [it["id"] for it in ints if str(it.get("wave")) not in known]
    if loose:
        L.append(f"| {TBD} | {TBD} | {', '.join(loose)} | | | |")
    return L


def security_section(d: dict) -> list[str]:
    sec = d.get("security") or []
    if not sec:
        return []
    L = ["## Security and data", "", "| Area | Control | Source |", "|---|---|---|"]
    L += [f"| {_v(s.get('area'))} | {_v(s.get('control'))} | {_v(s.get('source'))} |" for s in sec]
    return L


def _lc_first(s: str) -> str:
    """"Event backbone" -> "event backbone"; "API entry point" stays (an acronym keeps its capitals)."""
    return s if len(s) > 1 and s[1].isupper() else s[:1].lower() + s[1:]


def bottom_line(d: dict, decs: list[dict], n_open: int) -> str:
    if not d.get("description") and not decs:
        return f"{TBD} — target state in one sentence and the decision asked."
    parts = [f"**{d['system']}** — {d.get('description') or TBD}."]
    if decs:
        parts.append("Recommended: " + "; ".join(f"{_lc_first(x['title'])} on **{_v(x.get('chosen'))}** ({x['id']})" for x in decs[:3]) + ".")
    ws = d.get("waves") or []
    if ws:
        parts.append(f"Delivered in {len(ws)} wave{'s' if len(ws) != 1 else ''}: " + "; ".join(f"wave {w.get('wave')} — {_v(w.get('goal')).rstrip('.')}" for w in ws) + ".")
    hi = [r for r in rated_risks(d) if r["band"] == "high"]
    if hi:
        parts.append(f"{len(hi)} high-rated risk{'s' if len(hi) != 1 else ''}, led by: {hi[0]['risk'].rstrip('.')}.")
    parts.append(f"{n_open} item{'s' if n_open != 1 else ''} still need a baseline or an owner (see Open items)." if n_open else "No open items.")
    return " ".join(parts)


def open_items(d: dict, nfrs: list[dict], decs: list[dict]) -> list[tuple[str, str]]:
    items = [(f"NFR target: {n['category']} — {n['requirement']}", "Non-functional requirements") for n in nfrs if n["target"] == TBD]
    items += [(f"Wave for {it['id']}", "Integration map") for it in d.get("integrations", []) if it.get("wave") == TBD]
    items += [(f"Owner for risk: {r['risk']}", "Risks") for r in rated_risks(d) if not str(r.get("owner") or "").strip()]
    items += [(f"Mitigation for risk: {r['risk']}", "Risks") for r in rated_risks(d) if not str(r.get("mitigation") or "").strip()]
    items += [(f"Control for: {s.get('area')}", "Security and data") for s in d.get("security") or [] if not str(s.get("control") or "").strip()]
    items += [(f"Owner for {x['id']}", "Options and decisions") for x in decs if not str(x.get("owner") or "").strip()]
    return items


def sources(d: dict, nfrs: list[dict], decs: list[dict]) -> list[str]:
    found = [x.get("source") for x in d.get("drivers") or []] + [n["source"] for n in nfrs] + [x.get("source") for x in decs] + \
            [s.get("source") for s in d.get("security") or []]
    seen, out = set(), []
    for s in found:
        s = str(s or "").strip()
        if s and s != TBD and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ───────────────────────── HTML ─────────────────────────

CSS = """
:root{--ink:#0f1a21;--ink2:#4c5c68;--rule:#d9e0e5;--wash:#f4f6f8;--accent:#1168bd;--tbb:#9a5b00}
*{box-sizing:border-box}body{margin:0;font:15px/1.6 Helvetica,Arial,sans-serif;color:var(--ink);background:#fff}
main{max-width:1040px;margin:0 auto;padding:48px 40px 80px}
header.cover{border-bottom:3px solid var(--accent);padding-bottom:20px;margin-bottom:28px}
header.cover .eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:var(--ink2)}
h1{font-size:32px;line-height:1.2;margin:6px 0 8px}h2{font-size:22px;margin:40px 0 10px;padding-top:8px;border-top:1px solid var(--rule)}
h3{font-size:17px;margin:26px 0 8px}p{margin:8px 0}
.sample{background:#fff7e6;border:1px solid #f0d9a8;padding:10px 14px;border-radius:6px;font-size:13px}
.bottom{background:var(--wash);border-left:4px solid var(--accent);padding:14px 18px;border-radius:4px}
table{border-collapse:collapse;width:100%;margin:10px 0 14px;font-size:13.5px}th,td{border:1px solid var(--rule);padding:7px 9px;text-align:left;vertical-align:top}
th{background:var(--wash);font-weight:700}tr:nth-child(even) td{background:#fbfcfd}
figure{margin:16px 0 22px;border:1px solid var(--rule);border-radius:8px;padding:12px;background:#fff}figure svg{width:100%;height:auto;display:block}
figcaption{font-size:12.5px;color:var(--ink2);margin-top:6px}
.tbb{color:var(--tbb);font-weight:600}code{background:var(--wash);padding:1px 4px;border-radius:3px;font-size:12.5px}
nav.toc{columns:2;font-size:13.5px;background:var(--wash);padding:12px 18px;border-radius:6px}nav.toc a{color:var(--accent);text-decoration:none}
footer{margin-top:48px;font-size:12px;color:var(--ink2);border-top:1px solid var(--rule);padding-top:12px}
@media print{main{padding:0}h2{break-before:page}figure,table{break-inside:avoid}nav.toc{display:none}@page{margin:18mm}}
"""


def _inline(s: str) -> str:
    s = escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = s.replace(escape(TBD), f'<span class="tbb">{escape(TBD)}</span>')
    return s


def to_html(md: str, svgs: list[str], title: str, sample: str | None) -> str:
    """Our own markdown (headings, tables, lists, paragraphs, mermaid blocks) as HTML; the k-th mermaid block becomes
    the k-th rendered diagram, so the page shows the same pictures as the SVG and draw.io files."""
    out, lines, i, fig, toc = [], md.splitlines(), 0, 0, []
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```mermaid"):
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                i += 1
            svg = svgs[fig] if fig < len(svgs) else ""
            svg = re.sub(r"^<\?xml[^>]*>\s*", "", svg)
            out.append(f"<figure>{svg}")
            fig += 1
            i += 1
            if i < len(lines) and lines[i].startswith("*Figure"):
                out.append(f"<figcaption>{_inline(lines[i].strip('*'))}</figcaption>")
                i += 1
            out.append("</figure>")
            continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not all(set(c) <= set("-: ") for c in r)]
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>" +
                       "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")
            continue
        if ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{_inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        m = re.match(r"(#{1,3}) (.*)", ln)
        if m:
            lvl, text = len(m.group(1)), m.group(2)
            if lvl == 1:
                i += 1
                continue                                  # the cover carries the title
            hid = slug(text)
            if lvl == 2:
                toc.append((hid, text))
            out.append(f'<h{lvl} id="{hid}">{_inline(text)}</h{lvl}>')
        elif ln.startswith("*Sample:"):
            pass                                          # shown on the cover
        elif ln.strip():
            cls = ' class="bottom"' if out and out[-1].startswith('<h2 id="bottom-line"') else ""
            out.append(f"<p{cls}>{_inline(ln)}</p>")
        i += 1
    cover = (f'<header class="cover"><div class="eyebrow">Solution architecture</div><h1>{escape(title)}</h1></header>'
             + (f'<p class="sample">{escape(sample)}</p>' if sample else "")
             + '<nav class="toc">' + "".join(f'<div><a href="#{h}">{escape(t)}</a></div>' for h, t in toc) + "</nav>")
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{escape(title)}</title><style>{CSS}</style></head><body><main>{cover}{''.join(out)}"
            "<footer>Generated by the solution-architecture-doc skill from the stated inputs only. Every value is sourced or marked "
            f"{escape(TBD)}. Diagrams are also delivered as SVG and as an editable draw.io file.</footer></main></body></html>\n")
