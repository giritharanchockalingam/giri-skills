#!/usr/bin/env python3
"""Compile a guardrail policy (JSON) into a deterministic rule set and test it.

Policy keys (all required unless marked optional; keys starting with '_' are comments):
  blocked_topics     list of keywords/phrases blocked in inputs and outputs
  pii_handling       {email|phone|card|ssn: mask|block|allow}; an unlisted type is reported as
                     [TO BE BASELINED — owner: Data protection officer] and left un-actioned (allow)
  max_input_chars    int > 0
  max_output_chars   int > 0
  allowed_tools      list of tool names (everything else is denied)
  injection_markers  optional list of extra prompt-injection phrases (added to the bundled list in
                     assets/injection-phrases.txt)

Outputs in --out:
  guardrails.json        compiled rules for scripts/guard.py (regex/keyword rules, PII detectors with
                         Luhn validation for cards, length limits, tool allowlist, injection markers)
  guardrail-tests.json   per-case expected vs actual decision (texts stored redacted, never raw PII)
  guardrails.md          Rule set, PII handling, Tool allowlist, Test results, Limits

Brownfield (--baseline): pass the guardrails.json that is live today. The run diffs the new rule set
against it (topics, injection markers, PII actions, length limits, tool allowlist; each change marked
tightened or loosened) and, with --tests, replays every case against both rule sets so decision changes
are visible. The diff lands in guardrail-tests.json ("baseline") and guardrails.md ("Changes vs live rules").

Usage:
  python3 -I build_guardrails.py --policy policy.json [--tests cases.csv] [--baseline live-guardrails.json] --out <dir>
Test CSV columns: case_id, direction (in|out), text, expected (allow|block|mask), optional tool.

Exit codes: 0 compiled (and every test case matched) · 1 a test case's actual decision differs from
expected · 2 required input missing or unusable. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402

DEFAULT_INJECTION_LIST = HERE.parent / "assets" / "injection-phrases.txt"
PII_OWNER = "Data protection officer"
TEST_OWNER = "AI security lead"
REQUIRED = ["blocked_topics", "pii_handling", "max_input_chars", "max_output_chars", "allowed_tools"]
OPTIONAL = ["injection_markers"]
ACTIONS = {"mask", "block", "allow"}


class InputError(Exception):
    """A required input is missing or unusable (exit 2)."""


def tbb(owner: str) -> str:
    return f"[TO BE BASELINED — owner: {owner}]"


def _str_list(policy: dict, key: str) -> list[str]:
    v = policy.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise InputError(f"policy '{key}' must be a list of strings")
    out = []
    for x in v:
        x = " ".join(x.split())
        if not x:
            raise InputError(f"policy '{key}' has an empty entry")
        if x.lower() not in (y.lower() for y in out):
            out.append(x)
    return out


def load_policy(path: Path) -> tuple[dict, str]:
    if not path.is_file():
        raise InputError(f"policy file not found: {path}")
    raw = path.read_bytes()
    try:
        policy = json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise InputError(f"policy is not valid JSON: {e}") from e
    if not isinstance(policy, dict):
        raise InputError("policy must be a JSON object")
    missing = [k for k in REQUIRED if k not in policy]
    if missing:
        raise InputError(f"policy lacks required key(s): {missing}")
    unknown = [k for k in policy if k not in REQUIRED + OPTIONAL and not k.startswith("_")]
    if unknown:
        raise InputError(f"policy has unknown key(s) {unknown}; allowed: {REQUIRED + OPTIONAL} (prefix '_' for comments)")
    for k in ("max_input_chars", "max_output_chars"):
        v = policy[k]
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise InputError(f"policy '{k}' must be a positive integer, got {v!r}")
    ph = policy["pii_handling"]
    if not isinstance(ph, dict):
        raise InputError("policy 'pii_handling' must be an object {pii_type: mask|block|allow}")
    for t, act in ph.items():
        if t not in guard.PII_TYPES:
            raise InputError(f"pii_handling: unknown PII type {t!r}; supported: {guard.PII_TYPES}")
        if act not in ACTIONS:
            raise InputError(f"pii_handling.{t}: action must be one of {sorted(ACTIONS)}, got {act!r}")
    return policy, hashlib.sha256(raw).hexdigest()


def load_bundled(path: Path) -> list[str]:
    if not path.is_file():
        raise InputError(f"bundled injection list not found: {path}")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = " ".join(line.split())
        if line and not line.startswith("#"):
            out.append(line)
    return out


def compile_policy(policy: dict, sha: str, bundled: list[str]) -> dict:
    rules = []
    topics = _str_list(policy, "blocked_topics")
    for i, t in enumerate(topics, 1):
        rules.append({"id": f"TOPIC-{i:03d}", "kind": "blocked_topic", "directions": ["in", "out"],
                      "phrase": t, "pattern": guard.phrase_pattern(t), "action": "block"})
    extra = _str_list(policy, "injection_markers")
    seen: set[str] = set()
    n = 0
    for source, phrases in (("bundled", bundled), ("policy", extra)):
        for ph in phrases:
            if ph.lower() in seen:
                continue
            seen.add(ph.lower())
            n += 1
            rules.append({"id": f"INJ-{n:03d}", "kind": "injection", "directions": ["in"], "phrase": ph,
                          "source": source, "pattern": guard.phrase_pattern(ph), "action": "block"})
    unconfigured = []
    for d in guard.PII_DETECTORS:
        act = policy["pii_handling"].get(d["pii_type"])
        if act is None:
            unconfigured.append(d["pii_type"])
        rules.append({"id": f"PII-{d['pii_type'].upper()}", "kind": "pii", "pii_type": d["pii_type"],
                      "directions": ["in", "out"], "pattern": d["pattern"], "validator": d["validator"],
                      "mask": d["mask"], "action": act or "allow", "configured": act is not None})
    return {
        "schema": guard.SCHEMA,
        "policy_sha256": sha,
        "limits": {"in": {"max_chars": policy["max_input_chars"]}, "out": {"max_chars": policy["max_output_chars"]}},
        "tools": {"allowed": _str_list(policy, "allowed_tools"), "default": "deny"},
        "rules": rules,
        "pii_unconfigured": unconfigured,
        "precedence": ["length", "injection (in)", "blocked_topic", "tool allowlist", "pii block",
                       "pii mask", "allow"],
        "owner_markers": {t: tbb(PII_OWNER) for t in unconfigured},
    }


def load_tests(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"test inputs file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in ("case_id", "direction", "text", "expected") if c not in header]
        if missing:
            raise InputError(f"test CSV lacks column(s) {missing}; header is {header}")
        cases, ids = [], set()
        for i, row in enumerate(reader, start=2):
            row = {(k or "").strip(): (v if v is not None else "") for k, v in row.items() if k is not None}
            cid = row.get("case_id", "").strip()
            if not cid or cid.startswith("#"):
                continue
            if cid in ids:
                raise InputError(f"test line {i}: duplicate case_id {cid!r}")
            ids.add(cid)
            d, e = row.get("direction", "").strip().lower(), row.get("expected", "").strip().lower()
            if d not in ("in", "out"):
                raise InputError(f"test line {i}: direction must be in|out, got {d!r}")
            if e not in ("allow", "block", "mask"):
                raise InputError(f"test line {i}: expected must be allow|block|mask, got {e!r}")
            cases.append({"case_id": cid, "direction": d, "text": row.get("text", ""), "expected": e,
                          "tool": row.get("tool", "").strip() or None})
    if not cases:
        raise InputError("test CSV has no cases")
    return cases


def run_tests(rules: dict, cases: list[dict]) -> dict:
    compiled = guard.rules_from_dict(rules)
    results = []
    for c in cases:
        res = guard.evaluate(compiled, c["text"], c["direction"], c["tool"])
        results.append({"case_id": c["case_id"], "direction": c["direction"], "tool": c["tool"],
                        "expected": c["expected"], "actual": res["decision"],
                        "pass": res["decision"] == c["expected"], "reasons": res["reasons"],
                        "pii_found": res["pii_found"], "chars": len(c["text"]),
                        "redacted_text": guard.redact(compiled, res["output_text"] if res["decision"] == "mask"
                                                      else c["text"])})
    passed = sum(r["pass"] for r in results)
    return {"status": "run", "total": len(results), "passed": passed, "failed": len(results) - passed,
            "cases": results}


PII_RANK = {"allow": 0, "mask": 1, "block": 2}


def load_baseline(path: Path) -> dict:
    """The live compiled rule set to compare against (validated by guard.py)."""
    if not path.is_file():
        raise InputError(f"baseline rules file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise InputError(f"baseline is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise InputError("baseline must be a compiled guardrails.json object")
    guard.rules_from_dict(data)  # RulesError if it is not a usable rule set
    return data


def _phrases(rules: dict, kind: str) -> dict[str, str]:
    return {r["phrase"].lower(): r["phrase"] for r in rules["rules"] if r["kind"] == kind}


def diff_rules(base: dict, new: dict) -> list[dict]:
    """Every rule-level change from the live (base) rule set to the new one, with its effect."""
    changes: list[dict] = []

    def add(area, item, before, after, effect):
        changes.append({"area": area, "item": item, "before": before, "after": after, "effect": effect})

    for kind, area in (("blocked_topic", "blocked topic"), ("injection", "injection marker")):
        b, n = _phrases(base, kind), _phrases(new, kind)
        for k in sorted(n.keys() - b.keys()):
            add(area, n[k], "absent", "block", "tightened")
        for k in sorted(b.keys() - n.keys()):
            add(area, b[k], "block", "absent", "loosened")
    bp = {r["pii_type"]: r["action"] for r in base["rules"] if r["kind"] == "pii"}
    npii = {r["pii_type"]: r["action"] for r in new["rules"] if r["kind"] == "pii"}
    for t in sorted(bp.keys() | npii.keys()):
        b_act, n_act = bp.get(t, "allow"), npii.get(t, "allow")
        if b_act != n_act:
            add("pii", t, b_act, n_act, "tightened" if PII_RANK[n_act] > PII_RANK[b_act] else "loosened")
    for d, label in (("in", "max input chars"), ("out", "max output chars")):
        b_lim, n_lim = base["limits"][d]["max_chars"], new["limits"][d]["max_chars"]
        if b_lim != n_lim:
            add("limit", label, b_lim, n_lim, "tightened" if n_lim < b_lim else "loosened")
    bt, nt = set(base["tools"]["allowed"]), set(new["tools"]["allowed"])
    for t in sorted(nt - bt):
        add("tool", t, "denied", "allowed", "loosened")
    for t in sorted(bt - nt):
        add("tool", t, "allowed", "denied", "tightened")
    return changes


def compare_baseline(base: dict, new: dict, cases: list[dict] | None, base_path: Path) -> dict:
    changes = diff_rules(base, new)
    out = {"baseline_file": base_path.name, "baseline_policy_sha256": base.get("policy_sha256", ""),
           "rule_changes": changes,
           "tightened": sum(c["effect"] == "tightened" for c in changes),
           "loosened": sum(c["effect"] == "loosened" for c in changes),
           "decision_changes": [], "cases_replayed": 0}
    if cases:
        bc, nc = guard.rules_from_dict(base), guard.rules_from_dict(new)
        for c in cases:
            b_dec = guard.evaluate(bc, c["text"], c["direction"], c["tool"])["decision"]
            n_dec = guard.evaluate(nc, c["text"], c["direction"], c["tool"])["decision"]
            if b_dec != n_dec:
                out["decision_changes"].append({"case_id": c["case_id"], "direction": c["direction"],
                                                "live": b_dec, "new": n_dec, "expected": c["expected"],
                                                "fixes_expectation": n_dec == c["expected"] != b_dec})
        out["cases_replayed"] = len(cases)
    return out


def md_cell(s: str) -> str:
    s = s.replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= 80 else s[:77] + "..."


def render_baseline_md(b: dict) -> list[str]:
    L = ["", "## Changes vs live rules", "",
         f"Compared with the live rule set `{b['baseline_file']}` (policy sha256 "
         f"`{(b['baseline_policy_sha256'] or 'unknown')[:12]}`): {len(b['rule_changes'])} rule change(s), "
         f"{b['tightened']} tightened, {b['loosened']} loosened."]
    if b["rule_changes"]:
        L += ["", "| Area | Item | Live | New | Effect |", "|---|---|---|---|---|"]
        for c in b["rule_changes"]:
            L.append(f"| {c['area']} | {md_cell(str(c['item']))} | {c['before']} | {c['after']} | {c['effect']} |")
    if b["loosened"]:
        L += ["", f"Loosened rules need sign-off before deploy — owner: {TEST_OWNER}."]
    if b["cases_replayed"]:
        L += ["", f"Replayed {b['cases_replayed']} test case(s) against both rule sets: "
              f"{len(b['decision_changes'])} decision change(s)."]
        if b["decision_changes"]:
            L += ["", "| Case | Dir | Live decision | New decision | Expected | Now matches expected |",
                  "|---|---|---|---|---|---|"]
            for c in b["decision_changes"]:
                L.append(f"| {c['case_id']} | {c['direction']} | {c['live']} | {c['new']} | {c['expected']} | "
                         f"{'yes' if c['new'] == c['expected'] else 'no'} |")
    return L


def render_md(rules: dict, tests: dict) -> str:
    L = ["# Guardrails", ""]
    L += ["## Rule set", ""]
    L.append(f"Compiled from policy sha256 `{rules['policy_sha256'][:12]}`. Precedence: "
             + " > ".join(rules["precedence"]) + ".")
    L += ["", "| Limit | Max characters | Action |", "|---|---|---|",
          f"| Input | {rules['limits']['in']['max_chars']} | block |",
          f"| Output | {rules['limits']['out']['max_chars']} | block |", ""]
    topics = [r for r in rules["rules"] if r["kind"] == "blocked_topic"]
    inj = [r for r in rules["rules"] if r["kind"] == "injection"]
    L += ["| Rule | Kind | Phrase | Applies to |", "|---|---|---|---|"]
    for r in topics + inj:
        kind = r["kind"] + (f" ({r['source']})" if r.get("source") else "")
        L.append(f"| {r['id']} | {kind} | {md_cell(r['phrase'])} | {', '.join(r['directions'])} |")
    if not topics:
        L += ["", "No blocked topics in the policy."]
    L += ["", "## PII handling", "", "| Rule | PII type | Action | Mask token | Detection |", "|---|---|---|---|---|"]
    det = {"card": "13-19 digits, Luhn-valid", "ssn": "US SSN pattern NNN-NN-NNNN (invalid areas excluded)",
           "email": "address pattern", "phone": "NANP or +country-code pattern with separators"}
    for r in rules["rules"]:
        if r["kind"] != "pii":
            continue
        act = r["action"] if r["configured"] else f"not configured (allow) {tbb(PII_OWNER)}"
        L.append(f"| {r['id']} | {r['pii_type']} | {act} | `{r['mask']}` | {det[r['pii_type']]} |")
    L += ["", "## Tool allowlist", ""]
    allowed = rules["tools"]["allowed"]
    L.append("Allowed: " + (", ".join(f"`{t}`" for t in allowed) if allowed else "none (every tool call is denied)")
             + ". Any other tool call is blocked (`TOOL-DENY`).")
    L += ["", "## Test results", ""]
    if tests["status"] != "run":
        L.append(f"No test inputs supplied: {tbb(TEST_OWNER)}. Add a test CSV before deploying.")
    else:
        L.append(f"**{tests['passed']}/{tests['total']} cases match** "
                 f"({'all pass' if tests['failed'] == 0 else str(tests['failed']) + ' mismatched'}). "
                 "Texts are shown redacted.")
        L += ["", "| Case | Dir | Tool | Expected | Actual | Result | Reasons | Text (redacted) |",
              "|---|---|---|---|---|---|---|---|"]
        for c in tests["cases"]:
            L.append(f"| {c['case_id']} | {c['direction']} | {c['tool'] or ''} | {c['expected']} | {c['actual']} | "
                     f"{'pass' if c['pass'] else 'MISMATCH'} | {', '.join(c['reasons'])} | {md_cell(c['redacted_text'])} |")
    if tests.get("baseline"):
        L += render_baseline_md(tests["baseline"])
    L += ["", "## Limits", "",
          "**Known limitations.** The prompt-injection rules match fixed phrases (`assets/injection-phrases.txt` plus "
          "your `injection_markers`); a reworded attack — e.g. \"kindly set aside what you were told\" — can evade them. "
          "Treat this skill as a baseline policy, not a complete prompt-injection defense. Before client-facing use, "
          "layer it with model-level and system-level controls.", "",
          "- Deterministic keyword and regex rules: paraphrased, translated or encoded attacks (base64, leetspeak) "
          "can pass. Layer a classifier or model-based moderation for semantic coverage.",
          "- Prompt-injection markers apply to inputs only; indirect injection inside retrieved documents or tool "
          "results needs the same check on that content before it reaches the model.",
          "- PII detectors cover email, phone (NANP / +country code), payment card (Luhn) and US SSN pattern only; "
          "names, addresses and other identifiers are not detected.",
          "- Blocked topics match phrases, not meaning; review false positives and negatives from production logs.",
          "- Reasons record rule ids only; matched text is never logged."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", type=Path, required=True, help="policy JSON")
    ap.add_argument("--tests", type=Path, help="test-inputs CSV: case_id,direction,text,expected[,tool]")
    ap.add_argument("--injection-list", type=Path, default=DEFAULT_INJECTION_LIST,
                    help="bundled prompt-injection phrases (default: assets/injection-phrases.txt)")
    ap.add_argument("--baseline", type=Path, help="live compiled guardrails.json to diff against (brownfield)")
    ap.add_argument("--out", type=Path, required=True, help="directory for the three outputs")
    a = ap.parse_args(argv)
    try:
        policy, sha = load_policy(a.policy)
        rules = compile_policy(policy, sha, load_bundled(a.injection_list))
        guard.rules_from_dict(rules)  # every pattern must compile
        cases = load_tests(a.tests) if a.tests else None
        base = load_baseline(a.baseline) if a.baseline else None
    except (InputError, guard.RulesError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    tests = run_tests(rules, cases) if cases else {"status": "not_run", "total": 0, "passed": 0, "failed": 0,
                                                   "cases": [], "note": f"No test inputs supplied: {tbb(TEST_OWNER)}"}
    if base is not None:
        tests["baseline"] = compare_baseline(base, rules, cases, a.baseline)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "guardrails.json").write_text(json.dumps(rules, indent=2), encoding="utf-8")
    (a.out / "guardrail-tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    (a.out / "guardrails.md").write_text(render_md(rules, tests), encoding="utf-8")
    print(f"compiled {len(rules['rules'])} rules; tests {tests['passed']}/{tests['total']} matched; wrote {a.out}")
    if base is not None:
        b = tests["baseline"]
        print(f"vs live rules: {len(b['rule_changes'])} change(s), {b['tightened']} tightened, "
              f"{b['loosened']} loosened; {len(b['decision_changes'])} decision change(s)")
    if tests["failed"]:
        bad = [c["case_id"] for c in tests["cases"] if not c["pass"]]
        print(f"test case(s) with unexpected decision: {', '.join(bad)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
