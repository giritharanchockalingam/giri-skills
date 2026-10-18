#!/usr/bin/env python3
"""Audit an eval dataset: coverage vs targets, duplicates, references, leakage, graders.

Engineers the dataset; it does not run evals (llm-eval-harness does). Applies the
leakage, coverage and verifier-coverage concerns of the upstream `eval-engineering` skill
(langchain-ai/langchain-skills, pinned in vendor/pins.json) to a flat eval set.

Dataset: JSONL (one object per line) or CSV. Columns (aliases accepted, case-insensitive):
  id | input (prompt, question) | expected (reference, answer, ideal) |
  category (or tags: ';', '|' or ',' separated) | grader (grader_type) [optional] |
  split [optional] | label [optional]
Targets CSV (optional): category, min_cases

Cleaning (eval-clean.jsonl), in order:
  1. drop rows whose input is empty
  2. drop rows whose reference is empty when the grader needs one (blank, exact, contains,
     regex, numeric, json_match, code); llm_judge, rubric, human and pairwise may omit it
  3. drop exact duplicates of an earlier row (same normalised input); flag conflicting
     references and cross-split leakage
  4. keep near-duplicates (token Jaccard >= --near-dup-threshold) but flag them
  5. give rows without an id `row-<line>`; suffix repeated ids `-dup<n>`
Normalisation: NFKC, lowercase, punctuation removed, whitespace collapsed.
Coverage counts use the cleaned set.

Usage: python3 -I audit_evals.py --dataset evals.jsonl [--targets targets.csv]
       [--near-dup-threshold 0.9] --out-dir OUT
Exit: 0 audited (and every category meets its target) · 1 a category below target or the
dataset lacks required columns · 2 dataset/targets file missing or unreadable. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ALIASES = {"id": ("id", "case_id"), "input": ("input", "prompt", "question"),
           "expected": ("expected", "reference", "answer", "ideal", "expected_output"),
           "category": ("category",), "tags": ("tags",), "grader": ("grader", "grader_type"),
           "split": ("split",), "label": ("label",)}
REFERENCE_FREE = {"llm_judge", "rubric", "human", "pairwise"}
KNOWN_GRADERS = REFERENCE_FREE | {"exact", "contains", "regex", "numeric", "json_match", "code"}
TBD_TARGET = "[TO BE BASELINED — owner: Eval owner]"


# ------------------------------------------------------------------ input

def _die(msg: str, code: int = 2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def read_dataset(path: Path) -> list[dict]:
    """Rows as dicts with lower-cased keys and string values; '_line' is the source line."""
    if not path.is_file():
        _die(f"dataset not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    rows: list[dict] = []
    if path.suffix.lower() in (".jsonl", ".ndjson") or (text.lstrip().startswith("{") and path.suffix.lower() != ".csv"):
        for n, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                _die(f"{path.name} line {n} is not JSON: {e}")
            if not isinstance(obj, dict):
                _die(f"{path.name} line {n} is not a JSON object")
            row = {str(k).strip().lower(): ("" if v is None else (v if isinstance(v, str) else json.dumps(v)))
                   for k, v in obj.items()}
            row["_line"] = n
            rows.append(row)
    else:
        reader = csv.DictReader(text.splitlines())
        for n, r in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "") for k, v in r.items()}
            row["_line"] = n
            rows.append(row)
    return rows


def read_targets(path: Path | None) -> dict[str, int] | None:
    if path is None:
        return None
    if not path.is_file():
        _die(f"targets file not found: {path}")
    out: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = [c.strip().lower() for c in (reader.fieldnames or [])]
        if "category" not in cols or "min_cases" not in cols:
            _die(f"targets file needs columns category,min_cases; has {cols}")
        for n, r in enumerate(reader, start=2):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
            if not r["category"]:
                continue
            try:
                v = float(r["min_cases"])
                if v < 0 or v != int(v):
                    raise ValueError
            except ValueError:
                _die(f"targets line {n}: min_cases must be a whole number >= 0, got {r['min_cases']!r}")
            out[r["category"].strip().lower()] = int(v)
    return out


def resolve_columns(rows: list[dict]) -> dict[str, str | None]:
    keys = set()
    for r in rows:
        keys |= set(r)
    return {canon: next((a for a in al if a in keys), None) for canon, al in ALIASES.items()}


# ------------------------------------------------------------------ helpers

def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> set[str]:
    return set(normalise(text).split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def categories_of(row: dict, cols: dict) -> list[str]:
    if cols["category"] and row.get(cols["category"], "").strip():
        return [row[cols["category"]].strip().lower()]
    if cols["tags"] and row.get(cols["tags"], "").strip():
        raw = row[cols["tags"]]
        try:  # tags may arrive as a JSON list from JSONL
            val = json.loads(raw)
            if isinstance(val, list):
                return [str(t).strip().lower() for t in val if str(t).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
        return [t.strip().lower() for t in re.split(r"[;|,]", raw) if t.strip()]
    return []


# ------------------------------------------------------------------ audit

def audit(rows: list[dict], cols: dict, targets: dict[str, int] | None, threshold: float) -> dict:
    issues: list[dict] = []

    def issue(kind: str, severity: str, line, rid, detail: str):
        issues.append({"type": kind, "severity": severity, "line": line, "id": rid, "detail": detail})

    clean: list[dict] = []
    seen_input: dict[str, dict] = {}
    id_count: dict[str, int] = {}
    splits_by_input: dict[str, set[str]] = {}
    for r in rows:
        line = r["_line"]
        rid = (r.get(cols["id"]) or "").strip() if cols["id"] else ""
        if not rid:
            rid = f"row-{line}"
            issue("missing_id", "low", line, rid, "no id; assigned from the line number")
        inp = (r.get(cols["input"]) or "").strip() if cols["input"] else ""
        exp = (r.get(cols["expected"]) or "").strip() if cols["expected"] else ""
        grader = (r.get(cols["grader"]) or "").strip().lower() if cols["grader"] else ""
        split = (r.get(cols["split"]) or "").strip().lower() if cols["split"] else ""
        cats = categories_of(r, cols)
        norm = normalise(inp)
        if split and norm:
            splits_by_input.setdefault(norm, set()).add(split)
        if not inp:
            issue("empty_input", "high", line, rid, "input is empty; row dropped")
            continue
        if not cats:
            issue("missing_category", "medium", line, rid, "no category or tags; counted as 'uncategorised'")
            cats = ["uncategorised"]
        if norm in seen_input:  # duplicates are dropped before per-row grader/reference findings
            first = seen_input[norm]
            if exp and first["expected"] and normalise(exp) != normalise(first["expected"]):
                issue("conflicting_reference", "high", line, rid,
                      f"same input as {first['id']} (line {first['_line']}) with a different reference; kept the first")
            else:
                issue("duplicate", "medium", line, rid, f"exact duplicate of {first['id']} (line {first['_line']}); row dropped")
            continue
        if grader and grader not in KNOWN_GRADERS:
            issue("unknown_grader", "low", line, rid, f"grader '{grader}' not in {sorted(KNOWN_GRADERS)}")
        if not exp and grader not in REFERENCE_FREE:
            issue("empty_reference", "high", line, rid,
                  f"reference is empty and grader '{grader or 'unspecified'}' needs one; row dropped")
            continue
        if not grader:
            issue("missing_grader", "medium", line, rid, "no grader type; a reference-based grader is assumed")
        id_count[rid] = id_count.get(rid, 0) + 1
        if id_count[rid] > 1:
            new = f"{rid}-dup{id_count[rid]}"
            issue("duplicate_id", "medium", line, rid, f"id repeated; renamed {new} in the cleaned set")
            rid = new
        rec = {"id": rid, "input": inp, "expected": exp, "category": cats[0], "tags": cats, "grader": grader or None,
               "split": split or None, "_line": line}
        if cols["label"]:
            rec["label"] = (r.get(cols["label"]) or "").strip() or None
        seen_input[norm] = rec
        clean.append(rec)

    # leakage across splits
    leaks = sorted(k for k, v in splits_by_input.items() if len(v) > 1)
    for k in leaks:
        rec = seen_input.get(k)
        issue("split_leakage", "high", rec["_line"] if rec else None, rec["id"] if rec else None,
              f"identical input appears in splits {sorted(splits_by_input[k])}; only the first occurrence is kept")

    # near-duplicates among kept rows
    toks = [tokens(c["input"]) for c in clean]
    near: list[tuple[int, int, float]] = []
    by_cat_only = len(clean) > 4000
    for i in range(len(clean)):
        for j in range(i + 1, len(clean)):
            if by_cat_only and clean[i]["category"] != clean[j]["category"]:
                continue
            s = jaccard(toks[i], toks[j])
            if s >= threshold:
                near.append((i, j, s))
    for i, j, s in near:
        issue("near_duplicate", "medium", clean[j]["_line"], clean[j]["id"],
              f"token Jaccard {round(s, 3)} with {clean[i]['id']}; kept, review whether it adds coverage")

    # coverage per category (cleaned set; a multi-tag row counts for each tag)
    counts: dict[str, int] = {}
    graders: dict[str, dict[str, int]] = {}
    no_grader: dict[str, int] = {}
    for c in clean:
        for t in c["tags"]:
            counts[t] = counts.get(t, 0) + 1
            g = c["grader"] or "unspecified"
            graders.setdefault(t, {})[g] = graders.setdefault(t, {}).get(g, 0) + 1
            if not c["grader"]:
                no_grader[t] = no_grader.get(t, 0) + 1
    raw_counts: dict[str, int] = {}
    for r in rows:
        for t in categories_of(r, cols) or ["uncategorised"]:
            raw_counts[t] = raw_counts.get(t, 0) + 1
    near_by_cat: dict[str, int] = {}
    for _, j, _ in near:
        near_by_cat[clean[j]["category"]] = near_by_cat.get(clean[j]["category"], 0) + 1
    cats = sorted(set(counts) | set(targets or {}))
    total = len(clean)
    coverage = []
    for cat in cats:
        n = counts.get(cat, 0)
        tgt = (targets or {}).get(cat)
        gap = max(0, tgt - n) if tgt is not None else None
        status = "NO TARGET" if tgt is None else ("BELOW" if gap else "OK")
        coverage.append({"category": cat, "raw_rows": raw_counts.get(cat, 0), "clean_cases": n,
                         "share_pct": round(100 * n / total, 1) if total else 0.0,
                         "min_cases": tgt, "gap": gap, "status": status,
                         "graders": graders.get(cat, {}), "rows_without_grader": no_grader.get(cat, 0),
                         "near_duplicates": near_by_cat.get(cat, 0)})
    present = [c["clean_cases"] for c in coverage if c["clean_cases"] > 0]
    balance = {"categories": len(present), "max_cases": max(present) if present else 0,
               "min_cases": min(present) if present else 0,
               "max_to_min_ratio": round(max(present) / min(present), 2) if present else None}
    labels = None
    if cols["label"]:
        labels = {}
        for c in clean:
            lab = c.get("label") or "(blank)"
            labels[lab] = labels.get(lab, 0) + 1
    below = [c for c in coverage if c["status"] == "BELOW"]
    verdict = "NOT GATED" if targets is None else ("FAIL" if below else "PASS")

    recs = []
    for c in coverage:
        if c["status"] == "BELOW":
            recs.append({"category": c["category"], "priority": "high",
                         "action": f"add {c['gap']} distinct case(s) to reach min_cases {c['min_cases']}"})
        if c["near_duplicates"]:
            recs.append({"category": c["category"], "priority": "medium",
                         "action": f"replace or justify {c['near_duplicates']} near-duplicate case(s) with distinct inputs"})
        if c["rows_without_grader"]:
            recs.append({"category": c["category"], "priority": "medium",
                         "action": f"assign a grader type to {c['rows_without_grader']} case(s)"})
        if c["status"] == "NO TARGET":
            recs.append({"category": c["category"], "priority": "low",
                         "action": f"set min_cases {TBD_TARGET}"})
    kinds = {i["type"] for i in issues}
    if "split_leakage" in kinds:
        recs.append({"category": "(all)", "priority": "high",
                     "action": "re-split so no input appears in more than one split; regenerate from eval-clean.jsonl"})
    if "conflicting_reference" in kinds:
        recs.append({"category": "(all)", "priority": "high",
                     "action": "resolve conflicting references with the domain owner before scoring"})
    if "empty_reference" in kinds:
        recs.append({"category": "(all)", "priority": "high",
                     "action": "write references for dropped rows or mark them with a reference-free grader"})

    for c in clean:
        c.pop("_line", None)
    return {"verdict": verdict, "rows_in": len(rows), "rows_clean": total, "rows_dropped": len(rows) - total,
            "near_dup_threshold": threshold, "near_dup_scope": "within category" if by_cat_only else "all pairs",
            "coverage": coverage, "balance": balance, "label_distribution": labels,
            "issue_counts": {k: sum(1 for i in issues if i["type"] == k) for k in sorted(kinds)},
            "issues": issues, "recommendations": recs, "clean": clean, "targets_supplied": targets is not None}


# ------------------------------------------------------------------ report

def gen_markdown(a: dict, ds_name: str, tg_name: str | None) -> str:
    L = [f"# Eval dataset audit — {ds_name}", "",
         "## Verdict", "",
         f"**{a['verdict']}** — {a['rows_in']} rows in, {a['rows_clean']} kept in `eval-clean.jsonl`, {a['rows_dropped']} dropped. "
         + ("Every category meets its target." if a["verdict"] == "PASS" else
            f"{sum(1 for c in a['coverage'] if c['status'] == 'BELOW')} category(ies) below target." if a["verdict"] == "FAIL" else
            f"No targets file supplied: coverage is reported, not gated; min_cases {TBD_TARGET}."),
         f"Targets: `{tg_name or 'none'}`. Near-duplicate threshold: token Jaccard >= {a['near_dup_threshold']} ({a['near_dup_scope']}; method parameter, override with --near-dup-threshold).",
         "Wraps eval-engineering from langchain-ai/langchain-skills (pinned in vendor/pins.json). This audit engineers the dataset; it does not run the evals.", "",
         "## Coverage", "",
         "| Category | Raw rows | Clean cases | Share % | Min cases | Gap | Status | Graders | Without grader |",
         "|---|---|---|---|---|---|---|---|---|"]
    for c in a["coverage"]:
        gr = ", ".join(f"{k} {v}" for k, v in sorted(c["graders"].items())) or "-"
        L.append(f"| {c['category']} | {c['raw_rows']} | {c['clean_cases']} | {c['share_pct']} | "
                 f"{c['min_cases'] if c['min_cases'] is not None else TBD_TARGET} | {c['gap'] if c['gap'] is not None else '-'} | "
                 f"{c['status']} | {gr} | {c['rows_without_grader']} |")
    b = a["balance"]
    L += ["", f"Balance: {b['categories']} non-empty categories; largest {b['max_cases']}, smallest {b['min_cases']}, "
          f"ratio {b['max_to_min_ratio']}.", ""]
    if a["label_distribution"]:
        L += ["| Label | Cases |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(a["label_distribution"].items())] + [""]
    L += ["## Quality issues", ""]
    if a["issues"]:
        L += ["| Type | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in a["issue_counts"].items()] + [""]
        L += ["| Severity | Type | Line | Id | Detail |", "|---|---|---|---|---|"]
        order = {"high": 0, "medium": 1, "low": 2}
        for i in sorted(a["issues"], key=lambda x: (order[x["severity"]], x["line"] or 0)):
            L.append(f"| {i['severity']} | {i['type']} | {i['line'] if i['line'] is not None else '-'} | {i['id'] or '-'} | {i['detail']} |")
    else:
        L.append("None found.")
    L += ["", "## Recommendations", ""]
    if a["recommendations"]:
        L += ["| Priority | Category | Action | Owner |", "|---|---|---|---|"]
        order = {"high": 0, "medium": 1, "low": 2}
        for r in sorted(a["recommendations"], key=lambda x: order[x["priority"]]):
            L.append(f"| {r['priority']} | {r['category']} | {r['action']} | Eval owner |")
    else:
        L.append("None: the dataset meets its targets with no quality issues.")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit an eval dataset; write eval-audit.json/.md and eval-clean.jsonl")
    ap.add_argument("--dataset", required=True, help="eval set JSONL or CSV (layout: assets/eval-dataset.example.jsonl)")
    ap.add_argument("--targets", help="CSV category,min_cases (layout: assets/coverage-targets.example.csv)")
    ap.add_argument("--near-dup-threshold", type=float, default=0.9,
                    help="token Jaccard at or above which two inputs are near-duplicates (default 0.9)")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    if not 0 < a.near_dup_threshold <= 1:
        _die("--near-dup-threshold must be in (0, 1]")
    ds = Path(a.dataset)
    rows = read_dataset(ds)
    targets = read_targets(Path(a.targets)) if a.targets else None
    cols = resolve_columns(rows)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    missing = [k for k in ("input", "expected") if not cols[k]]
    if not cols["category"] and not cols["tags"]:
        missing.append("category or tags")
    if not rows or missing:
        msg = "dataset is empty" if not rows else f"dataset lacks required column(s): {missing}"
        (out / "eval-audit.json").write_text(json.dumps({"verdict": "FAIL", "error": msg}, indent=2) + "\n", encoding="utf-8")
        (out / "eval-audit.md").write_text(f"# Eval dataset audit — {ds.name}\n\n## Verdict\n\n**FAIL** — {msg}.\n", encoding="utf-8")
        print(f"error: {msg}", file=sys.stderr)
        return 1
    result = audit(rows, cols, targets, a.near_dup_threshold)
    clean = result.pop("clean")
    with (out / "eval-clean.jsonl").open("w", encoding="utf-8") as f:
        for c in clean:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    result["inputs"] = {"dataset": ds.name, "targets": Path(a.targets).name if a.targets else None,
                        "columns": {k: v for k, v in cols.items() if v}}
    result["upstream"] = "eval-engineering (langchain-ai/langchain-skills, vendor/pins.json)"
    (out / "eval-audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "eval-audit.md").write_text(gen_markdown(result, ds.name, result["inputs"]["targets"]), encoding="utf-8")
    print(f"eval audit: {result['verdict']} — {result['rows_clean']}/{result['rows_in']} rows kept, "
          f"{len(result['issues'])} issue(s); wrote {out}")
    below = [c["category"] for c in result["coverage"] if c["status"] == "BELOW"]
    if below:
        print(f"  below target: {below}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
