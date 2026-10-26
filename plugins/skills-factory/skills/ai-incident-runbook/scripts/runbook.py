#!/usr/bin/env python3
"""AI incident runbook: incident facts + severity matrix -> classified runbook and incident record.

Classifies severity (SEV1 highest .. SEV4) by evaluating every row of the severity matrix and
taking the most severe row that fires; every fired row is listed as reasoning. Without --matrix
the skill's documented default matrix is used (references/severity-matrix.default.csv; see
references/severity-matrix.md) and the output says so. Assembles the runbook from the bundled
per-category playbook (assets/playbooks/<category>.md: Contain, Eradicate, Recover, Verify), a
timeline skeleton anchored on started_at, a communications checklist (regulator track only when
regulated_data is yes or unknown — unknown escalates), and a postmortem skeleton.
Unknowns stay `[TO BE BASELINED — owner: <role>]`; no time or name is invented.

Usage:
  python3 -I runbook.py --incident incident.csv [--matrix severity-matrix.csv] --out-dir OUT

Incident CSV key,value. Required: category (hallucination|data-leak|prompt-injection|outage|
cost-spike|harmful-output), started_at (ISO 8601). Optional: system_name, summary,
users_affected (integer or unknown), data_exposed (yes|no|unknown), regulated_data
(yes|no|unknown), detected_at, detected_by, owner_incident_commander, owner_engineering_lead,
owner_comms_lead, owner_legal_privacy, owner_security_lead. Missing yes/no fields are unknown.
Matrix CSV: rule_id,conditions,severity,reason. conditions = `always` or `;`-joined clauses
`field=value`, `field!=value`, `field>=n`, `field>n`, `field<=n`, `field<n`, `field in a|b`
(all must hold). Numeric clauses never fire on unknown.

Outputs (in --out-dir): runbook.md (Severity, Immediate actions, Containment, Recovery,
Communications, Postmortem), incident.json.
Exit codes: 0 written · 1 no matrix row fired (matrix lacks a baseline row) or playbook missing ·
2 missing/invalid required input. Stdlib only; no network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = SKILL_DIR / "references" / "severity-matrix.default.csv"
PLAYBOOKS = SKILL_DIR / "assets" / "playbooks"
CATEGORIES = ("hallucination", "data-leak", "prompt-injection", "outage", "cost-spike", "harmful-output")
TRISTATE = ("yes", "no", "unknown")
SEVERITIES = ("SEV1", "SEV2", "SEV3", "SEV4")
ROLES = {  # role key -> (display name, role accountable for naming the person when missing)
    "incident_commander": ("Incident commander", "On-call engineering manager"),
    "engineering_lead": ("Engineering lead", "Incident commander"),
    "comms_lead": ("Comms lead", "Incident commander"),
    "legal_privacy": ("Legal / privacy", "Incident commander"),
    "security_lead": ("Security lead", "Incident commander"),
}
CLAUSE_RE = re.compile(r"^\s*([a-z_]+)\s*(>=|<=|!=|=|>|<| in )\s*(.+?)\s*$")


class InputError(Exception):
    """Missing or invalid required input -> exit 2."""


def tbd(role: str) -> str:
    return f"[TO BE BASELINED — owner: {role}]"


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"input file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO("\n".join(lines)))]


def parse_ts(v: str) -> datetime:
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_incident(path: Path) -> dict:
    rows = read_rows(path)
    if rows and ("key" not in rows[0] or "value" not in rows[0]):
        raise InputError("incident CSV needs columns key,value")
    inc = {r["key"]: r["value"] for r in rows if r.get("key") and r.get("value", "") != ""}
    missing = [k for k in ("category", "started_at") if k not in inc]
    if missing:
        raise InputError(f"incident missing required keys: {', '.join(missing)}")
    inc["category"] = inc["category"].lower()
    if inc["category"] not in CATEGORIES:
        raise InputError(f"category must be one of {CATEGORIES}, got {inc['category']!r}")
    for k in ("data_exposed", "regulated_data"):
        inc[k] = inc.get(k, "unknown").lower()
        if inc[k] not in TRISTATE:
            raise InputError(f"{k} must be yes|no|unknown, got {inc[k]!r}")
    ua = inc.get("users_affected", "unknown").lower()
    if ua != "unknown" and not ua.isdigit():
        raise InputError(f"users_affected must be a whole number or unknown, got {ua!r}")
    inc["users_affected"] = ua
    for k in ("started_at", "detected_at"):
        if k in inc:
            try:
                parse_ts(inc[k])
            except ValueError:
                raise InputError(f"{k} is not an ISO 8601 timestamp: {inc[k]!r}") from None
    return inc


def load_matrix(path: Path) -> list[dict]:
    rows = read_rows(path)
    if not rows:
        raise InputError(f"severity matrix has no rows: {path}")
    for col in ("rule_id", "conditions", "severity", "reason"):
        if col not in rows[0]:
            raise InputError(f"severity matrix needs columns rule_id,conditions,severity,reason (missing {col})")
    for r in rows:
        if r["severity"].upper() not in SEVERITIES:
            raise InputError(f"rule {r['rule_id']}: severity must be one of {SEVERITIES}")
        r["severity"] = r["severity"].upper()
        for clause in split_conditions(r["conditions"]):
            if clause != "always" and not CLAUSE_RE.match(clause):
                raise InputError(f"rule {r['rule_id']}: cannot parse condition {clause!r}")
    return rows


def split_conditions(cond: str) -> list[str]:
    return [c.strip() for c in cond.split(";") if c.strip()]


def clause_holds(clause: str, inc: dict) -> bool:
    if clause == "always":
        return True
    field, op, val = CLAUSE_RE.match(clause).groups()
    op = op.strip()
    actual = str(inc.get(field, "unknown")).lower()
    if op == "in":
        return actual in [v.strip().lower() for v in val.split("|")]
    if op in ("=", "!="):
        return (actual == val.lower()) == (op == "=")
    try:
        a, b = float(actual), float(val)
    except ValueError:
        return False  # numeric clause on unknown/non-numeric never fires
    return {">=": a >= b, ">": a > b, "<=": a <= b, "<": a < b}[op]


def classify(inc: dict, matrix: list[dict]) -> tuple[str | None, list[dict]]:
    fired = [r for r in matrix if all(clause_holds(c, inc) for c in split_conditions(r["conditions"]))]
    fired = [{"rule_id": r["rule_id"], "conditions": r["conditions"], "severity": r["severity"], "reason": r["reason"]}
             for r in fired]
    if not fired:
        return None, []
    return min((r["severity"] for r in fired), key=SEVERITIES.index), fired


def load_playbook(category: str) -> dict[str, list[str]]:
    path = PLAYBOOKS / f"{category}.md"
    if not path.is_file():
        return {}
    sections: dict[str, list[str]] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections[current] = []
        elif current and line.strip().startswith(("- ", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
            sections[current].append(re.sub(r"^\s*(-|\d+\.)\s*", "", line).strip())
        elif current == "references" and line.strip():
            sections[current].append(line.strip())
    return sections


def owners(inc: dict) -> dict[str, str]:
    return {name: inc.get(f"owner_{key}") or tbd(fallback) for key, (name, fallback) in ROLES.items()}


def build(inc: dict, matrix: list[dict], matrix_source: str) -> dict:
    sev, fired = classify(inc, matrix)
    pb = load_playbook(inc["category"])
    own = owners(inc)
    ic = own["Incident commander"]
    started = parse_ts(inc["started_at"])
    timeline = [{"event": "Incident started (impact began)", "time": started.isoformat(), "source": "started_at"}]
    ttd = None
    if inc.get("detected_at"):
        det = parse_ts(inc["detected_at"])
        ttd = round((det - started).total_seconds() / 60.0, 1)
        timeline.append({"event": f"Detected by {inc.get('detected_by', tbd('Incident commander'))}",
                         "time": det.isoformat(), "source": "detected_at"})
    else:
        timeline.append({"event": f"Detected by {inc.get('detected_by', tbd('Incident commander'))}",
                         "time": tbd("Incident commander"), "source": "not supplied"})
    for ev in ("Incident commander assigned and acknowledged", "Containment in place", "Eradication complete",
               "Service recovered", "Verification passed; incident resolved", "Postmortem review held"):
        timeline.append({"event": ev, "time": tbd("Incident commander"), "source": "to record"})

    ua = inc["users_affected"]
    reg = inc["regulated_data"]
    comms = {
        "internal": [f"Open the incident channel and post severity {sev or 'unclassified'} with the fired rules",
                     "Notify the system owner and the engineering on-call"]
                    + (["Notify the executive sponsor (SEV1/SEV2)"] if sev in ("SEV1", "SEV2") else [])
                    + [f"Status updates on the cadence the Incident commander sets: {tbd('Incident commander')}"],
        "customer": ([] if ua == "0" else
                     ["Decide whether affected users/customers are notified; record the decision and who made it",
                      "Draft the customer message (what happened, what data, what we did, what they should do)",
                      f"Approver for customer messages: {own['Comms lead']}"]),
        "regulator": [],
        "regulator_basis": "",
    }
    if reg in ("yes", "unknown"):
        comms["regulator"] = [
            "Legal / privacy confirms which notification obligations apply (e.g. GDPR Article 33, sector or state "
            "breach rules) and their deadlines — the skill does not set them",
            "Preserve evidence: affected records, access logs, traces, prompts and outputs for the window",
            f"Regulator notification owner: {own['Legal / privacy']}",
        ]
        comms["regulator_basis"] = ("regulated_data = yes" if reg == "yes" else
                                    "regulated_data = unknown — unknown escalates: treat as regulated until Legal / privacy rules it out")
    else:
        comms["regulator_basis"] = "regulated_data = no — no regulator track"

    unknowns = [k for k in ("users_affected", "data_exposed", "regulated_data") if inc[k] == "unknown"]
    unknowns += [k for k in ("detected_at", "detected_by", "system_name") if not inc.get(k)]
    return {
        "incident": {k: v for k, v in inc.items() if not k.startswith("owner_")},
        "severity": sev,
        "fired_rules": fired,
        "matrix_source": matrix_source,
        "playbook": {"category": inc["category"], "sections": pb},
        "time_to_detect_min": ttd,
        "timeline": timeline,
        "communications": comms,
        "owners": own,
        "unknowns": unknowns,
        "incident_commander": ic,
    }


def bullets(items: list[str]) -> list[str]:
    return [f"- [ ] {x}" for x in items] if items else ["- (none)"]


def render(rec: dict) -> str:
    inc, own, pb = rec["incident"], rec["owners"], rec["playbook"]["sections"]
    title = inc.get("system_name") or tbd("Incident commander")
    L = [f"# Incident runbook — {title} — {inc['category']}", "",
         f"Summary: {inc.get('summary') or tbd('Incident commander')}", "",
         "## Severity", "",
         f"**{rec['severity']}** — most severe of the rows that fired. Matrix: {rec['matrix_source']}.", "",
         "| Rule | Conditions | Severity | Reason |", "|---|---|---|---|"]
    for r in rec["fired_rules"]:
        L.append(f"| {r['rule_id']} | `{r['conditions']}` | {r['severity']} | {r['reason']} |")
    L += ["", "| Fact | Value |", "|---|---|"]
    for k in ("category", "users_affected", "data_exposed", "regulated_data", "started_at", "detected_at", "detected_by"):
        L.append(f"| {k} | {inc.get(k) or tbd('Incident commander')} |")
    if rec["unknowns"]:
        L += ["", "Unknown now (each resolves to a fact, not a guess): " + ", ".join(rec["unknowns"]) + "."]
    L += ["", "## Immediate actions", "",
          f"- [ ] Incident commander: {own['Incident commander']} — acknowledge and own the timeline",
          f"- [ ] Engineering lead: {own['Engineering lead']} — join and take the playbook below",
          "- [ ] Freeze deploys and prompt/config changes to the affected system except fixes for this incident",
          "- [ ] Preserve evidence: traces, prompts, outputs, retrieval logs and config versions for the window"]
    if rec["severity"] in ("SEV1", "SEV2"):
        L.append(f"- [ ] Security lead: {own['Security lead']} — engaged for {rec['severity']}")
    L += ["", "### Timeline", "", "| Event | Time | Source |", "|---|---|---|"]
    for t in rec["timeline"]:
        L.append(f"| {t['event']} | {t['time']} | {t['source']} |")
    if rec["time_to_detect_min"] is not None:
        L += ["", f"Time to detect (detected_at − started_at): {rec['time_to_detect_min']} minutes."]
    L += ["", "## Containment", "", "### Contain", ""] + bullets(pb.get("contain", []))
    L += ["", "### Eradicate", ""] + bullets(pb.get("eradicate", []))
    L += ["", "## Recovery", "", "### Recover", ""] + bullets(pb.get("recover", []))
    L += ["", "### Verify", ""] + bullets(pb.get("verify", []))
    c = rec["communications"]
    L += ["", "## Communications", "", "### Internal", ""] + bullets(c["internal"])
    L += ["", "### Customer", ""] + (bullets(c["customer"]) if c["customer"] else ["- Not required: users_affected = 0."])
    L += ["", "### Regulator", "", f"Basis: {c['regulator_basis']}.", ""]
    L += bullets(c["regulator"]) if c["regulator"] else ["- Not required."]
    L += ["", "## Postmortem", "",
          "Blameless; held after resolution. Fill from the timeline and evidence, not memory.", "",
          f"| Field | Value |", "|---|---|",
          f"| Owner | {own['Incident commander']} |",
          f"| Review date | {tbd('Incident commander')} |",
          f"| Severity (final) | {rec['severity']} (confirm or revise with evidence) |",
          f"| Impact (users, data, duration) | {tbd('Incident commander')} |",
          f"| Root cause | {tbd('Engineering lead')} |",
          f"| Contributing factors | {tbd('Engineering lead')} |",
          f"| Detection gap (time to detect) | {str(rec['time_to_detect_min']) + ' minutes' if rec['time_to_detect_min'] is not None else tbd('Incident commander')} |",
          "", "### Action items", "", "| Action | Type (prevent/detect/mitigate) | Owner | Due |", "|---|---|---|---|",
          f"| Add a regression eval case for this failure (feedback-improvement-loop / llm-eval-harness) | detect | {tbd('Engineering lead')} | {tbd('Engineering lead')} |",
          f"| Add or tighten the alert that should have fired (llm-observability SLO) | detect | {tbd('Engineering lead')} | {tbd('Engineering lead')} |"]
    if pb.get("references"):
        L += ["", "Playbook references: " + " ".join(pb["references"])]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--incident", type=Path, required=True, help="incident facts CSV (key,value)")
    ap.add_argument("--matrix", type=Path, help="severity matrix CSV; default: the skill's documented default")
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        inc = load_incident(args.incident)
        matrix_path = args.matrix or DEFAULT_MATRIX
        source = (f"supplied ({args.matrix.name})" if args.matrix else
                  "the skill's default matrix (references/severity-matrix.default.csv) — no matrix supplied")
        rec = build(inc, load_matrix(matrix_path), source)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "incident.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out_dir / "runbook.md").write_text(render(rec), encoding="utf-8")
    if rec["severity"] is None:
        print("no severity-matrix row fired; add a baseline row (conditions: always)", file=sys.stderr)
        return 1
    if not rec["playbook"]["sections"]:
        print(f"no playbook for category {inc['category']}", file=sys.stderr)
        return 1
    print(f"runbook written: {rec['severity']} ({len(rec['fired_rules'])} rule(s) fired)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
