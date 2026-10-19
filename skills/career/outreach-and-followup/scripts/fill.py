#!/usr/bin/env python3
"""Fill a message skeleton from supplied facts and compute the follow-up cadence — no invented facts.

    python3 -I scripts/fill.py --type thank-you --context context.json \
        --templates assets/message-templates.md --cadence-ref references/cadence.md \
        --message message.md --cadence cadence.csv

context.json: {"recipient": "Dana Okafor", "company": "...", "role": "...", "last_touch_date": "YYYY-MM-DD",
               "specifics": ["slot: text", {"slot": "specific thing they said", "text": "..."}, "free fact"],
               optional: "sender", "channel", "req_id", "timeline_date", "relationship": "warm|cold"}

What it does, deterministically:
  * takes the variants of the message type from assets/message-templates.md (one `## N. Title` section
    per type, `**A — label**` + code block per variant);
  * fills `<placeholders>` only from context.json: recipient / company / role / dates / req id directly,
    anything else from `specifics` whose slot name matches the placeholder. Every other placeholder
    becomes `[TO BE BASELINED — owner: Sender]` and is listed, so nothing is silently made up;
  * cadence.csv — touch, date, channel, template, basis, stop_rule: the touches of the matching row of
    references/cadence.md, dated in business days from last_touch_date (or timeline_date where the row
    says so). A touch without a computable date is left for the user with its basis.
Existing thread (--thread thread.md: the conversation so far, one `## YYYY-MM-DD — sent …` or
`## YYYY-MM-DD — received …` heading per message): the touches you already sent are counted, the
cadence is anchored on your first sent message and only the touches still due are listed (or the
stop rule is reported when none remain), a reply from them is noted, and every fact already used in
the thread is marked so the next touch adds a new element instead of repeating it.
--draft-only --final message-final.md: no model step — writes the final message on
assets/message-final-template.md's sections (Message = variant A, Alternate variant = B, Facts used,
Cadence) from the filled skeleton, labelled as a draft; unfilled slots stay owned markers.
Exit 1 on a missing/invalid context, an unknown type, a template section without variants, or a
last_touch_date that is not YYYY-MM-DD. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Sender]"
TYPES = {
    "referral-ask": {"section": "1", "cadence": "Referral ask (warm contact)", "cold": "Referral ask (cold contact)"},
    "recruiter-reply": {"section": "2", "cadence": "Recruiter inbound"},
    "thank-you": {"section": "3", "cadence": "Post-interview thank-you"},
    "status-check": {"section": "4", "cadence": "Awaiting decision (no timeline)", "timeline": "Awaiting decision (timeline given)"},
    "decline": {"section": "5", "cadence": "After decline (yours or theirs)"},
    "negotiation-open": {"section": "6", "cadence": "Offer received, negotiating"},
}
SECTION_RE = re.compile(r"^## (\d+)\. (.+)$")
VARIANT_RE = re.compile(r"^\*\*([A-Z]) [—–-] (.+?)\*\*")
PLACEHOLDER_RE = re.compile(r"<([^<>\n`]{1,80})>")
ID_SLOT_RE = re.compile(r"\s*\[(?:SB-nn|MR-Lnn)\]")
ID_RE = re.compile(r"\[(?:SB-\d+|MR-L\d+)\]")
DIRECT = {  # placeholder (normalised) -> context key
    "first name": "recipient_first", "role title": "role", "company": "company", "name": "sender",
    "title line": "sender_title", "req id": "req_id", "date": "last_touch_date", "time zone": "time_zone",
    "window 1": "window_1", "window 2": "window_2", "window": "window_1", "range": "comp_range",
    "timeline": "timeline", "location/remote": "location", "x": "travel_max", "team": "team",
    "their team / with the company": "relationship_note", "level": "level", "scope": "scope",
    "period": "period", "market source": "market_source", "date − 2": "deadline_minus_2",
}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s/−-]", "", s.lower())).strip()


# ------------------------------------------------------------------ context

def load_context(path: str) -> dict:
    try:
        ctx = json.loads(read(path))
    except json.JSONDecodeError as e:
        die(f"context is not valid JSON: {e}")
    if not isinstance(ctx, dict):
        die("context.json must be an object")
    for key in ("recipient", "company", "role", "last_touch_date"):
        if not str(ctx.get(key, "")).strip():
            die(f"context.json needs '{key}' (recipient, company, role, last_touch_date are required)")
    try:
        ctx["_last"] = dt.date.fromisoformat(str(ctx["last_touch_date"]))
    except ValueError:
        die("last_touch_date must be YYYY-MM-DD")
    if ctx.get("timeline_date"):
        try:
            ctx["_timeline"] = dt.date.fromisoformat(str(ctx["timeline_date"]))
        except ValueError:
            die("timeline_date must be YYYY-MM-DD")
    ctx["recipient_first"] = str(ctx["recipient"]).split()[0]
    slots, facts = {}, []
    for item in ctx.get("specifics") or []:
        if isinstance(item, dict) and item.get("slot") and item.get("text"):
            slots[norm(str(item["slot"]))] = str(item["text"])
        elif isinstance(item, str) and ":" in item and len(item.split(":", 1)[0]) <= 60:
            slot, _, text = item.partition(":")
            slots[norm(slot)] = text.strip()
            facts.append(item.strip())
        elif isinstance(item, str) and item.strip():
            facts.append(item.strip())
    ctx["_slots"], ctx["_facts"] = slots, facts
    return ctx


# ------------------------------------------------------------------ templates

def load_variants(templates: str, section_no: str) -> tuple[str, list[dict]]:
    title, variants, cur, in_block = "", [], None, False
    active = False
    for ln in templates.splitlines():
        m = SECTION_RE.match(ln)
        if m:
            active = m.group(1) == section_no
            if active:
                title = m.group(2).strip()
            continue
        if not active:
            continue
        vm = VARIANT_RE.match(ln.strip())
        if vm:
            cur = {"key": vm.group(1), "label": vm.group(2).strip(), "body": []}
            variants.append(cur)
            continue
        if ln.strip().startswith("```"):
            in_block = not in_block
            continue
        if in_block and cur is not None:
            cur["body"].append(ln)
    if not variants:
        die(f"message-templates has no variants under section {section_no}")
    return title, variants


def fill(body: str, ctx: dict) -> tuple[str, list[str]]:
    unfilled = []

    def rep(m):
        raw = m.group(1)
        key = norm(raw)
        if key in ctx["_slots"]:
            return ctx["_slots"][key]
        for slot, text in ctx["_slots"].items():
            if slot and slot in key:
                return text
        ck = DIRECT.get(key)
        if ck and str(ctx.get(ck, "")).strip():
            return str(ctx[ck])
        if ck == "deadline_minus_2" and ctx.get("_timeline"):
            return business_days_from(ctx["_timeline"], -2).isoformat()
        unfilled.append(raw)
        return TBD
    out_lines = []
    for ln in PLACEHOLDER_RE.sub(rep, body).splitlines():
        if ID_SLOT_RE.search(ln):
            # a `[SB-nn]` / `[MR-Lnn]` note slot: drop it when the fact already carries its id, else flag it
            if ID_RE.search(ln):
                ln = ID_SLOT_RE.sub("", ln)
            else:
                ln = ID_SLOT_RE.sub(" " + TBD, ln)
                unfilled.append("source id (SB-nn / MR-Lnn) for the cited fact")
        out_lines.append(ln)
    return "\n".join(out_lines), unfilled


# ------------------------------------------------------------------ cadence

def business_days_from(start: dt.date, n: int) -> dt.date:
    d, step, left = start, (1 if n >= 0 else -1), abs(n)
    while left:
        d += dt.timedelta(days=step)
        if d.weekday() < 5:
            left -= 1
    return d


def cadence_row(ref: str, situation: str) -> tuple[list[str], list[str]]:
    header = []
    for ln in ref.splitlines():
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not header:
            header = cells
            continue
        if cells[0].lower() == situation.lower():
            return header, cells
    die(f"cadence.md has no row '{situation}'")
    return [], []


def touch_date(cell: str, prev: dt.date | None, ctx: dict) -> tuple[dt.date | None, str]:
    """-> (date or None, basis). Day N = N business days after the last touch; +N = after the previous touch."""
    c = cell.strip()
    last = ctx["_last"]
    if not c or c == "—":
        return None, ""
    if re.search(r"\bEvery\b", c):
        return None, c
    m = re.search(r"Timeline date \+ (\d+)", c)
    if m:
        if ctx.get("_timeline"):
            return business_days_from(ctx["_timeline"], int(m.group(1))), c
        return None, c + " (timeline_date not supplied)"
    m = re.search(r"Deadline − (\d+)", c)
    if m:
        if ctx.get("_timeline"):
            return business_days_from(ctx["_timeline"], -int(m.group(1))), c
        return None, c + " (timeline_date not supplied)"
    m = re.search(r"\bDay (\d+)", c)
    if m:
        return business_days_from(last, int(m.group(1))), c
    m = re.search(r"Within (\d+)\s*(h|hour|hours|business day|business days|day|days)", c)
    if m:
        n = 1 if m.group(2).startswith("h") else int(m.group(1))
        return business_days_from(last, n), c
    m = re.search(r"^\+\s*(\d+)", c)
    if m:
        return business_days_from(prev or last, int(m.group(1))), c
    if re.search(r"Immediately|Reply within 1", c):
        return last, c
    return None, c


def channel_of(cell: str, default: str) -> str:
    c = cell.lower()
    if "linkedin or email" in c:
        return default
    if "inmail" in c:
        return "LinkedIn InMail"
    if "linkedin" in c or "connection note" in c:
        return "LinkedIn"
    if "email" in c:
        return "email"
    if "different channel" in c:
        return "LinkedIn" if default.lower() == "email" else "email"
    if "call" in c:
        return "call"
    return default


def build_cadence(ref: str, msg_type: str, ctx: dict, template_label: str) -> list[dict]:
    spec = TYPES[msg_type]
    situation = spec["cadence"]
    if msg_type == "referral-ask" and str(ctx.get("relationship", "")).lower() == "cold":
        situation = spec["cold"]
    if msg_type == "status-check" and ctx.get("_timeline"):
        situation = spec["timeline"]
    header, cells = cadence_row(ref, situation)
    stop = cells[header.index("Stop rule")] if "Stop rule" in header else ""
    default_channel = str(ctx.get("channel") or "email")
    rows, prev = [], None
    for i, col in enumerate(header):
        if not col.lower().startswith("touch"):
            continue
        cell = cells[i] if i < len(cells) else ""
        if not cell.strip() or cell.strip() == "—":
            continue
        date, basis = touch_date(cell, prev, ctx)
        prev = date or prev
        rows.append({"touch": col, "date": date.isoformat() if date else "",
                     "channel": channel_of(cell, default_channel),
                     "template": template_label if col == "Touch 1" else "new element (see cadence.md timing rules)",
                     "basis": f"{situation}: {basis}" + ("" if date else " — date needs the user"),
                     "stop_rule": stop})
    return rows


# ------------------------------------------------------------------ existing thread

THREAD_HEAD_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*[—–-]\s*(sent|received)\b(.*)$", re.I)


def read_thread(text: str) -> dict:
    msgs, cur = [], None
    for ln in text.splitlines():
        m = THREAD_HEAD_RE.match(ln.strip())
        if m:
            try:
                d = dt.date.fromisoformat(m.group(1))
            except ValueError:
                die(f"thread heading has an invalid date: {ln.strip()}")
            cur = {"date": d, "dir": m.group(2).lower(), "note": m.group(3).strip(" ()—-"), "body": []}
            msgs.append(cur)
        elif cur is not None:
            cur["body"].append(ln)
    sent = [m_ for m_ in msgs if m_["dir"] == "sent"]
    if not sent:
        die("thread has no '## YYYY-MM-DD — sent' message")
    return {"messages": msgs, "sent": sent, "received": [m_ for m_ in msgs if m_["dir"] == "received"],
            "text": norm(" ".join(" ".join(m_["body"]) for m_ in msgs))}


def used_in_thread(fact: str, thread: dict) -> bool:
    words = [w for w in norm(fact.split(":", 1)[-1]).split() if len(w) > 3]
    if not words:
        return False
    hits = sum(1 for w in words if w in thread["text"].split())
    return hits / len(words) >= 0.6


# ------------------------------------------------------------------ output

def write_message(path: Path, msg_type: str, title: str, variants, ctx: dict, cadence: list[dict],
                  thread: dict | None = None, stop_note: str = "") -> list[dict]:
    L = [f"# {title} — {ctx['role']}, {ctx['company']}", "",
         f"Type: {msg_type} | Recipient: {ctx['recipient']} | Channel: {ctx.get('channel') or 'email'} | "
         f"Last touch: {ctx['last_touch_date']}", "",
         "Facts come only from context.json. Every unfilled slot is `[TO BE BASELINED — owner: Sender]` and listed "
         "below; the polish step fills a slot only when a listed fact supports it.", ""]
    if thread is not None:
        sent, recv = thread["sent"], thread["received"]
        L += ["## Thread so far", "",
              f"{len(sent)} message(s) sent (first {sent[0]['date']}, last {sent[-1]['date']}); "
              + (f"{len(recv)} reply(ies), last {recv[-1]['date']} — answer it before following up." if recv
                 else "no reply yet."), ""]
        if stop_note:
            L += [f"**{stop_note}**", ""]
    all_unfilled, filled = [], []
    for v in variants:
        text, unfilled = fill("\n".join(v["body"]), ctx)
        all_unfilled += [f"{v['key']}: {u}" for u in unfilled]
        filled.append({"key": v["key"], "label": v["label"], "text": text.strip()})
        L += [f"## Variant {v['key']} — {v['label']}", "", text.strip(), ""]
    L += ["## Facts to work in (from context.json)", ""]
    L += [f"- {f}" + (" — already used in the thread; add a new element instead" if thread and used_in_thread(f, thread) else "")
          for f in ctx["_facts"]] or ["(none supplied — nothing specific can be cited)"]
    L += ["", "## Unfilled placeholders", ""]
    L += [f"- {u}" for u in dict.fromkeys(all_unfilled)] or ["none"]
    L += ["", "## Cadence", "", "| Touch | Date | Channel | Basis |", "|---|---|---|---|"]
    L += [f"| {r['touch']} | {r['date'] or TBD} | {r['channel']} | {r['basis']} |" for r in cadence]
    L += [f"", f"Stop rule: {cadence[0]['stop_rule'] if cadence else '—'}",
          "Log: add a row to tracker.csv (stage, touch date, next action).", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")
    return filled


def write_final(path: Path, title: str, msg_type: str, ctx: dict, filled: list[dict], cadence: list[dict],
                thread: dict | None, stop_note: str) -> None:
    """message-final.md without a model step: the filled variants on the final template's sections."""
    L = [f"# {title} — {ctx['role']}, {ctx['company']}", "",
         "> Script draft — the model polish step was not run (draft only): the filled skeleton, facts from "
         "context.json only; unfilled slots stay owned markers.", ""]
    if stop_note:
        L += [f"**{stop_note}**", ""]
    a, b = filled[0], (filled[1] if len(filled) > 1 else None)
    L += ["## Message", f"Variant: {a['key']} — {a['label']}", "", a["text"], ""]
    if b:
        L += ["## Alternate variant", f"Variant: {b['key']} — {b['label']}", "", b["text"], ""]
    L += ["## Facts used", "| Fact | Source |", "|---|---|"]
    facts = [f for f in ctx["_facts"] if not (thread and used_in_thread(f, thread))]
    L += [f"| {f.replace('|', '/')} | context.json" + (f" / {', '.join(ID_RE.findall(f))}" if ID_RE.search(f) else "") + " |"
          for f in facts] or [f"| none supplied | {TBD} |"]
    L += ["", "## Cadence", "| Touch | Date | Channel | Basis |", "|---|---|---|---|"]
    L += [f"| {r['touch']} | {r['date'] or TBD} | {r['channel']} | {r['basis']} |" for r in cadence]
    L += ["", f"Stop rule: {cadence[0]['stop_rule'] if cadence else '—'}",
          "Log: add a row to tracker.csv (stage, touch date, next action).", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


def write_cadence(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["touch", "date", "channel", "template", "basis", "stop_rule"])
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill a job-search message skeleton from context.json and date the cadence")
    ap.add_argument("--type", required=True, choices=sorted(TYPES))
    ap.add_argument("--context", required=True, help="context.json")
    ap.add_argument("--templates", default="assets/message-templates.md")
    ap.add_argument("--cadence-ref", default="references/cadence.md")
    ap.add_argument("--message", required=True, help="output message.md")
    ap.add_argument("--cadence", required=True, help="output cadence.csv")
    ap.add_argument("--thread", default="", help="the conversation so far (## YYYY-MM-DD — sent|received headings)")
    ap.add_argument("--final", default="", help="final message path (written with --draft-only)")
    ap.add_argument("--draft-only", action="store_true", help="no model step: write --final from the filled skeleton")
    a = ap.parse_args()
    ctx = load_context(a.context)
    thread = read_thread(read(a.thread)) if a.thread else None
    if thread is not None:
        ctx["_last"] = thread["sent"][0]["date"]      # cadence days count from the first message sent
        ctx["last_touch_date"] = thread["messages"][-1]["date"].isoformat()
    title, variants = load_variants(read(a.templates), TYPES[a.type]["section"])
    rows = build_cadence(read(a.cadence_ref), a.type, ctx, f"{TYPES[a.type]['section']}{variants[0]['key']} {variants[0]['label']}")
    if not rows:
        die("no touches found for this message type in cadence.md")
    stop_note = ""
    if thread is not None:
        done = len(thread["sent"])
        remaining = rows[done:]
        if not remaining:
            stop_note = f"Cadence exhausted after {done} touch(es) — stop rule: {rows[0]['stop_rule']}. Do not send another."
            remaining = [{**rows[-1], "touch": "Stop", "date": "", "template": "none",
                          "basis": f"{done} touch(es) already sent — {rows[0]['stop_rule']}"}]
        rows = remaining
    filled = write_message(Path(a.message), a.type, title, variants, ctx, rows, thread, stop_note)
    write_cadence(Path(a.cadence), rows)
    if a.draft_only and a.final:
        write_final(Path(a.final), title, a.type, ctx, filled, rows, thread, stop_note)
    print(f"{a.type}: {len(variants)} variants, {len(rows)} cadence touches; wrote {a.message}, {a.cadence}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
