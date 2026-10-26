#!/usr/bin/env python3
"""C4 diagrams as files people can use: SVG (crisp, embeddable) and draw.io (editable in diagrams.net / Confluence).

Pure standard library, deterministic (same model -> byte-identical files), so it runs in the browser runtime too.
One layout feeds both formats, so the picture and the editable file always match.

Views:
  context(model)     the system as one box, its people above, the external systems below
  container(model)   the system boundary with its containers in dependency layers; people above, externals below
  deployment(model)  hosting zones with the nodes in each and the containers each node runs

Model (the solution-architecture-doc components.json): system, actors, containers[{id,name,tech,responsibility}],
external_systems[{id,name}], integrations[{from,to,pattern,protocol,data}], deployment{zones[{id,name,nodes[{id,name,tech,runs[]}]}]}.
"""
from __future__ import annotations

import math
from html import escape
from xml.sax.saxutils import quoteattr

# C4 palette (Simon Brown's conventions), tuned for print and screen
PERSON = {"fill": "#08427B", "stroke": "#073B6F", "text": "#FFFFFF"}
SYSTEM = {"fill": "#1168BD", "stroke": "#0E5AA7", "text": "#FFFFFF"}
CONTAINER = {"fill": "#438DD5", "stroke": "#3C7FC0", "text": "#FFFFFF"}
EXTERNAL = {"fill": "#8C8C8C", "stroke": "#7A7A7A", "text": "#FFFFFF"}
NODE = {"fill": "#FFFFFF", "stroke": "#5B6B78", "text": "#0F1A21"}
EDGE = "#5B6B78"
FONT = "Helvetica, Arial, sans-serif"

BOX_W, BOX_H, PERSON_H = 210, 96, 112
GAP_X, GAP_Y, MARGIN, TITLE_H = 56, 84, 40, 54


def _name(x) -> str:
    return x if isinstance(x, str) else x.get("name", "")


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_") or "x"


def _wrap(text: str, width_chars: int, max_lines: int = 3) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) > width_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(0, width_chars - 1)].rstrip() + "…"
    return lines


class Box:
    def __init__(self, bid: str, title: str, kind: str, sub: str = "", desc: str = ""):
        self.id, self.title, self.kind, self.sub, self.desc = bid, title, kind, sub, desc
        self.x = self.y = 0.0
        self.w, self.h = BOX_W, (PERSON_H if kind == "person" else BOX_H)

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


class Layout:
    def __init__(self, title: str, caption: str):
        self.title, self.caption = title, caption
        self.boxes: list[Box] = []
        self.edges: list[tuple[str, str, str]] = []          # (from, to, label)
        self.frames: list[tuple[str, float, float, float, float]] = []   # (label, x, y, w, h) dashed boundaries
        self.width = self.height = 0.0

    def box(self, bid: str) -> Box | None:
        return next((b for b in self.boxes if b.id == bid), None)


def _row(boxes: list[Box], y: float, width: float) -> None:
    total = len(boxes) * BOX_W + max(0, len(boxes) - 1) * GAP_X
    x = (width - total) / 2
    for b in boxes:
        b.x, b.y = x, y
        x += BOX_W + GAP_X


