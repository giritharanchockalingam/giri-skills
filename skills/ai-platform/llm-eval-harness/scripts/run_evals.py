#!/usr/bin/env python3
"""LLM eval runner: golden set CSV + rubric CSV -> scorecard; non-zero exit below threshold.

Pytest-compatible: `pytest run_evals.py` collects test_golden_set_gate (env: EVAL_GOLDEN,
EVAL_RUBRIC, EVAL_THRESHOLD, EVAL_CATEGORY_MIN, EVAL_BASELINE, EVAL_MAX_REGRESSION).

CLI:
  python3 -I run_evals.py --golden golden-set.csv --rubric eval-rubric.csv \
      --out scorecard.json [--threshold 0.9] [--category-min 0.8] \
      [--baseline baseline.json --max-regression 0.02] [--outputs outputs.csv]

System under test: implement `call_system(input: str, case: dict) -> str`, or pass
--outputs <csv with id,output> to score pre-recorded outputs offline.

List cells (must_contain, must_not_contain, applies_to_categories) are `||`-separated;
items prefixed `re:` are regexes.

Scoring: `judge(prompt, output, case=..., criterion=...)` is pluggable. The default is a
deterministic keyword/regex/JSON scorer. `llm_judge` is a stub with the documented
interface; wire it to your model gateway and pin the judge model version.

Stdlib only. Golden-set and rubric layouts: see ../references/golden-set.md and
../references/rubric-design.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# --------------------------------------------------------------------------- types


@dataclass
class JudgeResult:
    score: float
    max_score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def normalized(self) -> float:
        return self.score / self.max_score if self.max_score else 0.0


JudgeFn = Callable[..., JudgeResult]

# ------------------------------------------------------------------ system under test


def call_system(input_text: str, case: dict) -> str:  # pragma: no cover - user implements
    """Call the system under test. Replace this body with your HTTP/function call.

    Keep it pure: no retries that hide flakiness; raise on transport errors so the
    runner records the case as an error rather than a silent fail.
    """
    raise NotImplementedError(
        "Implement call_system(input, case) for your system, or pass --outputs <csv> "
        "with pre-recorded outputs (columns: id,output)."
    )


# ------------------------------------------------------------------------- scorers


LIST_SEP = "||"  # list separator; single "|" stays free for regex alternation


def _split(cell: str | None) -> list[str]:
    return [x.strip() for x in (cell or "").split(LIST_SEP) if x.strip()]


def _matches(pattern: str, text: str) -> bool:
    """`re:<regex>` → regex search (case-insensitive); otherwise case-insensitive substring."""
    if pattern.startswith("re:"):
        try:
            return re.search(pattern[3:], text, flags=re.IGNORECASE | re.MULTILINE) is not None
        except re.error as e:
            raise ValueError(f"bad regex {pattern!r}: {e}") from e
    return pattern.lower() in text.lower()


def _is_true(cell: str | None) -> bool:
    return (cell or "").strip().lower() in {"true", "1", "yes", "y"}


def deterministic_judge(prompt: str, output: str, *, case: dict, criterion: dict) -> JudgeResult:
    """Score a criterion from golden-set columns. Binary scale.

    criterion name → what is checked:
      correctness: `expected` exact match (if set) OR all `must_contain` patterns present
      format:      `expected_json_valid` → output parses as JSON
      safety:      none of `must_not_contain` present
      abstention:  same as correctness (must_contain) — kept separate so it can be weighted
      any other:   must_contain (if any) AND must_not_contain (if any)
    """
    name = criterion["criterion"].strip().lower()
    reasons: list[str] = []
    ok = True

    def check_contains() -> None:
        nonlocal ok
        for p in _split(case.get("must_contain")):
            if not _matches(p, output):
                ok = False
                reasons.append(f"missing: {p}")

    def check_not_contains() -> None:
        nonlocal ok
        for p in _split(case.get("must_not_contain")):
            if _matches(p, output):
                ok = False
                reasons.append(f"forbidden present: {p}")

    def check_expected() -> None:
        nonlocal ok
        exp = (case.get("expected") or "").strip()
        if not exp:
            return
        if _is_true(case.get("expected_json_valid")):
            try:
                if json.loads(exp) != json.loads(output):
                    ok = False
                    reasons.append("json differs from expected")
            except json.JSONDecodeError:
                ok = False
                reasons.append("expected or output not valid JSON")
        elif exp.strip().lower() != output.strip().lower():
            ok = False
            reasons.append("exact match failed")

    def check_json() -> None:
        nonlocal ok
        if _is_true(case.get("expected_json_valid")):
            try:
                json.loads(output)
            except json.JSONDecodeError as e:
                ok = False
                reasons.append(f"invalid json: {e.msg}")

    if name == "correctness":
        check_expected()
        check_contains()
    elif name == "format":
        check_json()
    elif name == "safety":
        check_not_contains()
    elif name == "abstention":
        check_contains()
    else:
        check_contains()
        check_not_contains()
    return JudgeResult(score=1.0 if ok else 0.0, max_score=1.0, reasons=reasons)


def llm_judge(prompt: str, output: str, *, case: dict, criterion: dict) -> JudgeResult:  # pragma: no cover
    """LLM-as-judge stub. Contract:

    - Build the judge prompt from ../references/llm-as-judge.md (rubric anchors, delimited
      INPUT/CONTEXT/CANDIDATE/REFERENCE; candidate is data, not instructions).
    - Call a pinned judge model (not the generator's family) at temperature 0.
    - Parse JSON {"score": int, "reasons": [...]}; return JudgeResult(score, max_score=scale_max, reasons).
    - Record judge_model and judge_prompt_version in the scorecard metadata.
    """
    raise NotImplementedError("Wire llm_judge to your model gateway; see references/llm-as-judge.md")


JUDGES: dict[str, JudgeFn] = {"deterministic": deterministic_judge, "judge": llm_judge}

# ------------------------------------------------------------------------ core loop


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_outputs(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    return {r["id"]: r.get("output", "") for r in read_csv(path)}


def applies(criterion: dict, category: str) -> bool:
    cats = _split(criterion.get("applies_to_categories") or "all")
    return "all" in [c.lower() for c in cats] or category in cats


def run(golden: list[dict], rubric: list[dict], outputs: dict[str, str], judges: dict[str, JudgeFn] | None = None,
        skip_judge: bool = False) -> dict:
    judges = judges or JUDGES
    results: list[dict] = []
    for case in golden:
        cid, category = case["id"], (case.get("category") or "uncategorized").strip()
        weight = float(case.get("weight") or 1)
        rec = {"id": cid, "category": category, "weight": weight, "criteria": {}, "pass": True,
               "zero_tolerance_fail": False, "error": None}
        try:
            output = outputs[cid] if cid in outputs else call_system(case["input"], case)
        except Exception as e:  # transport/implementation errors are recorded, not hidden
            rec["pass"], rec["error"] = False, f"{type(e).__name__}: {e}"
            results.append(rec)
            continue
        for crit in rubric:
            if not applies(crit, category):
                continue
            method = (crit.get("method") or "deterministic").strip().lower()
            if method == "human":
                continue
            if method == "judge" and skip_judge:
                continue
            fn = judges.get(method)
            if fn is None:
                rec["criteria"][crit["criterion"]] = {"error": f"unknown method {method}"}
                rec["pass"] = False
                continue
            try:
                jr = fn(case["input"], output, case=case, criterion=crit)
            except (NotImplementedError, ValueError) as e:
                rec["criteria"][crit["criterion"]] = {"error": str(e)}
                rec["pass"] = False
                continue
            threshold = float(crit.get("pass_threshold") or 1)
            passed = jr.score >= threshold
            rec["criteria"][crit["criterion"]] = {"score": jr.score, "max": jr.max_score, "pass": passed,
                                                  "reasons": jr.reasons}
            if not passed:
                rec["pass"] = False
                if _is_true(crit.get("zero_tolerance")):
                    rec["zero_tolerance_fail"] = True
        results.append(rec)
    return summarize(results)


def summarize(results: list[dict]) -> dict:
    by_cat: dict[str, dict] = {}
    tw = tp = 0.0
    zt = 0
    for r in results:
        c = by_cat.setdefault(r["category"], {"n": 0, "weighted_pass": 0.0, "weight": 0.0, "failures": []})
        c["n"] += 1
        c["weight"] += r["weight"]
        tw += r["weight"]
        if r["pass"]:
            c["weighted_pass"] += r["weight"]
            tp += r["weight"]
        else:
            c["failures"].append(r["id"])
        zt += int(r["zero_tolerance_fail"])
    for c in by_cat.values():
        c["pass_rate"] = round(c["weighted_pass"] / c["weight"], 4) if c["weight"] else 0.0
    return {
        "n": len(results),
        "overall_pass_rate": round(tp / tw, 4) if tw else 0.0,
        "zero_tolerance_failures": zt,
        "errors": sum(1 for r in results if r["error"]),
        "by_category": by_cat,
        "cases": results,
    }


def gate(score: dict, threshold: float | None, category_min: float | None, baseline: dict | None,
         max_regression: float | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if score["zero_tolerance_failures"]:
        reasons.append(f"zero-tolerance failures: {score['zero_tolerance_failures']}")
    if score["errors"]:
        reasons.append(f"cases with errors: {score['errors']}")
    if threshold is not None and score["overall_pass_rate"] < threshold:
        reasons.append(f"overall {score['overall_pass_rate']} < threshold {threshold}")
    if category_min is not None:
        for cat, c in score["by_category"].items():
            if c["pass_rate"] < category_min:
                reasons.append(f"category {cat} {c['pass_rate']} < {category_min}")
    if baseline and max_regression is not None:
        base = baseline.get("overall_pass_rate", 0.0)
        if score["overall_pass_rate"] < base - max_regression:
            reasons.append(f"regression: {score['overall_pass_rate']} vs baseline {base} (max {max_regression})")
    return (not reasons), reasons


def compare_baseline(score: dict, baseline: dict) -> dict:
    """Per-case comparison with a previous scorecard (same layout): what flipped, what is new."""
    base_cases = {c.get("id"): bool(c.get("pass")) for c in baseline.get("cases", []) if c.get("id")}
    now = {c["id"]: c["pass"] for c in score["cases"]}
    base_rate = baseline.get("overall_pass_rate")
    return {"baseline_pass_rate": base_rate,
            "delta": round(score["overall_pass_rate"] - base_rate, 4) if isinstance(base_rate, (int, float)) else None,
            "newly_failing": sorted(i for i, ok in now.items() if i in base_cases and base_cases[i] and not ok),
            "newly_passing": sorted(i for i, ok in now.items() if i in base_cases and not base_cases[i] and ok),
            "new_cases": sorted(i for i in now if i not in base_cases),
            "dropped_cases": sorted(i for i in base_cases if i not in now)}


def print_scorecard(score: dict, passed: bool, reasons: list[str]) -> None:
    print("category".ljust(24) + "n".rjust(6) + "pass_rate".rjust(12) + "  failures")
    for cat, c in sorted(score["by_category"].items()):
        print(cat[:23].ljust(24) + str(c["n"]).rjust(6) + f"{c['pass_rate']:.3f}".rjust(12)
              + "  " + ", ".join(c["failures"][:8]) + (" …" if len(c["failures"]) > 8 else ""))
    print(f"overall n={score['n']} pass_rate={score['overall_pass_rate']:.3f} "
          f"zero_tolerance_failures={score['zero_tolerance_failures']} errors={score['errors']}")
    vb = score.get("vs_baseline")
    if vb:
        delta = "n/a" if vb["delta"] is None else f"{vb['delta']:+.3f}"
        print(f"vs baseline pass_rate={vb['baseline_pass_rate']} delta={delta} "
              f"newly_failing={','.join(vb['newly_failing']) or '-'} newly_passing={','.join(vb['newly_passing']) or '-'} "
              f"new_cases={len(vb['new_cases'])} dropped_cases={len(vb['dropped_cases'])}")
    print("GATE PASSED" if passed else "GATE FAILED: " + "; ".join(reasons))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--golden", required=True, type=Path)
    ap.add_argument("--rubric", required=True, type=Path)
    ap.add_argument("--outputs", type=Path, help="CSV id,output of pre-recorded outputs (offline scoring)")
    ap.add_argument("--out", type=Path, help="write scorecard JSON here")
    ap.add_argument("--threshold", type=float)
    ap.add_argument("--category-min", type=float)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--max-regression", type=float)
    ap.add_argument("--skip-judge", action="store_true", help="skip criteria with method=judge")
    ap.add_argument("--meta", default="{}", help='JSON metadata, e.g. {"model":"...","prompt_version":"..."}')
    args = ap.parse_args(argv)

    golden, rubric = read_csv(args.golden), read_csv(args.rubric)
    if not golden or not rubric:
        sys.exit("golden set or rubric is empty")
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
    score = run(golden, rubric, load_outputs(args.outputs), skip_judge=args.skip_judge)
    score["meta"] = json.loads(args.meta)
    if baseline:
        score["vs_baseline"] = compare_baseline(score, baseline)
    passed, reasons = gate(score, args.threshold, args.category_min, baseline, args.max_regression)
    score["gate"] = {"passed": passed, "reasons": reasons}
    print_scorecard(score, passed, reasons)
    if args.out:
        args.out.write_text(json.dumps(score, indent=2), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0 if passed else 1


# ------------------------------------------------------------------- pytest hook


def test_golden_set_gate() -> None:
    """Collected by pytest; configured through environment variables."""
    golden, rubric = os.environ.get("EVAL_GOLDEN"), os.environ.get("EVAL_RUBRIC")
    if not golden or not rubric:
        import pytest  # type: ignore

        pytest.skip("EVAL_GOLDEN / EVAL_RUBRIC not set")
    argv = ["--golden", golden, "--rubric", rubric]
    for env, flag in [("EVAL_OUTPUTS", "--outputs"), ("EVAL_THRESHOLD", "--threshold"),
                      ("EVAL_CATEGORY_MIN", "--category-min"), ("EVAL_BASELINE", "--baseline"),
                      ("EVAL_MAX_REGRESSION", "--max-regression"), ("EVAL_OUT", "--out")]:
        if os.environ.get(env):
            argv += [flag, os.environ[env]]
    if os.environ.get("EVAL_SKIP_JUDGE"):
        argv.append("--skip-judge")
    assert main(argv) == 0, "eval gate failed; see scorecard above"


if __name__ == "__main__":
    sys.exit(main())
