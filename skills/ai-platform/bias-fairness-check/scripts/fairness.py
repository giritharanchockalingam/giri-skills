#!/usr/bin/env python3
"""Group fairness check for a binary classifier: predictions CSV -> fairness.json + fairness-report.md.

Per group (sensitive attribute): n, base rate, selection rate, accuracy, TPR, FPR, precision
(and mean score when a `score` column exists). Fairness metrics across groups:

  demographic_parity_difference  max - min selection rate                  (lower is better)
  disparate_impact_ratio         min over groups of selection rate / reference group's  (higher is better)
  equal_opportunity_difference   max - min TPR                             (lower is better)
  equalized_odds_difference      max(TPR gap, FPR gap)                     (lower is better)

No threshold is built in. Thresholds come from --thresholds (CSV metric,threshold); a metric
without one is reported as `[TO BE BASELINED — owner: Responsible AI lead]` and never counted
as a pass. The four-fifths rule applies only if the user sets disparate_impact_ratio=0.8.
Reference group: --reference-group, else the group with the highest selection rate (stated).
Groups with n below --min-sample are flagged (still included in the metrics — not hidden).

Usage:
  python3 -I fairness.py --predictions preds.csv [--thresholds thresholds.csv]
      [--sensitive-attr group] [--reference-group A] [--min-sample 30] [--positive-label 1]
      --out <dir>            # writes <dir>/fairness.json and <dir>/fairness-report.md
  python3 -I fairness.py --predictions preds.csv --json   # JSON to stdout only

Exit codes: 0 no supplied threshold breached · 1 a metric breaches a supplied threshold ·
2 required input missing or unusable (file, column, non-binary label). Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

OWNER = "Responsible AI lead"
TBB = f"[TO BE BASELINED — owner: {OWNER}]"
# metric -> (direction, description). "max" = value must be <= threshold; "min" = value must be >= threshold
METRICS = {
    "demographic_parity_difference": ("max", "max - min selection rate across groups"),
    "disparate_impact_ratio": ("min", "lowest selection rate / reference-group selection rate"),
    "equal_opportunity_difference": ("max", "max - min true positive rate across groups"),
    "equalized_odds_difference": ("max", "max of the TPR gap and the FPR gap across groups"),
}
ALIASES = {"equalised_odds_difference": "equalized_odds_difference",
           "statistical_parity_difference": "demographic_parity_difference"}
TRUE_VALUES = {"1", "true", "yes", "y", "t"}
FALSE_VALUES = {"0", "false", "no", "n", "f"}
DP = 4  # decimals used in both JSON and Markdown so every reported number traces


class InputError(Exception):
    """A required input is missing or unusable (exit 2)."""


def r(x):
    return None if x is None else round(float(x), DP)


def div(a: float, b: float):
    return None if b == 0 else a / b


def to_bool(raw: str, positive: str, col: str, line: int) -> bool:
    """0/1, true/false, yes/no; or, with a custom positive label, that label vs anything else."""
    v, pos = (raw or "").strip().lower(), positive.strip().lower()
    if v == "":
        raise InputError(f"line {line}: column '{col}' is empty")
    if v == pos:
        return True
    if pos in TRUE_VALUES:
        if v in TRUE_VALUES:
            return True
        if v in FALSE_VALUES:
            return False
        raise InputError(f"line {line}: column '{col}' value {raw!r} is not binary (0/1, true/false, yes/no)")
    return False


def load_predictions(path: Path, attr: str, positive: str) -> tuple[list[dict], bool]:
    if not path.is_file():
        raise InputError(f"predictions file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in (attr, "label", "prediction") if c not in header]
        if missing:
            raise InputError(f"predictions CSV lacks column(s) {missing}; header is {header}")
        has_score = "score" in header
        rows = []
        for i, row in enumerate(reader, start=2):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            if not any(row.values()):
                continue
            g = row.get(attr, "")
            if g == "":
                raise InputError(f"line {i}: empty sensitive attribute '{attr}'")
            rec = {"group": g, "y": to_bool(row["label"], positive, "label", i),
                   "p": to_bool(row["prediction"], positive, "prediction", i), "score": None}
            if has_score and row.get("score", "") != "":
                try:
                    rec["score"] = float(row["score"])
                except ValueError as e:
                    raise InputError(f"line {i}: score {row['score']!r} is not numeric") from e
            rows.append(rec)
    if not rows:
        raise InputError("predictions CSV has no data rows")
    return rows, has_score


def load_thresholds(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    if not path.is_file():
        raise InputError(f"thresholds file not found: {path}")
    out: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        if "metric" not in header or "threshold" not in header:
            raise InputError(f"thresholds CSV needs columns metric,threshold; header is {header}")
        for i, row in enumerate(reader, start=2):
            m = (row.get("metric") or "").strip()
            t = (row.get("threshold") or "").strip()
            if not m or m.startswith("#"):
                continue
            m = ALIASES.get(m, m)
            if m not in METRICS:
                raise InputError(f"line {i}: unknown metric {m!r}; expected one of {sorted(METRICS)}")
            if t == "":
                continue  # blank = not yet baselined
            try:
                out[m] = float(t)
            except ValueError as e:
                raise InputError(f"line {i}: threshold {t!r} for {m} is not numeric") from e
    return out


def group_stats(rows: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for rec in rows:
        s = stats.setdefault(rec["group"], {"n": 0, "tp": 0, "fp": 0, "tn": 0, "fn": 0, "scores": []})
        s["n"] += 1
        key = ("tp" if rec["p"] else "fn") if rec["y"] else ("fp" if rec["p"] else "tn")
        s[key] += 1
        if rec["score"] is not None:
            s["scores"].append(rec["score"])
    out = {}
    for g in sorted(stats):
        s = stats[g]
        pos, neg, sel = s["tp"] + s["fn"], s["fp"] + s["tn"], s["tp"] + s["fp"]
        out[g] = {
            "n": s["n"], "positives": pos, "negatives": neg, "predicted_positive": sel,
            "tp": s["tp"], "fp": s["fp"], "tn": s["tn"], "fn": s["fn"],
            "base_rate": div(pos, s["n"]), "selection_rate": div(sel, s["n"]),
            "accuracy": div(s["tp"] + s["tn"], s["n"]), "tpr": div(s["tp"], pos),
            "fpr": div(s["fp"], neg), "precision": div(s["tp"], sel),
            "mean_score": (sum(s["scores"]) / len(s["scores"])) if s["scores"] else None,
        }
    return out


def gap(groups: dict, key: str):
    vals = [v[key] for v in groups.values() if v[key] is not None]
    return (max(vals) - min(vals)) if len(vals) >= 2 else None


def compute(rows: list[dict], thresholds: dict[str, float], reference: str | None,
            min_sample: int | None) -> dict:
    groups = group_stats(rows)
    if len(groups) < 2:
        raise InputError(f"need at least 2 groups to compare; found {list(groups)}")
    notes = []
    if reference is not None:
        if reference not in groups:
            raise InputError(f"reference group {reference!r} not in data; groups are {list(groups)}")
        ref, ref_basis = reference, "supplied"
    else:
        ref = max(groups, key=lambda g: (groups[g]["selection_rate"], g))
        ref_basis = "highest selection rate (no reference supplied)"
        notes.append(f"No reference group supplied; used '{ref}' (highest selection rate).")
    ref_sr = groups[ref]["selection_rate"]
    for g, v in groups.items():
        v["dir_vs_reference"] = r(div(v["selection_rate"], ref_sr)) if ref_sr else None
        v["selection_rate_diff_vs_reference"] = r(v["selection_rate"] - ref_sr)
        v["tpr_diff_vs_reference"] = (r(v["tpr"] - groups[ref]["tpr"])
                                      if v["tpr"] is not None and groups[ref]["tpr"] is not None else None)
        v["small_sample"] = bool(min_sample is not None and v["n"] < min_sample)
        for k in ("base_rate", "selection_rate", "accuracy", "tpr", "fpr", "precision", "mean_score"):
            v[k] = r(v[k])
        if v["tpr"] is None:
            notes.append(f"Group '{g}' has no actual positives: TPR undefined, excluded from TPR gaps.")
        if v["fpr"] is None:
            notes.append(f"Group '{g}' has no actual negatives: FPR undefined, excluded from FPR gaps.")

    ratios = [v["dir_vs_reference"] for g, v in groups.items() if g != ref and v["dir_vs_reference"] is not None]
    tpr_gap, fpr_gap = gap(groups, "tpr"), gap(groups, "fpr")
    values = {
        "demographic_parity_difference": gap(groups, "selection_rate"),
        "disparate_impact_ratio": min(ratios) if ratios else None,
        "equal_opportunity_difference": tpr_gap,
        "equalized_odds_difference": (max(x for x in (tpr_gap, fpr_gap) if x is not None)
                                      if (tpr_gap is not None or fpr_gap is not None) else None),
    }
    if ref_sr == 0:
        notes.append(f"Reference group '{ref}' has selection rate 0: disparate impact ratio undefined.")

    metrics, breaches, unbaselined = {}, [], []
    for m, (direction, desc) in METRICS.items():
        val = r(values[m])
        thr = thresholds.get(m)
        if thr is None:
            status = "to_be_baselined"
            unbaselined.append(m)
        elif val is None:
            status = "undefined"
        else:
            ok = val <= thr if direction == "max" else val >= thr
            status = "pass" if ok else "breach"
            if not ok:
                breaches.append(m)
        metrics[m] = {"value": val, "threshold": thr, "rule": "<=" if direction == "max" else ">=",
                      "status": status, "definition": desc,
                      "owner": OWNER if thr is None else None}
    if "disparate_impact_ratio" in thresholds and thresholds["disparate_impact_ratio"] == 0.8:
        notes.append("disparate_impact_ratio threshold 0.8 supplied: this is the four-fifths rule.")
    small = [g for g, v in groups.items() if v["small_sample"]]
    if breaches:
        verdict = "FAIL"
    elif unbaselined or any(metrics[m]["status"] == "undefined" for m in metrics):
        verdict = "INCOMPLETE"
    else:
        verdict = "PASS"
    return {
        "verdict": verdict, "breaches": breaches, "to_be_baselined": unbaselined,
        "reference_group": ref, "reference_basis": ref_basis,
        "n_total": sum(v["n"] for v in groups.values()), "n_groups": len(groups),
        "min_sample": min_sample, "small_groups": small,
        "metrics": metrics, "groups": groups, "notes": notes,
    }


def fmt(x) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int):
        return str(x)
    return f"{x:.{DP}f}"


def render_md(res: dict, attr: str) -> str:
    L = ["# Fairness report", ""]
    L += ["## Verdict", ""]
    v = res["verdict"]
    L.append(f"**{v}** — {res['n_total']} predictions across {res['n_groups']} groups of `{attr}`; "
             f"reference group `{res['reference_group']}` ({res['reference_basis']}).")
    L.append("")
    if res["breaches"]:
        L.append("Breached thresholds: " + ", ".join(f"`{m}`" for m in res["breaches"]) + ".")
    if res["to_be_baselined"]:
        L.append("Not assessed (no threshold supplied, not counted as a pass): "
                 + ", ".join(f"`{m}` {TBB}" for m in res["to_be_baselined"]) + ".")
    if v == "PASS":
        L.append("Every metric is within its supplied threshold.")
    L += ["", "## Metrics", "", "| Metric | Value | Rule | Threshold | Status |", "|---|---|---|---|---|"]
    for m, d in res["metrics"].items():
        thr = fmt(d["threshold"]) if d["threshold"] is not None else TBB
        L.append(f"| `{m}` | {fmt(d['value'])} | {d['rule']} | {thr} | {d['status']} |")
    L += ["", "Definitions: " + "; ".join(f"`{m}` = {d['definition']}" for m, d in res["metrics"].items()) + "."]
    L += ["", "## Per-group", "",
          "| Group | n | Base rate | Selection rate | Accuracy | TPR | FPR | Precision | DIR vs ref | Mean score | Small |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for g, s in res["groups"].items():
        L.append(f"| {g}{' (ref)' if g == res['reference_group'] else ''} | {s['n']} | {fmt(s['base_rate'])} | "
                 f"{fmt(s['selection_rate'])} | {fmt(s['accuracy'])} | {fmt(s['tpr'])} | {fmt(s['fpr'])} | "
                 f"{fmt(s['precision'])} | {fmt(s['dir_vs_reference'])} | {fmt(s['mean_score'])} | "
                 f"{fmt(s['small_sample'])} |")
    L += ["", "## Small groups", ""]
    if res["min_sample"] is None:
        L.append(f"Minimum sample size not supplied: {TBB}. No group was flagged.")
    elif res["small_groups"]:
        L.append(f"Groups with n below {res['min_sample']} (included in the metrics, estimates unstable; "
                 "collect more data before acting on them): " + ", ".join(f"`{g}`" for g in res["small_groups"]) + ".")
    else:
        L.append(f"No group has n below {res['min_sample']}.")
    L += ["", "## Limits", "",
          "- Group metrics on one labelled sample; no confidence intervals. Differences on small groups may be noise.",
          "- Fairness definitions conflict: equal selection rates and equal error rates cannot generally both hold "
          "when base rates differ. Which metric governs is a policy decision for the accountable owner.",
          "- Only the supplied sensitive attribute is checked; intersectional groups are not assessed unless encoded in that column.",
          "- Labels are taken as ground truth; label bias is not detected by this check.",
          "- Thresholds are user-supplied; this report does not establish legal compliance."]
    for n in res["notes"]:
        L.append(f"- Note: {n}")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--predictions", type=Path, required=True, help="CSV: <sensitive attr>,label,prediction[,score]")
    ap.add_argument("--thresholds", type=Path, help="CSV: metric,threshold (no defaults)")
    ap.add_argument("--sensitive-attr", default="group", help="sensitive-attribute column (default: group)")
    ap.add_argument("--reference-group", help="reference group for the disparate impact ratio")
    ap.add_argument("--min-sample", type=int, help="flag groups with n below this")
    ap.add_argument("--positive-label", default="1", help="label value treated as positive (default: 1)")
    ap.add_argument("--out", type=Path, help="directory for fairness.json and fairness-report.md")
    ap.add_argument("--json", action="store_true", help="print the JSON result to stdout")
    a = ap.parse_args(argv)
    try:
        if a.min_sample is not None and a.min_sample < 1:
            raise InputError("--min-sample must be >= 1")
        rows, _ = load_predictions(a.predictions, a.sensitive_attr, a.positive_label)
        res = compute(rows, load_thresholds(a.thresholds), a.reference_group, a.min_sample)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    res["sensitive_attribute"] = a.sensitive_attr
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "fairness.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        (a.out / "fairness-report.md").write_text(render_md(res, a.sensitive_attr), encoding="utf-8")
        print(f"{res['verdict']}: wrote {a.out / 'fairness.json'} and {a.out / 'fairness-report.md'}")
    if a.json or not a.out:
        print(json.dumps(res, indent=2))
    if res["breaches"]:
        print(f"threshold breached: {', '.join(res['breaches'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
