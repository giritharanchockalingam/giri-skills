#!/usr/bin/env python3
"""Turn a failure log (+ optional recent diff and repro steps) into a structured debug log.

    python3 -I scripts/debug_log.py --log failure.txt [--diff change.patch] [--repro repro.md] \
        --json debug.json --md debug-log.md
    python3 -I scripts/debug_log.py --validate debug.json      # contract check on a written debug.json

Implements the evidence-gathering half of the systematic-debugging method (root cause before
fix): read the error completely, check recent changes, trace frames, then rank hypotheses that
each carry a falsifying experiment. It never proposes a fix: the output carries a fix gate that
stays CLOSED until a hypothesis survives its experiment and a failing test reproduces it.

Parsed formats
  Python   `Traceback (most recent call last):` + `File "p", line N, in f`; pytest `p.py:N: in f`
           and `E   Type: msg` lines; the last exception line wins (chained tracebacks).
  JS / TS  `TypeError: msg` + `    at f (p:N:C)` / `    at p:N:C` (Node, Jest, Vitest, browsers).
  Java     `[Exception in thread "x"] pkg.Type: msg` + `\tat pkg.Cls.m(File.java:N)`; the deepest
           `Caused by:` is the root exception.

In-repo frames: a frame is third-party when its path or class is in site-packages, dist-packages,
node_modules, node:internal, <frozen …>, or a java./javax./jdk./sun./org.junit. package; a frame
whose file appears in the diff is always in-repo. Frames are stored innermost-first.

Diff correlation: a frame overlaps when its file is touched by the diff (path-suffix match; Java
frames match on package path or basename); a line overlap when the frame line is inside a changed
hunk range of the new file. Classification: regression-likely (overlap), no-overlap (diff given,
no overlap), no-diff (no diff supplied).

Exit codes: 0 written · 1 --validate found a contract violation · 2 a required input is missing
or the log contains no parsable error. Stdlib only; writes only the --json / --md paths.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

OWNER_REPRO = "[TO BE BASELINED — owner: Reporting engineer]"

# ------------------------------------------------------------------ patterns
PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.+))?\s*$')
PY_PYTEST_FRAME = re.compile(r"^(?P<file>[^\s:][^:]*\.py):(?P<line>\d+):(?: in (?P<func>\S+)|\s+(?P<etype>\w+))\s*$")
PY_ERROR = re.compile(r"^(?:E\s+)?(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Failure|Fault))"
                      r"(?::\s?(?P<msg>.*))?$")
JS_FRAME = re.compile(r"^\s*at (?:(?P<func>.+?) \()?(?P<file>(?:[A-Za-z]:)?[^():\s][^():]*?):(?P<line>\d+)(?::\d+)?\)?\s*$")
JS_ERROR = re.compile(r"^\s*(?:Uncaught\s+)?(?P<type>(?:[A-Z]\w*)?(?:Error|Exception))(?:\s*\[[\w-]+\])?:\s?(?P<msg>.*)$")
JAVA_FRAME = re.compile(r"^\s*at (?:[\w.$-]+/)?(?P<cls>[\w$.]+)\.(?P<func>[\w$<>]+)\((?P<file>[\w$]+\.(?:java|kt|scala|groovy)):(?P<line>\d+)\)\s*$")
JAVA_ERROR = re.compile(r"^(?:Exception in thread \"[^\"]*\"\s+|Caused by:\s+)?(?P<type>(?:[a-z_$][\w$]*\.)+[A-Z][\w$]*)"
                        r"(?::\s?(?P<msg>.*))?$")
JAVA_CAUSED = re.compile(r"^Caused by:\s+")

THIRD_PARTY_PATH = re.compile(r"site-packages|dist-packages|node_modules|node:internal|^internal/|<frozen|"
                              r"/lib/python\d|\(native\)|^<anonymous>|webpack-internal", re.I)
THIRD_PARTY_JAVA = re.compile(r"^(?:java|javax|jdk|sun|com\.sun|org\.junit|org\.opentest4j|kotlin|scala)\.")

# error-type families -> (category, hypothesis, falsifying experiment). Generic debugging
# categories, not facts about the user's system.
FAMILIES = [
    (re.compile(r"NoneType|undefined|null|NullPointer|NullReference", re.I),
     "null-value", "A null/None/undefined value reaches {where}; it is produced upstream, not at the failing line.",
     "Log or assert the value at entry to {where} and at its caller {caller}; if it is already null at the caller, "
     "the origin is further up (trace backwards), if it is non-null at entry the defect is inside {where}."),
    (re.compile(r"KeyError|IndexError|IndexOutOfBounds|ArrayIndex|RangeError|NoSuchElement", re.I),
     "missing-key-or-index", "{where} indexes a collection with a key/index it does not contain.",
     "Print the collection keys/length and the key used at {where} for the failing input; if the key is present the "
     "hypothesis is false."),
    (re.compile(r"Assert|expect|ComparisonFailure", re.I),
     "assertion-mismatch", "The code under test returns a value different from the expectation at {where}; either the "
     "code or the expectation changed.",
     "Run the single failing test on the last known-green commit; if it also fails there, the expectation (or "
     "environment) changed, not the code."),
    (re.compile(r"Import|ModuleNotFound|Cannot find module|ClassNotFound|NoClassDefFound|ERR_MODULE", re.I),
     "dependency-or-environment", "A dependency or module path differs between this environment and the last "
     "working one.",
     "Compare installed dependency versions / lockfile against the last green run; if identical, the hypothesis is "
     "false."),
    (re.compile(r"Timeout|TimedOut|deadline", re.I),
     "timing", "The failure is timing-dependent (race, slow dependency, arbitrary sleep).",
     "Re-run the repro 10 times and with the timeout doubled; a deterministic failure falsifies the timing hypothesis."),
    (re.compile(r"Connection|ECONNREFUSED|ENOTFOUND|Socket|Unavailable|HTTPError", re.I),
     "external-dependency", "An external service or network dependency is unreachable or returns an unexpected "
     "response.",
     "Call the dependency directly from the same environment; if it responds as expected, the hypothesis is false."),
    (re.compile(r"Type|Attribute|ClassCast|NoSuchMethod", re.I),
     "type-or-contract", "A caller passes {where} a value of the wrong type or shape (contract drift between "
     "caller and callee).",
     "Log the runtime type/shape of the arguments at {where}; if they match the declared contract, the hypothesis "
     "is false."),
]


# ------------------------------------------------------------------ parsing

def _norm(path: str) -> str:
    path = path.replace("\\", "/")
    return path[2:] if path.startswith("./") else path


def parse_log(text: str) -> dict:
    """Return {"error": {...} | None, "frames": [...innermost first], "format": str}."""
    lines = text.splitlines()
    py_frames, js_frames, java_frames = [], [], []
    py_err = js_err = java_err = None
    java_root = None
    pending_py_func = None
    for raw in lines:
        line = raw.rstrip()
        m = PY_FRAME.match(line)
        if m:
            py_frames.append({"file": _norm(m["file"]), "line": int(m["line"]), "func": (m["func"] or "").strip(),
                              "lang": "python"})
            continue
        m = PY_PYTEST_FRAME.match(line.strip())
        if m:
            py_frames.append({"file": _norm(m["file"]), "line": int(m["line"]), "func": m["func"] or "",
                              "lang": "python"})
            if m["etype"]:
                pending_py_func = m["etype"]
            continue
        m = JAVA_FRAME.match(line)
        if m:
            cls = m["cls"]
            pkg_path = "/".join(cls.split(".")[:-1])
            java_frames.append({"file": f"{pkg_path}/{m['file']}" if pkg_path else m["file"], "line": int(m["line"]),
                                "func": f"{cls}.{m['func']}", "lang": "java", "class": cls})
            continue
        m = JS_FRAME.match(line)
        if m and not line.strip().startswith("at java"):
            js_frames.append({"file": _norm(re.sub(r"^file://", "", m["file"])), "line": int(m["line"]),
                              "func": (m["func"] or "").strip(), "lang": "js"})
            continue
        s = line.strip()
        m = JAVA_ERROR.match(s)
        if m and "." in m["type"]:
            err = {"type": m["type"], "message": (m["msg"] or "").strip()}
            if JAVA_CAUSED.match(s):
                java_root = err
                java_frames.append({"marker": "caused-by"})
            elif java_err is None:
                java_err = err
        m = PY_ERROR.match(s)
        if m and (s.startswith("E ") or ":" in s or s == m["type"]):
            py_err = {"type": m["type"], "message": (m["msg"] or "").strip()}
        m = JS_ERROR.match(line)
        if m and js_err is None:
            js_err = {"type": m["type"], "message": (m["msg"] or "").strip()}
    if py_err is None and pending_py_func:
        py_err = {"type": pending_py_func, "message": ""}

    # Java: the root cause block is the last "Caused by"; its frames follow the marker.
    if java_root is not None:
        idx = max(i for i, f in enumerate(java_frames) if f.get("marker"))
        java_frames = [f for f in java_frames[idx + 1:] if not f.get("marker")] or \
            [f for f in java_frames if not f.get("marker")]
        java_err = java_root
    else:
        java_frames = [f for f in java_frames if not f.get("marker")]

    candidates = [
        ("python", py_err, list(reversed(py_frames))),   # most recent call last -> innermost first
        ("js", js_err, js_frames),
        ("java", java_err, java_frames),
    ]
    with_err = [c for c in candidates if c[1] is not None]
    if not with_err:
        return {"error": None, "frames": [], "format": "unknown"}
    fmt, err, frames = max(with_err, key=lambda c: len(c[2]))
    for i, f in enumerate(frames):
        f["depth"] = i
    return {"error": err, "frames": frames, "format": fmt}


def parse_diff(text: str) -> dict:
    """{path: {"hunks": [(start, end)], "added": set(lines)}} for the new side of a unified diff."""
    files: dict[str, dict] = {}
    cur = None
    new_line = 0
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            p = raw[4:].strip().split("\t")[0]
            if p == "/dev/null":
                cur = None
                continue
            p = re.sub(r"^[ab]/", "", p)
            cur = files.setdefault(p, {"hunks": [], "added": set()})
            continue
        if raw.startswith("--- ") or raw.startswith("diff --git"):
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", raw)
        if m and cur is not None:
            start, count = int(m[1]), int(m[2] if m[2] is not None else 1)
            cur["hunks"].append((start, start + max(count, 1) - 1))
            new_line = start
            continue
        if cur is None or not cur["hunks"]:
            continue
        if raw.startswith("+"):
            cur["added"].add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            cur["added"].add(new_line)  # a deletion changes the code at this new-side position
        elif raw.startswith(" ") or raw == "":
            new_line += 1
    return files


def _match_file(frame_file: str, diff_files: dict) -> str | None:
    ff = frame_file.replace("\\", "/")
    for p in diff_files:
        if ff == p or ff.endswith("/" + p) or p.endswith("/" + ff):
            return p
    base = ff.rsplit("/", 1)[-1]
    for p in diff_files:
        if p.rsplit("/", 1)[-1] == base and ff.count("/") and p.endswith(ff.split("/", 1)[-1]):
            return p
    return None


def is_third_party(frame: dict) -> bool:
    if frame.get("lang") == "java":
        return bool(THIRD_PARTY_JAVA.match(frame.get("class", "")))
    return bool(THIRD_PARTY_PATH.search(frame["file"]))


def correlate(frames: list[dict], diff_files: dict | None) -> None:
    for f in frames:
        f["in_repo"] = not is_third_party(f)
        f["diff_file"] = None
        f["file_touched"] = False
        f["line_touched"] = False
        if diff_files:
            p = _match_file(f["file"], diff_files)
            if p:
                f["in_repo"] = True
                f["diff_file"] = p
                f["file_touched"] = True
                d = diff_files[p]
                for a, b in d["hunks"]:
                    if a <= f["line"] <= b:
                        f["line_touched"] = True
                        f["hunk"] = [a, b]
                        f["changed_lines"] = sorted(x for x in d["added"] if a <= x <= b)
                        break


# ------------------------------------------------------------------ analysis

def _loc(f: dict | None) -> str:
    if not f:
        return "(no frame)"
    fn = f" in {f['func']}" if f.get("func") else ""
    return f"{f['file']}:{f['line']}{fn}"


def build(log_text: str, diff_text: str | None, repro_text: str | None, sources: dict) -> dict:
    parsed = parse_log(log_text)
    if parsed["error"] is None:
        raise ValueError("no parsable error in the log (no Python/JS/Java exception line found)")
    frames = parsed["frames"]
    diff_files = parse_diff(diff_text) if diff_text else None
    correlate(frames, diff_files)
    in_repo = [f for f in frames if f["in_repo"]]
    innermost = in_repo[0] if in_repo else None
    caller = in_repo[1] if len(in_repo) > 1 else None
    line_hits = [f for f in frames if f["line_touched"]]
    file_hits = [f for f in frames if f["file_touched"] and not f["line_touched"]]
    if diff_files is None:
        classification = "no-diff"
    elif line_hits or file_hits:
        classification = "regression-likely"
    else:
        classification = "no-overlap"

    err = parsed["error"]
    hyps = []

    def add(statement, evidence, score, test, kind):
        hyps.append({"statement": statement, "evidence": evidence, "evidence_score": score,
                     "falsifying_test": test, "kind": kind, "status": "untested"})

    for f in line_hits:
        changed = ", ".join(str(x) for x in f.get("changed_lines", [])) or "—"
        add(f"The recent change in {f['diff_file']} (hunk {f['hunk'][0]}-{f['hunk'][1]}, changed lines {changed}) "
            f"introduced the failure seen at line {f['line']}.",
            f"frame #{f['depth']} {_loc(f)} is inside a changed hunk of the diff", 3,
            f"Revert only the hunk {f['hunk'][0]}-{f['hunk'][1]} of {f['diff_file']} and re-run the reproduction; if it still "
            f"fails, this hypothesis is false.", "regression-line")
    for f in file_hits:
        add(f"A change elsewhere in {f['diff_file']} altered state or behaviour used at line {f['line']}.",
            f"frame #{f['depth']} {_loc(f)} is in a file the diff touches (not on a changed line)", 2,
            f"Revert the diff's changes to {f['diff_file']} only and re-run the reproduction; if it still fails, "
            f"this hypothesis is false.", "regression-file")
    where = _loc(innermost) if innermost else "the failing call"
    for rx, cat, stmt, test in FAMILIES:
        if rx.search(err["type"]) or (cat in ("null-value",) and rx.search(err["message"] or "")):
            add(stmt.format(where=where), f"error type {err['type']}" + (f" at innermost in-repo frame {where}"
                                                                         if innermost else ""),
                2 if innermost else 1, test.format(where=where, caller=_loc(caller)), cat)
            break
    if innermost and not any(h["kind"].startswith("regression") for h in hyps):
        add(f"The defect originates at the innermost in-repo frame {where} or in the value its caller passes.",
            f"innermost in-repo frame (depth {innermost['depth']} of {len(frames)})", 1,
            f"Add a temporary assertion on the inputs of {where} and re-run; if the inputs are valid there, "
            f"the defect is inside {where}; if not, trace one frame up to {_loc(caller)}.", "innermost-frame")
    if classification in ("no-overlap", "no-diff"):
        add("The failure is environmental (dependency versions, configuration, data or timing) rather than a code "
            "change.", "no frame overlaps the supplied diff" if diff_files is not None else "no diff supplied", 1,
            "Run the same reproduction on the last known-green commit in this environment; if it passes there, "
            "the cause is a code change and this hypothesis is false.", "environment")
    hyps.sort(key=lambda h: -h["evidence_score"])
    for i, h in enumerate(hyps, 1):
        h["id"] = f"H{i}"

    repro_lines = [ln.strip() for ln in (repro_text or "").splitlines()
                   if ln.strip() and not ln.lstrip().startswith("#")]
    next_exp = []
    if not repro_lines:
        next_exp.append({"order": 1, "experiment": "Establish a reliable reproduction (exact command, input, "
                         "environment) and record whether it fails every time.", "owner": "Reporting engineer"})
    if hyps:
        next_exp.append({"order": len(next_exp) + 1, "experiment": f"{hyps[0]['id']}: {hyps[0]['falsifying_test']}",
                         "owner": "Investigating engineer"})
    return {
        "skill": "systematic-debugging-runner",
        "sources": sources,
        "format": parsed["format"],
        "symptom": {"error_type": err["type"], "message": err["message"], "frames": len(frames),
                    "repro_steps": repro_lines or None},
        "frames": frames,
        "innermost_in_repo_frame": innermost,
        "diff": None if diff_files is None else {
            "files": sorted(diff_files), "overlapping_frames": [f["depth"] for f in frames if f["file_touched"]]},
        "classification": classification,
        "hypotheses": hyps,
        "next_experiments": next_exp,
        "gate": {"fix_allowed": False,
                 "reason": "Root cause not established: no hypothesis has survived its falsifying test.",
                 "unlock_when": ["one hypothesis confirmed by its falsifying test (status: confirmed)",
                                 "a failing automated test reproduces the defect before the fix",
                                 "after 3 failed fix attempts, stop and review the design instead of fix #4"]},
    }


# ------------------------------------------------------------------ rendering

def _cell(s) -> str:
    return str(s if s not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def render_md(d: dict) -> str:
    s = d["symptom"]
    out = ["# Debug log", "",
           f"_Generated by systematic-debugging-runner from {_cell(d['sources'].get('log'))}"
           + (f" and {_cell(d['sources'].get('diff'))}" if d['sources'].get('diff') else "")
           + ". Evidence only; no fix proposed._", "",
           "## Symptom", "",
           "| Field | Value |", "|---|---|",
           f"| Error type | `{_cell(s['error_type'])}` |",
           f"| Message | {_cell(s['message'])} |",
           f"| Log format | {d['format']} |",
           f"| Frames parsed | {s['frames']} |",
           f"| Classification | **{d['classification']}** |", ""]
    if s["repro_steps"]:
        out += ["Reproduction steps (as supplied):", ""] + [f"{i}. {t}" for i, t in enumerate(s["repro_steps"], 1)] + [""]
    else:
        out += [f"Reproduction steps: {OWNER_REPRO}", ""]
    out += ["## Evidence", "", "Frames, innermost first. `in-repo` excludes third-party/runtime frames.", "",
            "| # | File:line | Function | In-repo | Diff overlap |", "|---|---|---|---|---|"]
    for f in d["frames"]:
        ov = "line" if f["line_touched"] else ("file" if f["file_touched"] else "—")
        out.append(f"| {f['depth']} | `{_cell(f['file'])}:{f['line']}` | {_cell(f['func'])} | "
                   f"{'yes' if f['in_repo'] else 'no'} | {ov} |")
    if not d["frames"]:
        out.append("| — | no stack frames in the log | — | — | — |")
    im = d["innermost_in_repo_frame"]
    out += ["", f"Innermost in-repo frame: `{_loc(im)}`" if im else "Innermost in-repo frame: none found", ""]
    if d["diff"] is not None:
        out += [f"Diff files: {', '.join(f'`{p}`' for p in d['diff']['files']) or 'none'}", ""]
    else:
        out += ["Recent diff: not supplied (regression check not possible).", ""]
    out += ["## Hypotheses", "", "Ranked by evidence score (3 = changed line in the stack, 2 = changed file or "
            "error-type signal at an in-repo frame, 1 = weak). Status stays `untested` until its experiment runs.", "",
            "| ID | Hypothesis | Evidence | Score | Falsifying test | Status |", "|---|---|---|---|---|---|"]
    for h in d["hypotheses"]:
        out.append(f"| {h['id']} | {_cell(h['statement'])} | {_cell(h['evidence'])} | {h['evidence_score']} | "
                   f"{_cell(h['falsifying_test'])} | {h['status']} |")
    out += ["", "## Next experiment", ""]
    for e in d["next_experiments"]:
        out.append(f"{e['order']}. {e['experiment']} (owner: {e['owner']})")
    g = d["gate"]
    out += ["", "## Fix gate", "", f"Fix allowed: {'YES' if g['fix_allowed'] else 'NO'} — {g['reason']}", "",
            "Unlock only when:"] + [f"- [ ] {u}" for u in g["unlock_when"]] + [""]
    return "\n".join(out)


# ------------------------------------------------------------------ validation

def validate(path: Path) -> list[str]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"cannot read {path}: {e}"]
    problems = []
    if not d.get("symptom", {}).get("error_type"):
        problems.append("symptom.error_type empty")
    if not d.get("hypotheses"):
        problems.append("no hypotheses")
    for h in d.get("hypotheses", []):
        if not h.get("falsifying_test"):
            problems.append(f"{h.get('id')} has no falsifying test")
    scores = [h.get("evidence_score", 0) for h in d.get("hypotheses", [])]
    if scores != sorted(scores, reverse=True):
        problems.append("hypotheses not ranked by evidence score")
    g = d.get("gate", {})
    confirmed = any(h.get("status") == "confirmed" for h in d.get("hypotheses", []))
    if g.get("fix_allowed") and not confirmed:
        problems.append("fix gate open without a confirmed hypothesis")
    if d.get("classification") not in ("regression-likely", "no-overlap", "no-diff"):
        problems.append(f"bad classification {d.get('classification')!r}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Failure log (+diff, +repro) -> structured debug log; never a fix.")
    ap.add_argument("--log", help="failure log: test output or stack trace (Python, JS/TS, Java)")
    ap.add_argument("--diff", help="optional unified diff of recent changes")
    ap.add_argument("--repro", help="optional reproduction steps (text/markdown, one step per line)")
    ap.add_argument("--json", dest="json_out", help="write debug.json here")
    ap.add_argument("--md", dest="md_out", help="write debug-log.md here")
    ap.add_argument("--validate", metavar="DEBUG_JSON", help="check a written debug.json against the contract")
    a = ap.parse_args()

    if a.validate:
        problems = validate(Path(a.validate))
        for p in problems:
            print(f"FAIL: {p}", file=sys.stderr)
        print("debug.json contract: " + ("FAIL" if problems else "OK"))
        return 1 if problems else 0
    if not a.log or not Path(a.log).is_file():
        print(f"error: --log is required and must exist (got {a.log!r})", file=sys.stderr)
        return 2
    for opt in ("diff", "repro"):
        v = getattr(a, opt)
        if v and not Path(v).is_file():
            print(f"error: --{opt} file not found: {v}", file=sys.stderr)
            return 2
    if not a.json_out and not a.md_out:
        print("error: give --json and/or --md", file=sys.stderr)
        return 2
    read = lambda p: Path(p).read_text(encoding="utf-8", errors="replace") if p else None  # noqa: E731
    sources = {"log": Path(a.log).name, "diff": Path(a.diff).name if a.diff else None,
               "repro": Path(a.repro).name if a.repro else None}
    try:
        d = build(read(a.log), read(a.diff), read(a.repro), sources)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    if a.md_out:
        Path(a.md_out).write_text(render_md(d), encoding="utf-8")
    print(f"{d['symptom']['error_type']}: {len(d['frames'])} frames, {d['classification']}, "
          f"{len(d['hypotheses'])} hypotheses; fix gate CLOSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
