#!/usr/bin/env python3
"""Make "never break another thing" executable: snapshot the test suite before a fix, re-run after, diff.

    python3 -I scripts/safefix.py baseline --target <repo> --cmd "python3 -m pytest -q" --out baseline.json
    ... apply the fix ...
    python3 -I scripts/safefix.py verify   --target <repo> --cmd "python3 -m pytest -q" \
        --baseline baseline.json --out verify.json

`baseline` runs the test command inside --target, parses its output into per-test status plus
pass/fail counts, and stores stdout, stderr and the exit code. `verify` re-runs the same way and
diffs against the baseline:
  * collateral  — tests failing now that were not failing in the baseline (or a drop in the
                  passed count when the runner names only failures)   -> exit 1, list printed
  * fixed       — tests failing in the baseline that no longer fail
  * still_failing — failing in both
Recognised output: pytest (-q, -v, -rA), vitest / jest text (✓ ✗ × ✕), jest/vitest --reporter=json
(testResults[].assertionResults[]), and a generic "N passed, M failed" summary. A leading `python3`
in --cmd is replaced by this interpreter. Exit 1 on bad input or collateral, 2 never. Stdlib, offline.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

MAX_CAPTURE = 200_000
PYTEST_VERBOSE = re.compile(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.M)
PYTEST_SUMMARY = re.compile(r"^(PASSED|FAILED|ERROR)\s+(\S+::\S+)", re.M)
VITEST_LINE = re.compile(r"^\s*([✓✔✗✘×✕])\s+(.+?)(?:\s+\(?\d+\s*ms\)?)?\s*$", re.M)
COUNTS = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped)\b")
STATUS = {"PASSED": "passed", "FAILED": "failed", "ERROR": "failed", "SKIPPED": "skipped",
          "XFAIL": "skipped", "XPASS": "passed", "✓": "passed", "✔": "passed",
          "✗": "failed", "✘": "failed", "×": "failed", "✕": "failed"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------ run + parse

def run_tests(target: Path, cmd: str) -> dict:
    argv = shlex.split(cmd)
    if not argv:
        die("--cmd is empty")
    if argv[0] in ("python3", "python"):
        argv[0] = sys.executable
    try:
        r = subprocess.run(argv, cwd=str(target), capture_output=True, text=True, timeout=900)
    except FileNotFoundError as e:
        die(f"cannot run {argv[0]!r}: {e}")
    except subprocess.TimeoutExpired:
        die("test command timed out after 900 s")
    out, err = r.stdout[-MAX_CAPTURE:], r.stderr[-MAX_CAPTURE:]
    tests, counts, parser = parse_output(out + "\n" + err)
    return {"cmd": cmd, "exit_code": r.returncode, "parser": parser, "tests": tests,
            "counts": counts, "stdout": out, "stderr": err}


def _parse_json_reporter(text: str):
    start = text.find("{")
    if start < 0:
        return None
    for cand in (text[start:], text[start:text.rfind("}") + 1]):
        try:
            data = json.loads(cand)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict) and isinstance(data.get("testResults"), list):
            tests = {}
            for f in data["testResults"]:
                fname = f.get("name") or f.get("testFilePath") or ""
                for a in f.get("assertionResults", []) or []:
                    name = a.get("fullName") or a.get("title") or ""
                    st = str(a.get("status", "")).lower()
                    tests[f"{Path(fname).name}::{name}" if fname else name] = \
                        "passed" if st in ("passed", "pass") else ("failed" if st in ("failed", "fail") else "skipped")
            return tests
    return None


def parse_output(text: str):
    """Return (tests{id: status}, counts{passed, failed, skipped}, parser_name)."""
    tests: dict[str, str] = {}
    parser = "generic"
    j = _parse_json_reporter(text)
    if j is not None:
        tests, parser = j, "json-reporter"
    for m in PYTEST_VERBOSE.finditer(text):
        tests[m.group(1)] = STATUS[m.group(2)]
        parser = "pytest"
    for m in PYTEST_SUMMARY.finditer(text):
        tests[m.group(2)] = STATUS[m.group(1)]
        parser = "pytest"
    if parser == "generic":
        for m in VITEST_LINE.finditer(text):
            tests[m.group(2).strip()] = STATUS[m.group(1)]
            parser = "vitest/jest"
    counts = {"passed": None, "failed": None, "skipped": None}
    for m in COUNTS.finditer(text):
        key = m.group(2)
        key = "failed" if key.startswith("error") else key
        counts[key] = (counts[key] or 0) + int(m.group(1))
    if counts["passed"] is None and counts["failed"] is None and tests:
        counts["passed"] = sum(1 for s in tests.values() if s == "passed")
        counts["failed"] = sum(1 for s in tests.values() if s == "failed")
    return tests, counts, parser


# ------------------------------------------------------------------ diff

def diff(baseline: dict, after: dict) -> dict:
    b_tests, a_tests = baseline.get("tests", {}), after.get("tests", {})
    b_failed = {t for t, s in b_tests.items() if s == "failed"}
    a_failed = {t for t, s in a_tests.items() if s == "failed"}
    collateral = sorted(a_failed - b_failed)
    fixed = sorted(b_failed - a_failed)
    still = sorted(a_failed & b_failed)
    bc, ac = baseline.get("counts") or {}, after.get("counts") or {}
    b_pass, a_pass, b_fail, a_fail = bc.get("passed"), ac.get("passed"), bc.get("failed") or 0, ac.get("failed") or 0
    if not collateral:
        # runners that name only failures (pytest -q) or nothing at all (generic summary)
        if a_fail > b_fail and len(a_failed) <= len(b_failed):
            collateral.append(f"(unnamed) failed count rose from {b_fail} to {a_fail}")
        elif b_pass is not None and a_pass is not None and a_pass < b_pass and a_fail <= b_fail:
            collateral.append(f"(unnamed) passed count dropped from {b_pass} to {a_pass} — tests removed or skipped?")
        elif after.get("exit_code", 0) != 0 and baseline.get("exit_code", 0) == 0 and not a_failed:
            collateral.append(f"(unnamed) test command now exits {after['exit_code']} (baseline exited 0)")
    return {"ok": not collateral, "collateral": collateral, "fixed": fixed, "still_failing": still,
            "baseline_counts": baseline.get("counts"), "after_counts": after.get("counts")}


# ------------------------------------------------------------------ cli

def main() -> int:
    ap = argparse.ArgumentParser(description="Baseline a test suite before a fix and verify no collateral after")
    sub = ap.add_subparsers(dest="mode", required=True)
    for name in ("baseline", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--target", required=True, help="repo directory to run the tests in")
        p.add_argument("--cmd", required=True, help='test command, e.g. "python3 -m pytest -q" or "npx vitest run"')
        p.add_argument("--out", required=True, help="JSON file to write")
        if name == "verify":
            p.add_argument("--baseline", help="baseline.json (default: baseline.json beside --out)")
    a = ap.parse_args()
    target = Path(a.target)
    if not target.is_dir():
        die(f"target is not a directory: {target}")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if a.mode == "baseline":
        res = run_tests(target, a.cmd)
        res["mode"] = "baseline"
        out.write_text(json.dumps(res, indent=2), encoding="utf-8")
        c = res["counts"]
        print(f"baseline: exit {res['exit_code']}, {len(res['tests'])} named tests, "
              f"passed={c['passed']} failed={c['failed']} ({res['parser']}) -> {out}")
        return 0

    bpath = Path(a.baseline) if a.baseline else out.parent / "baseline.json"
    if not bpath.is_file():
        die(f"baseline not found: {bpath} (run `safefix.py baseline` first)")
    try:
        baseline = json.loads(bpath.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        die(f"baseline is not valid JSON: {e}")
    if baseline.get("cmd") and baseline["cmd"] != a.cmd:
        print(f"warning: baseline cmd was {baseline['cmd']!r}, verify cmd is {a.cmd!r}", file=sys.stderr)
    after = run_tests(target, a.cmd)
    res = diff(baseline, after)
    res.update({"mode": "verify", "cmd": a.cmd, "baseline_file": str(bpath), "after": after})
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    if res["fixed"]:
        print("fixed: " + ", ".join(res["fixed"]))
    if res["still_failing"]:
        print("still failing: " + ", ".join(res["still_failing"]))
    if res["collateral"]:
        print(f"COLLATERAL: {len(res['collateral'])} test(s) newly failing — fix rejected", file=sys.stderr)
        for t in res["collateral"]:
            print(f"  - {t}", file=sys.stderr)
        return 1
    print(f"verify: no collateral ({len(after['tests'])} named tests, exit {after['exit_code']}) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
