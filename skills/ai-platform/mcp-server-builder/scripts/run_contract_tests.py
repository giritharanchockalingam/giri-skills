#!/usr/bin/env python3
"""Run a scaffolded server's contract tests without pytest (stdlib only).

    python3 -I scripts/run_contract_tests.py <server>/tests

Imports every tests/test_*.py and calls each module-level `test_*` function that takes no arguments.
Functions that need pytest fixtures (any parameter) are reported as skipped, not passed. Exit 0 only
when at least one test ran and none failed; exit 1 otherwise. The same files still run under
`python3 -m pytest -q tests` where pytest is installed.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: run_contract_tests.py <tests-dir>", file=sys.stderr)
        return 1
    tests = Path(argv[0]).resolve()
    files = sorted(tests.glob("test_*.py")) if tests.is_dir() else []
    if not files:
        print(f"error: no test_*.py files in {tests}", file=sys.stderr)
        return 1
    ran = failed = skipped = 0
    for f in files:
        spec = importlib.util.spec_from_file_location(f"contract_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:  # noqa: BLE001 — an import error is a failure, reported with its cause
            failed += 1
            print(f"FAIL {f.name}: import error\n{traceback.format_exc(limit=3)}")
            continue
        for name, fn in sorted(vars(mod).items()):
            if not (name.startswith("test_") and inspect.isfunction(fn) and fn.__module__ == mod.__name__):
                continue
            if inspect.signature(fn).parameters:
                skipped += 1
                print(f"skip {f.name}::{name} (needs pytest fixtures)")
                continue
            ran += 1
            try:
                fn()
                print(f"ok   {f.name}::{name}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"FAIL {f.name}::{name}: {type(e).__name__}: {e}")
    print(f"{ran - failed} passed, {failed} failed, {skipped} skipped")
    return 0 if ran and not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
