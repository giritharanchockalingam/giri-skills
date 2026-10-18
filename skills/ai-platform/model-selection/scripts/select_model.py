#!/usr/bin/env python3
"""Weighted, constraint-gated model selection: candidates + criteria (+ workload) -> ranking.

    python3 -I scripts/select_model.py --candidates candidates.csv --criteria criteria.csv \
        [--workload workload.csv] --out-dir runs/x
    python3 -I scripts/select_model.py --verify runs/x/ranking.json     # recompute and cross-check

The skill supplies NO model facts. Every price, latency, context size and benchmark score comes
from the candidates CSV, with a row-level `source` and `as_of`; gaps become
`[TO BE BASELINED — owner: <role>]`.

Candidates CSV (assets/candidates-template.csv). Required columns:
  model, provider, hosting (api|self-host), context_tokens, price_in_per_1m, price_out_per_1m,
  p95_latency_ms, source, as_of
  plus any number of user-supplied score columns (benchmark / eval results) and text columns
  (e.g. region) that criteria can reference. `notes` is free text.

Criteria CSV (assets/criteria-template.csv). Columns:
  criterion   a candidates column, or `monthly_cost_usd` (derived; needs --workload)
  weight      >= 0; rows with weight 0 are constraint-only
  direction   higher|lower (required when weight > 0)
  hard_min, hard_max   optional numeric hard constraints
  hard_in     optional allowed text values, `;`-separated (e.g. `self-host` or `eu;uk`)

Workload CSV (key,value,... layout of assets/workload-template.csv), optional. Keys:
  tokens_in_per_request, tokens_out_per_request, requests_per_month
  monthly_cost_usd = requests_per_month * (tokens_in * price_in_per_1m + tokens_out * price_out_per_1m) / 1e6

Method (references/scoring-method.md):
  1. Hard constraints eliminate candidates, each with the reasons. A missing value on a
     hard-constrained criterion eliminates (the constraint cannot be verified).
  2. Survivors are min-max normalised per weighted criterion (direction-aware; all-equal -> 1.0;
     a missing value scores 0 and is listed as a gap).
  3. Score = sum(normalised weight x normalised value); rank by score desc, then model name.
  4. Sensitivity: each weight x0.8 and x1.2 (others renormalised); report whether the winner changes.

Writes ranking.json and decision.md (Recommendation, Criteria, Eliminated, Scores, Sensitivity,
Sources, Gaps). Every number in decision.md is present in ranking.json.
Exit 0 ok · 1 no candidate survives the hard constraints (or --verify mismatch) · 2 input error.
Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

REQUIRED_COLS = ["model", "provider", "hosting", "context_tokens", "price_in_per_1m", "price_out_per_1m",
                 "p95_latency_ms", "source", "as_of"]
HOSTING = {"api", "self-host"}
WORKLOAD_KEYS = ["tokens_in_per_request", "tokens_out_per_request", "requests_per_month"]
DERIVED = {"monthly_cost_usd"}
PERTURB = 0.20
OWNER_FACTS = "Model evaluation lead"
OWNER_WEIGHTS = "Solution architect"


class InputError(Exception):
    """Raised for missing or malformed inputs (exit 2)."""


def tbd(owner: str) -> str:
    return f"[TO BE BASELINED — owner: {owner}]"


def num(v):
    """Parse a numeric cell; '' -> None. Raises ValueError on non-numeric text."""
    s = (v or "").strip().replace(",", "")
    if s == "":
        return None
    x = float(s)
    if math.isnan(x) or math.isinf(x):
        raise ValueError(v)
    return x


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise InputError(f"file not found: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values() if isinstance(v, str))]
    return [{(k or "").strip(): (v or "").strip() if isinstance(v, str) else "" for k, v in r.items()} for r in rows]


def load_candidates(path: Path) -> list[dict]:
    rows = read_csv(path)
    if not rows:
        raise InputError(f"{path.name}: no candidate rows")
    missing = [c for c in REQUIRED_COLS if c not in rows[0]]
    if missing:
        raise InputError(f"{path.name}: missing required columns {missing}")
    seen = set()
    for i, r in enumerate(rows, start=2):
        if not r["model"]:
            raise InputError(f"{path.name} line {i}: empty model")
        if r["model"] in seen:
            raise InputError(f"{path.name} line {i}: duplicate model {r['model']!r}")
        seen.add(r["model"])
        if r["hosting"].lower() not in HOSTING:
            raise InputError(f"{path.name} line {i}: hosting must be api|self-host, got {r['hosting']!r}")
        r["hosting"] = r["hosting"].lower()
    return rows


def load_criteria(path: Path, cand_cols: set[str], have_workload: bool) -> list[dict]:
    rows = read_csv(path)
    if not rows:
        raise InputError(f"{path.name}: no criteria rows")
    for c in ("criterion", "weight"):
        if c not in rows[0]:
            raise InputError(f"{path.name}: missing required column {c!r}")
    out, seen = [], set()
    for i, r in enumerate(rows, start=2):
        name = r["criterion"]
        if not name:
            raise InputError(f"{path.name} line {i}: empty criterion")
        if name in seen:
            raise InputError(f"{path.name} line {i}: duplicate criterion {name!r}")
        seen.add(name)
        if name not in cand_cols and name not in DERIVED:
            raise InputError(f"{path.name} line {i}: criterion {name!r} is not a candidates column")
        if name == "monthly_cost_usd" and not have_workload:
            raise InputError("criterion 'monthly_cost_usd' needs --workload (tokens in/out per request, requests/month)")
        try:
            w = num(r.get("weight", ""))
            hmin, hmax = num(r.get("hard_min", "")), num(r.get("hard_max", ""))
        except ValueError:
            raise InputError(f"{path.name} line {i}: weight/hard_min/hard_max must be numeric") from None
        if w is None or w < 0:
            raise InputError(f"{path.name} line {i}: weight must be a number >= 0")
        direction = (r.get("direction") or "").lower()
        if w > 0 and direction not in ("higher", "lower"):
            raise InputError(f"{path.name} line {i}: direction must be higher|lower for weighted criterion {name!r}")
        allowed = [a.strip() for a in (r.get("hard_in") or "").split(";") if a.strip()]
        out.append({"criterion": name, "weight": w, "direction": direction or None,
                    "hard_min": hmin, "hard_max": hmax, "hard_in": allowed})
    total = sum(c["weight"] for c in out)
    if total <= 0:
        raise InputError(f"{path.name}: at least one criterion needs weight > 0")
    for c in out:
        c["weight_normalised"] = round(c["weight"] / total, 4)
    return out


def load_workload(path: Path) -> dict:
    vals = {}
    for r in read_csv(path):
        k = r.get("key", "")
        if k:
            try:
                v = num(r.get("value", ""))
            except ValueError:
                raise InputError(f"{path.name}: non-numeric value for {k}") from None
            if v is not None:
                vals[k] = {"value": v, "source": r.get("source", ""), "as_of": r.get("as_of_date", r.get("as_of", ""))}
    missing = [k for k in WORKLOAD_KEYS if k not in vals]
    if missing:
        raise InputError(f"{path.name}: missing workload keys {missing}")
    return vals


def monthly_cost(cand: dict, wl: dict):
    pin, pout = num(cand["price_in_per_1m"]), num(cand["price_out_per_1m"])
    if pin is None or pout is None:
        return None
    w = {k: wl[k]["value"] for k in WORKLOAD_KEYS}
    return round(w["requests_per_month"] * (w["tokens_in_per_request"] * pin + w["tokens_out_per_request"] * pout) / 1e6, 2)


def value_of(cand: dict, crit: str):
    """Raw value for a criterion: float for numeric cells, str for text, None for blank."""
    if crit == "monthly_cost_usd":
        return cand.get("monthly_cost_usd")
    raw = cand.get(crit, "")
    if raw == "":
        return None
    try:
        return num(raw)
    except ValueError:
        return raw


def fmt(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def eliminate(cands: list[dict], criteria: list[dict]):
    survivors, eliminated = [], []
    for c in cands:
        reasons = []
        for cr in criteria:
            if cr["hard_min"] is None and cr["hard_max"] is None and not cr["hard_in"]:
                continue
            v = value_of(c, cr["criterion"])
            name = cr["criterion"]
            if v is None:
                reasons.append(f"no value for {name}; hard constraint cannot be verified")
                continue
            if cr["hard_in"]:
                if str(fmt(v)).lower() not in {a.lower() for a in cr["hard_in"]}:
                    reasons.append(f"{name} = {fmt(v)} not in allowed {{{', '.join(cr['hard_in'])}}}")
            if cr["hard_min"] is not None or cr["hard_max"] is not None:
                if not isinstance(v, float):
                    reasons.append(f"{name} = {v!r} is not numeric; numeric hard constraint cannot be verified")
                    continue
                if cr["hard_min"] is not None and v < cr["hard_min"]:
                    reasons.append(f"{name} = {fmt(v)} below hard_min {fmt(cr['hard_min'])}")
                if cr["hard_max"] is not None and v > cr["hard_max"]:
                    reasons.append(f"{name} = {fmt(v)} above hard_max {fmt(cr['hard_max'])}")
        if reasons:
            eliminated.append({"model": c["model"], "provider": c["provider"], "reasons": reasons})
        else:
            survivors.append(c)
    return survivors, eliminated


def normalise(survivors: list[dict], criteria: list[dict]):
    """Return {model: {criterion: normalised or None}}, plus gaps and per-criterion min/max."""
    norm = {c["model"]: {} for c in survivors}
    gaps, bounds = [], {}
    for cr in criteria:
        if cr["weight"] <= 0:
            continue
        name = cr["criterion"]
        vals = {}
        for c in survivors:
            v = value_of(c, name)
            if v is None:
                gaps.append({"model": c["model"], "criterion": name, "issue": "missing value; scored 0",
                             "owner": OWNER_FACTS})
            elif not isinstance(v, float):
                raise InputError(f"weighted criterion {name!r} has non-numeric value {v!r} for {c['model']}")
            else:
                vals[c["model"]] = v
        lo = min(vals.values()) if vals else None
        hi = max(vals.values()) if vals else None
        bounds[name] = {"min": lo, "max": hi}
        for c in survivors:
            m = c["model"]
            if m not in vals:
                norm[m][name] = None
            elif hi == lo:
                norm[m][name] = 1.0
            elif cr["direction"] == "higher":
                norm[m][name] = round((vals[m] - lo) / (hi - lo), 4)
            else:
                norm[m][name] = round((hi - vals[m]) / (hi - lo), 4)
    return norm, gaps, bounds


def scores_for(norm: dict, weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    return {m: round(sum((weights[k] / total) * (n.get(k) or 0.0) for k in weights), 4) for m, n in norm.items()}


def rank(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda m: (-scores[m], m))


def sensitivity(norm: dict, weights: dict[str, float], base_winner: str | None):
    runs = []
    if not norm:
        return {"perturbation_pct": int(PERTURB * 100), "runs": runs, "winner_changes": False, "challengers": []}
    for k in weights:
        for f in (1 - PERTURB, 1 + PERTURB):
            w = dict(weights)
            w[k] = w[k] * f
            sc = scores_for(norm, w)
            win = rank(sc)[0]
            runs.append({"criterion": k, "factor": round(f, 2), "winner": win, "winner_score": sc[win],
                         "changes_winner": win != base_winner})
    challengers = sorted({r["winner"] for r in runs if r["changes_winner"]})
    return {"perturbation_pct": int(round(PERTURB * 100)), "runs": runs,
            "winner_changes": bool(challengers), "challengers": challengers}


def build(cands_path: Path, crit_path: Path, wl_path: Path | None) -> dict:
    cands = load_candidates(cands_path)
    wl = load_workload(wl_path) if wl_path else None
    cols = set(cands[0].keys())
    criteria = load_criteria(crit_path, cols, wl is not None)
    for c in cands:
        c["monthly_cost_usd"] = monthly_cost(c, wl) if wl else None
    survivors, eliminated = eliminate(cands, criteria)
    norm, gaps, bounds = normalise(survivors, criteria)
    weights = {c["criterion"]: c["weight"] for c in criteria if c["weight"] > 0}
    sc = scores_for(norm, weights)
    order = rank(sc)
    by_model = {c["model"]: c for c in survivors}
    ranking = []
    for i, m in enumerate(order, start=1):
        c = by_model[m]
        wsum = sum(weights.values())
        ranking.append({
            "rank": i, "model": m, "provider": c["provider"], "hosting": c["hosting"], "score": sc[m],
            "raw": {k: value_of(c, k) for k in weights},
            "normalised": norm[m],
            "contribution": {k: round(weights[k] / wsum * (norm[m].get(k) or 0.0), 4) for k in weights},
            "monthly_cost_usd": c["monthly_cost_usd"],
            "source": c["source"] or tbd(OWNER_FACTS), "as_of": c["as_of"] or tbd(OWNER_FACTS),
        })
    for c in cands:
        if c["model"] in by_model:
            if not c["source"] or not c["as_of"]:
                gaps.append({"model": c["model"], "criterion": "source/as_of", "issue": "provenance missing",
                             "owner": OWNER_FACTS})
            if wl and c["monthly_cost_usd"] is None:
                gaps.append({"model": c["model"], "criterion": "monthly_cost_usd",
                             "issue": "price_in/price_out missing; monthly cost not computed", "owner": OWNER_FACTS})
    winner = order[0] if order else None
    sens = sensitivity(norm, weights, winner)
    rec = None
    if winner:
        second = ranking[1] if len(ranking) > 1 else None
        rec = {"model": winner, "score": sc[winner],
               "runner_up": second["model"] if second else None,
               "runner_up_score": second["score"] if second else None,
               "margin": round(sc[winner] - second["score"], 4) if second else None,
               "robust_to_weight_changes": not sens["winner_changes"]}
    return {
        "inputs": {"candidates": cands_path.name, "criteria": crit_path.name,
                   "workload": wl_path.name if wl_path else None},
        "workload": {k: v for k, v in (wl or {}).items()},
        "criteria": criteria,
        "bounds": bounds,
        "candidates_total": len(cands),
        "survivors": len(survivors),
        "eliminated": eliminated,
        "ranking": ranking,
        "sensitivity": sens,
        "recommendation": rec,
        "gaps": gaps,
        "sources": [{"model": c["model"], "provider": c["provider"],
                     "source": c["source"] or tbd(OWNER_FACTS), "as_of": c["as_of"] or tbd(OWNER_FACTS)}
                    for c in cands],
    }


# ------------------------------------------------------------------ report

def render(res: dict) -> str:
    L = []
    rec = res["recommendation"]
    crit_w = [c for c in res["criteria"] if c["weight"] > 0]
    title = f"Select {rec['model']}" if rec else "No candidate meets the hard constraints"
    L += [f"# Model selection — {title}", ""]
    L += ["## Recommendation", ""]
    if rec:
        top = res["ranking"][0]
        line = (f"**{rec['model']}** ({top['provider']}, {top['hosting']}) ranks first of {res['survivors']} surviving "
                f"candidates with weighted score {rec['score']}")
        if rec["runner_up"]:
            line += f"; runner-up {rec['runner_up']} at {rec['runner_up_score']} (margin {rec['margin']})"
        L.append(line + ".")
        if top["monthly_cost_usd"] is not None:
            L.append(f"- Monthly cost at the supplied workload: ${top['monthly_cost_usd']:,.2f}.")
        if rec["robust_to_weight_changes"]:
            L.append(f"- Weight sensitivity: the winner holds when any single weight moves "
                     f"±{res['sensitivity']['perturbation_pct']}%.")
        else:
            L.append(f"- Weight sensitivity: the winner changes under a ±{res['sensitivity']['perturbation_pct']}% "
                     f"weight change (challengers: {', '.join(res['sensitivity']['challengers'])}); confirm weights "
                     f"{tbd(OWNER_WEIGHTS)} before committing.")
        if res["gaps"]:
            L.append(f"- {len(res['gaps'])} data gap(s) listed under Gaps; resolve before sign-off.")
    else:
        L.append(f"None of the {res['candidates_total']} candidates survives the hard constraints. Relax a constraint "
                 f"or add candidates {tbd(OWNER_WEIGHTS)}.")
    L += ["", "## Criteria", "", "| Criterion | Weight (normalised) | Direction | Hard constraint |", "|---|---|---|---|"]
    for c in res["criteria"]:
        hard = []
        if c["hard_min"] is not None:
            hard.append(f"≥ {fmt(c['hard_min'])}")
        if c["hard_max"] is not None:
            hard.append(f"≤ {fmt(c['hard_max'])}")
        if c["hard_in"]:
            hard.append("in {" + ", ".join(c["hard_in"]) + "}")
        L.append(f"| {c['criterion']} | {c['weight_normalised']} | {c['direction'] or 'constraint only'} | "
                 f"{'; '.join(hard) or '—'} |")
    L += ["", "## Eliminated", ""]
    if res["eliminated"]:
        L += ["| Model | Provider | Reasons |", "|---|---|---|"]
        for e in res["eliminated"]:
            L.append(f"| {e['model']} | {e['provider']} | {'; '.join(e['reasons'])} |")
    else:
        L.append(f"None — all {res['candidates_total']} candidates meet the hard constraints.")
    L += ["", "## Scores", ""]
    if res["ranking"]:
        L.append("Cells show raw value → normalised (0–1). Score = Σ normalised weight × normalised value.")
        L.append("")
        head = "| Rank | Model | Hosting | Score | " + " | ".join(c["criterion"] for c in crit_w) + " | Monthly cost (USD) |"
        L += [head, "|" + "---|" * (5 + len(crit_w))]
        for r in res["ranking"]:
            cells = []
            for c in crit_w:
                k = c["criterion"]
                n = r["normalised"].get(k)
                cells.append(f"{fmt(r['raw'][k])} → {fmt(n) if n is not None else '0 (missing)'}")
            cost = f"{r['monthly_cost_usd']:.2f}" if r["monthly_cost_usd"] is not None else "—"
            L.append(f"| {r['rank']} | {r['model']} | {r['hosting']} | {r['score']} | " + " | ".join(cells) + f" | {cost} |")
    else:
        L.append("No survivors to score.")
    L += ["", "## Sensitivity", ""]
    s = res["sensitivity"]
    if s["runs"]:
        L.append(f"Each weight scaled by −{s['perturbation_pct']}% and +{s['perturbation_pct']}% in turn; "
                 f"other weights renormalised; normalised values unchanged.")
        L += ["", "| Criterion | Winner at −20% | Winner at +20% |".replace("20", str(s["perturbation_pct"])),
              "|---|---|---|"]
        for k in [c["criterion"] for c in crit_w]:
            lo = next(r for r in s["runs"] if r["criterion"] == k and r["factor"] < 1)
            hi = next(r for r in s["runs"] if r["criterion"] == k and r["factor"] > 1)
            L.append(f"| {k} | {lo['winner']} ({lo['winner_score']}) | {hi['winner']} ({hi['winner_score']}) |")
        L += ["", "Verdict: " + ("winner stable under every single-weight change." if not s["winner_changes"]
                                  else f"winner changes — challengers: {', '.join(s['challengers'])}.")]
    else:
        L.append("Not run: no surviving candidates.")
    L += ["", "## Sources", "",
          f"Every model fact is user-supplied in `{res['inputs']['candidates']}`; this skill supplies none.", "",
          "| Model | Provider | Source | As of |", "|---|---|---|---|"]
    for src in res["sources"]:
        L.append(f"| {src['model']} | {src['provider']} | {src['source']} | {src['as_of']} |")
    if res["workload"]:
        L += ["", f"Workload from `{res['inputs']['workload']}`:", "", "| Key | Value | Source | As of |", "|---|---|---|---|"]
        for k, v in res["workload"].items():
            L.append(f"| {k} | {fmt(v['value'])} | {v['source'] or tbd(OWNER_FACTS)} | {v['as_of'] or tbd(OWNER_FACTS)} |")
    L += ["", "## Gaps", ""]
    if res["gaps"]:
        L += ["| Model | Item | Issue | Resolution |", "|---|---|---|---|"]
        for g in res["gaps"]:
            L.append(f"| {g['model']} | {g['criterion']} | {g['issue']} | {tbd(g['owner'])} |")
    else:
        L.append("None.")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ verify

def verify(path: Path) -> list[str]:
    """Recompute scores, ranks and weights from ranking.json; return a list of problems."""
    probs = []
    res = json.loads(path.read_text(encoding="utf-8"))
    crit = [c for c in res["criteria"] if c["weight"] > 0]
    wsum = sum(c["weight_normalised"] for c in crit)
    if abs(wsum - 1) > 0.001 * max(1, len(crit)):
        probs.append(f"normalised weights sum to {wsum}, not 1")
    prev = None
    for i, r in enumerate(res["ranking"], start=1):
        if r["rank"] != i:
            probs.append(f"rank {r['rank']} at position {i}")
        expect = sum(c["weight"] for c in crit)
        s = sum(c["weight"] / expect * (r["normalised"].get(c["criterion"]) or 0.0) for c in crit)
        if abs(s - r["score"]) > 0.0002:
            probs.append(f"{r['model']}: score {r['score']} != recomputed {round(s, 4)}")
        for k, n in r["normalised"].items():
            if n is not None and not (0 <= n <= 1):
                probs.append(f"{r['model']}: normalised {k} = {n} outside [0,1]")
        if prev is not None and r["score"] > prev:
            probs.append("ranking not sorted by score")
        prev = r["score"]
    if res["survivors"] != len(res["ranking"]):
        probs.append("survivors count != ranking length")
    if res["survivors"] + len(res["eliminated"]) != res["candidates_total"]:
        probs.append("survivors + eliminated != candidates_total")
    if res["ranking"] and (res["recommendation"] or {}).get("model") != res["ranking"][0]["model"]:
        probs.append("recommendation is not the top-ranked model")
    return probs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", type=Path, help="candidates CSV (model facts, user-supplied)")
    ap.add_argument("--criteria", type=Path, help="criteria CSV (weights, directions, hard constraints)")
    ap.add_argument("--workload", type=Path, help="optional workload CSV (key,value) for monthly cost")
    ap.add_argument("--out-dir", type=Path, help="directory for ranking.json and decision.md")
    ap.add_argument("--verify", type=Path, metavar="RANKING_JSON", help="recompute and cross-check a ranking.json")
    a = ap.parse_args(argv)
    if a.verify:
        if not a.verify.is_file():
            print(f"error: {a.verify} not found", file=sys.stderr)
            return 2
        probs = verify(a.verify)
        for p in probs:
            print(f"FAIL: {p}", file=sys.stderr)
        print(f"verify: {'OK' if not probs else f'{len(probs)} problem(s)'}")
        return 1 if probs else 0
    missing = [n for n in ("candidates", "criteria", "out_dir") if getattr(a, n) is None]
    if missing:
        print(f"error: missing required argument(s): {', '.join('--' + m.replace('_', '-') for m in missing)}",
              file=sys.stderr)
        return 2
    try:
        res = build(a.candidates, a.criteria, a.workload)
    except InputError as e:
        print(f"input error: {e}", file=sys.stderr)
        return 2
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / "ranking.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (a.out_dir / "decision.md").write_text(render(res), encoding="utf-8")
    if not res["ranking"]:
        print(f"no candidate survives the hard constraints ({len(res['eliminated'])} eliminated); "
              f"wrote {a.out_dir}/ranking.json, decision.md", file=sys.stderr)
        return 1
    print(f"winner: {res['recommendation']['model']} (score {res['recommendation']['score']}); "
          f"{res['survivors']}/{res['candidates_total']} survive; wrote {a.out_dir}/ranking.json, decision.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
