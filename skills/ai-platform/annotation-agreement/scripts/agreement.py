#!/usr/bin/env python3
"""Inter-annotator agreement for AI evaluation or training labels.

Reads one row per rating (item_id, annotator, label) and computes, with the standard library only:
  - percent agreement (mean pairwise agreement over items with >= 2 ratings);
  - Cohen's kappa for every annotator pair (items both rated);
  - Fleiss' kappa when every rated item has the same number of ratings (>= 2);
  - Krippendorff's alpha, nominal, from the coincidence matrix (handles missing ratings);
  - per-label (category-specific) agreement o_kk / n_k from the coincidence matrix — for two
    annotators this is the specific agreement 2a / (2a + b + c);
  - confusion pairs: how often two annotators gave two different labels to the same item;
  - disputed items (any disagreement), worst first, with the plurality label;
  - with --guidelines: which labels the guideline text does not mention, and which low-agreement
    labels (agreement below the overall percent agreement) are among them.
Interpretation bands: Landis & Koch (1977) for kappa, Krippendorff's 0.667 / 0.800 for alpha —
conventions, not tests.

Inputs:
  --labels         CSV item_id,annotator,label (blank label = not rated; '#' lines are comments)
  --guidelines     optional Markdown annotation guidelines
  --min-agreement  optional minimum Krippendorff's alpha; below it the run exits 1
  --previous       optional agreement.json from an earlier labelling round (e.g. the pilot before a
                   guideline revision); the report adds "Change since previous round" (alpha, percent
                   agreement and per-label agreement then vs now, labels added or dropped). Only the
                   summary figures are read from it and stored as `previous_round`, so --verify
                   re-derives the section from agreement.json alone.

Usage:
  python3 -I agreement.py --labels l.csv [--guidelines g.md] [--min-agreement 0.667] \
      [--previous round1/agreement.json] --out-dir <dir>
  python3 -I agreement.py --verify <dir>/agreement-report.md --labels l.csv

Writes agreement.json, disputed-items.csv, label-agreement.csv, agreement-report.md.
Exit codes: 0 ok · 1 alpha below --min-agreement, no item with 2+ ratings (no score is
produced), or --verify mismatch · 2 input missing or unusable. Deterministic.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from itertools import combinations
from pathlib import Path

OWNER = "Annotation lead"
TBB = f"[TO BE BASELINED — owner: {OWNER}]"
OUTPUTS = ("agreement.json", "disputed-items.csv", "label-agreement.csv", "agreement-report.md")


class InputError(Exception):
    """A required input is missing or unusable (exit 2)."""


# ------------------------------------------------------------------ input

def read_labels(path: Path) -> list[tuple[str, str, str]]:
    if not path.is_file():
        raise InputError(f"labels file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise InputError("labels CSV is empty")
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in ("item_id", "annotator", "label") if c not in header]
    if missing:
        raise InputError(f"labels CSV lacks column(s) {missing}; header is {header}")
    out, seen = [], {}
    for i, row in enumerate(reader, start=2):
        r = {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
        item, ann, lab = r.get("item_id", ""), r.get("annotator", ""), r.get("label", "")
        if not item or not ann:
            raise InputError(f"labels line {i}: blank item_id or annotator")
        if not lab:
            continue  # not rated
        key = (item, ann)
        if key in seen:
            raise InputError(f"labels line {i}: annotator {ann!r} rated item {item!r} twice "
                             f"(first on line {seen[key]}); keep one rating per annotator per item")
        seen[key] = i
        out.append((item, ann, lab))
    if not out:
        raise InputError("labels CSV has no ratings")
    return out


def label_terms(label: str) -> list[str]:
    base = label.lower()
    return sorted({base, base.replace("_", " "), base.replace("-", " "), base.replace("_", "-")})


def defined_in(label: str, text: str) -> bool:
    low = text.lower()
    return any(re.search(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])", low) for t in label_terms(label))


# ------------------------------------------------------------------ statistics

def landis_koch(k: float | None) -> str:
    if k is None:
        return "n/a"
    if k < 0:
        return "poor"
    for hi, band in ((0.20, "slight"), (0.40, "fair"), (0.60, "moderate"), (0.80, "substantial")):
        if k <= hi:
            return band
    return "almost perfect"


def alpha_band(a: float | None) -> str:
    if a is None:
        return "n/a"
    if a >= 0.800:
        return "reliable (>= 0.800)"
    if a >= 0.667:
        return "tentative (0.667–0.800)"
    return "below 0.667"


def cohen_kappa(pairs: list[tuple[str, str]]) -> dict:
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n
    cats = sorted({x for p in pairs for x in p})
    pa = {c: sum(1 for a, _ in pairs if a == c) / n for c in cats}
    pb = {c: sum(1 for _, b in pairs if b == c) / n for c in cats}
    pe = sum(pa[c] * pb[c] for c in cats)
    k = None if pe >= 1.0 else (po - pe) / (1.0 - pe)
    return {"n_items": n, "observed": po, "expected": pe, "kappa": k}


def fleiss_kappa(counts: dict[str, dict[str, int]], cats: list[str]) -> dict:
    ms = {sum(c.values()) for c in counts.values()}
    if len(ms) != 1:
        return {"kappa": None, "reason": f"items have different numbers of ratings ({sorted(ms)}); "
                                         "Fleiss' kappa needs the same number per item — use alpha"}
    m = ms.pop()
    N = len(counts)
    pj = {c: sum(cnt.get(c, 0) for cnt in counts.values()) / (N * m) for c in cats}
    Pi = [(sum(v * v for v in cnt.values()) - m) / (m * (m - 1)) for cnt in counts.values()]
    pbar = sum(Pi) / N
    pe = sum(p * p for p in pj.values())
    k = None if pe >= 1.0 else (pbar - pe) / (1.0 - pe)
    return {"kappa": k, "raters_per_item": m, "items": N, "p_bar": pbar, "p_e": pe,
            "reason": "" if k is not None else "all ratings use one label; chance agreement is 1"}


def coincidence(counts: dict[str, dict[str, int]], cats: list[str]) -> dict:
    o = {c: {k: 0.0 for k in cats} for c in cats}
    for cnt in counts.values():
        m = sum(cnt.values())
        for c in cnt:
            for k in cnt:
                pairs = cnt[c] * (cnt[k] - (1 if c == k else 0))
                o[c][k] += pairs / (m - 1)
    n_c = {c: sum(o[c].values()) for c in cats}
    return {"o": o, "n_c": n_c, "n": sum(n_c.values())}


def kripp_alpha(co: dict, cats: list[str]) -> float | None:
    o, n_c, n = co["o"], co["n_c"], co["n"]
    d_o = sum(o[c][k] for c in cats for k in cats if c != k)
    d_e = sum(n_c[c] * n_c[k] for c in cats for k in cats if c != k)
    if n <= 1 or d_e == 0:
        return None
    return 1.0 - (n - 1) * d_o / d_e


def analyse(ratings: list[tuple[str, str, str]], min_agreement: float | None,
            defined: dict[str, bool] | None) -> dict:
    items: dict[str, dict[str, str]] = {}
    for item, ann, lab in ratings:
        items.setdefault(item, {})[ann] = lab
    annotators = sorted({a for _, a, _ in ratings})
    pairable = {i: r for i, r in items.items() if len(r) >= 2}
    single = sorted(i for i, r in items.items() if len(r) < 2)
    res = {"n_ratings": len(ratings), "n_items": len(items), "n_annotators": len(annotators),
           "annotators": annotators, "n_pairable_items": len(pairable), "single_rated_items": single,
           "min_agreement": min_agreement, "guidelines_supplied": defined is not None}
    if not pairable:
        res.update({"status": "insufficient",
                    "error": "no item has ratings from 2 or more annotators; agreement cannot be computed "
                             "(no score is reported)"})
        return res
    cats = sorted({lab for r in pairable.values() for lab in r.values()})
    counts = {i: {} for i in sorted(pairable)}
    for i in counts:
        for lab in pairable[i].values():
            counts[i][lab] = counts[i].get(lab, 0) + 1

    # per item agreement and disputed items
    item_rows = []
    for i, cnt in counts.items():
        m = sum(cnt.values())
        p_i = sum(v * (v - 1) for v in cnt.values()) / (m * (m - 1))
        ordered = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
        top = [lab for lab, v in ordered if v == ordered[0][1]]
        item_rows.append({"item_id": i, "n_ratings": m, "labels": ";".join(f"{lab}:{v}" for lab, v in ordered),
                          "majority": top[0] if len(top) == 1 else "tie", "agreement": p_i})
    percent = sum(r["agreement"] for r in item_rows) / len(item_rows)
    disputed = sorted((r for r in item_rows if r["agreement"] < 1.0), key=lambda r: (r["agreement"], r["item_id"]))

    # pairwise Cohen
    pairs = []
    for a, b in combinations(annotators, 2):
        both = [(items[i][a], items[i][b]) for i in sorted(items) if a in items[i] and b in items[i]]
        if not both:
            pairs.append({"pair": f"{a}|{b}", "n_items": 0, "observed": None, "kappa": None, "band": "n/a",
                          "note": "no items rated by both"})
            continue
        ck = cohen_kappa(both)
        pairs.append({"pair": f"{a}|{b}", "n_items": ck["n_items"], "observed": ck["observed"],
                      "expected": ck["expected"], "kappa": ck["kappa"], "band": landis_koch(ck["kappa"]),
                      "note": "" if ck["kappa"] is not None else "undefined: both used a single identical label"})

    fl = fleiss_kappa(counts, cats)
    fl["band"] = landis_koch(fl["kappa"])
    co = coincidence(counts, cats)
    alpha = kripp_alpha(co, cats)

    # per-label agreement and confusion pairs
    labels = []
    for c in cats:
        nc = co["n_c"][c]
        agr = co["o"][c][c] / nc if nc else None
        labels.append({"label": c, "n": sum(cnt.get(c, 0) for cnt in counts.values()), "agreement": agr,
                       "defined_in_guidelines": None if defined is None else bool(defined.get(c, False))})
    conf: dict[tuple[str, str], int] = {}
    for i, r in pairable.items():
        for a, b in combinations(sorted(r), 2):
            if r[a] != r[b]:
                key = tuple(sorted((r[a], r[b])))
                conf[key] = conf.get(key, 0) + 1
    confusion = [{"label_a": k[0], "label_b": k[1], "count": v}
                 for k, v in sorted(conf.items(), key=lambda kv: (-kv[1], kv[0]))]
    low = [lab for lab in labels if lab["agreement"] is not None and lab["agreement"] < percent]
    gaps = None if defined is None else sorted(lab["label"] for lab in low if not lab["defined_in_guidelines"])
    undefined_all = None if defined is None else sorted(lab["label"] for lab in labels if not lab["defined_in_guidelines"])
    gate = None
    if min_agreement is not None:
        gate = {"min_agreement": min_agreement, "alpha": alpha,
                "passed": alpha is not None and alpha >= min_agreement}
    res.update({"status": "ok", "labels_used": cats, "percent_agreement": percent,
                "krippendorff_alpha": alpha, "alpha_band": alpha_band(alpha), "fleiss": fl, "pairs": pairs,
                "label_agreement": labels, "low_agreement_labels": sorted(lab["label"] for lab in low),
                "guideline_gaps": gaps, "labels_not_in_guidelines": undefined_all,
                "confusion_pairs": confusion, "items": item_rows, "disputed": disputed,
                "coincidence": {"n": co["n"], "n_c": co["n_c"]}, "gate": gate})
    return res


# ------------------------------------------------------------------ rendering

def f3(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def render_disputed(r: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["item_id", "labels", "majority", "agreement"])
    for d in r.get("disputed", []):
        w.writerow([d["item_id"], d["labels"], d["majority"], f3(d["agreement"])])
    return buf.getvalue()


def render_labels(r: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["label", "n", "agreement", "defined_in_guidelines"])
    for lab in r.get("label_agreement", []):
        d = lab["defined_in_guidelines"]
        w.writerow([lab["label"], lab["n"], f3(lab["agreement"]), TBB if d is None else ("yes" if d else "no")])
    return buf.getvalue()


def load_previous(path: Path) -> dict:
    """Summary of an earlier round's agreement.json (status ok only)."""
    if not path.is_file():
        raise InputError(f"previous round file not found: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputError(f"previous round is not valid JSON: {e}") from e
    if not isinstance(doc, dict) or "krippendorff_alpha" not in doc or "label_agreement" not in doc:
        raise InputError("previous round must be an agreement.json from this script")
    if doc.get("status") != "ok":
        raise InputError("previous round has no agreement score (status is not ok); nothing to compare")
    labels = {}
    for lab in doc["label_agreement"]:
        if not isinstance(lab, dict) or "label" not in lab:
            raise InputError("previous round: label_agreement rows need a label")
        labels[str(lab["label"])] = lab.get("agreement")
    return {"source": path.name, "krippendorff_alpha": doc["krippendorff_alpha"],
            "percent_agreement": doc.get("percent_agreement"), "n_pairable_items": doc.get("n_pairable_items"),
            "n_disputed": len(doc.get("disputed") or []), "label_agreement": labels}


def _chg(now, was) -> str:
    return "n/a" if now is None or was is None else f"{now - was:+.3f}"


def render_previous(r: dict) -> list[str]:
    pv = r["previous_round"]
    a, pa = r["krippendorff_alpha"], pv["krippendorff_alpha"]
    trend = ("n/a" if a is None or pa is None else "improved" if a > pa + 1e-9 else
             "declined" if a < pa - 1e-9 else "unchanged")
    L = ["", "## Change since previous round", "",
         f"Compared with `{pv['source']}`: alpha {trend} ({f3(pa)} → {f3(a)}).", "",
         "| Statistic | Previous round | This round | Change |", "|---|---|---|---|",
         f"| Krippendorff's alpha | {f3(pa)} | {f3(a)} | {_chg(a, pa)} |",
         f"| Percent agreement | {f3(pv['percent_agreement'])} | {f3(r['percent_agreement'])} | "
         f"{_chg(r['percent_agreement'], pv['percent_agreement'])} |",
         f"| Disputed items | {pv['n_disputed']} | {len(r['disputed'])} | {len(r['disputed']) - pv['n_disputed']:+d} |",
         "", "| Label | Previous agreement | This round | Change |", "|---|---|---|---|"]
    now = {lab["label"]: lab["agreement"] for lab in r["label_agreement"]}
    for lab in sorted(set(now) | set(pv["label_agreement"])):
        if lab not in pv["label_agreement"]:
            L.append(f"| {lab} | — | {f3(now[lab])} | new label |")
        elif lab not in now:
            L.append(f"| {lab} | {f3(pv['label_agreement'][lab])} | — | not used this round |")
        else:
            L.append(f"| {lab} | {f3(pv['label_agreement'][lab])} | {f3(now[lab])} | "
                     f"{_chg(now[lab], pv['label_agreement'][lab])} |")
    worse = [lab for lab in sorted(now) if lab in pv["label_agreement"] and now[lab] is not None
             and pv["label_agreement"][lab] is not None and now[lab] < pv["label_agreement"][lab] - 1e-9]
    L += ["", "Labels whose agreement fell: " + (", ".join(f"`{x}`" for x in worse) +
                                                 f" — review their guideline wording ({TBB})." if worse else "none.")]
    return L


def render_md(r: dict, max_disputed: int = 25) -> str:
    L = ["# Annotation agreement", ""]
    if r["status"] != "ok":
        L += ["## Summary", "", f"**No agreement score: {r['error']}.**", "",
              f"- Ratings: {r['n_ratings']} across {r['n_items']} items from {r['n_annotators']} annotator(s).",
              f"- Items with 2+ ratings: 0. Collect a second, independent rating for a sample of items "
              f"({TBB}) and re-run.", "",
              "## Agreement", "", "Not computed — fewer than 2 annotators on every item.", "",
              "## Disputed items", "", "Not computed.", "",
              "## Guideline gaps", "", "Not computed.", "",
              "## Method & limits", "", "Agreement needs at least two independent ratings of the same item. "
              "The run exits 1 rather than report a score."]
        return "\n".join(L) + "\n"
    a, fl, gate = r["krippendorff_alpha"], r["fleiss"], r["gate"]
    if gate is None:
        verdict = f"No minimum agreement set ({TBB}); no gate applied."
    elif gate["passed"]:
        verdict = f"**PASS** — alpha {f3(a)} ≥ minimum {gate['min_agreement']:g}."
    else:
        verdict = (f"**FAIL** — alpha {f3(a)} is below the minimum {gate['min_agreement']:g}; "
                   "the run exits 1. Fix the guidelines and re-label the disputed items before using these labels.")
    L += ["## Summary", "", verdict, "",
          f"- Krippendorff's alpha (nominal): **{f3(a)}** — {r['alpha_band']}.",
          f"- Percent agreement (mean pairwise): {f3(r['percent_agreement'])}.",
          f"- Fleiss' kappa: {f3(fl['kappa'])}" + (f" ({fl['band']})." if fl["kappa"] is not None
                                                    else f" — {fl['reason']}."),
          f"- Data: {r['n_ratings']} ratings, {r['n_items']} items ({r['n_pairable_items']} with 2+ ratings), "
          f"{r['n_annotators']} annotators, {len(r['labels_used'])} labels.",
          f"- Disputed items: {len(r['disputed'])} of {r['n_pairable_items']}.",
          f"- Low-agreement labels (below the overall percent agreement): "
          f"{', '.join(r['low_agreement_labels']) or 'none'}."]
    if r["single_rated_items"]:
        L.append(f"- Items with a single rating, excluded from every statistic: {len(r['single_rated_items'])} "
                 f"({', '.join(r['single_rated_items'][:10])}{' …' if len(r['single_rated_items']) > 10 else ''}).")

    L += ["", "## Agreement", "", "| Statistic | Value | Interpretation (convention) |", "|---|---|---|",
          f"| Krippendorff's alpha (nominal) | {f3(a)} | {r['alpha_band']} |",
          f"| Fleiss' kappa | {f3(fl['kappa'])} | {fl['band'] if fl['kappa'] is not None else fl['reason']} |",
          f"| Percent agreement | {f3(r['percent_agreement'])} | not chance-corrected |",
          "", "### Annotator pairs (Cohen's kappa)", "",
          "| Pair | Items both rated | Observed agreement | Cohen's kappa | Landis & Koch band |", "|---|---|---|---|---|"]
    for p in r["pairs"]:
        a1, a2 = p["pair"].split("|", 1)
        note = f" ({p['note']})" if p.get("note") else ""
        L.append(f"| {a1} – {a2} | {p['n_items']} | {f3(p['observed'])} | {f3(p['kappa'])}{note} | {p['band']} |")
    L += ["", "### Per-label agreement", "",
          "Share of a label's pairable ratings whose paired rating on the same item is the same label "
          "(o_kk / n_k from the coincidence matrix).", "",
          "| Label | Ratings | Agreement | In guidelines |", "|---|---|---|---|"]
    for lab in r["label_agreement"]:
        d = lab["defined_in_guidelines"]
        L.append(f"| {lab['label']} | {lab['n']} | {f3(lab['agreement'])} | "
                 f"{TBB if d is None else ('yes' if d else 'no')} |")
    L += ["", "### Confusion pairs", ""]
    if r["confusion_pairs"]:
        L += ["| Label A | Label B | Disagreeing annotator pairs |", "|---|---|---|"]
        for c in r["confusion_pairs"]:
            L.append(f"| {c['label_a']} | {c['label_b']} | {c['count']} |")
    else:
        L.append("None: every annotator pair agreed on every shared item.")

    L += ["", "## Disputed items", ""]
    if r["disputed"]:
        L += [f"{len(r['disputed'])} item(s) with any disagreement, lowest agreement first"
              + (f" (first {max_disputed} shown; all in disputed-items.csv)." if len(r["disputed"]) > max_disputed else "."),
              "", "| Item | Labels (count) | Plurality | Agreement |", "|---|---|---|---|"]
        for d in r["disputed"][:max_disputed]:
            L.append(f"| {d['item_id']} | {d['labels'].replace(';', ', ')} | {d['majority']} | {f3(d['agreement'])} |")
        L += ["", "Route these to an adjudicator; do not resolve ties by majority vote without review."]
    else:
        L.append("None: every item with 2+ ratings has full agreement.")

    L += ["", "## Guideline gaps", ""]
    if not r["guidelines_supplied"]:
        L.append(f"No guidelines supplied: {TBB}. Low-agreement labels to define first: "
                 f"{', '.join(r['low_agreement_labels']) or 'none'}.")
    else:
        gaps = r["guideline_gaps"]
        L.append("Low-agreement labels the guidelines do not mention: " + (", ".join(f"`{g}`" for g in gaps)
                                                                         if gaps else "none") + ".")
        others = [x for x in r["labels_not_in_guidelines"] if x not in gaps]
        if others:
            L.append("")
            L.append("Other labels the guidelines do not mention (agreement at or above the overall level): "
                     + ", ".join(f"`{x}`" for x in others) + ".")
        top = [c for c in r["confusion_pairs"]][:3]
        if top:
            L += ["", "Clarify the boundary between the most-confused pairs: "
                  + "; ".join(f"`{c['label_a']}` vs `{c['label_b']}` ({c['count']})" for c in top) + "."]

    if r.get("previous_round"):
        L += render_previous(r)
    L += ["", "## Method & limits", "",
          "- Krippendorff's alpha (nominal) from the coincidence matrix: alpha = 1 − (n − 1) · Σ_{c≠k} o_ck / "
          "Σ_{c≠k} n_c·n_k; items with fewer than 2 ratings are not pairable and are excluded. Verified against "
          "Krippendorff's published worked example (alpha 0.743).",
          "- Fleiss' kappa (Fleiss 1971) only when every item has the same number of ratings; verified against "
          "the Wikipedia worked example (kappa 0.210).",
          "- Cohen's kappa (Cohen 1960) per annotator pair on the items both rated.",
          "- Percent agreement: mean over items of the share of agreeing annotator pairs; not chance-corrected.",
          "- Interpretation bands are conventions: Landis & Koch (1977) for kappa; Krippendorff's 0.800 / 0.667 for "
          "alpha. They are not significance tests.",
          "- Guideline check is a text match of each label name (case-insensitive; `_` and `-` read as spaces) — "
          "it shows a label is mentioned, not that its definition is clear.",
          "- Limits: nominal labels only (no ordinal or interval weighting); no confidence intervals; agreement "
          "measures consistency, not correctness — annotators can agree on a wrong label."]
    return "\n".join(L) + "\n"


def to_json(r: dict) -> str:
    def rnd(x):
        if isinstance(x, float):
            return round(x, 6)
        if isinstance(x, dict):
            return {k: rnd(v) for k, v in x.items()}
        if isinstance(x, list):
            return [rnd(v) for v in x]
        return x
    return json.dumps(rnd({**r, "tbd_owner": OWNER}), indent=2, sort_keys=True) + "\n"


def build(labels: Path, min_agreement: float | None, defined: dict[str, bool] | None,
          previous: dict | None = None) -> tuple[dict, dict[str, str], int]:
    r = analyse(read_labels(labels), min_agreement, defined)
    r["defined"] = defined
    if previous is not None:
        r["previous_round"] = previous
    files = {"agreement.json": to_json(r), "disputed-items.csv": render_disputed(r),
             "label-agreement.csv": render_labels(r), "agreement-report.md": render_md(r)}
    code = 0
    if r["status"] != "ok" or (r["gate"] is not None and not r["gate"]["passed"]):
        code = 1
    return r, files, code


def parse_min(raw: str | None) -> float | None:
    if raw in (None, ""):
        return None
    try:
        v = float(raw)
    except ValueError as e:
        raise InputError(f"--min-agreement must be a number, got {raw!r}") from e
    if not -1.0 <= v <= 1.0:
        raise InputError(f"--min-agreement must be between -1 and 1, got {v}")
    return v


def verify(path: Path, labels: Path) -> int:
    meta = path.parent / "agreement.json"
    if not path.is_file() or not meta.is_file() or path.name not in OUTPUTS:
        print(f"verify: {path} must be one of {OUTPUTS} next to agreement.json")
        return 1
    doc = json.loads(meta.read_text(encoding="utf-8"))
    try:
        _, files, _ = build(labels, doc.get("min_agreement"), doc.get("defined"), doc.get("previous_round"))
    except InputError as e:
        print(f"verify: cannot re-derive: {e}")
        return 1
    if path.read_text(encoding="utf-8") != files[path.name]:
        print(f"verify: {path.name} does not match the re-derived output")
        return 1
    print(f"verify: {path.name} matches the re-derived output")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", type=Path, help="CSV item_id,annotator,label")
    ap.add_argument("--guidelines", type=Path, help="optional Markdown annotation guidelines")
    ap.add_argument("--min-agreement", help="optional minimum Krippendorff's alpha (gate)")
    ap.add_argument("--previous", type=Path, help="optional agreement.json from an earlier labelling round")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--verify", type=Path, help="re-derive one output from --labels and its sibling agreement.json")
    a = ap.parse_args(argv)
    if a.labels is None:
        print("error: --labels is required", file=sys.stderr)
        return 2
    if a.verify:
        return verify(a.verify, a.labels)
    if a.out_dir is None:
        print("error: --out-dir is required", file=sys.stderr)
        return 2
    try:
        mn = parse_min(a.min_agreement)
        defined = None
        if a.guidelines is not None:
            if not a.guidelines.is_file():
                raise InputError(f"guidelines file not found: {a.guidelines}")
            text = a.guidelines.read_text(encoding="utf-8")
            labs = sorted({lab for _, _, lab in read_labels(a.labels)})
            defined = {lab: defined_in(lab, text) for lab in labs}
        previous = load_previous(a.previous) if a.previous is not None else None
        r, files, code = build(a.labels, mn, defined, previous)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (a.out_dir / name).write_text(text, encoding="utf-8")
    if r["status"] != "ok":
        print(f"error: {r['error']}", file=sys.stderr)
        return 1
    print(f"alpha {f3(r['krippendorff_alpha'])}, {len(r['disputed'])} disputed item(s); wrote {', '.join(OUTPUTS)} "
          f"to {a.out_dir}")
    if code:
        print(f"below minimum agreement: alpha {f3(r['krippendorff_alpha'])} < {mn:g}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
