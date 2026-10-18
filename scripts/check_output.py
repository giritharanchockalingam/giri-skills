#!/usr/bin/env python3
"""Output checks for skill runs — one fixed vocabulary, implemented once.

Check spec syntax (a string):
  exists                       file exists and is non-empty
  json                         file parses as JSON
  csv:[a,b]                    CSV header contains every listed column
  csv_rows:<col>!empty         every row has a non-empty <col>
  csv_rows:<col>~<regex>       every row's <col> matches <regex> (re.search); the column must exist
                               and the CSV must have >= 1 data row. Dry mode: a column that is
                               blank in every row is an unfilled llm slot and is skipped
  yaml                       file is non-empty and parses with the repo's YAML subset
  sections:[A,B]               a Markdown heading contains each listed text (case-insensitive)
  no_unowned_tbd               every `[TO BE BASELINED` marker names an owner (real mode);
                               dry mode only verifies the marker format `— owner:`
  numbers_trace_to:<file>      every number in the output with >= 3 significant digits, or
                               with a $ or % sign, appears in <file> (list of files allowed);
                               skipped in dry mode
  cites_source_ids:<file>      every `[Sn]` citation in the output exists as an id `Sn` in <file>;
                               skipped in dry mode
  mermaid_parses               every ```mermaid block has balanced brackets and >= 1 edge
  max_lines:N                  output has at most N lines
  contains:"text"              output contains the literal text
  cmd:"..."                    run the command (python3 -> this interpreter, `{path}` substituted);
                               expect exit 0
  exit:N                       run-level: the process exit code equals N
  needs_input:<name>           run-level: needs_input.json in the out dir names <name>

Programmatic:
    run_check(spec, path=None, *, mode="dry", exit_code=None, out_dir=None, cwd=None) -> dict
    returns {"check": spec, "pass": bool, "evidence": str}
CLI:
    python3 scripts/check_output.py <file> <check> [<check> ...] [--mode dry|real]
Exit 0 when every check passes, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skillmeta  # noqa: E402

VOCAB = {
    "exists", "json", "csv", "csv_rows", "yaml", "sections", "no_unowned_tbd", "numbers_trace_to",
    "cites_source_ids", "mermaid_parses", "max_lines", "contains", "cmd", "exit", "needs_input",
}
RUN_LEVEL = {"exit", "needs_input"}

TBD_RE = re.compile(r"\[TO BE BASELINED[^\]]*\]")
NUMBER_RE = re.compile(r"(?<![\w.])([$€£]?)(-?\d[\d,]*(?:\.\d+)?)(%?)(?![\w])")
CITE_RE = re.compile(r"\[(S\d+)\]")


def parse_spec(spec: str):
    """Split 'name:arg' into (name, arg). arg is a str, list or None."""
    spec = str(spec).strip()
    if ":" not in spec:
        return spec, None
    name, _, arg = spec.partition(":")
    arg = arg.strip()
    if arg.startswith("["):
        arg = skillmeta.parse_flow(arg)
        if not isinstance(arg, list):
            arg = [arg]
        arg = [str(a) for a in arg]
    else:
        arg = str(skillmeta.scalar(arg))
    return name.strip(), arg


def _result(spec, ok, evidence):
    return {"check": str(spec), "pass": bool(ok), "evidence": str(evidence)[:300]}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _sig_digits(num: str) -> int:
    digits = num.replace(",", "").replace("-", "").replace(".", "").lstrip("0")
    return len(digits)


def _numbers(text: str):
    """Numbers worth tracing: >=3 significant digits or carrying $ / %."""
    out = []
    for m in NUMBER_RE.finditer(text):
        sym, num, pct = m.groups()
        if sym or pct or _sig_digits(num) >= 3:
            out.append(num.replace(",", ""))
    return out


def _all_numbers(text: str):
    return [m.group(2).replace(",", "") for m in NUMBER_RE.finditer(text)]


def _number_in(num: str, ref_numbers: list[str]) -> bool:
    if num in ref_numbers:
        return True
    try:
        n = float(num)
    except ValueError:
        return False
    decimals = len(num.split(".")[1]) if "." in num else 0
    tol = 0.5 * 10 ** (-decimals)
    for r in ref_numbers:
        try:
            rv = float(r)
        except ValueError:
            continue
        if abs(rv - n) <= tol + 1e-9:
            return True
    return False


def _resolve(ref, cwd):
    p = Path(str(ref))
    if not p.is_absolute() and cwd:
        p = Path(cwd) / p
    return p


def _csv_rows(spec, arg: str, text: str, mode: str) -> dict:
    """csv_rows:<col>!empty | csv_rows:<col>~<regex> — a per-row predicate on one column."""
    arg = arg.strip()
    if arg.endswith("!empty"):
        col, pred, pattern = arg[: -len("!empty")].strip(), "!empty", None
    elif "~" in arg:
        col, _, pattern = arg.partition("~")
        col, pred = col.strip(), "~"
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return _result(spec, False, f"bad regex {pattern!r}: {e}")
    else:
        return _result(spec, False, f"csv_rows needs '<col>!empty' or '<col>~<regex>', got {arg!r}")
    if not col:
        return _result(spec, False, "csv_rows: empty column name")
    rows = list(csv.DictReader(io.StringIO(text)))
    header = rows[0].keys() if rows else next(csv.reader(io.StringIO(text)), [])
    if col not in header:
        return _result(spec, False, f"column '{col}' not in header {list(header)}")
    if not rows:
        return _result(spec, False, "no data rows")
    values = [(r.get(col) or "").strip() for r in rows]
    if mode == "dry" and all(v == "" for v in values):
        return _result(spec, True, f"skipped in dry mode: '{col}' unfilled in all {len(rows)} rows")
    if pred == "!empty":
        bad = [i + 2 for i, v in enumerate(values) if v == ""]
        label = "empty"
    else:
        bad = [i + 2 for i, v in enumerate(values) if not rx.search(v)]
        label = f"not matching {pattern!r}"
    return _result(spec, not bad, f"{len(bad)} of {len(rows)} rows {label} in '{col}'"
                   + (f" (lines {bad[:6]})" if bad else ""))


# ------------------------------------------------------------------ checks

def run_check(spec, path=None, *, mode: str = "dry", exit_code=None, out_dir=None, cwd=None) -> dict:
    name, arg = parse_spec(spec)
    if name not in VOCAB:
        return _result(spec, False, f"unknown check '{name}'")

    # ---- run-level checks
    if name == "exit":
        want = int(arg) if arg not in (None, "") else 0
        return _result(spec, exit_code == want, f"exit code {exit_code}, expected {want}")
    if name == "needs_input":
        f = Path(out_dir or ".") / "needs_input.json"
        if not f.exists():
            return _result(spec, False, "needs_input.json not written")
        try:
            data = json.loads(_read(f))
        except Exception as e:  # noqa: BLE001
            return _result(spec, False, f"needs_input.json invalid: {e}")
        names = [m.get("name") for m in data.get("missing", [])]
        return _result(spec, arg in names, f"missing inputs named: {names}")

    # ---- file-level checks
    if path is None:
        return _result(spec, False, "no file given")
    p = Path(path)
    if name == "exists":
        ok = p.is_file() and p.stat().st_size > 0
        return _result(spec, ok, f"{p} {'exists' if p.exists() else 'missing'}"
                       + ("" if ok or not p.exists() else " (empty)"))
    if name == "cmd":
        if not arg:
            return _result(spec, False, "cmd has no command")
        tokens = shlex.split(str(arg).replace("{path}", str(p)))
        if tokens and tokens[0] in ("python3", "python"):
            tokens = [sys.executable, "-I"] + [t for t in tokens[1:] if t != "-I"]
        try:
            r = subprocess.run(tokens, capture_output=True, text=True, cwd=cwd, timeout=600)
        except Exception as e:  # noqa: BLE001
            return _result(spec, False, f"could not run: {e}")
        tail = (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]
        return _result(spec, r.returncode == 0, f"exit {r.returncode}: {tail[0]}")
    if not p.is_file():
        return _result(spec, False, f"{p} missing")
    text = _read(p)

    if name == "json":
        try:
            json.loads(text)
            return _result(spec, True, "valid JSON")
        except Exception as e:  # noqa: BLE001
            return _result(spec, False, f"invalid JSON: {e}")
    if name == "csv":
        try:
            header = next(csv.reader(io.StringIO(text)))
        except StopIteration:
            return _result(spec, False, "empty CSV")
        want = arg if isinstance(arg, list) else ([arg] if arg else [])
        missing = [c for c in want if c not in header]
        return _result(spec, not missing, f"missing columns {missing}" if missing else f"header has {want}")
    if name == "csv_rows":
        return _csv_rows(spec, str(arg or ""), text, mode)
    if name == "yaml":
        if not text.strip():
            return _result(spec, False, "empty file")
        try:
            data = skillmeta.parse_yaml_subset(text)
            return _result(spec, bool(data), f"parsed {len(data)} top-level keys")
        except Exception as e:  # noqa: BLE001
            return _result(spec, False, f"yaml subset parse failed: {e}")
    if name == "sections":
        heads = [ln.lstrip("#").strip().lower() for ln in text.splitlines() if ln.startswith("#")]
        want = arg if isinstance(arg, list) else ([arg] if arg else [])
        missing = [w for w in want if not any(w.lower() in h for h in heads)]
        return _result(spec, not missing, f"missing headings {missing}" if missing else f"found {want}")
    if name == "no_unowned_tbd":
        bad = []
        for m in TBD_RE.finditer(text):
            marker = m.group(0)
            om = re.search(r"owner:\s*([^\]]*)", marker)
            if mode == "dry":
                if om is None:
                    bad.append(marker)
            else:
                owner = om.group(1).strip() if om else ""
                if not owner or set(owner) <= set("_ "):
                    bad.append(marker)
        n = len(TBD_RE.findall(text))
        return _result(spec, not bad, f"{len(bad)} unowned of {n} markers" + (f": {bad[0]}" if bad else ""))
    if name == "numbers_trace_to":
        if mode == "dry":
            return _result(spec, True, "skipped in dry mode")
        refs = arg if isinstance(arg, list) else [arg]
        ref_nums = []
        for ref in refs:
            rp = _resolve(ref, cwd)
            if not rp.is_file():
                return _result(spec, False, f"reference file missing: {rp}")
            ref_nums += _all_numbers(_read(rp))
        missing = sorted({n for n in _numbers(text) if not _number_in(n, ref_nums)})
        return _result(spec, not missing, f"untraced numbers {missing[:8]}" if missing
                       else f"all {len(_numbers(text))} numbers trace")
    if name == "cites_source_ids":
        if mode == "dry":
            return _result(spec, True, "skipped in dry mode")
        rp = _resolve(arg, cwd)
        if not rp.is_file():
            return _result(spec, False, f"reference file missing: {rp}")
        ids = set(re.findall(r"\bS\d+\b", _read(rp)))
        cited = set(CITE_RE.findall(text))
        missing = sorted(cited - ids)
        return _result(spec, not missing and bool(cited),
                       f"unknown source ids {missing}" if missing
                       else (f"{len(cited)} citations resolve" if cited else "no [Sn] citations found"))
    if name == "mermaid_parses":
        blocks = re.findall(r"```mermaid\s*\n(.*?)```", text, re.S)
        if not blocks:
            return _result(spec, False, "no mermaid block")
        for b in blocks:
            for o, c in ("[]", "{}", "()"):
                if b.count(o) != b.count(c):
                    return _result(spec, False, f"unbalanced {o}{c}")
            if "-->" not in b and "---" not in b and "->>" not in b:
                return _result(spec, False, "no edges")
        return _result(spec, True, f"{len(blocks)} block(s) ok")
    if name == "max_lines":
        n = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        limit = int(arg)
        return _result(spec, n <= limit, f"{n} lines (max {limit})")
    if name == "contains":
        needle = str(arg)
        return _result(spec, needle in text, f"{'found' if needle in text else 'missing'}: {needle}")
    return _result(spec, False, "unhandled")


def run_checks(specs, path=None, **kw) -> list[dict]:
    return [run_check(s, path, **kw) for s in specs]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run output checks on a file")
    ap.add_argument("file")
    ap.add_argument("checks", nargs="+")
    ap.add_argument("--mode", choices=["dry", "real"], default="real")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    results = run_checks(a.checks, a.file, mode=a.mode, cwd=str(Path.cwd()))
    if a.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['check']}  — {r['evidence']}")
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
