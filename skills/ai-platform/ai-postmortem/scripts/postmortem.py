#!/usr/bin/env python3
"""Blameless postmortem for an AI incident: measured timings, contributing factors, owned actions.

Usage:
    python3 -I postmortem.py --incident incident.csv --timeline timeline.csv
        [--factors factors.csv] [--actions actions.csv] [--strict] --out-dir OUT
    python3 -I postmortem.py --verify OUT/<postmortem.md|timings.json|actions.csv|eval-cases.csv>

Inputs (lines starting with '#' are comments):
  incident  key,value[,source,notes]. Required keys: id, title, started_at (ISO 8601 with timezone).
            Optional: severity (SEV1-SEV4), system, customer_impact, detection_source,
            went_well (';'-separated).
  timeline  timestamp,event,description,actor_role; event in detected|acknowledged|mitigated|
            resolved|note|change. Timestamps need a timezone.
  factors   factor,category,evidence; category = id or name in assets/factor-taxonomy.csv.
            Factors get ids F1..Fn in row order.
  actions   action,type,owner,due,factor[,status]; type prevent|detect|mitigate|process;
            factor = F-ids or factor text, ';'-separated.

Math (minutes, 1 decimal): time_to_detect = started_at -> first detected; time_to_acknowledge =
first detected -> first acknowledged; time_to_mitigate = started_at -> first mitigated;
time_to_resolve = started_at -> first resolved; impact_duration = started_at -> first mitigated
(or resolved when no mitigated event). A missing milestone is never invented: its timings are
null and flagged; no `resolved` event means the incident is reported as OPEN. A negative interval
is null and flagged as out of order.

Outputs: postmortem.md, timings.json, actions.csv, eval-cases.csv (llm-eval-harness golden-set
columns; inputs only from input:"..." markers in timeline/factor text).

Exit codes: 0 ok; 1 --strict and (a factor has no action, an action has no owner, or no factors
were supplied so coverage cannot be shown), or a --verify failure; 2 input error. Stdlib only; deterministic.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
TAXONOMY_CSV = SKILL_DIR / "assets" / "factor-taxonomy.csv"
BLAME_CSV = SKILL_DIR / "assets" / "blame-phrases.csv"

IC = "Incident commander"
EVAL_LEAD = "Eval lead"


def tbd(role: str = IC) -> str:
    return f"[TO BE BASELINED — owner: {role}]"


EVENTS = ("detected", "acknowledged", "mitigated", "resolved", "note", "change")
MILESTONES = ("detected", "acknowledged", "mitigated", "resolved")
ACTION_TYPES = ("prevent", "detect", "mitigate", "process")
ACTION_STATUS_IN = ("open", "in-progress", "done")
STATUS_NO_OWNER = "blocked: no owner"
STATUS_NO_DUE = "blocked: no due date"
SEV_RE = re.compile(r"^SEV[1-4]$")
INPUT_RE = re.compile(r'input:\s*["\u201c]([^"\u201d]+)["\u201d]', re.I)
OUTPUT_RE = re.compile(r'output:\s*["\u201c]([^"\u201d]+)["\u201d]', re.I)
GOLDEN_COLS = ["id", "category", "difficulty", "input", "expected", "must_contain", "must_not_contain",
               "expected_json_valid", "weight", "source", "notes"]
ACTION_COLS = ["action", "type", "owner", "due", "factor", "status"]
SECTIONS = ["Summary", "Impact", "Timeline", "Timings", "Contributing factors", "What went well",
            "Actions", "Lessons for the eval set", "Method"]
TIMING_DEFS = [  # key, label, from, to
    ("time_to_detect", "Time to detect", "started_at", "detected"),
    ("time_to_acknowledge", "Time to acknowledge", "detected", "acknowledged"),
    ("time_to_mitigate", "Time to mitigate", "started_at", "mitigated"),
    ("time_to_resolve", "Time to resolve", "started_at", "resolved"),
    ("impact_duration", "Impact duration", "started_at", "mitigated"),
]


class InputError(Exception):
    pass


# ------------------------------------------------------------------ reading

def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8-sig").splitlines() if not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items() if k is not None} for r in rows]


def need_cols(rows: list[dict], cols: tuple, name: str, path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    header = next((ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")), "")
    have = {c.strip().lower() for c in next(csv.reader([header]), [])}
    missing = [c for c in cols if c not in have]
    if missing:
        raise InputError(f"{name} CSV needs columns {','.join(cols)} (missing {','.join(missing)})")


def parse_ts(value: str, where: str) -> datetime:
    v = value.strip()
    if v.endswith(("Z", "z")):
        v = v[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(v)
    except ValueError:
        raise InputError(f"{where}: not an ISO 8601 timestamp: {value!r}")
    if ts.tzinfo is None:
        raise InputError(f"{where}: timestamp needs a timezone (e.g. Z or +05:30): {value!r}")
    return ts


def load_incident(path: Path) -> dict:
    rows = read_csv(path)
    need_cols(rows, ("key", "value"), "incident", path)
    facts, sources = {}, {}
    for r in rows:
        k = r.get("key", "").lower()
        if k and r.get("value", "") != "":
            facts[k] = r["value"]
            sources[k] = r.get("source", "")
    missing = [k for k in ("id", "title", "started_at") if k not in facts]
    if missing:
        raise InputError(f"incident missing required keys: {', '.join(missing)}")
    if "severity" in facts:
        facts["severity"] = facts["severity"].upper().replace(" ", "")
        if not SEV_RE.match(facts["severity"]):
            raise InputError(f"incident severity must be SEV1-SEV4, got {facts['severity']!r}")
    facts["_started"] = parse_ts(facts["started_at"], "incident started_at")
    facts["_sources"] = sources
    return facts


def load_timeline(path: Path) -> list[dict]:
    rows = read_csv(path)
    need_cols(rows, ("timestamp", "event", "description"), "timeline", path)
    if not rows:
        raise InputError("timeline CSV has no events")
    out = []
    for i, r in enumerate(rows, 1):
        ev = r.get("event", "").lower()
        if ev not in EVENTS:
            raise InputError(f"timeline row {i}: event must be one of {'|'.join(EVENTS)}, got {r.get('event')!r}")
        out.append({"row": i, "ts": parse_ts(r.get("timestamp", ""), f"timeline row {i}"),
                    "timestamp": r.get("timestamp", ""), "event": ev, "description": r.get("description", ""),
                    "actor_role": r.get("actor_role", "")})
    return out


def load_taxonomy() -> list[dict]:
    return read_csv(TAXONOMY_CSV)


def load_factors(path: Path | None, taxonomy: list[dict]) -> list[dict] | None:
    if path is None:
        return None
    rows = read_csv(path)
    need_cols(rows, ("factor", "category"), "factors", path)
    lookup = {}
    for t in taxonomy:
        lookup[t["id"].lower()] = t
        lookup[t["name"].lower()] = t
    out = []
    for i, r in enumerate([r for r in rows if r.get("factor")], 1):
        cat = lookup.get(r.get("category", "").lower())
        if cat is None:
            allowed = ", ".join(t["id"] for t in taxonomy)
            raise InputError(f"factor F{i}: category {r.get('category')!r} is not in the taxonomy ({allowed})")
        out.append({"id": f"F{i}", "factor": r["factor"], "category": cat["id"], "category_name": cat["name"],
                    "eval_relevant": cat["eval_relevant"] == "yes", "evidence": r.get("evidence", "")})
    return out


def load_actions(path: Path | None) -> list[dict] | None:
    if path is None:
        return None
    rows = read_csv(path)
    need_cols(rows, ("action", "type", "owner", "due", "factor"), "actions", path)
    out = []
    for i, r in enumerate([r for r in rows if r.get("action")], 1):
        typ = r.get("type", "").lower()
        if typ and typ not in ACTION_TYPES:
            raise InputError(f"action A{i}: type must be one of {'|'.join(ACTION_TYPES)}, got {r.get('type')!r}")
        st = r.get("status", "").lower()
        if st and st not in ACTION_STATUS_IN:
            raise InputError(f"action A{i}: status must be one of {'|'.join(ACTION_STATUS_IN)}, got {r.get('status')!r}")
        out.append({"id": f"A{i}", "action": r["action"], "type": typ, "owner": r.get("owner", ""),
                    "due": r.get("due", ""), "factor_ref": r.get("factor", ""), "status_in": st})
    return out


# ------------------------------------------------------------------ analysis

def minutes(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 60.0, 1)


def hmm(m: float) -> str:
    total = int(round(m))
    return f"{total // 60}h {total % 60:02d}m"


def analyse_timeline(inc: dict, tl: list[dict]) -> dict:
    started = inc["_started"]
    flags = []
    for prev, cur in zip(tl, tl[1:]):
        if cur["ts"] < prev["ts"]:
            flags.append(f"timeline row {cur['row']} ({cur['timestamp']}) is listed after a later event "
                         f"(row {prev['row']}, {prev['timestamp']}); shown in time order below")
    ordered = sorted(tl, key=lambda e: (e["ts"], e["row"]))
    first = {}
    for e in ordered:
        if e["event"] in MILESTONES:
            if e["event"] in first:
                flags.append(f"duplicate `{e['event']}` event at {e['timestamp']} (row {e['row']}); the first one is used")
            else:
                first[e["event"]] = e
        if e["event"] in MILESTONES and e["ts"] < started:
            flags.append(f"`{e['event']}` at {e['timestamp']} (row {e['row']}) is before started_at "
                         f"{inc['started_at']}")
    for m in MILESTONES:
        if m not in first:
            if m == "resolved":
                flags.append("missing milestone: `resolved` - the incident is OPEN")
            else:
                flags.append(f"missing milestone: `{m}`")
    seq = [("started_at", started)] + [(m, first[m]["ts"]) for m in MILESTONES if m in first]
    for (n1, t1), (n2, t2) in zip(seq, seq[1:]):
        if t2 < t1:
            flags.append(f"out of order: `{n2}` ({t2.isoformat()}) is before `{n1}` ({t1.isoformat()})")

    points = {"started_at": started, **{m: first[m]["ts"] for m in first}}
    timings, basis = {}, {}
    for key, _label, frm, to in TIMING_DEFS:
        if key == "impact_duration" and "mitigated" not in points and "resolved" in points:
            to = "resolved"
        basis[key] = f"{frm} -> {to}"
        if frm in points and to in points:
            m = minutes(points[frm], points[to])
            if m < 0:
                timings[key] = None
                flags.append(f"{key} is negative ({m} min): reported as null, fix the timeline")
            else:
                timings[key] = m
        else:
            timings[key] = None
    return {"ordered": ordered, "first": first, "flags": flags, "timings": timings, "basis": basis,
            "status": "resolved" if "resolved" in first else "open"}


def link_actions(factors: list[dict] | None, actions: list[dict] | None) -> list[str]:
    flags = []
    if actions is None:
        return flags
    by_id = {f["id"].lower(): f for f in (factors or [])}
    by_text = {f["factor"].lower(): f for f in (factors or [])}
    for a in actions:
        ids = []
        for ref in [x.strip() for x in a["factor_ref"].split(";") if x.strip()]:
            f = by_id.get(ref.lower()) or by_text.get(ref.lower())
            if f is None:
                flags.append(f"action {a['id']} links to unknown factor {ref!r}")
            elif f["id"] not in ids:
                ids.append(f["id"])
        a["factor_ids"] = ids
        if not a["factor_ref"]:
            flags.append(f"action {a['id']} is not linked to any factor")
        a["owner_out"] = a["owner"] or tbd()
        a["due_out"] = a["due"] or tbd()
        a["type_out"] = a["type"] or tbd()
        if a["due"]:
            try:
                date.fromisoformat(a["due"])
            except ValueError:
                flags.append(f"action {a['id']} due {a['due']!r} is not a YYYY-MM-DD date")
        if not a["owner"]:
            a["status"] = STATUS_NO_OWNER
        elif not a["due"]:
            a["status"] = STATUS_NO_DUE
        else:
            a["status"] = a["status_in"] or "open"
    for f in factors or []:
        f["action_ids"] = [a["id"] for a in actions if f["id"] in a["factor_ids"]]
    return flags


def blame_scan(inc: dict, tl: list[dict], factors, actions) -> list[dict]:
    phrases = [(re.compile(r["pattern"], re.I), r["pattern"], r["why"], r["rewrite_hint"]) for r in read_csv(BLAME_CSV)]
    fields = [("incident", k, inc[k]) for k in ("title", "customer_impact", "went_well") if k in inc]
    fields += [("timeline", f"row {e['row']}", e["description"]) for e in tl]
    fields += [("timeline", f"row {e['row']} actor_role", e["actor_role"]) for e in tl if e["actor_role"]]
    for f in factors or []:
        fields += [("factors", f"{f['id']} factor", f["factor"]), ("factors", f"{f['id']} evidence", f["evidence"])]
    for a in actions or []:
        fields.append(("actions", f"{a['id']}", a["action"]))
    hits = []
    for src, where, text in fields:
        for rx, pat, why, hint in phrases:
            m = rx.search(text or "")
            if m:
                hits.append({"input": src, "where": where, "phrase": m.group(0), "pattern": pat,
                             "why": why, "rewrite_hint": hint})
    return hits


def eval_cases(inc: dict, tl: list[dict], factors) -> list[dict]:
    cases, seen = [], {}
    src_tag = f"incident-{inc['id']}"

    def add(text: str, category: str, difficulty: str, origin: str, observed: list[str], factor_note: str):
        key = text.strip().lower()
        if key in seen:
            seen[key]["_origins"].append(origin)
            seen[key]["_observed"] += [o for o in observed if o not in seen[key]["_observed"]]
            return
        row = {"input": text.strip(), "category": category, "difficulty": difficulty, "_origins": [origin],
               "_observed": observed, "_factor": factor_note}
        seen[key] = row
        cases.append(row)

    for f in factors or []:
        found = INPUT_RE.findall(f["factor"]) + INPUT_RE.findall(f["evidence"])
        obs = OUTPUT_RE.findall(f["factor"]) + OUTPUT_RE.findall(f["evidence"])
        diff = "adversarial" if f["category"] == "prompt-guardrail-gap" else "medium"
        for text in found:
            add(text, f["category"], diff, f"factor {f['id']}", obs, f"{f['id']} {f['factor']}")
        if f["eval_relevant"] and not found:
            cases.append({"input": tbd(EVAL_LEAD), "category": f["category"], "difficulty": diff,
                          "_origins": [f"factor {f['id']}"], "_observed": obs,
                          "_factor": f"{f['id']} {f['factor']}", "_needs_input": True})
    for e in tl:
        obs = OUTPUT_RE.findall(e["description"])
        for text in INPUT_RE.findall(e["description"]):
            add(text, "incident-regression", "medium", f"timeline row {e['row']}", obs, "")
    out = []
    for n, c in enumerate(cases, 1):
        notes = [f"from {'; '.join(c['_origins'])}"]
        if c["_factor"]:
            notes.append(f"regression for {c['_factor']}")
        if c["_observed"]:
            notes.append("observed bad output: " + " / ".join(c["_observed"]))
        notes.append(f"must_contain and must_not_contain {tbd(EVAL_LEAD)}")
        out.append({"id": f"{inc['id']}-RC{n:02d}", "category": c["category"], "difficulty": c["difficulty"],
                    "input": c["input"], "expected": "", "must_contain": "", "must_not_contain": "",
                    "expected_json_valid": "false", "weight": "1", "source": src_tag, "notes": "; ".join(notes),
                    "_needs_input": c.get("_needs_input", False)})
    return out


def gate(factors, actions) -> dict:
    reasons = []
    if factors is None:
        reasons.append("no factors supplied: coverage cannot be shown")
    for f in factors or []:
        if not f["action_ids"]:
            reasons.append(f"factor {f['id']} has no action")
    for a in actions or []:
        if not a["owner"]:
            reasons.append(f"action {a['id']} has no owner")
    return {"pass": not reasons, "reasons": reasons}


# ------------------------------------------------------------------ rendering

def cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def fmt_min(m) -> str:
    return "—" if m is None else f"{m:.1f} min ({hmm(m)})"


def build(inc, tl, factors, actions, strict: bool) -> dict:
    an = analyse_timeline(inc, tl)
    flags = list(an["flags"]) + link_actions(factors, actions)
    blame = blame_scan(inc, tl, factors, actions)
    cases = eval_cases(inc, tl, factors)
    g = gate(factors, actions)
    uncovered = [f["id"] for f in factors or [] if not f["action_ids"]]
    t = an["timings"]
    timings = {
        "incident_id": inc["id"], "title": inc["title"], "severity": inc.get("severity"),
        "system": inc.get("system"), "status": an["status"], "started_at": inc["started_at"],
        "milestones": {m: (an["first"][m]["timestamp"] if m in an["first"] else None) for m in MILESTONES},
        "timings_min": t, "basis": an["basis"], "flags": flags,
        "factors": None if factors is None else len(factors),
        "factors_covered": None if factors is None else len(factors) - len(uncovered),
        "uncovered_factors": uncovered,
        "actions": None if actions is None else len(actions),
        "actions_unowned": sum(1 for a in actions or [] if not a["owner"]),
        "actions_undated": sum(1 for a in actions or [] if not a["due"]),
        "action_types": {k: sum(1 for a in actions or [] if a["type"] == k) for k in ACTION_TYPES},
        "blame_flags": len(blame), "eval_cases": len(cases),
        "eval_cases_need_input": sum(1 for c in cases if c["_needs_input"]),
        "strict": strict, "strict_gate": g,
    }
    md = render_md(inc, an, factors, actions, blame, cases, timings)
    return {"timings": timings, "md": md, "actions": actions, "cases": cases}


def render_md(inc, an, factors, actions, blame, cases, tj) -> str:
    t = an["timings"]
    sev = inc.get("severity") or tbd()
    L = [f"# Postmortem {inc['id']}: {inc['title']}", ""]
    # Summary
    L += ["## Summary", ""]
    status = "RESOLVED" if an["status"] == "resolved" else "OPEN — no `resolved` event in the timeline"
    L.append(f"- **Status:** {status}")
    L.append(f"- **Severity:** {sev} · **System:** {inc.get('system') or tbd()}")
    L.append(f"- **Time to detect:** {fmt_min(t['time_to_detect'])} · **Time to mitigate:** "
             f"{fmt_min(t['time_to_mitigate'])} · **Time to resolve:** {fmt_min(t['time_to_resolve'])}")
    if factors is None:
        L.append(f"- **Contributing factors:** not supplied {tbd()}")
    else:
        L.append(f"- **Contributing factors:** {len(factors)}; with at least one action: {tj['factors_covered']} of {len(factors)}")
    if actions is None:
        L.append(f"- **Actions:** not supplied {tbd()}")
    else:
        L.append(f"- **Actions:** {len(actions)}; without owner: {tj['actions_unowned']}; without due date: {tj['actions_undated']}")
    L.append(f"- **Blame phrasing flagged:** {len(blame)} (see Method)")
    L.append(f"- **Proposed regression eval cases:** {len(cases)} (needing an input: {tj['eval_cases_need_input']})")
    g = tj["strict_gate"]
    verdict = "PASS" if g["pass"] else "FAIL — " + "; ".join(g["reasons"])
    L.append(f"- **Strict gate (every factor has an action, every action has an owner):** {verdict}"
             + (" — `--strict` was set: the run fails (exit 1)." if tj["strict"] and not g["pass"] else ""))
    L.append("")
    # Impact
    L += ["## Impact", "", "| Fact | Value | Source |", "|---|---|---|"]
    src = inc["_sources"]
    for key, label in (("customer_impact", "Customer impact"), ("severity", "Severity"),
                       ("detection_source", "Detection source"), ("started_at", "Impact started")):
        L.append(f"| {label} | {cell(inc.get(key) or tbd())} | {cell(src.get(key) or '—')} |")
    imp = t["impact_duration"]
    imp_txt = fmt_min(imp) if imp is not None else ("ongoing — no mitigated or resolved event" if not
                                                      ({"mitigated", "resolved"} & set(an["first"])) else "—")
    L.append(f"| Impact duration ({an['basis']['impact_duration']}) | {imp_txt} | timeline |")
    L.append("")
    # Timeline
    L += ["## Timeline", "", "| Time (as given) | T+ min | Event | Description | Actor role |", "|---|---|---|---|---|"]
    for e in an["ordered"]:
        tp = minutes(inc["_started"], e["ts"])
        L.append(f"| {cell(e['timestamp'])} | {tp:.1f} | {e['event']} | {cell(e['description'])} | {cell(e['actor_role'] or '—')} |")
    L.append("")
    tl_flags = [f for f in tj["flags"] if not f.startswith("action ")]
    L.append("Timeline flags:" if tl_flags else "Timeline flags: none.")
    L += [f"- {f}" for f in tl_flags]
    L.append("")
    # Timings
    L += ["## Timings", "", "| Measure | From → to | Minutes | Status |", "|---|---|---|---|"]
    for key, label, _f, _t in TIMING_DEFS:
        v = t[key]
        frm, to = an["basis"][key].split(" -> ")
        if v is not None:
            st = "measured"
        elif to == "resolved" and "resolved" not in an["first"]:
            st = "open — not resolved"
        elif to not in an["first"] or (frm != "started_at" and frm not in an["first"]):
            missing = [x for x in (frm, to) if x != "started_at" and x not in an["first"]]
            st = "missing milestone: " + ", ".join(missing)
        else:
            st = "out of order — see flags"
        L.append(f"| {label} | {frm} → {to} | {fmt_min(v)} | {st} |")
    L.append("")
    # Contributing factors
    L += ["## Contributing factors", ""]
    if factors is None:
        L += [f"No factors CSV supplied: contributing factors {tbd()}. Use the categories in "
              "`assets/factor-taxonomy.csv`.", ""]
    else:
        L += ["| ID | Factor | Category | Evidence | Actions |", "|---|---|---|---|---|"]
        for f in factors:
            acts = ", ".join(f["action_ids"]) if f["action_ids"] else f"NONE {tbd()}"
            L.append(f"| {f['id']} | {cell(f['factor'])} | {f['category_name']} | {cell(f['evidence'] or tbd())} | {acts} |")
        L.append("")
    # What went well
    L += ["## What went well", ""]
    ww = [x.strip() for x in inc.get("went_well", "").split(";") if x.strip()]
    L += [f"- {cell(x)}" for x in ww] if ww else [f"- {tbd()} (incident key `went_well`)"]
    L.append("")
    # Actions
    L += ["## Actions", ""]
    if actions is None:
        L += [f"No actions CSV supplied: actions {tbd()}.", ""]
    else:
        L += ["| ID | Action | Type | Owner | Due | Factor | Status |", "|---|---|---|---|---|---|---|"]
        for a in actions:
            L.append(f"| {a['id']} | {cell(a['action'])} | {a['type_out']} | {cell(a['owner_out'])} | "
                     f"{cell(a['due_out'])} | {', '.join(a['factor_ids']) or '—'} | {a['status']} |")
        L.append("")
        types = tj["action_types"]
        L.append("Action mix: " + ", ".join(f"{k} {types[k]}" for k in ACTION_TYPES) + ".")
        if actions and types["prevent"] == 0:
            L.append("No prevent action: add at least one so the incident cannot recur the same way [S2].")
        a_flags = [f for f in tj["flags"] if f.startswith("action ")]
        L += [f"- {f}" for f in a_flags]
        if factors is not None:
            unc = tj["uncovered_factors"]
            L.append("Factors with no action: " + (", ".join(unc) + f" — {tbd()}" if unc else "none."))
        L.append("")
    # Lessons for the eval set
    L += ["## Lessons for the eval set", ""]
    if cases:
        L += ["Proposed regression cases for `ai-platform/llm-eval-harness` (`eval-cases.csv`, golden-set columns). "
              "Inputs come only from `input:\"...\"` markers in the timeline and factor text; scoring "
              "(`must_contain` / `must_not_contain`) is left to the Eval lead.", "",
              "| ID | Category | Input | Source |", "|---|---|---|---|"]
        for c in cases:
            origin = c["notes"].split(";")[0].replace("from ", "")
            L.append(f"| {c['id']} | {c['category']} | {cell(c['input'])} | {cell(origin)} |")
        L += ["", "Next: complete the TBD scoring columns, then run "
              "`python3 scripts/run_skill.py ai-platform/llm-eval-harness --input cases=<out>/eval-cases.csv --out <dir>`."]
    else:
        L.append(f"No regression case could be drawn: no `input:\"...\"` marker and no eval-relevant factor. "
                 f"Failing inputs {tbd(EVAL_LEAD)}.")
    non_eval = [f["id"] for f in factors or [] if not f["eval_relevant"]]
    if non_eval:
        L.append(f"Factors {', '.join(non_eval)} are not model-output failures; they close through detect/process "
                 "actions, not eval cases.")
    L.append("")
    # Method
    L += ["## Method", "",
          "- Timings: minutes between the first event of each milestone, per `references/method.md`; "
          "missing milestones are never inferred and an incident without `resolved` is reported as open.",
          "- Factors use the AI factor taxonomy in `assets/factor-taxonomy.csv` (this skill's own design, not an "
          "external standard). Coverage = every factor linked by at least one action.",
          "- Blameless practice: focus on systems and processes, not individuals [S1]; every action has an owner "
          "and tracking, and the action set includes preventative items [S2]. Sources: `references/sources.md`.",
          "- Limits: the blame check is a word-list scan (`assets/blame-phrases.csv`), not a judgement of tone; it "
          "cannot detect personal names. Timings are only as accurate as the timeline timestamps. Not a legal or "
          "regulatory determination.", "",
          "### Blameless language check", ""]
    if blame:
        L += ["| Input | Where | Phrase | Why it reads as blame | Rewrite as |", "|---|---|---|---|---|"]
        for b in blame:
            L.append(f"| {b['input']} | {b['where']} | {cell(b['phrase'])} | {cell(b['why'])} | {cell(b['rewrite_hint'])} |")
    else:
        L.append("No phrase from the blame word list was found.")
    L.append("")
    return "\n".join(L)


def write_outputs(out: Path, res: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "postmortem.md").write_text(res["md"], encoding="utf-8")
    (out / "timings.json").write_text(json.dumps(res["timings"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out / "actions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(ACTION_COLS)
        for a in res["actions"] or []:
            w.writerow([a["action"], a["type_out"], a["owner_out"], a["due_out"],
                        ";".join(a["factor_ids"]), a["status"]])
    with (out / "eval-cases.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=GOLDEN_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(res["cases"])


# ------------------------------------------------------------------ verify

def verify(path: Path) -> list[str]:
    errs = []
    if not path.is_file():
        return [f"not found: {path}"]
    name = path.name
    tj_path = path.parent / "timings.json"
    tj = json.loads(tj_path.read_text(encoding="utf-8")) if tj_path.is_file() else None
    if name == "timings.json":
        started = parse_ts(tj["started_at"], "started_at")
        pts = {"started_at": started}
        pts.update({m: parse_ts(v, m) for m, v in tj["milestones"].items() if v})
        for key, _l, _f, _t in TIMING_DEFS:
            frm, to = tj["basis"][key].split(" -> ")
            exp = minutes(pts[frm], pts[to]) if frm in pts and to in pts else None
            if exp is not None and exp < 0:
                exp = None
            if tj["timings_min"][key] != exp:
                errs.append(f"{key}: file says {tj['timings_min'][key]}, recomputed {exp}")
        if (tj["status"] == "resolved") != bool(tj["milestones"].get("resolved")):
            errs.append("status disagrees with the resolved milestone")
        if not tj["status"] in ("open", "resolved"):
            errs.append(f"bad status {tj['status']!r}")
        want_pass = tj["factors"] is not None and not tj["uncovered_factors"] and tj["actions_unowned"] == 0
        if tj["strict_gate"]["pass"] != want_pass:
            errs.append("strict_gate.pass disagrees with uncovered factors / unowned actions")
    elif name == "actions.csv":
        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
        if not rows or rows[0] != ACTION_COLS:
            return [f"header must be {','.join(ACTION_COLS)}"]
        allowed = set(ACTION_STATUS_IN) | {STATUS_NO_OWNER, STATUS_NO_DUE}
        for i, r in enumerate(rows[1:], 2):
            d = dict(zip(ACTION_COLS, r))
            for col in ("action", "type", "owner", "due", "status"):
                if not d.get(col):
                    errs.append(f"line {i}: empty {col}")
            if d.get("type") not in ACTION_TYPES and d.get("type") != tbd():
                errs.append(f"line {i}: bad type {d.get('type')!r}")
            if d.get("status") not in allowed:
                errs.append(f"line {i}: bad status {d.get('status')!r}")
            if (d.get("owner") == tbd()) != (d.get("status") == STATUS_NO_OWNER):
                errs.append(f"line {i}: status disagrees with owner")
        if tj is not None and tj["actions"] is not None and tj["actions"] != len(rows) - 1:
            errs.append(f"{len(rows) - 1} action rows but timings.json says {tj['actions']}")
    elif name == "eval-cases.csv":
        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
        if not rows or rows[0] != GOLDEN_COLS:
            return [f"header must be the llm-eval-harness golden-set columns {','.join(GOLDEN_COLS)}"]
        ids = set()
        for i, r in enumerate(rows[1:], 2):
            d = dict(zip(GOLDEN_COLS, r))
            if not d.get("input") or not d.get("source") or not d.get("id"):
                errs.append(f"line {i}: id, input and source are required")
            if d.get("id") in ids:
                errs.append(f"line {i}: duplicate id {d.get('id')}")
            ids.add(d.get("id"))
        if tj is not None and tj["eval_cases"] != len(rows) - 1:
            errs.append(f"{len(rows) - 1} eval rows but timings.json says {tj['eval_cases']}")
    elif name == "postmortem.md":
        text = path.read_text(encoding="utf-8")
        heads = [ln[3:].strip() for ln in text.splitlines() if ln.startswith("## ")]
        if heads != SECTIONS:
            errs.append(f"sections must be {SECTIONS}, got {heads}")
        for m in re.finditer(r"\[TO BE BASELINED([^\]]*)\]", text):
            if not re.match(r" — owner: \S", m.group(1)):
                errs.append(f"TBD without an owner: {m.group(0)}")
        if tj is None:
            errs.append("timings.json missing next to postmortem.md")
        else:
            for key, v in tj["timings_min"].items():
                if v is not None and fmt_min(v) not in text:
                    errs.append(f"{key} {fmt_min(v)} not shown in postmortem.md")
            if tj["status"] == "open" and "OPEN" not in text:
                errs.append("open incident not reported as OPEN")
    else:
        errs.append(f"don't know how to verify {name}")
    return errs


# ------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--incident", type=Path, help="incident facts key,value[,source,notes]")
    ap.add_argument("--timeline", type=Path, help="timeline timestamp,event,description,actor_role")
    ap.add_argument("--factors", type=Path, help="factors factor,category,evidence (optional)")
    ap.add_argument("--actions", type=Path, help="actions action,type,owner,due,factor (optional)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if a factor has no action or an action no owner")
    ap.add_argument("--out-dir", type=Path, help="directory for the four outputs")
    ap.add_argument("--verify", type=Path, metavar="FILE", help="re-check one output file for consistency")
    args = ap.parse_args(argv)
    if args.verify:
        try:
            errs = verify(args.verify)
        except (InputError, KeyError, ValueError, json.JSONDecodeError) as e:
            errs = [f"unreadable: {e}"]
        for e in errs:
            print(f"verify: {e}", file=sys.stderr)
        print(f"verify {args.verify.name}: {'OK' if not errs else f'{len(errs)} problem(s)'}")
        return 1 if errs else 0
    if not (args.incident and args.timeline and args.out_dir):
        print("error: --incident, --timeline and --out-dir are required", file=sys.stderr)
        return 2
    try:
        inc = load_incident(args.incident)
        tl = load_timeline(args.timeline)
        factors = load_factors(args.factors, load_taxonomy())
        actions = load_actions(args.actions)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    res = build(inc, tl, factors, actions, args.strict)
    write_outputs(args.out_dir, res)
    tj = res["timings"]
    print(f"{inc['id']}: {tj['status']}; ttd={tj['timings_min']['time_to_detect']} "
          f"ttm={tj['timings_min']['time_to_mitigate']} ttr={tj['timings_min']['time_to_resolve']} min; "
          f"uncovered factors {len(tj['uncovered_factors'])}; unowned actions {tj['actions_unowned']}; "
          f"blame flags {tj['blame_flags']}; eval cases {tj['eval_cases']}")
    if args.strict and not tj["strict_gate"]["pass"]:
        print("strict: " + "; ".join(tj["strict_gate"]["reasons"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
