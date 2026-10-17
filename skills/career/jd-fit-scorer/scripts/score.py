#!/usr/bin/env python3
"""Offline JD fit scorer (stdlib only).

Reads a job-description text file and a profile keyword file, buckets JD
requirement lines (must-have / nice-to-have / culture), matches them against
profile keywords by token overlap, applies red-flag penalties, and prints a
fit table plus a go/no-go verdict.

Usage:
    python3 score.py --jd jd.txt --profile profile-keywords.txt [--threshold 0.5] [--json]

Profile file format: one skill per line; optional "| YEAR"; "#" comments;
"!key: value" hard constraints (location, travel_max, comp_floor, clearance).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WEIGHTS = {"must": 60, "nice": 25, "culture": 15}
MUST_HINTS = ("required", "must", "minimum", "years of", "degree", "certif", "clearance", "essential")
NICE_HINTS = ("preferred", "plus", "ideally", "bonus", "nice to have", "familiarity", "desirable")
CULTURE_HINTS = ("location", "remote", "hybrid", "onsite", "on-site", "travel", "reports to", "salary", "compensation", "pay range", "team of", "relocat")
STOP = {"and", "or", "the", "a", "an", "of", "in", "with", "to", "for", "on", "at", "by", "is", "are", "as", "be", "experience", "strong", "ability", "skills", "knowledge", "years", "year", "working"}

RED_FLAGS = [
    ("R2 hands-on contradiction", 8, r"hands-on coding|player[- ]coach|write production code"),
    ("R6 perpetual urgency", 5, r"fast-paced|thrive under pressure|hit the ground running|24/7"),
    ("R10 contract disguised as FTE", 6, r"contract-to-hire|contract to hire|\b1099\b|6-month engagement"),
    ("R9 active clearance required", 100, r"active (ts|top secret|ts/sci|secret) clearance|must currently hold"),
    ("R5 vague scope", 5, r"wear many hats|jack of all trades"),
]


def tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9\+\#\.]+", s.lower()) if t not in STOP and len(t) > 1}


def load_profile(path: Path) -> tuple[list[tuple[str, set[str]]], dict[str, str]]:
    skills, constraints = [], {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            k, _, v = line[1:].partition(":")
            constraints[k.strip().lower()] = v.strip()
            continue
        text = line.split("|")[0].strip()
        skills.append((text, tokens(text)))
    return skills, constraints


def bucket(line: str) -> str:
    low = line.lower()
    if any(h in low for h in CULTURE_HINTS):
        return "culture"
    if any(h in low for h in MUST_HINTS):
        return "must"  # explicit "required/must" wins even if "preferred" also appears
    if any(h in low for h in NICE_HINTS):
        return "nice"
    return "must"  # unlabeled requirement lines default to must-have (conservative)


def requirement_lines(jd: str) -> list[str]:
    out = []
    for raw in jd.splitlines():
        line = raw.strip(" \t-•*·")
        if len(line) < 12 or line.endswith(":"):
            continue
        if not out and len(line.split()) <= 6 and not re.search(r"[.;]", line):
            continue  # title line
        out.append(line)
    return out


def match_culture(req: str, constraints: dict[str, str]) -> tuple[str, float, str]:
    low = req.lower()
    if "remote" in low and "remote" in constraints.get("location", "").lower():
        return "MATCH", 1.0, "constraint: location allows remote"
    if any(h in low for h in ("location", "onsite", "on-site", "hybrid")) and constraints.get("location"):
        for city in constraints["location"].split(","):
            c = city.strip().lower()
            if c and c != "remote" and c in low:
                return "MATCH", 1.0, f"constraint: location includes {city.strip()}"
        return "GAP", 0.0, "location not in constraint list"
    m = re.search(r"travel[^0-9]{0,20}(\d{1,3})\s*%", low)
    if m and constraints.get("travel_max"):
        try:
            t, mx = int(m.group(1)), int(constraints["travel_max"])
        except ValueError:
            return "PARTIAL", 0.5, "review manually"
        if t <= mx:
            return "MATCH", 1.0, f"constraint: travel {t}% <= max {mx}%"
        if t <= mx + 10:
            return "PARTIAL", 0.5, f"constraint: travel {t}% within max+10"
        return "GAP", 0.0, f"constraint: travel {t}% > max {mx}%"
    return "PARTIAL", 0.5, "review manually (reporting line / team / comp)"


def match(req: str, skills: list[tuple[str, set[str]]], threshold: float) -> tuple[str, float, str]:
    rt = tokens(req)
    if not rt:
        return "GAP", 0.0, ""
    best, best_skill = 0.0, ""
    for text, st in skills:
        if not st:
            continue
        overlap = len(rt & st) / len(st)
        if overlap > best:
            best, best_skill = overlap, text
    if best >= 1.0:
        return "MATCH", 1.0, best_skill
    if best >= threshold:
        return "PARTIAL", 0.5, best_skill
    return "GAP", 0.0, ""


def score(jd_text: str, skills, constraints, threshold: float) -> dict:
    rows = []
    for req in requirement_lines(jd_text):
        b = bucket(req)
        if b == "culture":
            status, credit, evidence = match_culture(req, constraints)
        else:
            status, credit, evidence = match(req, skills, threshold)
        rows.append({"requirement": req[:90], "bucket": b, "status": status, "credit": credit, "evidence": evidence})

    buckets = {}
    active_weight = sum(WEIGHTS[b] for b in WEIGHTS if any(r["bucket"] == b for r in rows)) or 1
    for b, w in WEIGHTS.items():
        items = [r for r in rows if r["bucket"] == b]
        if not items:
            buckets[b] = {"weight": 0, "items": 0, "score": 0.0, "coverage": 0.0}
            continue
        eff_w = w * 100 / active_weight
        cov = sum(r["credit"] for r in items) / len(items)
        buckets[b] = {"weight": round(eff_w, 1), "items": len(items), "score": round(eff_w * cov, 1), "coverage": round(cov, 2)}

    flags, penalty, hard_no = [], 0, False
    low = jd_text.lower()
    for name, pen, pattern in RED_FLAGS:
        if re.search(pattern, low):
            if pen >= 100 and constraints.get("clearance", "none").lower() in ("", "none"):
                hard_no = True
            flags.append({"flag": name, "penalty": pen})
            penalty += pen

    travel = re.search(r"travel[^0-9]{0,20}(\d{1,3})\s*%", low)
    if travel and constraints.get("travel_max"):
        try:
            if int(travel.group(1)) > int(constraints["travel_max"]) + 15:
                hard_no = True
                flags.append({"flag": "R8 travel above max+15", "penalty": 8})
                penalty += 8
        except ValueError:
            pass

    total = max(0.0, min(100.0, sum(b["score"] for b in buckets.values()) - penalty))
    must_cov = buckets["must"]["coverage"]
    if hard_no:
        verdict = "NO-GO (hard constraint)"
    elif total >= 80 and must_cov >= 0.75:
        verdict = "GO"
    elif total >= 65 and must_cov >= 0.60:
        verdict = "LEAN GO"
    elif total >= 50 and must_cov >= 0.50:
        verdict = "LEAN NO"
    else:
        verdict = "NO-GO"
    return {"verdict": verdict, "total": round(total, 1), "buckets": buckets, "red_flags": flags, "penalty": penalty, "rows": rows}


def render(result: dict) -> str:
    out = [f"{result['verdict']} — {result['total']}/100 (penalties −{result['penalty']})", ""]
    out.append("| Bucket | Weight | Items | Coverage | Score |")
    out.append("|---|---|---|---|---|")
    for b, v in result["buckets"].items():
        out.append(f"| {b} | {v['weight']} | {v['items']} | {v['coverage']} | {v['score']} |")
    out += ["", "| Requirement | Bucket | Status | Evidence |", "|---|---|---|---|"]
    for r in result["rows"]:
        out.append(f"| {r['requirement']} | {r['bucket']} | {r['status']} | {r['evidence']} |")
    if result["red_flags"]:
        out += ["", "| Red flag | Penalty |", "|---|---|"]
        out += [f"| {f['flag']} | −{f['penalty']} |" for f in result["red_flags"]]
    out += ["", "Note: script pass is keyword-based. Review PARTIAL/GAP rows with judgement before the final verdict."]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jd", required=True, type=Path, help="JD text file")
    ap.add_argument("--profile", required=True, type=Path, help="profile keyword file")
    ap.add_argument("--threshold", type=float, default=0.5, help="token overlap for PARTIAL (default 0.5)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    a = ap.parse_args()
    for p in (a.jd, a.profile):
        if not p.exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            return 2
    skills, constraints = load_profile(a.profile)
    result = score(a.jd.read_text(encoding="utf-8"), skills, constraints, a.threshold)
    print(json.dumps(result, indent=2) if a.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
