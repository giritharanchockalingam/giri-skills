#!/usr/bin/env python3
"""Deterministic guardrail engine: apply a compiled guardrails.json to one text (input or output).

Importable (stdlib only, no network, no model calls):

    from guard import load_rules, evaluate, redact
    rules = load_rules("guardrails.json")
    res = evaluate(rules, text, direction="in", tool=None)
    # -> {"decision": "allow"|"mask"|"block", "reasons": [rule ids], "output_text": str, "pii_found": {...}}

Decision order: any block rule (length, prompt-injection marker, blocked topic, tool not on the
allowlist, PII with action block) -> "block" with output_text ""; else any PII with action mask ->
"mask" with each match replaced by its token (e.g. [EMAIL]); else "allow" (text unchanged).
Reasons carry rule ids only, never the matched text, so logs do not echo raw PII.

CLI:
  python3 -I guard.py --rules guardrails.json --direction in --text "..." [--tool NAME]
  python3 -I guard.py --rules guardrails.json --direction out --text-file reply.txt
  python3 -I guard.py --rules guardrails.json --validate     # load + compile every rule
  python3 -I guard.py --scan-pii report.json                 # exit 1 if any raw PII is present

Exit codes: 0 allow/mask (or validate/scan clean) · 1 block (or raw PII found by --scan-pii) ·
2 unusable input (rules file, arguments).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

SCHEMA = "giri-skills/guardrails@1"

# Built-in PII detectors. The compiler copies these into guardrails.json; the engine runs the
# patterns from the rules file. Order matters: earlier detectors claim overlapping spans.
PII_DETECTORS = [
    {"pii_type": "card", "mask": "[CARD]", "validator": "luhn",
     "pattern": r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])"},
    {"pii_type": "ssn", "mask": "[SSN]", "validator": None,
     "pattern": r"(?<![\w-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\w-])"},
    {"pii_type": "email", "mask": "[EMAIL]", "validator": None,
     "pattern": r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w])"},
    {"pii_type": "phone", "mask": "[PHONE]", "validator": None,
     "pattern": r"(?<![\w+])(?:\+\d{1,3}(?:[ .-]\d{2,4}){2,4}"
                r"|(?:\+1[ .-]?)?(?:\(\d{3}\) ?|\d{3}[ .-])\d{3}[ .-]\d{4})(?![\w])"},
]
PII_TYPES = [d["pii_type"] for d in PII_DETECTORS]
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)


class RulesError(Exception):
    """The rules file is missing or malformed (exit 2)."""


def luhn_ok(digits: str) -> bool:
    """Luhn checksum over a digit string of length 13..19."""
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


VALIDATORS = {"luhn": lambda s: luhn_ok(re.sub(r"\D", "", s))}


def normalise(text: str) -> str:
    """Text used for keyword/injection matching: NFKC, zero-width removed, whitespace collapsed."""
    t = unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH)
    return re.sub(r"\s+", " ", t)


def phrase_pattern(phrase: str) -> str:
    """Case-insensitive whole-phrase regex; inner whitespace matches any whitespace run."""
    words = [re.escape(w) for w in phrase.split()]
    if not words:
        raise ValueError("empty phrase")
    body = r"\s+".join(words)
    lead = r"(?<!\w)" if re.match(r"\w", phrase.strip()) else ""
    tail = r"(?!\w)" if re.search(r"\w$", phrase.strip()) else ""
    return f"(?i){lead}{body}{tail}"


def _compile(rules: dict) -> dict:
    """Attach compiled regexes (under '_re') to every pattern rule; raise RulesError if invalid."""
    if rules.get("schema") != SCHEMA:
        raise RulesError(f"not a guardrails rule set (schema {rules.get('schema')!r}, expected {SCHEMA!r})")
    for key in ("limits", "rules", "tools"):
        if key not in rules:
            raise RulesError(f"rules file lacks '{key}'")
    for r in rules["rules"]:
        if "pattern" in r:
            try:
                r["_re"] = re.compile(r["pattern"])
            except re.error as e:
                raise RulesError(f"rule {r.get('id')}: bad pattern: {e}") from e
        if r.get("validator") and r["validator"] not in VALIDATORS:
            raise RulesError(f"rule {r.get('id')}: unknown validator {r['validator']!r}")
    return rules


def load_rules(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise RulesError(f"rules file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RulesError(f"rules file is not JSON: {e}") from e
    return _compile(data)


def rules_from_dict(data: dict) -> dict:
    """Compile an in-memory rule set (as written by build_guardrails.py)."""
    return _compile(json.loads(json.dumps(data)))


def pii_spans(rules_or_detectors, text: str) -> list[dict]:
    """Non-overlapping PII matches [{start,end,pii_type,mask,action,id}] in detector order."""
    dets = rules_or_detectors
    if isinstance(rules_or_detectors, dict):
        dets = [r for r in rules_or_detectors["rules"] if r.get("kind") == "pii"]
    spans: list[dict] = []
    for d in dets:
        rx = d.get("_re") or re.compile(d["pattern"])
        val = VALIDATORS.get(d.get("validator") or "")
        for m in rx.finditer(text):
            if val and not val(m.group(0)):
                continue
            s, e = m.span()
            if any(s < x["end"] and e > x["start"] for x in spans):
                continue
            spans.append({"start": s, "end": e, "pii_type": d["pii_type"], "mask": d["mask"],
                          "action": d.get("action", "mask"), "id": d.get("id", f"PII-{d['pii_type'].upper()}")})
    return sorted(spans, key=lambda x: x["start"])


def _apply_masks(text: str, spans: list[dict]) -> str:
    out, pos = [], 0
    for s in spans:
        out.append(text[pos:s["start"]])
        out.append(s["mask"])
        pos = s["end"]
    out.append(text[pos:])
    return "".join(out)


def redact(rules_or_detectors, text: str) -> str:
    """Mask every detected PII span regardless of policy action (for reports and logs)."""
    return _apply_masks(text, pii_spans(rules_or_detectors, text))


def evaluate(rules: dict, text: str, direction: str = "in", tool: str | None = None) -> dict:
    if direction not in ("in", "out"):
        raise ValueError(f"direction must be 'in' or 'out', got {direction!r}")
    text = text or ""
    blocks: list[str] = []
    norm = normalise(text)
    lim = rules["limits"].get(direction, {}).get("max_chars")
    if lim is not None and len(text) > lim:
        blocks.append(f"LEN-{direction.upper()}")
    for r in rules["rules"]:
        if r.get("kind") in ("injection", "blocked_topic") and direction in r.get("directions", ["in", "out"]):
            if r["_re"].search(norm):
                blocks.append(r["id"])
    if tool:
        allowed = rules["tools"].get("allowed", [])
        if tool not in allowed:
            blocks.append("TOOL-DENY")
    spans = [s for s in pii_spans(rules, text)]
    pii_found: dict[str, int] = {}
    for s in spans:
        pii_found[s["pii_type"]] = pii_found.get(s["pii_type"], 0) + 1
    pii_block = sorted({s["id"] for s in spans if s["action"] == "block"})
    masks = [s for s in spans if s["action"] == "mask"]
    reasons = blocks + pii_block
    if reasons:
        decision, output = "block", ""
    elif masks:
        decision, output = "mask", _apply_masks(text, masks)
        reasons = sorted({s["id"] for s in masks})
    else:
        decision, output = "allow", text
        reasons = sorted({f"{s['id']}:allowed" for s in spans})
    return {"decision": decision, "reasons": reasons, "output_text": output, "pii_found": pii_found}


def scan_pii(text: str) -> dict[str, int]:
    """Counts of raw PII found by the built-in detectors (values never returned)."""
    counts: dict[str, int] = {}
    for s in pii_spans(PII_DETECTORS, text):
        counts[s["pii_type"]] = counts.get(s["pii_type"], 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", help="compiled guardrails.json")
    ap.add_argument("--direction", choices=["in", "out"], default="in")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--text")
    g.add_argument("--text-file")
    ap.add_argument("--tool", help="tool the model wants to call (checked against the allowlist)")
    ap.add_argument("--validate", action="store_true", help="load and compile the rules, then exit")
    ap.add_argument("--scan-pii", metavar="FILE", help="exit 1 if FILE contains raw PII (counts only)")
    a = ap.parse_args(argv)
    if a.scan_pii:
        p = Path(a.scan_pii)
        if not p.is_file():
            print(f"error: file not found: {p}", file=sys.stderr)
            return 2
        counts = scan_pii(p.read_text(encoding="utf-8", errors="replace"))
        print(json.dumps({"file": p.name, "raw_pii": counts}))
        return 1 if counts else 0
    if not a.rules:
        ap.error("--rules is required (or use --scan-pii)")
    try:
        rules = load_rules(a.rules)
    except RulesError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.validate:
        n = len(rules["rules"])
        print(json.dumps({"valid": True, "rules": n, "allowed_tools": rules["tools"].get("allowed", [])}))
        return 0
    if a.text is None and a.text_file is None and not a.tool:
        ap.error("give --text, --text-file or --tool")
    text = a.text or ""
    if a.text_file:
        tp = Path(a.text_file)
        if not tp.is_file():
            print(f"error: file not found: {tp}", file=sys.stderr)
            return 2
        text = tp.read_text(encoding="utf-8")
    res = evaluate(rules, text, a.direction, a.tool)
    print(json.dumps(res, indent=2))
    return 1 if res["decision"] == "block" else 0


if __name__ == "__main__":
    sys.exit(main())
