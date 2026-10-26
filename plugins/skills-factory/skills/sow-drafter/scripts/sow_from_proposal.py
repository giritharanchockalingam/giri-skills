#!/usr/bin/env python3
"""Draft a Statement of Work from an approved proposal.

    python3 -I scripts/sow_from_proposal.py proposal.md --template assets/sow-template.md \
        --out SOW.md --deliverables deliverables.csv --assumptions-check assumptions-check.csv

Reads from proposal.md (Markdown produced by proposal-writer or on its section library):
  * "Scope and deliverables" table rows  -> deliverables (D-nn) and in-scope statements (S-nn)
  * "Out of scope" line                   -> out-of-scope statements (O-nn)
  * "Assumption register" table rows      -> SOW assumptions (A-nn), every one carried over
  * "Timeline" milestone rows             -> milestones (M-nn)
  * "Team" role rows                      -> team table
  * H1 "<Client> — <Initiative> — Proposal" -> SOW header
Writes SOW.md on the template (scope in/out, deliverables with acceptance criteria, assumptions,
RACI stub, the template's change-control clause verbatim), deliverables.csv (id, deliverable,
acceptance, phase, format) and assumptions-check.csv listing proposal assumptions NOT carried
over (header only when the SOW is complete). Any missing acceptance criterion, date or amount is
`[TO BE BASELINED — owner: Delivery lead]`; nothing is invented. Exit 1 when proposal.md is missing or has
no scope/deliverables table. Stdlib only, offline.

Existing SOW (--existing-sow SOW-v2.md --reconcile reconciliation.md): a SOW draft already in play (the
client's paper or an earlier version) is reconciled against the approved proposal — every proposal
deliverable is found in it or listed missing, acceptance criteria that are absent or subjective
("reasonable satisfaction", "to be agreed", "best efforts") are flagged, deliverable ids the proposal
does not have are flagged as scope added, proposal assumptions it does not carry are listed, and the
change-control, acceptance and assumptions clauses are checked for presence. SOW.md is still drafted
from the proposal, so the two can be compared side by side.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

TBD = "[TO BE BASELINED — owner: Delivery lead]"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


def section(md: str, heading: str) -> list[str]:
    lines, out, level = md.splitlines(), [], None
    for ln in lines:
        if ln.startswith("#"):
            lvl = len(ln) - len(ln.lstrip("#"))
            if level is None:
                if heading.lower() in ln.lower():
                    level = lvl
                continue
            if lvl <= level:
                break
        elif level is not None:
            out.append(ln)
    return out


def cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def table_after(lines: list[str], header_startswith: str) -> list[list[str]]:
    """Data rows of the first table whose header line starts with the given text."""
    rows, inside = [], False
    for ln in lines:
        if not inside:
            if ln.startswith(header_startswith):
                inside = True
            continue
        if not ln.startswith("|"):
            break
        body = ln.replace("|", "").strip()
        if set(body) <= set("-: "):
            continue
        c = cells(ln)
        if any(c):
            rows.append(c)
    return rows


def val(c: list[str], i: int) -> str:
    v = c[i].strip("`").strip() if i < len(c) else ""
    return v if v and not v.startswith("[TO BE BASELINED") else ""


SUBJECTIVE = re.compile(r"reasonable satisfaction|to be agreed|\btbd\b|best efforts|as required|sole discretion", re.I)
CLAUSES = [("Change control", r"change control|change request"), ("Acceptance", r"acceptance"),
           ("Assumptions", r"assumption")]


def reconcile(existing: str, deliverables: list[dict], assumptions: list[dict], name: str) -> tuple[list[str], int]:
    """Reconciliation of an existing SOW against the proposal; returns (lines, number of issues)."""
    rows: dict[str, str] = {}          # deliverable id -> acceptance cell, from tables with a Deliverable column
    header: list[str] | None = None
    for ln in existing.splitlines():
        if not ln.startswith("|"):
            header = None
            continue
        c = cells(ln)
        if header is None:
            header = [h.lower() for h in c]
            continue
        if set("".join(c)) <= set("-: "):
            continue
        if any("deliverable" in h for h in header) and c and re.fullmatch(r"D-\d+", c[0].strip("` ")):
            acc_i = next((i for i, h in enumerate(header) if "acceptance" in h), None)
            rows.setdefault(c[0].strip("` "), c[acc_i] if acc_i is not None and acc_i < len(c) else "")
    issues = 0
    L = [f"# SOW reconciliation — {name} vs the approved proposal", "", "## Deliverables",
         "| ID | Proposal deliverable | In this SOW | Acceptance in this SOW | Finding |", "|---|---|---|---|---|"]
    for d in deliverables:
        c = rows.get(d["id"])
        if c is None:
            issues += 1
            L.append(f"| {d['id']} | {d['deliverable']} | no | — | missing — add it with the proposal's acceptance: {d['acceptance']} |")
            continue
        acc = "" if c.startswith("[TO BE BASELINED") else c
        if not acc:
            issues += 1
            finding = f"no acceptance criterion — use the proposal's: {d['acceptance']}"
        elif SUBJECTIVE.search(acc):
            issues += 1
            finding = f"subjective acceptance — replace with the proposal's: {d['acceptance']}"
        else:
            finding = "ok"
        L.append(f"| {d['id']} | {d['deliverable']} | yes | {acc or '—'} | {finding} |")
    extra = [k for k in rows if k not in {d['id'] for d in deliverables}]
    for k in extra:
        issues += 1
        L.append(f"| {k} | — | yes | {rows[k] or '—'} | scope added: not in the approved proposal — "
                 f"change request or remove ({TBD}) |")
    L += ["", "## Assumptions", "| ID | Proposal assumption | In this SOW |", "|---|---|---|"]
    for s_ in assumptions:
        hit = s_["assumption"] in existing
        issues += not hit
        L.append(f"| {s_['id']} | {s_['assumption']} | {'yes' if hit else 'no — carry it over'} |")
    if not assumptions:
        L.append("| — | the proposal carries no assumption register | — |")
    L += ["", "## Clauses", "| Clause | Present |", "|---|---|"]
    heads = "\n".join(ln for ln in existing.splitlines() if ln.startswith("#"))
    for label, rx in CLAUSES:
        ok = re.search(rx, heads, re.I) is not None
        issues += not ok
        L.append(f"| {label} | {'yes' if ok else 'no — add the section from assets/sow-template.md'} |")
    L.insert(2, f"**{issues} issue(s) to resolve before signature.**\n")
    return L, issues


def marker_or(v: str) -> str:
    return v or TBD


def main() -> int:
    ap = argparse.ArgumentParser(description="proposal.md -> SOW.md + deliverables.csv + assumptions-check.csv")
    ap.add_argument("proposal")
    ap.add_argument("--template", required=True, help="assets/sow-template.md")
    ap.add_argument("--out", required=True, help="SOW.md")
    ap.add_argument("--deliverables", required=True, help="deliverables.csv")
    ap.add_argument("--assumptions-check", required=True, help="assumptions-check.csv")
    ap.add_argument("--existing-sow", default="", help="a SOW draft already in play, to reconcile with the proposal")
    ap.add_argument("--reconcile", default="", help="with --existing-sow: write the reconciliation here")
    a = ap.parse_args()

    prop, tmpl = read(a.proposal), read(a.template)
    m = re.search(r"^# (.+?) — (.+?) — Proposal\s*$", prop, re.M)
    client, initiative = (m.group(1), m.group(2)) if m else (TBD, TBD)

    scope = section(prop, "Scope and deliverables")
    drows = table_after(scope, "| ID | Deliverable |")
    if not drows:
        die("proposal has no 'Scope and deliverables' table with rows (header '| ID | Deliverable |')")
    deliverables = []
    for i, c in enumerate(drows, 1):
        deliverables.append({"id": val(c, 0) or f"D-{i:02d}", "deliverable": marker_or(val(c, 1)),
                             "description": marker_or(val(c, 2)), "acceptance": marker_or(val(c, 3)),
                             "phase": marker_or(val(c, 4)), "format": marker_or(val(c, 5))})
    out_of_scope = []
    for ln in scope:
        if ln.lower().startswith("out of scope"):
            body = ln.split(":", 1)[1] if ":" in ln else ""
            out_of_scope = [s.strip(" .") for s in re.split(r";|\n|(?<=[a-z0-9\)])\.\s", body) if s.strip(" .")]
            if body.strip().startswith("[TO BE BASELINED"):
                out_of_scope = []
    arows = table_after(section(prop, "Risks and assumptions"), "| ID | Assumption |")
    assumptions = [{"id": val(c, 0) or f"A-{i:02d}", "assumption": marker_or(val(c, 1)), "basis": marker_or(val(c, 2)),
                    "if_false": marker_or(val(c, 3)), "cc": val(c, 4) or "Y", "confirm_by": marker_or(val(c, 5))}
                   for i, c in enumerate(arows, 1)]
    mrows = table_after(section(prop, "Timeline"), "| Milestone |")
    milestones = [{"id": f"M{i}", "name": marker_or(val(c, 0)), "when": marker_or(val(c, 1)),
                   "dep": marker_or(val(c, 2))} for i, c in enumerate(mrows, 1)]
    trows = table_after(section(prop, "Team and governance"), "| Role |")
    team = [{"role": marker_or(val(c, 0)), "resp": marker_or(val(c, 1)), "alloc": marker_or(val(c, 2)),
             "loc": marker_or(val(c, 3)), "named": val(c, 4) or "—"} for c in trows]

    exec_lines = [ln for ln in section(prop, "Executive summary") if ln.strip() and not ln.startswith("|")]
    background = exec_lines[0] if exec_lines else TBD
    for n, d in enumerate(deliverables, 1):
        d["milestone"] = milestones[min(n, len(milestones)) - 1]["id"] if milestones else "M1"

    # ---- build the SOW on the template: keep every template section, fill the tables we own
    L = (tmpl.replace("<Client>", client).replace("<Initiative>", initiative)
         .replace("| Client | <legal entity> |", f"| Client | {client} (legal entity {TBD}) |")
         .replace("<Two to four sentences from the approved proposal: situation and objective. No marketing language.>",
                  f"From the approved proposal: {background}")).splitlines()
    out = []
    i = 0
    while i < len(L):
        ln = L[i]
        if ln.startswith("| S-01 |"):
            for n, d in enumerate(deliverables, 1):
                out.append(f"| S-{n:02d} | Deliver {d['deliverable']} ({d['phase']}) | Appendix D |")
            i += 1; continue
        if ln.startswith("| O-01 |"):
            if out_of_scope:
                for n, s in enumerate(out_of_scope, 1):
                    out.append(f"| O-{n:02d} | {s} | S-{min(n, len(deliverables)):02d} |")
            else:
                out.append(f"| O-01 | {TBD} | S-01 |")
            i += 1; continue
        if ln.startswith("| D-01 | A | R |"):
            for d in deliverables:
                out.append(f"| {d['id']} | A | R | R | I | C | C |")
            i += 1; continue
        if ln.startswith("| D-01 |"):
            for d in deliverables:
                out.append(f"| {d['id']} | {d['deliverable']} | {d['description']} | {d['format']} | "
                           f"{d['acceptance']} | review | 5 | {TBD} | {d['milestone']} |")
            i += 1; continue
        if ln.startswith("| M1 |"):
            if milestones:
                for ms in milestones:
                    dels = ", ".join(d["id"] for d in deliverables if d["milestone"] == ms["id"]) or "—"
                    out.append(f"| {ms['id']} | {ms['name']} | {ms['when']} | {dels} | {ms['dep']} |")
            else:
                out.append(f"| M1 | {TBD} | {TBD} | {', '.join(d['id'] for d in deliverables)} | DEP-01 |")
            i += 1; continue
        if ln.startswith("| A-01 |"):
            if assumptions:
                for s in assumptions:
                    out.append(f"| {s['id']} | {s['assumption']} | {s['basis']} | {s['if_false']} | {s['cc']} | {s['confirm_by']} |")
            else:
                out.append(f"| A-01 | {TBD} (proposal carries no assumption register) | | | Y | |")
            i += 1; continue
        if ln.startswith("| Role | Responsibilities |") and team:
            out.append(ln); out.append(L[i + 1])
            for t in team:
                out.append(f"| {t['role']} | {t['resp']} | {t['alloc']} | {t['loc']} | {t['named']} |")
            i += 2; continue
        out.append(re.sub(r"<[^<>\n`]{1,200}>", TBD, ln))
        i += 1
    sow = "\n".join(out).rstrip("\n") + "\n"
    sow = sow.replace("| Version | 0.1 — draft |", "| Version | 0.1 — draft (generated from proposal.md) |")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(sow, encoding="utf-8")

    with Path(a.deliverables).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "deliverable", "description", "acceptance", "phase", "format", "milestone"])
        w.writeheader(); w.writerows(deliverables)
    # every proposal assumption must appear in the SOW text; list the ones that do not
    missing = [s for s in assumptions if s["assumption"] not in sow]
    with Path(a.assumptions_check).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "assumption", "status"])
        w.writeheader()
        w.writerows([{"id": s["id"], "assumption": s["assumption"], "status": "NOT IN SOW"} for s in missing])
    if a.existing_sow:
        rec, n_issues = reconcile(read(a.existing_sow), deliverables, assumptions, Path(a.existing_sow).name)
        if a.reconcile:
            Path(a.reconcile).write_text("\n".join(rec) + "\n", encoding="utf-8")
        print(f"reconciliation: {Path(a.existing_sow).name} — {n_issues} issue(s)")
    n_tbd = sum(1 for d in deliverables if d["acceptance"] == TBD)
    print(f"SOW: {len(deliverables)} deliverables ({n_tbd} acceptance criteria to baseline), "
          f"{len(assumptions)} assumptions carried, {len(missing)} not carried, {len(out_of_scope)} out-of-scope -> {a.out}")
    return 0


if __name__ == "__main__":
    main()
