#!/usr/bin/env python3
"""AI delivery program status from a RAID log and milestones, as of a stated date.

Computes (references/method.md):
  * milestone slip_days = forecast_date - baseline_date; RAG by slip thresholds
    (green <= green_max_slip_days < amber <= amber_max_slip_days < red; defaults 0 / 10);
    a not-done milestone whose forecast date is before as_of is `late` and red; done -> complete;
    blocked -> at least amber.
  * critical path = longest path through depends_on, weighted by duration_days (ties -> lowest id);
    a dependency cycle is an error (exit 1).
  * RAID exposure = likelihood x impact (1-5 each; an issue with blank likelihood counts 5 — it
    has already occurred); overdue_days = as_of - due for open items; age_days = as_of - raised.
  * overall RAG: RED if an open critical-path milestone is red, or an open RAID item with
    exposure >= red_exposure (default 20) is overdue; AMBER if any open milestone is amber/red,
    any open RAID item is overdue, or any open item has no owner; else GREEN.
  * owners missing -> `[TO BE BASELINED — owner: Program manager]`.

Usage:
  python3 -I raid_status.py --raid raid.csv --milestones milestones.csv --as-of YYYY-MM-DD
      [--thresholds thresholds.csv] [--previous last-status.json] [--strict] --out-dir OUT
  python3 -I raid_status.py --verify OUT/status.csv --as-of YYYY-MM-DD   (or raid-actions.csv)

Inputs:
  raid        CSV id,type,description,owner,likelihood,impact,due,status,mitigation[,raised]
              type risk|assumption|issue|dependency; status open|closed; dates YYYY-MM-DD.
  milestones  CSV id,milestone,baseline_date,forecast_date,duration_days,depends_on,status[,owner]
              depends_on '|'-separated ids; status not_started|in_progress|blocked|done.
  thresholds  CSV key,value: green_max_slip_days, amber_max_slip_days, red_exposure.
  Lines starting with '#' are comments.

Brownfield (--previous): the status.json of the last report. The run adds "since_previous": overall RAG
then and now, per milestone forecast movement (days) and RAG change, milestones completed since, RAID
items opened and closed since — in status.json and a "Since last report" section of the report.

Outputs (in --out-dir): status.csv, raid-actions.csv, status-report.md (with a mermaid flowchart
of the critical path), status.json.
Exit codes: 0 written · 1 dependency cycle (nothing written), or --strict and overall RAG is red
(outputs still written) · 2 missing or invalid input. Stdlib only; no network.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Program manager]"
RAID_TYPES = ("risk", "assumption", "issue", "dependency")
M_STATUS = ("not_started", "in_progress", "blocked", "done")
DEFAULTS = {"green_max_slip_days": 0, "amber_max_slip_days": 10, "red_exposure": 20}
RAG_ORDER = {"complete": 0, "green": 1, "amber": 2, "red": 3}


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


class CycleError(Exception):
    """Dependency cycle -> exit 1."""


_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")


def csv_safe(v) -> str:
    """OWASP CSV-injection guard: prefix a formula-leading text cell with a single quote (numbers untouched)."""
    s = "" if v is None else str(v)
    if s.startswith(_FORMULA_LEAD) and not _NUMBER.fullmatch(s):
        return "'" + s
    return s


def read_csv(path: Path, label: str, cols: tuple[str, ...]) -> list[dict]:
    if not path.is_file():
        raise InputError(f"{label} file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        raise InputError(f"{label} file {path.name} is not a UTF-8 text CSV ({e.reason} at byte {e.start}); "
                         "save it as CSV UTF-8") from None
    if "\x00" in text:
        raise InputError(f"{label} file {path.name} is not a text CSV (contains NUL bytes)")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise InputError(f"{label} CSV is empty")
    try:
        header = [h.strip() for h in next(csv.reader(io.StringIO(lines[0])))]
        missing = [c for c in cols if c not in header]
        if missing:
            raise InputError(f"{label} CSV needs columns {','.join(cols)} (missing {','.join(missing)})")
        return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None}
                for r in csv.DictReader(io.StringIO("\n".join(lines)))]
    except csv.Error as e:
        raise InputError(f"{label} file {path.name}: malformed CSV ({e})") from None


def date(v: str, label: str, allow_blank: bool = False):
    if allow_blank and not v:
        return None
    try:
        return dt.date.fromisoformat(v)
    except (TypeError, ValueError):
        raise InputError(f"{label}: expected YYYY-MM-DD, got {v!r}") from None


def score(v: str, label: str):
    if v == "":
        return None
    try:
        n = int(v)
    except ValueError:
        raise InputError(f"{label}: expected an integer 1-5, got {v!r}") from None
    if not 1 <= n <= 5:
        raise InputError(f"{label}: {n} out of range 1-5")
    return n


def load_thresholds(path: Path | None) -> dict:
    t = dict(DEFAULTS)
    if path is not None:
        for r in read_csv(path, "thresholds", ("key", "value")):
            if r["key"] in t and r["value"] != "":
                try:
                    t[r["key"]] = int(r["value"])
                except ValueError:
                    raise InputError(f"thresholds {r['key']}: expected an integer, got {r['value']!r}") from None
    if t["green_max_slip_days"] > t["amber_max_slip_days"]:
        raise InputError("thresholds: green_max_slip_days must be <= amber_max_slip_days")
    return t


def load_milestones(path: Path) -> list[dict]:
    rows = read_csv(path, "milestones", ("id", "milestone", "baseline_date", "forecast_date",
                                         "duration_days", "depends_on", "status"))
    if not rows:
        raise InputError("milestones CSV has no rows")
    out, ids = [], set()
    for i, r in enumerate(rows, start=2):
        if not r["id"] or r["id"] in ids:
            raise InputError(f"milestones row {i}: id missing or duplicated")
        ids.add(r["id"])
        st = r["status"].lower()
        if st not in M_STATUS:
            raise InputError(f"milestones row {i}: status {r['status']!r} not in {M_STATUS}")
        try:
            dur = int(r["duration_days"])
        except ValueError:
            raise InputError(f"milestones row {i}: duration_days must be an integer, got {r['duration_days']!r}") from None
        if dur < 0:
            raise InputError(f"milestones row {i}: duration_days must be >= 0")
        out.append({"id": r["id"], "milestone": r["milestone"], "status": st, "duration_days": dur,
                    "baseline": date(r["baseline_date"], f"milestones row {i} baseline_date"),
                    "forecast": date(r["forecast_date"], f"milestones row {i} forecast_date"),
                    "depends_on": sorted({d.strip() for d in r["depends_on"].split("|") if d.strip()}),
                    "owner": r.get("owner", "") or TBD})
    for m in out:
        unknown = [d for d in m["depends_on"] if d not in ids]
        if unknown:
            raise InputError(f"milestone {m['id']} depends on unknown id(s): {', '.join(unknown)}")
    return out


def load_raid(path: Path) -> list[dict]:
    rows = read_csv(path, "raid", ("id", "type", "description", "owner", "likelihood", "impact",
                                   "due", "status", "mitigation"))
    out, ids = [], set()
    for i, r in enumerate(rows, start=2):
        if not r["id"] or r["id"] in ids:
            raise InputError(f"raid row {i}: id missing or duplicated")
        ids.add(r["id"])
        typ, st = r["type"].lower(), r["status"].lower()
        if typ not in RAID_TYPES:
            raise InputError(f"raid row {i}: type {r['type']!r} not in {RAID_TYPES}")
        if st not in ("open", "closed"):
            raise InputError(f"raid row {i}: status {r['status']!r} not in open|closed")
        lik, imp = score(r["likelihood"], f"raid row {i} likelihood"), score(r["impact"], f"raid row {i} impact")
        if typ == "issue" and lik is None:
            lik = 5
        if typ == "risk" and (lik is None or imp is None):
            raise InputError(f"raid row {i}: a risk needs likelihood and impact (1-5)")
        out.append({"id": r["id"], "type": typ, "description": r["description"], "status": st,
                    "owner": r["owner"], "likelihood": lik, "impact": imp,
                    "exposure": lik * imp if lik is not None and imp is not None else None,
                    "due": date(r["due"], f"raid row {i} due", allow_blank=True),
                    "raised": date(r.get("raised", ""), f"raid row {i} raised", allow_blank=True),
                    "mitigation": r["mitigation"]})
    return out


def critical_path(ms: list[dict]) -> tuple[list[str], int, list[str]]:
    """Displayed chain (ties -> lowest id), its length, and every zero-float milestone (CPM)."""
    by_id = {m["id"]: m for m in ms}
    indeg = {m["id"]: len(m["depends_on"]) for m in ms}
    children: dict[str, list[str]] = {m["id"]: [] for m in ms}
    for m in ms:
        for d in m["depends_on"]:
            children[d].append(m["id"])
    ready = sorted(k for k, v in indeg.items() if v == 0)
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for c in sorted(children[n]):
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
                ready.sort()
    if len(order) != len(ms):
        cyc = sorted(k for k, v in indeg.items() if v > 0)
        raise CycleError("dependency cycle among milestones: " + ", ".join(cyc))
    ef, pred = {}, {}
    for n in order:
        best = None
        for d in by_id[n]["depends_on"]:
            if best is None or ef[d] > ef[best] or (ef[d] == ef[best] and d < best):
                best = d
        pred[n] = best
        ef[n] = by_id[n]["duration_days"] + (ef[best] if best else 0)
    end = min(ef, key=lambda k: (-ef[k], k))
    path = [end]
    while pred[path[-1]]:
        path.append(pred[path[-1]])
    finish = ef[end]
    lf: dict[str, int] = {}
    for n in reversed(order):  # backward pass: latest finish without moving the end date
        kids = children[n]
        lf[n] = min((lf[c] - by_id[c]["duration_days"] for c in kids), default=finish)
    zero_float = sorted(n for n in order if lf[n] == ef[n])
    return list(reversed(path)), finish, zero_float


def rag_for(m: dict, as_of: dt.date, t: dict) -> tuple[int, str, bool]:
    slip = (m["forecast"] - m["baseline"]).days
    if m["status"] == "done":
        return slip, "complete", False
    late = m["forecast"] < as_of
    if late or slip > t["amber_max_slip_days"]:
        rag = "red"
    elif slip > t["green_max_slip_days"]:
        rag = "amber"
    else:
        rag = "green"
    if m["status"] == "blocked" and rag == "green":
        rag = "amber"
    return slip, rag, late


def next_action(r: dict, overdue: int | None) -> str:
    parts = []
    if not r["owner"]:
        parts.append("Assign an owner")
    if r["due"] is None:
        parts.append("Set a due date")
    elif overdue:
        parts.append(f"Overdue {overdue} days: close or re-plan at the next review")
    if r["type"] == "assumption":
        parts.append("Validate the assumption" + (f" ({r['mitigation']})" if r["mitigation"] else ""))
    elif r["mitigation"]:
        parts.append(r["mitigation"])
    else:
        parts.append("Define a mitigation")
    return "; ".join(parts)


def bucket(days: int) -> str:
    return "1-7 days" if days <= 7 else ("8-30 days" if days <= 30 else "31+ days")


def build(ms, raid, as_of: dt.date, t: dict) -> dict:
    cp, cp_len, zero_float = critical_path(ms)
    cp_set = set(cp) | set(zero_float)
    cp_ties = [m for m in zero_float if m not in cp]
    status_rows = []
    for m in sorted(ms, key=lambda m: m["id"]):
        slip, rag, late = rag_for(m, as_of, t)
        status_rows.append({"id": m["id"], "milestone": m["milestone"], "baseline": m["baseline"].isoformat(),
                            "forecast": m["forecast"].isoformat(), "slip_days": slip, "rag": rag,
                            "late": late, "on_critical_path": "yes" if m["id"] in cp_set else "no",
                            "status": m["status"], "duration_days": m["duration_days"],
                            "depends_on": m["depends_on"], "owner": m["owner"]})
    actions = []
    for r in raid:
        if r["status"] != "open":
            continue
        overdue = max(0, (as_of - r["due"]).days) if r["due"] else None
        actions.append({"id": r["id"], "type": r["type"], "description": r["description"],
                        "exposure": r["exposure"], "owner": r["owner"] or TBD,
                        "due": r["due"].isoformat() if r["due"] else TBD, "overdue_days": overdue,
                        "age_days": (as_of - r["raised"]).days if r["raised"] else None,
                        "mitigation": r["mitigation"], "next_action": next_action(r, overdue)})
    actions.sort(key=lambda a: (-(a["overdue_days"] or 0), -(a["exposure"] or 0), a["id"]))
    top_risks = sorted([a for a in actions if a["type"] == "risk"], key=lambda a: (-a["exposure"], a["id"]))[:5]
    overdue = [a for a in actions if a["overdue_days"]]
    open_ms = [s for s in status_rows if s["rag"] != "complete"]
    reasons_red = [f"critical-path milestone {s['id']} is red" for s in open_ms
                   if s["on_critical_path"] == "yes" and s["rag"] == "red"]
    reasons_red += [f"{a['id']} (exposure {a['exposure']}) is overdue {a['overdue_days']} days"
                    for a in overdue if a["exposure"] is not None and a["exposure"] >= t["red_exposure"]]
    reasons_amber = [f"milestone {s['id']} is {s['rag']}" for s in open_ms if s["rag"] in ("amber", "red")]
    reasons_amber += [f"{a['id']} is overdue" for a in overdue]
    reasons_amber += [f"{a['id']} has no owner" for a in actions if a["owner"] == TBD]
    overall = "red" if reasons_red else ("amber" if reasons_amber else "green")
    decisions = []
    for s in open_ms:
        if s["on_critical_path"] == "yes" and s["rag"] == "red":
            why = "forecast date has passed" if s["late"] else f"forecast slips {s['slip_days']} days"
            decisions.append(f"Recover or re-baseline {s['id']} {s['milestone']} ({why}; critical path) — owner: {s['owner']}")
    for a in actions:
        if a["exposure"] is not None and a["exposure"] >= t["red_exposure"]:
            decisions.append(f"Fund, accept or escalate {a['id']} (exposure {a['exposure']}) — owner: {a['owner']}")
        elif a["type"] == "dependency" and a["overdue_days"]:
            decisions.append(f"Escalate dependency {a['id']} (overdue {a['overdue_days']} days) — owner: {a['owner']}")
        elif a["owner"] == TBD:
            decisions.append(f"Name an owner for {a['id']} — {TBD}")
    ageing = {}
    for a in overdue:
        ageing[bucket(a["overdue_days"])] = ageing.get(bucket(a["overdue_days"]), 0) + 1
    return {"as_of": as_of.isoformat(), "thresholds": t, "overall_rag": overall,
            "overall_reasons": reasons_red if overall == "red" else reasons_amber,
            "critical_path": cp, "critical_path_days": cp_len, "critical_path_ties": cp_ties,
            "milestones": status_rows,
            "raid_actions": actions, "top_risks": [a["id"] for a in top_risks],
            "overdue": [a["id"] for a in overdue], "overdue_ageing": dict(sorted(ageing.items())),
            "decisions": decisions,
            "counts": {"milestones": len(status_rows), "open_raid": len(actions),
                       "closed_raid": sum(1 for r in raid if r["status"] == "closed"),
                       "rag": {k: sum(1 for s in status_rows if s["rag"] == k) for k in RAG_ORDER}}}


def load_previous(path: Path) -> dict:
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise InputError(f"previous status not found: {path}") from e
    except json.JSONDecodeError as e:
        raise InputError(f"previous status is not JSON: {e}") from e
    if not isinstance(prev, dict) or not {"as_of", "overall_rag", "milestones", "raid_actions"} <= set(prev):
        raise InputError("previous status must be a status.json from this skill (as_of, overall_rag, milestones, raid_actions)")
    return prev


def since_previous(st: dict, prev: dict) -> dict:
    """What moved between the last report and this one."""
    if prev["as_of"] >= st["as_of"]:
        raise InputError(f"previous status as_of {prev['as_of']} is not before {st['as_of']}")
    pm = {m["id"]: m for m in prev["milestones"]}
    moves = []
    for m in st["milestones"]:
        p = pm.get(m["id"])
        if p is None:
            moves.append({"id": m["id"], "change": "added", "forecast_moved_days": None,
                          "rag_before": None, "rag_now": m["rag"]})
            continue
        moved = (dt.date.fromisoformat(m["forecast"]) - dt.date.fromisoformat(p["forecast"])).days
        if moved or p["rag"] != m["rag"]:
            change = "completed" if m["rag"] == "complete" and p["rag"] != "complete" else \
                     ("slipped" if moved > 0 else "pulled in" if moved < 0 else "rag changed")
            moves.append({"id": m["id"], "change": change, "forecast_moved_days": moved,
                          "rag_before": p["rag"], "rag_now": m["rag"]})
    for mid in sorted(set(pm) - {m["id"] for m in st["milestones"]}):
        moves.append({"id": mid, "change": "removed", "forecast_moved_days": None, "rag_before": pm[mid]["rag"],
                      "rag_now": None})
    prev_open = {a["id"] for a in prev["raid_actions"]}
    now_open = {a["id"] for a in st["raid_actions"]}
    end_prev = {m["id"]: m["forecast"] for m in prev["milestones"]}
    return {"previous_as_of": prev["as_of"], "overall_before": prev["overall_rag"], "overall_now": st["overall_rag"],
            "milestone_changes": moves,
            "slipped_total_days": sum(x["forecast_moved_days"] for x in moves
                                      if x["forecast_moved_days"] and x["forecast_moved_days"] > 0),
            "raid_opened": sorted(now_open - prev_open), "raid_closed": sorted(prev_open - now_open),
            "critical_path_before": prev.get("critical_path", []), "critical_path_now": st["critical_path"],
            "end_milestone": st["critical_path"][-1] if st["critical_path"] else None,
            "end_forecast_before": end_prev.get(st["critical_path"][-1]) if st["critical_path"] else None}


def render_since(sp: dict, st: dict) -> list[str]:
    L = ["", "## Since last report", "",
         f"Compared with the report as of {sp['previous_as_of']}: overall RAG {sp['overall_before'].upper()} → "
         f"{sp['overall_now'].upper()}; {len(sp['milestone_changes'])} milestone change(s); "
         f"RAID opened: {', '.join(sp['raid_opened']) or 'none'}; closed: {', '.join(sp['raid_closed']) or 'none'}."]
    if sp["milestone_changes"]:
        L += ["", "| ID | Change | Forecast moved (days) | RAG before | RAG now |", "|---|---|---|---|---|"]
        for x in sp["milestone_changes"]:
            mv = "—" if x["forecast_moved_days"] is None else f"{x['forecast_moved_days']:+d}"
            L.append(f"| {x['id']} | {x['change']} | {mv} | {x['rag_before'] or '—'} | {x['rag_now'] or '—'} |")
    if sp["end_milestone"] and sp["end_forecast_before"]:
        now = next(m["forecast"] for m in st["milestones"] if m["id"] == sp["end_milestone"])
        if now != sp["end_forecast_before"]:
            L += ["", f"End of the critical path ({sp['end_milestone']}) moved from {sp['end_forecast_before']} to {now}."]
    if sp["critical_path_before"] and sp["critical_path_before"] != sp["critical_path_now"]:
        L += ["", f"Critical path changed: {' → '.join(sp['critical_path_before'])} → now {' → '.join(sp['critical_path_now'])}."]
    return L


def label(text: str) -> str:
    return re.sub(r"[\[\]{}()\"<>|]", " ", text).replace("  ", " ").strip()


def mermaid(st: dict) -> list[str]:
    by_id = {s["id"]: s for s in st["milestones"]}
    L = ["```mermaid", "flowchart LR", "  START([Start])"]
    for mid in st["critical_path"]:
        s = by_id[mid]
        L.append(f"  {mid}[\"{mid} {label(s['milestone'])} · {s['duration_days']}d · {s['rag']}\"]")
    L.append("  FINISH([Finish])")
    chain = ["START"] + st["critical_path"] + ["FINISH"]
    for a, b in zip(chain, chain[1:]):
        L.append(f"  {a} --> {b}")
    for rag, style in (("red", "fill:#f8d7da,stroke:#b02a37"), ("amber", "fill:#fff3cd,stroke:#b58105"),
                       ("green", "fill:#d1e7dd,stroke:#146c43"), ("complete", "fill:#e2e3e5,stroke:#6c757d")):
        ids = [m for m in st["critical_path"] if by_id[m]["rag"] == rag]
        if ids:
            L += [f"  classDef {rag} {style}", f"  class {','.join(ids)} {rag}"]
    L.append("```")
    return L


def render(st: dict, strict: bool) -> str:
    t = st["thresholds"]
    c = st["counts"]
    L = [f"# Program status — as of {st['as_of']}", "", "## Summary", "",
         f"**Overall RAG: {st['overall_rag'].upper()}**" + (f" — {'; '.join(st['overall_reasons'])}." if st["overall_reasons"] else "."),
         "",
         f"- Milestones: {c['milestones']} ({c['rag']['red']} red, {c['rag']['amber']} amber, {c['rag']['green']} green, "
         f"{c['rag']['complete']} complete).",
         f"- Critical path: {' → '.join(st['critical_path'])} ({st['critical_path_days']} days of planned duration).",
         f"- RAID: {c['open_raid']} open, {c['closed_raid']} closed; {len(st['overdue'])} open items overdue.",
         f"- Overall RAG rule: RED if an open critical-path milestone is red, or an open RAID item with exposure ≥ "
         f"{t['red_exposure']} is overdue; AMBER if any open milestone is amber or red, any open RAID item is overdue, "
         f"or any open item has no owner; otherwise GREEN."]
    if strict:
        L.append(f"- `--strict` was set: {'the run fails (exit 1) because overall RAG is red.' if st['overall_rag'] == 'red' else 'gate passed.'}")
    L += ["", "## Milestones", "",
          "| ID | Milestone | Baseline | Forecast | Slip (days) | RAG | Critical path | Status | Owner |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s in st["milestones"]:
        rag = s["rag"] + (" (late)" if s["late"] else "")
        L.append(f"| {s['id']} | {s['milestone']} | {s['baseline']} | {s['forecast']} | {s['slip_days']} | {rag} | "
                 f"{s['on_critical_path']} | {s['status']} | {s['owner']} |")
    L += ["", f"RAG thresholds: green ≤ {t['green_max_slip_days']} days slip; amber ≤ {t['amber_max_slip_days']} days; "
          "red above, or forecast date already passed while not done (late).",
          ]
    if st.get("since_previous"):
        L += render_since(st["since_previous"], st)
    L += ["", "## Critical path", "",
          f"Longest chain through `depends_on` by duration_days: {' → '.join(st['critical_path'])} = "
          f"{st['critical_path_days']} days. A slip on any of these moves the end date.", ""]
    if st.get("critical_path_ties"):
        L += [f"Tie: {', '.join(st['critical_path_ties'])} also has zero float (a parallel chain of equal length), so it is "
              "marked on the critical path too; a slip there also moves the end date.", ""]
    L += mermaid(st)
    acts = {a["id"]: a for a in st["raid_actions"]}
    L += ["", "## Top risks", "", "| ID | Risk | Exposure (L×I) | Owner | Due | Mitigation |", "|---|---|---|---|---|---|"]
    for rid in st["top_risks"]:
        a = acts[rid]
        L.append(f"| {rid} | {a['description']} | {a['exposure']} | {a['owner']} | {a['due']} | {a['mitigation'] or 'none recorded'} |")
    if not st["top_risks"]:
        L.append("| — | No open risks | — | — | — | — |")
    L += ["", "## Overdue items", ""]
    if st["overdue"]:
        L += ["| ID | Type | Overdue (days) | Age (days) | Owner | Next action |", "|---|---|---|---|---|---|"]
        for rid in st["overdue"]:
            a = acts[rid]
            age = a["age_days"] if a["age_days"] is not None else "—"
            L.append(f"| {rid} | {a['type']} | {a['overdue_days']} | {age} | {a['owner']} | {a['next_action']} |")
        L += ["", "Ageing of overdue items: " + ", ".join(f"{k}: {v}" for k, v in st["overdue_ageing"].items()) + "."]
    else:
        L.append("None: no open RAID item is past its due date.")
    L += ["", "## Decisions needed", ""]
    L += [f"{i}. {d}" for i, d in enumerate(st["decisions"], start=1)] or ["None this period."]
    L += ["", "## Method", "",
          "- slip_days = forecast_date − baseline_date (calendar days); RAG thresholds from the thresholds input or "
          f"the defaults in `references/method.md` (green ≤ {DEFAULTS['green_max_slip_days']}, amber ≤ "
          f"{DEFAULTS['amber_max_slip_days']}, red exposure ≥ {DEFAULTS['red_exposure']}).",
          "- Critical path = longest path through depends_on weighted by duration_days; the chart shows one chain (ties go "
          "to the lowest id) and every zero-float milestone is marked on_critical_path.",
          "- Exposure = likelihood × impact (1–5 each); an issue with blank likelihood counts 5 (it has occurred).",
          f"- Overdue days = as-of date ({st['as_of']}) − due date for open items; age = as-of − raised.",
          f"- Missing owners are {TBD}.",
          "- Limits: the status is only as current as the RAID log and forecasts supplied; duration_days are planned, "
          "not resource-levelled; float is computed only to mark zero-float milestones."]
    return "\n".join(L) + "\n"


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: csv_safe("" if r.get(k) is None else r.get(k)) for k in cols})
    path.write_text(buf.getvalue(), encoding="utf-8")


def verify(path: Path, as_of: dt.date | None) -> int:
    errs = []
    with path.open(encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        rows = list(rdr)
        header = rdr.fieldnames or []
    is_status = path.name == "status.csv" or "slip_days" in header
    if not rows and is_status:
        errs.append("no rows")  # a program always has milestones; zero open RAID items is valid
    if not header:
        errs.append("no header row")
    if is_status:
        sj = path.parent / "status.json"
        t = json.loads(sj.read_text(encoding="utf-8"))["thresholds"] if sj.exists() else DEFAULTS
        for r in rows:
            slip = (dt.date.fromisoformat(r["forecast"]) - dt.date.fromisoformat(r["baseline"])).days
            if str(slip) != r["slip_days"]:
                errs.append(f"{r['id']}: slip_days {r['slip_days']} != {slip}")
            if r["rag"] not in RAG_ORDER:
                errs.append(f"{r['id']}: unknown rag {r['rag']!r}")
            elif r["rag"] == "green" and slip > t["green_max_slip_days"]:
                errs.append(f"{r['id']}: green with slip {slip}")
            elif r["rag"] in ("green", "amber") and as_of and dt.date.fromisoformat(r["forecast"]) < as_of:
                errs.append(f"{r['id']}: forecast before as-of but not red")
        if rows and not any(r["on_critical_path"] == "yes" for r in rows):
            errs.append("no milestone on the critical path")
    else:
        for r in rows:
            if r["exposure"] and not 1 <= int(r["exposure"]) <= 25:
                errs.append(f"{r['id']}: exposure {r['exposure']} outside 1-25")
            if not r["owner"]:
                errs.append(f"{r['id']}: blank owner")
            if not r.get("next_action"):
                errs.append(f"{r['id']}: blank next_action")
            if as_of and r["due"][:1].isdigit():
                expect = max(0, (as_of - dt.date.fromisoformat(r["due"])).days)
                if str(expect) != r["overdue_days"]:
                    errs.append(f"{r['id']}: overdue_days {r['overdue_days']} != {expect}")
    for e in errs:
        print(f"verify: {e}", file=sys.stderr)
    if not errs:
        print(f"verify: ok ({len(rows)} rows)")
    return 1 if errs else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raid", type=Path)
    ap.add_argument("--milestones", type=Path)
    ap.add_argument("--as-of", dest="as_of", help="status date YYYY-MM-DD (required; never defaults to today)")
    ap.add_argument("--thresholds", type=Path)
    ap.add_argument("--strict", action="store_true", help="exit 1 when overall RAG is red")
    ap.add_argument("--previous", type=Path, help="status.json of the last report (adds 'Since last report')")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--verify", type=Path, help="re-verify status.csv or raid-actions.csv and exit")
    args = ap.parse_args(argv)
    try:
        as_of = date(args.as_of, "--as-of") if args.as_of else None
        if args.verify:
            return verify(args.verify, as_of)
        if not (args.raid and args.milestones and args.out_dir and as_of):
            raise InputError("--raid, --milestones, --as-of and --out-dir are required")
        st = build(load_milestones(args.milestones), load_raid(args.raid), as_of, load_thresholds(args.thresholds))
        if args.previous:
            st["since_previous"] = since_previous(st, load_previous(args.previous))
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except CycleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "status.csv", ["id", "milestone", "baseline", "forecast", "slip_days", "rag", "on_critical_path", "status"],
              st["milestones"])
    write_csv(out / "raid-actions.csv", ["id", "type", "exposure", "owner", "due", "overdue_days", "age_days", "next_action"],
              st["raid_actions"])
    st["strict"] = bool(args.strict)
    (out / "status.json").write_text(json.dumps(st, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (out / "status-report.md").write_text(render(st, args.strict), encoding="utf-8")
    if args.strict and st["overall_rag"] == "red":
        print("strict gate failed: overall RAG is red — " + "; ".join(st["overall_reasons"]), file=sys.stderr)
        return 1
    print(f"status written: overall {st['overall_rag'].upper()}, critical path {' -> '.join(st['critical_path'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
