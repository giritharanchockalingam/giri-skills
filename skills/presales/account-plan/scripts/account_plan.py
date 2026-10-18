#!/usr/bin/env python3
"""Account plan from stakeholder, pipeline and service-coverage CSVs.

    python3 -I scripts/account_plan.py stakeholders.csv pipeline.csv services.csv \
        --out account-plan.md --plays plays.csv [--client "Acme"] [--as-of 2026-10-01]

stakeholders.csv: name, role, stance (-2..2), influence (1-5), last_contact (yyyy-mm-dd or blank), departure_risk
pipeline.csv:     opportunity, stage, value, close_date, owner, next_step
services.csv:     service, status_at_account (active | proposed | none)

Produces account-plan.md: stakeholder map (influence × stance grid), white-space matrix, pipeline
table with total, risks (departure risk, stale contacts when --as-of is given), and 90-day plays:
one per service with status none, one per stakeholder with stance <= 0 and influence >= 4, one per
stakeholder flagged departure_risk. Play owner and date are `[TO BE BASELINED — owner: Account owner]` (the
plan never assigns people it was not told about); plays.csv carries the same rows. Blank pipeline
values become the marker and are excluded from the total, which then says so.
Exit 1 on missing columns, stance/influence out of range, non-numeric values or an unknown
status. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Account owner]"
STATUSES = ("active", "proposed", "none")
STALE_DAYS = 90


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_csv(path: str, cols: list[str]) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    if not rows:
        die(f"{p.name}: no data rows")
    missing = [c for c in cols if c not in rows[0]]
    if missing:
        die(f"{p.name}: missing columns {missing}")
    return rows


def int_in(row: dict, col: str, lo: int, hi: int, where: str) -> int:
    raw = row.get(col, "")
    if not re.fullmatch(r"-?\d+", raw) or not lo <= int(raw) <= hi:
        die(f"{where}: {col} must be an integer {lo}..{hi}, got {raw!r}")
    return int(raw)


def money(raw: str, where: str):
    if raw == "":
        return None
    try:
        return float(raw.replace(",", "").replace("$", ""))
    except ValueError:
        die(f"{where}: non-numeric value {raw!r}")


def date_or_none(raw: str, where: str):
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        die(f"{where}: date must be yyyy-mm-dd, got {raw!r}")


def truthy(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "y", "high", "h")


def fmt(x) -> str:
    return TBD if x is None else (f"{int(round(x)):,}" if abs(x - round(x)) < 0.005 else f"{x:,.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="stakeholders + pipeline + services -> account-plan.md + plays.csv")
    ap.add_argument("stakeholders"); ap.add_argument("pipeline"); ap.add_argument("services")
    ap.add_argument("--out", required=True); ap.add_argument("--plays", required=True)
    ap.add_argument("--client", default="<Client>")
    ap.add_argument("--as-of", default="", help="yyyy-mm-dd; enables stale-contact detection")
    a = ap.parse_args()
    as_of = date_or_none(a.as_of, "--as-of")
    stk = read_csv(a.stakeholders, ["name", "role", "stance", "influence", "last_contact", "departure_risk"])
    pipe = read_csv(a.pipeline, ["opportunity", "stage", "value", "close_date", "owner", "next_step"])
    svc = read_csv(a.services, ["service", "status_at_account"])
    for i, s in enumerate(stk, 1):
        w = f"stakeholders row {i}"
        s["stance_i"] = int_in(s, "stance", -2, 2, w)
        s["infl_i"] = int_in(s, "influence", 1, 5, w)
        s["last"] = date_or_none(s["last_contact"], w)
        s["risk"] = truthy(s["departure_risk"])
        s["stale"] = bool(as_of and (s["last"] is None or (as_of - s["last"]).days > STALE_DAYS))
    for i, p in enumerate(pipe, 1):
        p["value_f"] = money(p["value"], f"pipeline row {i}")
    for i, s in enumerate(svc, 1):
        if s["status_at_account"].lower() not in STATUSES:
            die(f"services row {i}: status_at_account must be one of {STATUSES}, got {s['status_at_account']!r}")
        s["status"] = s["status_at_account"].lower()

    plays = []
    for s in svc:
        if s["status"] == "none":
            plays.append({"play": f"Open white space: {s['service']}", "addresses": f"white-space cell {s['service']} (none)",
                          "type": "white-space"})
    for s in stk:
        if s["stance_i"] <= 0 and s["infl_i"] >= 4:
            plays.append({"play": f"Move {s['name']} ({s['role']}) from stance {s['stance_i']} to +1",
                          "addresses": f"stakeholder {s['name']}: influence {s['infl_i']}, stance {s['stance_i']}", "type": "stakeholder"})
        if s["risk"]:
            plays.append({"play": f"Cover departure risk: {s['name']} ({s['role']})",
                          "addresses": f"departure risk on {s['name']}", "type": "risk"})
        elif s["stale"]:
            plays.append({"play": f"Re-establish contact with {s['name']} ({s['role']})",
                          "addresses": f"no contact in {STALE_DAYS} days (last: {s['last_contact'] or 'never'})", "type": "coverage"})
    if not plays:
        plays.append({"play": "Confirm posture, target and coverage with the account team",
                      "addresses": "no gap triggered by the inputs; validate the inputs are complete", "type": "posture"})
    for i, p in enumerate(plays, 1):
        p.update({"play_id": f"P{i}", "owner": TBD, "date": TBD, "success_measure": TBD})

    known = [p for p in pipe if p["value_f"] is not None]
    total = sum(p["value_f"] for p in known)
    L = [f"# Account Plan — {a.client} — 90-day plan" + (f" (as of {as_of})" if as_of else ""), "",
         "**INTERNAL.** Sources: stakeholders.csv, pipeline.csv, services.csv as supplied; nothing else.", "",
         "## Bottom line",
         f"{len(stk)} stakeholders ({sum(1 for s in stk if s['stance_i'] <= 0 and s['infl_i'] >= 4)} influential and not yet supportive, "
         f"{sum(1 for s in stk if s['risk'])} at departure risk) · pipeline {fmt(total)}"
         + (f" across {len(known)} of {len(pipe)} opportunities ({len(pipe) - len(known)} unvalued)" if len(known) != len(pipe) else f" across {len(pipe)} opportunities")
         + f" · {sum(1 for s in svc if s['status'] == 'none')} white-space cells · {len(plays)} plays. Posture: {TBD}.", "",
         "## Stakeholder map (influence × stance)", "| Influence \\ Stance | −2 blocker | −1 sceptic | 0 neutral | +1 supporter | +2 champion |",
         "|---|---|---|---|---|---|"]
    for infl in (5, 4, 3, 2, 1):
        cells = []
        for st in (-2, -1, 0, 1, 2):
            names = [s["name"] + (" ⚠" if s["risk"] else "") for s in stk if s["infl_i"] == infl and s["stance_i"] == st]
            cells.append(", ".join(names) or "—")
        L.append(f"| {infl} | " + " | ".join(cells) + " |")
    L += ["", "⚠ = departure risk flagged", "", "| Name | Role | Stance | Influence | Last contact | Departure risk | Coverage |", "|---|---|---|---|---|---|---|"]
    L += [f"| {s['name']} | {s['role']} | {s['stance_i']} | {s['infl_i']} | {s['last_contact'] or TBD} | "
          f"{'yes' if s['risk'] else 'no'} | {'stale' if s['stale'] else ('n/a' if not as_of else 'ok')} |" for s in stk]
    L += ["", "## White-space matrix", "| Service | Status at account | Play |", "|---|---|---|"]
    for s in svc:
        play = next((p["play_id"] for p in plays if p["type"] == "white-space" and s["service"] in p["play"]), "—")
        L.append(f"| {s['service']} | {s['status']} | {play} |")
    L += ["", "## Pipeline", "| Opportunity | Stage | Value | Close date | Owner | Next step |", "|---|---|---|---|---|---|"]
    L += [f"| {p['opportunity']} | {p['stage'] or TBD} | {fmt(p['value_f'])} | {p['close_date'] or TBD} | {p['owner'] or TBD} | {p['next_step'] or TBD} |"
          for p in pipe]
    L.append(f"| **Total** | | {fmt(total)}" + (f" (excludes {len(pipe) - len(known)} unvalued)" if len(known) != len(pipe) else "") + " | | | |")
    L += ["", "## Risks to the account", "| Risk | Early signal | Mitigation (play) | Owner |", "|---|---|---|---|"]
    L += [f"| Departure of {s['name']} ({s['role']}) | departure_risk flagged | {next((p['play_id'] for p in plays if p['type'] == 'risk' and s['name'] in p['play']), '—')} | {TBD} |"
          for s in stk if s["risk"]]
    L += [f"| Coverage gap: {s['name']} | no contact in {STALE_DAYS} days | {next((p['play_id'] for p in plays if p['type'] == 'coverage' and s['name'] in p['play']), '—')} | {TBD} |"
          for s in stk if s["stale"] and not s["risk"]]
    if L[-1].startswith("|---"):
        L.append("| none identified from inputs | | | |")
    L += ["", "## 90-day plays", "| # | Play | Addresses | Owner | Date | Success measure |", "|---|---|---|---|---|---|"]
    L += [f"| {p['play_id']} | {p['play']} | {p['addresses']} | {p['owner']} | {p['date']} | {p['success_measure']} |" for p in plays] \
        or ["| — | no play triggered by the inputs | | | | |"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    with Path(a.plays).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["play_id", "play", "type", "addresses", "owner", "date", "success_measure"])
        w.writeheader(); w.writerows(plays)
    print(f"account plan: {len(stk)} stakeholders, {len(pipe)} opportunities, {len(plays)} plays -> {a.out}, {a.plays}")
    return 0


if __name__ == "__main__":
    main()