def _layers(ids: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Longest-path layering of a (possibly cyclic) graph; ties keep the input order."""
    inside = set(ids)
    succ = {i: [t for f, t in edges if f == i and t in inside and t != i] for i in ids}
    depth: dict[str, int] = {}

    def visit(n: str, stack: set[str]) -> int:
        if n in depth:
            return depth[n]
        stack.add(n)
        preds = [f for f, t in edges if t == n and f in inside and f != n and f not in stack]
        depth[n] = 0 if not preds else 1 + max(visit(p, stack) for p in preds)
        stack.discard(n)
        return depth[n]

    for i in ids:
        visit(i, set())
    del succ
    rows: dict[int, list[str]] = {}
    for i in ids:
        rows.setdefault(depth[i], []).append(i)
    return [rows[k] for k in sorted(rows)]


def _people(model: dict) -> list[Box]:
    out = []
    for a in model.get("actors", []):
        n = _name(a)
        ext = isinstance(a, dict) and a.get("external")
        out.append(Box(f"actor_{_slug(n)}", n, "person", "[Person, external]" if ext else "[Person]", a.get("description", "") if isinstance(a, dict) else ""))
    return out


def _externals(model: dict) -> list[Box]:
    return [Box(e["id"], e["name"], "external", "[Software System, external]", e.get("description", "")) for e in model.get("external_systems", [])]


def context(model: dict) -> Layout:
    sysname = model.get("system", "System")
    lay = Layout(f"System context — {sysname}", "C4 level 1: who uses the system and what it exchanges data with.")
    people, ext = _people(model), _externals(model)
    sysbox = Box("SYS", sysname, "system", "[Software System]", model.get("description", ""))
    lay.width = max(len(people), len(ext), 1) * (BOX_W + GAP_X) - GAP_X + 2 * MARGIN
    lay.width = max(lay.width, BOX_W + 2 * MARGIN + 260)
    y = MARGIN + TITLE_H
    _row(people, y, lay.width)
    y += (PERSON_H + GAP_Y) if people else 0
    _row([sysbox], y, lay.width)
    y += BOX_H + GAP_Y * 1.5
    _row(ext, y, lay.width)
    lay.height = y + (BOX_H if ext else 0) + MARGIN + 30
    lay.boxes = people + [sysbox] + ext
    cids = {c["id"] for c in model.get("containers", [])}
    for p in people:
        lay.edges.append((p.id, "SYS", "uses"))
    seen = set()
    for i in model.get("integrations", []):
        f = "SYS" if i["from"] in cids else i["from"]
        t = "SYS" if i["to"] in cids else i["to"]
        if f == t or not lay.box(f) or not lay.box(t):
            continue
        key = (f, t)
        if key in seen:
            continue
        seen.add(key)
        lay.edges.append((f, t, f"{i.get('pattern', '')}: {i.get('data', '')}".strip(": ")))
    return lay


def container(model: dict) -> Layout:
    sysname = model.get("system", "System")
    lay = Layout(f"Containers — {sysname}", "C4 level 2: the deployable parts of the system and how they integrate.")
    people, ext = _people(model), _externals(model)
    cs = model.get("containers", [])
    conts = {c["id"]: Box(c["id"], c["name"], "container", f"[Container: {c.get('tech', '')}]" if c.get("tech") else "[Container]", c.get("responsibility", "")) for c in cs}
    ints = [(i["from"], i["to"]) for i in model.get("integrations", [])]
    layers = _layers([c["id"] for c in cs], ints)
    where = {cid: (li, ci, len(layer)) for li, layer in enumerate(layers) for ci, cid in enumerate(layer)}
    # an external system sits beside the container it talks to (left or right column, at that row) unless that container
    # is on the bottom row, where it sits underneath: lines stay short and never cross the boundary's other boxes
    side: dict[str, tuple[str, str]] = {}
    for e in ext:
        peers = [t if f == e.id else f for f, t in ints if e.id in (f, t) and (t if f == e.id else f) in where]
        if not peers:
            side[e.id] = ("bottom", "")
            continue
        li, ci, n = min(where[p] for p in peers)
        side[e.id] = ("bottom", peers[0]) if li == len(layers) - 1 else ("left" if ci < n / 2 or (n == 1 and sum(1 for v in side.values() if v[0] == "left") <= sum(1 for v in side.values() if v[0] == "right")) else "right", peers[0])
    left = [e for e in ext if side[e.id][0] == "left"]
    right = [e for e in ext if side[e.id][0] == "right"]
    bottom = [e for e in ext if side[e.id][0] == "bottom"]
    widest = max([len(l) for l in layers] + [1])
    inner = widest * (BOX_W + GAP_X) - GAP_X + 2 * 28
    colw = BOX_W + GAP_X
    ox = MARGIN + (colw if left else 0)
    lay.width = ox + inner + (colw if right else 0) + MARGIN
    lay.width = max(lay.width, len(people) * (BOX_W + GAP_X) - GAP_X + 2 * MARGIN, len(bottom) * (BOX_W + GAP_X) - GAP_X + 2 * MARGIN)
    y = MARGIN + TITLE_H
    _row(people, y, inner)                      # people centred over the system boundary
    for p in people:
        p.x += ox
    y += (PERSON_H + GAP_Y) if people else 0
    top = y
    y += 40
    for layer in layers:
        row = [conts[i] for i in layer]
        _row(row, y, inner)
        for b_ in row:
            b_.x += ox
        y += BOX_H + GAP_Y * 0.8
    y -= GAP_Y * 0.8
    lay.frames.append((f"{sysname} [Software System]", ox, top, inner, y - top + 28))
    for col, x0 in ((left, MARGIN), (right, ox + inner + GAP_X)):
        taken: list[float] = []
        for e in col:
            peer = conts.get(side[e.id][1])
            ey = peer.y if peer else top
            while any(abs(ey - t) < BOX_H + 16 for t in taken):
                ey += BOX_H + 16
            taken.append(ey)
            e.x, e.y = x0, ey
    y += 28 + GAP_Y
    _row(bottom, y, inner)
    for e in bottom:
        e.x += ox
    lay.height = max(y + (BOX_H if bottom else 0), max([e.y + BOX_H for e in left + right] + [0])) + MARGIN + 30
    lay.boxes = people + list(conts.values()) + ext
    # people reach the system through the container the model names as their entry point (actor "uses"), else the
    # first container whose name says it faces users (gateway, portal, UI), else the first container
    facing = next((c["id"] for c in cs if any(k in f" {c.get('name', '')} ".lower() for k in ("gateway", "portal", " ui", "front", "web app", "app "))), cs[0]["id"] if cs else None)
    for p, a in zip(people, model.get("actors", [])):
        target = a.get("uses") if isinstance(a, dict) and a.get("uses") in conts else facing
        if target:
            lay.edges.append((p.id, target, "uses"))
    for i in model.get("integrations", []):
        if lay.box(i["from"]) and lay.box(i["to"]):
            label = " ".join(x for x in (i.get("id", ""), i.get("pattern", ""), f"({i['protocol']})" if i.get("protocol") else "") if x)
            lay.edges.append((i["from"], i["to"], label))
    return lay


def deployment(model: dict) -> Layout | None:
    dep = model.get("deployment") or {}
    zones = dep.get("zones") or []
    if not zones:
        return None
    sysname = model.get("system", "System")
    lay = Layout(f"Deployment — {sysname}", dep.get("caption") or "Where each container runs, by hosting zone.")
    names = {c["id"]: c["name"] for c in model.get("containers", [])}
    links = [(e["from"], e["to"]) for e in dep.get("links", [])]
    zone_of = {n["id"]: zi for zi, z in enumerate(zones) for n in z.get("nodes", [])}
    # each zone is a grid of up to two columns; a node linked to another zone sits in the column facing it, and its
    # row follows its partner's, so cross-zone lines run straight across instead of through other nodes
    pos: dict[str, tuple[int, int]] = {}                 # node id -> (column, row) inside its zone
    for zi, z in enumerate(zones):
        nodes = z.get("nodes", [])
        if len(nodes) <= 2:
            for r, n in enumerate(nodes):
                pos[n["id"]] = (0, r)
            continue
        facing: dict[str, int] = {}
        for n in nodes:
            others = [zone_of[t if f == n["id"] else f] for f, t in links if n["id"] in (f, t) and zone_of.get(t if f == n["id"] else f, zi) != zi]
            if others:
                facing[n["id"]] = 1 if sum(1 if o > zi else -1 for o in others) >= 0 else 0
        cols: list[list[dict]] = [[], []]
        for n in nodes:
            cols[facing.get(n["id"], 1 - (1 if any(v == 1 for v in facing.values()) else 0))].append(n)
        while len(cols[0]) - len(cols[1]) > 1:
            cols[1].append(cols[0].pop())
        while len(cols[1]) - len(cols[0]) > 1:
            cols[0].append(cols[1].pop())
        for c, col in enumerate(cols):
            for r, n in enumerate(col):
                pos[n["id"]] = (c, r)
    for zi, z in enumerate(zones):                       # rows follow cross-zone partners already placed
        nodes = z.get("nodes", [])
        if zi == 0 or len(nodes) > 2:
            continue
        partner_row = lambda n: min([pos[t if f == n["id"] else f][1] for f, t in links if n["id"] in (f, t) and (t if f == n["id"] else f) in pos and zone_of.get(t if f == n["id"] else f) != zi] or [99])
        for r, n in enumerate(sorted(nodes, key=partner_row)):
            pos[n["id"]] = (0, r)
    x = MARGIN
    zone_h = 0.0
    for z in zones:
        nodes = z.get("nodes", [])
        ncols = 1 if len(nodes) <= 2 else 2
        zw = ncols * (BOX_W + GAP_X) - GAP_X + 2 * 28
        heights = {}
        for n in nodes:
            runs = [names.get(r, r) for r in n.get("runs", [])]
            b = Box(n["id"], n["name"], "node", f"[Node: {n.get('tech', '')}]" if n.get("tech") else "[Node]", " · ".join(runs))
            b.h = BOX_H + 14 * max(0, len(_wrap(b.desc, 32, 4)) - 2)
            c, r = pos[n["id"]]
            b.x = x + 28 + c * (BOX_W + GAP_X)
            b.y = MARGIN + TITLE_H + 44 + r * (BOX_H + GAP_Y * 0.7)
            heights[n["id"]] = b.y + b.h
            lay.boxes.append(b)
        zh = (max(heights.values()) if heights else MARGIN + TITLE_H + 44 + BOX_H) - (MARGIN + TITLE_H) + 44
        zone_h = max(zone_h, zh)
        lay.frames.append((f"{z['name']} [Deployment zone]", x, MARGIN + TITLE_H, zw, zh))
        x += zw + GAP_X * 1.6
    lay.frames = [(l, fx, fy, fw, zone_h) for l, fx, fy, fw, _ in lay.frames]
    lay.width = x - GAP_X * 1.6 + MARGIN
    lay.height = MARGIN + TITLE_H + zone_h + MARGIN + 30
    for e in dep.get("links", []):
        if lay.box(e["from"]) and lay.box(e["to"]):
            lay.edges.append((e["from"], e["to"], e.get("label", "")))
    return lay


# ───────────────────────── geometry ─────────────────────────

def _anchor(b: Box, tx: float, ty: float) -> tuple[float, float]:
    """Where the line from the box centre towards (tx, ty) leaves the box border."""
    dx, dy = tx - b.cx, ty - b.cy
    if dx == 0 and dy == 0:
        return b.cx, b.cy
    sx = (b.w / 2) / abs(dx) if dx else math.inf
    sy = (b.h / 2) / abs(dy) if dy else math.inf
    s = min(sx, sy)
    return b.cx + dx * s, b.cy + dy * s


def _text_w(s: str, size: float) -> float:
    return len(s) * size * 0.56


# ───────────────────────── SVG ─────────────────────────

def to_svg(lay: Layout) -> str:
    W, H = round(lay.width), round(lay.height)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" role="img" aria-label={quoteattr(lay.title)}>',
         f"<title>{escape(lay.title)}</title>",
         '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
         f'<path d="M0,0 L10,5 L0,10 z" fill="{EDGE}"/></marker></defs>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="#FFFFFF"/>',
         f'<text x="{MARGIN}" y="{MARGIN + 18}" font-size="20" font-weight="700" fill="#0F1A21">{escape(lay.title)}</text>',
         f'<text x="{MARGIN}" y="{MARGIN + 38}" font-size="12" fill="#4C5C68">{escape(lay.caption)}</text>']
    for label, x, y, w, h in lay.frames:
        o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" fill="none" stroke="#7C8A96" stroke-width="1.4" stroke-dasharray="8 5"/>')
        o.append(f'<text x="{x + 14:.1f}" y="{y + h - 12:.1f}" font-size="12" font-weight="700" fill="#4C5C68">{escape(label)}</text>')
    placed: list[tuple[float, float, float, float]] = []      # label rectangles already drawn, to keep labels apart
    lines, labels = [], []
    for f, t, label in lay.edges:
        a, b = lay.box(f), lay.box(t)
        if not a or not b:
            continue
        x1, y1 = _anchor(a, b.cx, b.cy)
        x2, y2 = _anchor(b, a.cx, a.cy)
        lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{EDGE}" stroke-width="1.4" stroke-dasharray="5 3" marker-end="url(#arrow)"/>')
        if not label:
            continue
        rows = _wrap(label, 26, 2)
        lw = max(_text_w(r, 10.5) for r in rows) + 10
        lh = 14 * len(rows) + 4
        best = None
        for t in (0.5, 0.62, 0.38, 0.72, 0.28, 0.8, 0.2):
            mx, my = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            r = (mx - lw / 2, my - lh / 2, lw, lh)
            hit = any(not (r[0] + r[2] < q[0] or q[0] + q[2] < r[0] or r[1] + r[3] < q[1] or q[1] + q[3] < r[1]) for q in placed)
            if not hit:
                best = r
                break
            best = best or r
        placed.append(best)
        rx, ry, _, _ = best
        labels.append(f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{lw:.1f}" height="{lh:.1f}" rx="3" fill="#FFFFFF" fill-opacity="0.94"/>')
        for k, row in enumerate(rows):
            labels.append(f'<text x="{rx + lw / 2:.1f}" y="{ry + 13 + 14 * k:.1f}" font-size="10.5" fill="#33414C" text-anchor="middle">{escape(row)}</text>')
    o += lines + labels
    for b in lay.boxes:
        pal = {"person": PERSON, "system": SYSTEM, "container": CONTAINER, "external": EXTERNAL, "node": NODE}[b.kind]
        top = b.y
        if b.kind == "person":
            o.append(f'<circle cx="{b.cx:.1f}" cy="{b.y + 16:.1f}" r="16" fill="{pal["fill"]}" stroke="{pal["stroke"]}"/>')
            top = b.y + 26
        h = b.h - (top - b.y)
        o.append(f'<rect x="{b.x:.1f}" y="{top:.1f}" width="{b.w:.1f}" height="{h:.1f}" rx="{18 if b.kind == "person" else 8}" fill="{pal["fill"]}" stroke="{pal["stroke"]}" stroke-width="1.2"/>')
        ty = top + 24
        for line in _wrap(b.title, 24, 2):
            o.append(f'<text x="{b.cx:.1f}" y="{ty:.1f}" font-size="14" font-weight="700" fill="{pal["text"]}" text-anchor="middle">{escape(line)}</text>')
            ty += 17
        if b.sub:
            o.append(f'<text x="{b.cx:.1f}" y="{ty:.1f}" font-size="10.5" fill="{pal["text"]}" fill-opacity="0.85" text-anchor="middle">{escape(b.sub)}</text>')
            ty += 16
        for line in _wrap(b.desc, 32, 3 if b.kind != "node" else 4):
            o.append(f'<text x="{b.cx:.1f}" y="{ty:.1f}" font-size="10.5" fill="{pal["text"]}" text-anchor="middle">{escape(line)}</text>')
            ty += 14
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ───────────────────────── draw.io ─────────────────────────

_DRAWIO_STYLE = {
    "person": "rounded=1;arcSize=30;whiteSpace=wrap;html=1;fillColor=#08427B;strokeColor=#073B6F;fontColor=#FFFFFF;fontSize=12;",
    "system": "rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor=#1168BD;strokeColor=#0E5AA7;fontColor=#FFFFFF;fontSize=12;",
    "container": "rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor=#438DD5;strokeColor=#3C7FC0;fontColor=#FFFFFF;fontSize=12;",
    "external": "rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor=#8C8C8C;strokeColor=#7A7A7A;fontColor=#FFFFFF;fontSize=12;",
    "node": "rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#5B6B78;fontColor=#0F1A21;fontSize=12;",
}


def _drawio_page(lay: Layout, page_id: str) -> str:
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    cells.append(f'<mxCell id="{page_id}-title" value={quoteattr(f"<b>{escape(lay.title)}</b><br/><font style=\"font-size:11px\">{escape(lay.caption)}</font>")} '
                 f'style="text;html=1;align=left;verticalAlign=top;fontSize=16;" vertex="1" parent="1"><mxGeometry x="{MARGIN}" y="{MARGIN - 6}" width="{max(300, lay.width - 2 * MARGIN):.0f}" height="48" as="geometry"/></mxCell>')
    for n, (label, x, y, w, h) in enumerate(lay.frames):
        cells.append(f'<mxCell id="{page_id}-frame{n}" value={quoteattr(label)} style="rounded=1;arcSize=3;dashed=1;dashPattern=8 5;fillColor=none;strokeColor=#7C8A96;'
                     f'verticalAlign=bottom;align=left;spacingLeft=10;spacingBottom=6;fontStyle=1;fontColor=#4C5C68;html=1;" vertex="1" parent="1">'
                     f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" as="geometry"/></mxCell>')
    for b in lay.boxes:
        value = f"<b>{escape(b.title)}</b><br/><font style=\"font-size:10px\">{escape(b.sub)}</font>" + (f"<br/><font style=\"font-size:10px\">{escape(b.desc)}</font>" if b.desc else "")
        cells.append(f'<mxCell id="{page_id}-{escape(b.id)}" value={quoteattr(value)} style="{_DRAWIO_STYLE[b.kind]}" vertex="1" parent="1">'
                     f'<mxGeometry x="{b.x:.0f}" y="{b.y:.0f}" width="{b.w:.0f}" height="{b.h:.0f}" as="geometry"/></mxCell>')
    for n, (f, t, label) in enumerate(lay.edges):
        if not lay.box(f) or not lay.box(t):
            continue
        cells.append(f'<mxCell id="{page_id}-e{n}" value={quoteattr(label)} style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;dashed=1;strokeColor={EDGE};fontSize=10;fontColor=#33414C;labelBackgroundColor=#FFFFFF;endArrow=block;endFill=1;" '
                     f'edge="1" parent="1" source="{page_id}-{escape(f)}" target="{page_id}-{escape(t)}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    return (f'<diagram id="{page_id}" name={quoteattr(lay.title)}><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
            f'fold="1" page="1" pageScale="1" pageWidth="{max(1100, round(lay.width))}" pageHeight="{max(850, round(lay.height))}" math="0" shadow="0"><root>{"".join(cells)}</root></mxGraphModel></diagram>')


def to_drawio(layouts: list[Layout]) -> str:
    pages = "".join(_drawio_page(l, f"p{i + 1}") for i, l in enumerate(layouts))
    return f'<mxfile host="skills-factory" type="device" version="24.0.0">{pages}</mxfile>\n'


def views(model: dict) -> list[tuple[str, Layout]]:
    out = [("context", context(model)), ("container", container(model))]
    d = deployment(model)
    if d:
        out.append(("deployment", d))
    return out
