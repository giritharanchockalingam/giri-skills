#!/usr/bin/env python3
"""Job application tracker CLI (stdlib only).

Operates on a CSV with the header defined in assets/tracker.csv.

Usage:
    tracker.py add    --file tracker.csv --company X --role Y --stage Applied --date YYYY-MM-DD
                      [--next "action" --next-date YYYY-MM-DD] [--level --location --source --fit --contact --comp --notes]
    tracker.py update --file tracker.csv --id N [--stage S] [--date YYYY-MM-DD] [--next ...] [--next-date ...]
                      [--close-reason "..."] [--notes "..."]
    tracker.py list   --file tracker.csv [--stage S] [--open] [--json]
    tracker.py aging  --file tracker.csv [--as-of YYYY-MM-DD] [--json]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

HEADER = ["id", "company", "role", "level", "location", "source", "fit_score", "stage", "applied_date",
          "last_touch", "next_action", "next_action_date", "contact", "comp_band", "close_reason", "notes"]

STAGES = ["Identified", "Applied", "Screen", "HM", "Panel", "Exec", "Offer", "Accepted", "Declined", "Rejected", "Passed", "Ghosted", "Stalled"]
OPEN_STAGES = {"Identified", "Applied", "Screen", "HM", "Panel", "Exec", "Offer", "Stalled"}
# stage -> (watch_days, stale_days)
AGING = {"Identified": (3, 7), "Applied": (7, 14), "Screen": (5, 10), "HM": (5, 10), "Panel": (5, 10),
         "Exec": (7, 14), "Offer": (2, 5), "Stalled": (14, 30)}
SEVERITY = ["MISSING", "OVERDUE", "STALE", "DUE", "WATCH", "OK"]


def parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"error: date must be YYYY-MM-DD, got '{s}'")


def canon_stage(s: str) -> str:
    for st in STAGES:
        if st.lower() == s.strip().lower():
            return st
    raise SystemExit(f"error: unknown stage '{s}'. Valid: {', '.join(STAGES)}")


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != HEADER:
            raise SystemExit(f"error: header mismatch in {path}. Expected: {','.join(HEADER)}")
        return [row for row in reader]


def save(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADER})


def next_id(rows: list[dict]) -> str:
    ids = [int(r["id"]) for r in rows if r.get("id", "").isdigit()]
    return str(max(ids) + 1 if ids else 1)


def cmd_add(a) -> int:
    rows = load(a.file)
    stage = canon_stage(a.stage)
    parse_date(a.date)
    if a.next_date:
        parse_date(a.next_date)
    if stage in OPEN_STAGES and not (a.next and a.next_date):
        print("warning: open row without next action/date; it will flag MISSING", file=sys.stderr)
    row = {"id": next_id(rows), "company": a.company, "role": a.role, "level": a.level or "", "location": a.location or "",
           "source": a.source or "", "fit_score": a.fit or "", "stage": stage,
           "applied_date": a.date if stage != "Identified" else "", "last_touch": a.date,
           "next_action": a.next or "", "next_action_date": a.next_date or "", "contact": a.contact or "",
           "comp_band": a.comp or "", "close_reason": "", "notes": a.notes or ""}
    rows.append(row)
    save(a.file, rows)
    print(f"added id={row['id']} {row['company']} — {row['role']} [{stage}]")
    return 0


def cmd_update(a) -> int:
    rows = load(a.file)
    target = next((r for r in rows if r["id"] == str(a.id)), None)
    if target is None:
        raise SystemExit(f"error: id {a.id} not found")
    if a.stage:
        target["stage"] = canon_stage(a.stage)
        if target["stage"] == "Applied" and not target["applied_date"] and a.date:
            target["applied_date"] = a.date
    if a.date:
        parse_date(a.date)
        target["last_touch"] = a.date
    if a.next is not None:
        target["next_action"] = a.next
    if a.next_date is not None:
        if a.next_date:
            parse_date(a.next_date)
        target["next_action_date"] = a.next_date
    if a.close_reason is not None:
        target["close_reason"] = a.close_reason
    if a.notes is not None:
        target["notes"] = a.notes
    if target["stage"] not in OPEN_STAGES and not target["close_reason"]:
        print("warning: closed stage without close_reason", file=sys.stderr)
    save(a.file, rows)
    print(f"updated id={target['id']} {target['company']} — {target['role']} [{target['stage']}]")
    return 0


def table(rows: list[dict], cols: list[str]) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def cmd_list(a) -> int:
    rows = load(a.file)
    if a.stage:
        st = canon_stage(a.stage)
        rows = [r for r in rows if r["stage"] == st]
    if a.open:
        rows = [r for r in rows if r["stage"] in OPEN_STAGES]
    rows.sort(key=lambda r: (STAGES.index(r["stage"]) if r["stage"] in STAGES else 99, r.get("next_action_date", "")))
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        print(table(rows, ["id", "company", "role", "stage", "last_touch", "next_action", "next_action_date"]))
        print(f"\n{len(rows)} rows")
    return 0


def flag_row(r: dict, as_of: date) -> tuple[str, int]:
    age = (as_of - parse_date(r["last_touch"])).days if r.get("last_touch") else -1
    flags = []
    if not r.get("next_action") or not r.get("next_action_date"):
        flags.append("MISSING")
    else:
        nd = parse_date(r["next_action_date"])
        if nd < date.fromordinal(as_of.toordinal() - 3):
            flags.append("OVERDUE")
        elif nd <= as_of:
            flags.append("DUE")
    watch, stale = AGING.get(r["stage"], (7, 14))
    if age >= stale:
        flags.append("STALE")
    elif age >= watch:
        flags.append("WATCH")
    if not flags:
        flags.append("OK")
    flags.sort(key=SEVERITY.index)
    return "+".join(flags), age


def cmd_aging(a) -> int:
    rows = [r for r in load(a.file) if r["stage"] in OPEN_STAGES]
    as_of = parse_date(a.as_of) if a.as_of else date.today()
    out = []
    for r in rows:
        flag, age = flag_row(r, as_of)
        out.append({"id": r["id"], "company": r["company"], "role": r["role"], "stage": r["stage"],
                    "age_days": age, "flag": flag, "next_action": r["next_action"], "due": r["next_action_date"]})
    out.sort(key=lambda x: (SEVERITY.index(x["flag"].split("+")[0]), -x["age_days"]))
    if a.json:
        print(json.dumps({"as_of": as_of.isoformat(), "rows": out}, indent=2))
    else:
        print(f"Aging as of {as_of.isoformat()} — {len(out)} open rows\n")
        print(table(out, ["id", "company", "role", "stage", "age_days", "flag", "next_action", "due"]))
        counts = {}
        for x in out:
            counts[x["stage"]] = counts.get(x["stage"], 0) + 1
        print("\nFunnel: " + ", ".join(f"{s}={counts[s]}" for s in STAGES if s in counts))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--file", required=True, type=Path, help="tracker.csv path")

    p = sub.add_parser("add"); common(p)
    p.add_argument("--company", required=True); p.add_argument("--role", required=True)
    p.add_argument("--stage", required=True); p.add_argument("--date", required=True, help="event date YYYY-MM-DD")
    p.add_argument("--next"); p.add_argument("--next-date", dest="next_date")
    for opt in ("--level", "--location", "--source", "--fit", "--contact", "--comp", "--notes"):
        p.add_argument(opt)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("update"); common(p)
    p.add_argument("--id", required=True, type=int)
    p.add_argument("--stage"); p.add_argument("--date"); p.add_argument("--next"); p.add_argument("--next-date", dest="next_date")
    p.add_argument("--close-reason", dest="close_reason"); p.add_argument("--notes")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("list"); common(p)
    p.add_argument("--stage"); p.add_argument("--open", action="store_true"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("aging"); common(p)
    p.add_argument("--as-of", dest="as_of"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_aging)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
