#!/usr/bin/env python3
"""Feedback improvement loop: user feedback (+ eval failures) -> ranked backlog and regression eval cases.

Normalises ratings (1-5 or thumbs up/down) to a severity, groups issues deterministically (row tag
matching a taxonomy alias, else the first taxonomy keyword found in the comment, else `other`;
taxonomy in assets/taxonomy.json), ranks (bucket, feature) groups by frequency × mean severity
(= sum of severities), links eval failures to the same buckets, and writes an improvement backlog
with hypothesis, proposed fix type (prompt|retrieval|guardrail|model|data|UX) and owner role, plus
NEW eval cases in this repo's evals.json agent-case shape (id, prompt, expected) so the reported
failures become regression tests. Nothing is invented: prompts replay the recorded trace, or are
`[TO BE BASELINED — owner: Eval lead]` when no trace_id was recorded.

Usage:
  python3 -I improve.py --feedback feedback.csv --min-rows 10 --out-dir OUT
        [--eval-failures eval-failures.csv] [--taxonomy assets/taxonomy.json] [--cases-per-issue 3]

Feedback CSV: id, ts, rating (1-5 | up | down), comment, feature; optional tags (';'-separated),
trace_id. Eval-failures CSV: case_id, feature, failure_reason[, tags]. '#' lines are comments.
Severity from rating: 1 or down -> 3 · 2 -> 2 · 3 -> 1 · 4, 5 or up -> 0 (not an issue).

Outputs (in --out-dir): backlog.csv, new-eval-cases.json, improvement-report.md
(Top issues, Backlog, New eval cases, Regression gate).
Exit codes: 0 written · 1 fewer valid feedback rows than --min-rows (outputs still written) ·
2 missing/invalid required input. Stdlib only; no network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

DEFAULT_TAXONOMY = Path(__file__).resolve().parent.parent / "assets" / "taxonomy.json"
FIX_TYPES = ("prompt", "retrieval", "guardrail", "model", "data", "UX")
THUMBS = {"up": 0, "thumbs up": 0, "thumbs_up": 0, "+1": 0, "down": 3, "thumbs down": 3, "thumbs_down": 3, "-1": 3}
STAR_SEVERITY = {1: 3, 2: 2, 3: 1, 4: 0, 5: 0}
BACKLOG_COLUMNS = ["rank", "bucket", "feature", "feedback_count", "mean_severity", "score", "eval_failures",
                   "hypothesis", "fix_type", "owner", "feedback_ids", "trace_ids", "eval_case_ids"]


class InputError(Exception):
    """Missing or invalid required input -> exit 2."""


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"input file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO("\n".join(lines)))]


def load_taxonomy(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"taxonomy not found: {path}")
    buckets = json.loads(path.read_text(encoding="utf-8")).get("buckets", [])
    ids = [b["id"] for b in buckets]
    if "other" not in ids:
        raise InputError("taxonomy must contain an 'other' bucket")
    for b in buckets:
        if b.get("fix_type") not in FIX_TYPES:
            raise InputError(f"taxonomy bucket {b['id']}: fix_type must be one of {FIX_TYPES}")
    return buckets


def severity(rating: str):
    r = rating.strip().lower()
    if r in THUMBS:
        return THUMBS[r]
    if re.fullmatch(r"[1-5](\.0)?", r):
        return STAR_SEVERITY[int(float(r))]
    return None


def bucket_for(tags: str, text: str, taxonomy: list[dict]) -> tuple[str, str]:
    """(bucket id, basis) — tag alias first, then keyword, else other."""
    tag_list = [t.strip().lower() for t in re.split(r"[;|,]", tags or "") if t.strip()]
    for b in taxonomy:
        for t in tag_list:
            if t in [a.lower() for a in b.get("tag_aliases", [])]:
                return b["id"], f"tag:{t}"
    low = (text or "").lower()
    for b in taxonomy:
        for kw in b.get("keywords", []):
            if re.search(r"(?<![a-z0-9])" + re.escape(kw.lower()), low):  # keyword starts at a word start
                return b["id"], f"keyword:{kw}"
    return "other", "no match"


def load_feedback(path: Path, taxonomy: list[dict]) -> tuple[list[dict], list[dict]]:
    rows = read_rows(path)
    if not rows:
        raise InputError("feedback CSV has no rows")
    need = ("id", "rating", "comment", "feature")
    missing = [c for c in need if c not in rows[0]]
    if missing:
        raise InputError(f"feedback CSV missing columns: {', '.join(missing)}")
    valid, rejected = [], []
    for i, r in enumerate(rows, start=2):
        sev = severity(r.get("rating", ""))
        if not r.get("id") or not r.get("feature") or sev is None:
            rejected.append({"line": i, "reason": "missing id/feature or rating not 1-5/up/down"})
            continue
        b, basis = bucket_for(r.get("tags", ""), r.get("comment", ""), taxonomy)
        valid.append({"id": r["id"], "ts": r.get("ts", ""), "rating": r["rating"], "severity": sev,
                      "comment": r.get("comment", ""), "feature": r["feature"], "trace_id": r.get("trace_id", ""),
                      "bucket": b, "basis": basis})
    return valid, rejected


def load_failures(path: Path | None, taxonomy: list[dict]) -> list[dict]:
    if path is None:
        return []
    rows = read_rows(path)
    if rows and any(c not in rows[0] for c in ("case_id", "feature", "failure_reason")):
        raise InputError("eval-failures CSV needs columns case_id,feature,failure_reason")
    out = []
    for r in rows:
        if not r.get("case_id"):
            continue
        b, basis = bucket_for(r.get("tags", ""), r.get("failure_reason", ""), taxonomy)
        out.append({"case_id": r["case_id"], "feature": r.get("feature", ""), "failure_reason": r["failure_reason"],
                    "bucket": b, "basis": basis})
    return out


def build(feedback, rejected, failures, taxonomy, min_rows: int, per_issue: int) -> dict:
    tax = {b["id"]: b for b in taxonomy}
    order = [b["id"] for b in taxonomy]
    groups: dict[tuple[str, str], dict] = {}

    def group(bucket, feature):
        return groups.setdefault((bucket, feature), {"bucket": bucket, "feature": feature, "feedback": [], "failures": []})

    for f in feedback:
        if f["severity"] > 0:
            group(f["bucket"], f["feature"])["feedback"].append(f)
    for e in failures:
        group(e["bucket"], e["feature"])["failures"].append(e)

    items = []
    for (b, feat), g in groups.items():
        sevs = [f["severity"] for f in g["feedback"]]
        t = tax[b]
        items.append({
            "bucket": b, "feature": feat, "feedback_count": len(sevs),
            "mean_severity": round(sum(sevs) / len(sevs), 2) if sevs else 0,
            "score": sum(sevs), "eval_failures": len(g["failures"]),
            "hypothesis": t["hypothesis"], "fix_type": t["fix_type"],
            "owner": f"[TO BE BASELINED — owner: {t['owner_role']}]",
            "feedback_ids": ";".join(f["id"] for f in g["feedback"]),
            "trace_ids": ";".join(f["trace_id"] for f in g["feedback"] if f["trace_id"]),
            "eval_case_ids": ";".join(e["case_id"] for e in g["failures"]),
            "_feedback": g["feedback"],
        })
    items.sort(key=lambda x: (-x["score"], -x["eval_failures"], order.index(x["bucket"]), x["feature"]))
    for i, it in enumerate(items, start=1):
        it["rank"] = i

    cases = []
    for it in items:
        exemplars = sorted(it["_feedback"], key=lambda f: (-f["severity"], f["id"]))[:per_issue]
        for f in exemplars:
            if f["trace_id"]:
                prompt = f"Replay the user input recorded in trace {f['trace_id']} (feature {f['feature']})."
            else:
                prompt = (f"[TO BE BASELINED — owner: Eval lead] original user input for feedback {f['id']} "
                          f"(feature {f['feature']}); no trace_id was recorded.")
            expected = list(tax[it["bucket"]]["expected"])
            if f["comment"]:
                expected.append(f"Does not repeat the reported failure: \"{f['comment']}\"")
            cases.append({
                "id": f"fil-{it['bucket']}-{re.sub(r'[^a-z0-9]+', '-', f['feature'].lower()).strip('-')}-{re.sub(r'[^A-Za-z0-9]+', '-', f['id'])}",
                "prompt": prompt,
                "expected": expected,
                "provenance": {"feedback_id": f["id"], "trace_id": f["trace_id"] or None, "feature": f["feature"],
                               "bucket": it["bucket"], "backlog_rank": it["rank"], "basis": f["basis"]},
            })
    n_valid = len(feedback)
    return {
        "valid_rows": n_valid, "rejected_rows": len(rejected), "rejected": rejected[:50], "min_rows": min_rows,
        "sufficient": n_valid >= min_rows,
        "issue_rows": sum(1 for f in feedback if f["severity"] > 0),
        "positive_rows": sum(1 for f in feedback if f["severity"] == 0),
        "eval_failures": len(failures),
        "backlog": [{k: v for k, v in it.items() if k != "_feedback"} for it in items],
        "cases": cases,
    }


def write_backlog(path: Path, backlog: list[dict]) -> None:
    buf = io.StringIO()
    # QUOTE_ALL keeps adjacent numeric fields distinct for tools that scan the text for numbers
    w = csv.DictWriter(buf, fieldnames=BACKLOG_COLUMNS, lineterminator="\n", quoting=csv.QUOTE_ALL)
    w.writeheader()
    for it in backlog:
        w.writerow({k: it[k] for k in BACKLOG_COLUMNS})
    path.write_text(buf.getvalue(), encoding="utf-8")


def render(res: dict, top_n: int = 5) -> str:
    L = ["# Improvement report", "",
         f"Feedback rows: {res['valid_rows']} valid ({res['issue_rows']} issues, {res['positive_rows']} positive), "
         f"{res['rejected_rows']} rejected; eval failures linked: {res['eval_failures']}; minimum rows required: {res['min_rows']}.", ""]
    if not res["sufficient"]:
        L += [f"**INSUFFICIENT DATA** — {res['valid_rows']} valid rows < minimum {res['min_rows']}. "
              "Ranking is shown for inspection only; collect more feedback before prioritising.", ""]
    L += ["## Top issues", "", "Score = frequency × mean severity (sum of severities: 1★/down = 3, 2★ = 2, 3★ = 1).", "",
          "| Rank | Bucket | Feature | Feedback | Mean severity | Score | Eval failures | Fix type |",
          "|---|---|---|---|---|---|---|---|"]
    for it in res["backlog"][:top_n]:
        L.append(f"| {it['rank']} | {it['bucket']} | {it['feature']} | {it['feedback_count']} | {it['mean_severity']} | "
                 f"{it['score']} | {it['eval_failures']} | {it['fix_type']} |")
    if not res["backlog"]:
        L.append("| — | no issues found | — | 0 | 0 | 0 | 0 | — |")
    L += ["", "## Backlog", "", "| Rank | Bucket / feature | Hypothesis | Fix type | Owner | Evidence |", "|---|---|---|---|---|---|"]
    for it in res["backlog"]:
        ev = ", ".join(x for x in (f"feedback {it['feedback_ids']}" if it["feedback_ids"] else "",
                                    f"eval {it['eval_case_ids']}" if it["eval_case_ids"] else "") if x)
        L.append(f"| {it['rank']} | {it['bucket']} / {it['feature']} | {it['hypothesis']} | {it['fix_type']} | {it['owner']} | {ev} |")
    L += ["", "## New eval cases", "",
          f"{len(res['cases'])} new cases in `new-eval-cases.json` (shape: id, prompt, expected — merge into the feature's "
          "`evals/evals.json` or the llm-eval-harness golden set).", "", "| Case id | Backlog rank | Trace |", "|---|---|---|"]
    for c in res["cases"]:
        L.append(f"| {c['id']} | {c['provenance']['backlog_rank']} | {c['provenance']['trace_id'] or 'none recorded'} |")
    L += ["", "## Regression gate", "",
          "- Add every new case above to the eval set before the fix ships; replay inputs from the recorded traces.",
          "- Gate: every new case passes, and the existing suite pass rate does not fall below the last accepted baseline "
          "(use it as an `offline_eval` gate in ai-release-plan).",
          "- Linked eval failures stay in the suite; a fix is done only when they pass too.",
          "- Gate owner: [TO BE BASELINED — owner: Eval lead]."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--feedback", type=Path, required=True)
    ap.add_argument("--eval-failures", type=Path)
    ap.add_argument("--min-rows", required=True, help="minimum valid feedback rows to rank (owner-chosen)")
    ap.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    ap.add_argument("--cases-per-issue", type=int, default=3, help="max new eval cases per backlog item")
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if not args.min_rows.strip().isdigit():
            raise InputError(f"--min-rows must be a whole number, got {args.min_rows!r}")
        taxonomy = load_taxonomy(args.taxonomy)
        feedback, rejected = load_feedback(args.feedback, taxonomy)
        failures = load_failures(args.eval_failures, taxonomy)
        res = build(feedback, rejected, failures, taxonomy, int(args.min_rows), max(args.cases_per_issue, 1))
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_backlog(args.out_dir / "backlog.csv", res["backlog"])
    (args.out_dir / "new-eval-cases.json").write_text(
        json.dumps({"source": "feedback-improvement-loop", "cases": res["cases"]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (args.out_dir / "improvement-report.md").write_text(render(res), encoding="utf-8")
    if not res["sufficient"]:
        print(f"only {res['valid_rows']} valid feedback rows; minimum is {res['min_rows']}", file=sys.stderr)
        return 1
    print(f"backlog written: {len(res['backlog'])} items, {len(res['cases'])} new eval cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
