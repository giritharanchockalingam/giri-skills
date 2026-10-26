#!/usr/bin/env python3
"""AI vendor assessment: weighted scoring, ±20% weight sensitivity and third-party AI risk red flags.

Usage:
  python3 -I vendor_assess.py --options O.csv --criteria C.csv [--risk R.csv]
                              [--questions Q.csv] [--require-clear-winner]
                              [--previous LAST/scores.csv] --out-dir OUT
  python3 -I vendor_assess.py --verify OUT/scores.csv        # or OUT/sensitivity.csv

Inputs ('#' lines are comments):
  options   option,criterion,score,source    score 1-5; a blank score = missing (never imputed)
  criteria  criterion,weight,description     weights >= 0, any scale; normalised to sum 1
  risk      option,question_id,answer,evidence   answers to assets/third-party-ai-risk-questions.csv;
            'unknown' (or blank) = unanswered; 'n/a' = not applicable (e.g. a build option)
Math:
  weighted_score = sum(normalised weight x score), complete options only (3 dp in outputs).
  Rank: score descending, option name ascending on ties (tied scores share a rank).
  Sensitivity: for each criterion, weight x0.8 and x1.2, renormalise, recompute; the top option
  "changes" if a different option is first or the first place is tied. Rank stability % =
  unchanged runs / all runs x 100.
  Red flag: an answer matching the question's red_flag_rule (eq:<v>, gt:<n>, lt:<n>).
Recommendation: the top complete option when it is not tied, has no red flags and stays first in
every perturbation; otherwise "no clear winner" (exit 0, or exit 1 with --require-clear-winner).
Re-assessment (--previous): the scores.csv of an earlier run (e.g. at contract renewal). The report gains
"Changes since last assessment": per option the score and rank then and now, red flags raised and cleared,
and options that are new or no longer assessed. Nothing from the earlier file feeds today's scores.
Outputs: OUT/scores.csv, OUT/sensitivity.csv, OUT/vendor-report.md.
Exit: 0 ok · 1 --require-clear-winner and no clear winner · 2 bad/missing input.
Stdlib only; deterministic.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUESTIONS = HERE.parent / "assets" / "third-party-ai-risk-questions.csv"
TBD_PROC = "[TO BE BASELINED — owner: Procurement lead]"
TBD_RISK = "[TO BE BASELINED — owner: Third-party risk manager]"
PERTURB = (("-20%", 0.8), ("+20%", 1.2))
SCORE_COLS = ["option", "weighted_score", "rank", "complete", "red_flags", "missing_criteria", "risk_unanswered"]
SENS_COLS = ["criterion", "change", "weight_before", "weight_after", "top_option", "top_score",
             "runner_up", "margin", "top_changed"]
ANSWER_TYPES = {"yes_no": {"yes", "no"}, "yes_no_progress": {"yes", "no", "in_progress"}}
EPS = 1e-9


class InputError(Exception):
    pass


def read_csv(path: Path, label: str, cols: list[str]) -> list[dict]:
    if not path.is_file():
        raise InputError(f"{label}: file not found: {path}")
    lines = [ln for ln in path.read_text(encoding="utf-8-sig").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise InputError(f"{label}: file is empty")
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    header = [h.strip() for h in reader.fieldnames or []]
    missing = [c for c in cols if c not in header]
    if missing:
        raise InputError(f"{label}: missing column(s) {', '.join(missing)}; header is {', '.join(header)}")
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    if not rows:
        raise InputError(f"{label}: no data rows")
    return rows


def num(v: str, label: str) -> float:
    try:
        x = float(v)
    except ValueError:
        raise InputError(f"{label}: {v!r} is not a number") from None
    if x != x or x in (float("inf"), float("-inf")):
        raise InputError(f"{label}: {v!r} is not a finite number")
    return x


def load_criteria(path: Path) -> tuple[list[str], dict[str, float], dict[str, str]]:
    rows = read_csv(path, "criteria", ["criterion", "weight"])
    names, raw, desc = [], {}, {}
    for n, r in enumerate(rows, 2):
        c = r["criterion"]
        if not c:
            raise InputError(f"criteria row {n}: blank criterion")
        if c in raw:
            raise InputError(f"criteria row {n}: duplicate criterion {c!r}")
        w = num(r["weight"], f"criteria row {n} weight")
        if w < 0:
            raise InputError(f"criteria row {n}: weight must be >= 0")
        names.append(c)
        raw[c] = w
        desc[c] = r.get("description", "")
    if sum(raw.values()) <= 0:
        raise InputError("criteria: weights sum to 0")
    return names, raw, desc


def load_options(path: Path, criteria: list[str]):
    rows = read_csv(path, "options", ["option", "criterion", "score", "source"])
    options, scores, sources = [], {}, {}
    for n, r in enumerate(rows, 2):
        o, c = r["option"], r["criterion"]
        if not o:
            raise InputError(f"options row {n}: blank option")
        if c not in criteria:
            raise InputError(f"options row {n}: criterion {c!r} is not in the criteria file")
        if (o, c) in scores:
            raise InputError(f"options row {n}: duplicate score for {o} × {c}")
        if o not in options:
            options.append(o)
        if r["score"] == "":
            scores[(o, c)] = None
        else:
            s = num(r["score"], f"options row {n} score")
            if not 1 <= s <= 5:
                raise InputError(f"options row {n}: score {r['score']} outside 1-5")
            scores[(o, c)] = s
        sources[(o, c)] = r["source"]
    return options, scores, sources


def load_questions(path: Path) -> list[dict]:
    rows = read_csv(path, "questions", ["question_id", "topic", "question", "answer_type", "red_flag_rule"])
    for n, r in enumerate(rows, 2):
        if r["answer_type"] not in ("yes_no", "yes_no_progress", "number"):
            raise InputError(f"questions row {n}: answer_type {r['answer_type']!r}")
        if not re.fullmatch(r"(eq:[a-z_]+|gt:\d+(\.\d+)?|lt:\d+(\.\d+)?)", r["red_flag_rule"]):
            raise InputError(f"questions row {n}: red_flag_rule {r['red_flag_rule']!r} (use eq:/gt:/lt:)")
    return rows


def load_risk(path: Path | None, options: list[str], questions: list[dict]):
    if path is None:
        return None
    qmap = {q["question_id"]: q for q in questions}
    rows = read_csv(path, "risk", ["option", "question_id", "answer"])
    answers: dict[tuple[str, str], dict] = {}
    for n, r in enumerate(rows, 2):
        o, q, a = r["option"], r["question_id"], r["answer"].strip().lower()
        if o not in options:
            raise InputError(f"risk row {n}: option {o!r} is not in the options file")
        if q not in qmap:
            raise InputError(f"risk row {n}: unknown question_id {q!r}")
        if (o, q) in answers:
            raise InputError(f"risk row {n}: duplicate answer for {o} × {q}")
        if a not in ("", "unknown", "n/a"):
            t = qmap[q]["answer_type"]
            if t == "number":
                if num(a, f"risk row {n} answer") < 0:
                    raise InputError(f"risk row {n}: answer must be >= 0")
            elif a not in ANSWER_TYPES[t]:
                raise InputError(f"risk row {n}: answer {a!r} not in {'|'.join(sorted(ANSWER_TYPES[t]))}")
        answers[(o, q)] = {"answer": a or "unknown", "evidence": r.get("evidence", "")}
    return answers


def is_red(answer: str, rule: str) -> bool:
    if answer in ("unknown", "n/a"):
        return False
    op, _, v = rule.partition(":")
    if op == "eq":
        return answer == v
    x = float(answer)
    return x > float(v) if op == "gt" else x < float(v)


def normalise(raw: dict[str, float]) -> dict[str, float]:
    total = sum(raw.values())
    return {c: w / total for c, w in raw.items()}


def weighted(options: list[str], criteria: list[str], weights: dict, scores: dict) -> dict[str, float]:
    return {o: sum(weights[c] * scores[(o, c)] for c in criteria) for o in options}


def order(ws: dict[str, float]) -> list[str]:
    return sorted(ws, key=lambda o: (-round(ws[o], 9), o))


def analyse(options, criteria, raw, scores, risk, questions):
    w = normalise(raw)
    complete = [o for o in options if all(scores.get((o, c)) is not None for c in criteria)]
    missing = {o: [c for c in criteria if scores.get((o, c)) is None] for o in options}
    ws = weighted(complete, criteria, w, scores)
    ranked = order(ws)
    ranks, prev, rank = {}, None, 0
    for i, o in enumerate(ranked, 1):
        if prev is None or abs(ws[o] - ws[prev]) > EPS:
            rank = i
        ranks[o] = rank
        prev = o
    base_top = ranked[0] if ranked else None
    base_tied = len(ranked) > 1 and abs(ws[ranked[0]] - ws[ranked[1]]) <= EPS
    sens = []
    for c in criteria:
        for label, f in PERTURB:
            r2 = dict(raw)
            r2[c] = raw[c] * f
            w2 = normalise(r2)
            s2 = weighted(complete, criteria, w2, scores)
            o2 = order(s2)
            top = o2[0] if o2 else None
            ru = o2[1] if len(o2) > 1 else None
            margin = s2[top] - s2[ru] if ru else None
            changed = top != base_top or (margin is not None and margin <= EPS)
            sens.append({"criterion": c, "change": label, "weight_before": w[c], "weight_after": w2[c],
                         "top_option": top, "top_score": s2[top] if top else None, "runner_up": ru,
                         "margin": margin, "top_changed": changed})
    stable = sum(1 for s in sens if not s["top_changed"])
    stability = 100.0 * stable / len(sens) if sens else 0.0
    flags, unanswered = {}, {}
    for o in options:
        if risk is None:
            flags[o], unanswered[o] = None, None
            continue
        flags[o] = [q["question_id"] for q in questions
                    if is_red(risk.get((o, q["question_id"]), {"answer": "unknown"})["answer"], q["red_flag_rule"])]
        unanswered[o] = [q["question_id"] for q in questions
                         if risk.get((o, q["question_id"]), {"answer": "unknown"})["answer"] == "unknown"]
    reasons = []
    if not base_top:
        reasons.append("no option has a complete set of scores")
    else:
        if base_tied:
            reasons.append(f"{ranked[0]} and {ranked[1]} tie on weighted score")
        if flags[base_top]:
            reasons.append(f"top-scoring {base_top} has red flags: {', '.join(flags[base_top])}")
        flips = [s for s in sens if s["top_changed"]]
        if flips:
            reasons.append("the top option changes under " + ", ".join(
                f"{s['criterion']} {s['change']}" for s in flips))
    return {"weights": w, "complete": complete, "missing": missing, "ws": ws, "ranked": ranked, "ranks": ranks,
            "top": base_top, "sens": sens, "stability": stability, "flags": flags, "unanswered": unanswered,
            "reasons": reasons, "clear": not reasons}


def load_previous(path: Path) -> dict[str, dict]:
    """Earlier scores.csv -> {option: {score, rank, complete, flags}}; flags None when risk was not assessed."""
    out: dict[str, dict] = {}
    for r in read_csv(path, "previous scores", SCORE_COLS):
        if r["option"] in out:
            raise InputError(f"previous scores: duplicate option {r['option']!r}")
        if r["complete"] not in ("yes", "no"):
            raise InputError(f"previous scores: {r['option']}: complete must be yes or no")
        score = None
        if r["complete"] == "yes":
            score = num(r["weighted_score"], f"previous scores: {r['option']} weighted_score")
        fl = r["red_flags"]
        out[r["option"]] = {"score": score, "rank": r["rank"] if r["complete"] == "yes" else "n/a",
                            "flags": None if fl == "not assessed" else
                            ([] if fl in ("", "none") else [x for x in fl.split(";") if x])}
    return out


def changes(options: list[str], a: dict, prev: dict[str, dict]) -> list[dict]:
    rows = []
    for o in [*a["ranked"], *[o for o in options if o not in a["complete"]]]:
        was = prev.get(o)
        now_s = a["ws"][o] if o in a["complete"] else None
        now_f = a["flags"][o]
        if was is None:
            rows.append({"option": o, "was": None, "now": now_s, "rank_was": "—",
                         "rank_now": a["ranks"][o] if o in a["complete"] else "n/a",
                         "delta": "new option", "raised": now_f or [], "cleared": []})
            continue
        delta = (f"{now_s - was['score']:+.3f}" if now_s is not None and was["score"] is not None
                 else "not comparable (incomplete)")
        if now_f is None or was["flags"] is None:
            raised, cleared = None, None
        else:
            raised = [f for f in now_f if f not in was["flags"]]
            cleared = [f for f in was["flags"] if f not in now_f]
        rows.append({"option": o, "was": was["score"], "now": now_s, "rank_was": was["rank"],
                     "rank_now": a["ranks"][o] if o in a["complete"] else "n/a",
                     "delta": delta, "raised": raised, "cleared": cleared})
    for o, was in prev.items():
        if o not in options:
            rows.append({"option": o, "was": was["score"], "now": None, "rank_was": was["rank"], "rank_now": "—",
                         "delta": "no longer assessed", "raised": [], "cleared": []})
    return rows


def changes_md(rows: list[dict], source: str) -> list[str]:
    def fl(x):
        return "not comparable (risk not assessed then or now)" if x is None else (", ".join(x) or "none")
    L = ["## Changes since last assessment", "", f"Compared with `{source}`; today's scores use only today's inputs.", "",
         "| Option | Score then | Score now | Change | Rank then | Rank now | Red flags raised | Red flags cleared |",
         "|---|---|---|---|---|---|---|---|"]
    L += [f"| {cell(r['option'])} | {f3(r['was'])} | {f3(r['now'])} | {r['delta']} | {r['rank_was']} | {r['rank_now']} | "
          f"{fl(r['raised'])} | {fl(r['cleared'])} |" for r in rows]
    raised = [r for r in rows if r["raised"]]
    L += ["", (f"New red flags: " + "; ".join(f"{r['option']} ({', '.join(r['raised'])})" for r in raised)
               + f" — raise with the vendor before renewal; owner: Third-party risk manager.")
          if raised else "New red flags: none.", ""]
    return L


def f3(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def write_scores(path: Path, options: list[str], a: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(SCORE_COLS)
        rows = [o for o in a["ranked"]] + [o for o in options if o not in a["complete"]]
        for o in rows:
            comp = o in a["complete"]
            fl = a["flags"][o]
            un = a["unanswered"][o]
            w.writerow([o, f3(a["ws"][o]) if comp else "n/a", a["ranks"][o] if comp else "n/a",
                        "yes" if comp else "no",
                        "not assessed" if fl is None else (";".join(fl) or "none"),
                        "none" if comp else ";".join(a["missing"][o]) + " " + TBD_PROC,
                        TBD_RISK + " risk not assessed" if un is None else
                        ("none" if not un else ";".join(un) + " " + TBD_RISK)])


def write_sens(path: Path, a: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(SENS_COLS)
        for s in a["sens"]:
            w.writerow([s["criterion"], s["change"], f"{s['weight_before']:.4f}", f"{s['weight_after']:.4f}",
                        s["top_option"] or "n/a", f3(s["top_score"]), s["runner_up"] or "n/a",
                        f3(s["margin"]), "yes" if s["top_changed"] else "no"])


def cell(s: str) -> str:
    return str(s).replace("|", "\\|")


def render(options, criteria, raw, desc, scores, sources, risk, questions, a, require) -> str:
    total = sum(raw.values())
    rec = (f"**{a['top']}** (weighted score {f3(a['ws'][a['top']])})" if a["clear"] else "**No clear winner**")
    L = ["# AI vendor assessment", "", "## Summary", "",
         f"- Recommendation: {rec}.",
         f"- Options: {len(options)}; complete and ranked: {len(a['complete'])}; "
         f"incomplete (excluded): {len(options) - len(a['complete'])}.",
         f"- Rank stability under ±20% weight changes: {a['stability']:.1f}% "
         f"({sum(1 for s in a['sens'] if not s['top_changed'])} of {len(a['sens'])} runs keep the same top option).",
         "- Third-party risk: " + ("not assessed — no risk answers supplied " + TBD_RISK + "." if risk is None else
                                   f"{sum(1 for o in options if a['flags'][o])} option(s) with red flags."),
         f"- Weights sum to {total:g}; normalised to 1.000 before scoring.", "",
         "## Scores", "",
         "| Rank | Option | Weighted score | Complete | Red flags |", "|---|---|---|---|---|"]
    for o in a["ranked"]:
        fl = a["flags"][o]
        L.append(f"| {a['ranks'][o]} | {cell(o)} | {f3(a['ws'][o])} | yes | "
                 f"{'not assessed' if fl is None else (', '.join(fl) or 'none')} |")
    for o in options:
        if o not in a["complete"]:
            fl = a["flags"][o]
            L.append(f"| n/a | {cell(o)} | n/a | no — missing {', '.join(a['missing'][o])} {TBD_PROC} | "
                     f"{'not assessed' if fl is None else (', '.join(fl) or 'none')} |")
    L += ["", "Score matrix (1–5; weight normalised):", "",
          "| Criterion | Weight | " + " | ".join(cell(o) for o in options) + " |",
          "|---|---|" + "---|" * len(options)]
    for c in criteria:
        vals = ["missing" if scores.get((o, c)) is None else f"{scores[(o, c)]:g}" for o in options]
        L.append(f"| {cell(c)} | {a['weights'][c]:.3f} | " + " | ".join(vals) + " |")
    unsourced = sorted(f"{o} × {c}" for (o, c), s in sources.items() if not s and scores.get((o, c)) is not None)
    if unsourced:
        L += ["", "Scores without a source (confirm before relying on them): " + "; ".join(unsourced) + "."]
    L += ["", "## Sensitivity", ""]
    if not a["complete"]:
        L.append("Not computed: no complete option.")
    else:
        L += ["| Criterion | Change | Weight before → after | Top option | Runner-up | Margin | Top changes |",
              "|---|---|---|---|---|---|---|"]
        for s in a["sens"]:
            L.append(f"| {cell(s['criterion'])} | {s['change']} | {s['weight_before']:.3f} → {s['weight_after']:.3f} "
                     f"| {cell(s['top_option'])} | {cell(s['runner_up'] or 'n/a')} | {f3(s['margin'])} "
                     f"| {'yes' if s['top_changed'] else 'no'} |")
    L += ["", "## Third-party risk", ""]
    if risk is None:
        L.append(f"Not assessed: supply a risk file answering `assets/third-party-ai-risk-questions.csv` {TBD_RISK}.")
    else:
        L += ["| Question | Topic | Red flag if | " + " | ".join(cell(o) for o in options) + " |",
              "|---|---|---|" + "---|" * len(options)]
        for q in questions:
            vals = []
            for o in options:
                ans = risk.get((o, q["question_id"]), {"answer": "unknown"})["answer"]
                vals.append(f"**{ans} (RED)**" if is_red(ans, q["red_flag_rule"]) else ans)
            L.append(f"| {q['question_id']} | {cell(q['topic'])} | {q['red_flag_rule']} | " + " | ".join(vals) + " |")
        gaps = [o for o in options if a["unanswered"][o]]
        if gaps:
            L += ["", "Unanswered questions (not counted as red flags; resolve before contract) " + TBD_RISK + ": "
                  + "; ".join(f"{o}: {', '.join(a['unanswered'][o])}" for o in gaps) + "."]
    L += ["", "## Recommendation", ""]
    if a["clear"]:
        un = a["unanswered"][a["top"]]
        flag_txt = "red flags not yet assessed" if un is None else "no red flags"
        L.append(f"Select **{a['top']}**: highest weighted score ({f3(a['ws'][a['top']])}), {flag_txt}, and first "
                 f"in all {len(a['sens'])} sensitivity runs.")
        if un is None:
            L.append(f"Conditional on a third-party risk review {TBD_RISK}.")
        elif un:
            L.append(f"Conditional on answers to {', '.join(un)} {TBD_RISK}.")
    else:
        L.append("**No clear winner.** Reasons: " + "; ".join(a["reasons"]) + ".")
        clean = [o for o in a["ranked"] if not a["flags"][o]]
        if a["top"] and a["flags"][a["top"]] and clean:
            L.append(f"Highest-scoring option without red flags: {clean[0]} ({f3(a['ws'][clean[0]])}).")
        L.append("Next step: resolve the reasons above (re-score, renegotiate terms or re-weight with the decision "
                 "owner) and re-run.")
        if require:
            L.append("`--require-clear-winner` was set: the run fails (exit 1).")
    L += ["", "## Method", "",
          "- Weighted score = Σ (normalised weight × score) on the 1–5 scale; ties share a rank and are listed by name.",
          "- An option missing any criterion score is incomplete: no score is imputed and it is excluded from the "
          "ranking and the recommendation.",
          "- Sensitivity: each criterion weight ×0.8 and ×1.2, renormalised; the top option \"changes\" if another "
          "option is first or first place is tied. Rank stability = unchanged runs ÷ all runs.",
          "- Red flags follow `red_flag_rule` in the questions file (eq/gt/lt). The 30-day retention, 30-day "
          "change-notice and 72-hour incident thresholds are template defaults; the Third-party risk manager "
          "should set them to policy. `unknown` answers are gaps, not red flags; `n/a` is not applicable.",
          "- Limits: scores are only as good as their sources; this is a decision aid, not a legal or contract "
          "review, and it does not verify vendor claims (certificates and reports must be inspected).", ""]
    if desc and any(desc.values()):
        L += ["Criteria:", "", "| Criterion | Raw weight | Description |", "|---|---|---|"]
        L += [f"| {cell(c)} | {raw[c]:g} | {cell(desc[c])} |" for c in criteria]
        L.append("")
    return "\n".join(L)


def verify(path: Path) -> int:
    errs = []
    head = path.read_text(encoding="utf-8").splitlines()[:1] if path.is_file() else []
    try:
        if head and "top_changed" in head[0]:
            rows = read_csv(path, "sensitivity", SENS_COLS)
            for r in rows:
                if r["top_changed"] not in ("yes", "no"):
                    errs.append(f"{r['criterion']}: top_changed {r['top_changed']!r}")
                for k in ("weight_before", "weight_after"):
                    if not 0 <= float(r[k]) <= 1:
                        errs.append(f"{r['criterion']}: {k} out of range")
        else:
            rows = read_csv(path, "scores", SCORE_COLS)
            done = [r for r in rows if r["complete"] == "yes"]
            last = None
            for r in rows:
                if r["complete"] not in ("yes", "no"):
                    errs.append(f"{r['option']}: complete {r['complete']!r}")
                elif r["complete"] == "no" and TBD_PROC not in r["missing_criteria"]:
                    errs.append(f"{r['option']}: incomplete without a Procurement lead TBD")
            for r in done:
                s = float(r["weighted_score"])
                if not 1 <= s <= 5:
                    errs.append(f"{r['option']}: score {s} outside 1-5")
                if last is not None and s > last + EPS:
                    errs.append(f"{r['option']}: not sorted by score")
                last = s
            if done and done[0]["rank"] != "1":
                errs.append("first complete option is not rank 1")
    except (InputError, ValueError) as e:
        errs.append(str(e))
    for e in errs[:20]:
        print(f"verify: {e}")
    print(f"verify: {path.name}: {len(errs)} problem(s)")
    return 1 if errs else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--options", type=Path)
    ap.add_argument("--criteria", type=Path)
    ap.add_argument("--risk", type=Path)
    ap.add_argument("--questions", type=Path, default=QUESTIONS)
    ap.add_argument("--require-clear-winner", action="store_true")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--previous", type=Path, metavar="CSV", help="scores.csv from an earlier assessment")
    ap.add_argument("--verify", type=Path, metavar="CSV")
    args = ap.parse_args(argv)
    if args.verify:
        return verify(args.verify)
    try:
        if not (args.options and args.criteria and args.out_dir):
            raise InputError("--options, --criteria and --out-dir are required")
        criteria, raw, desc = load_criteria(args.criteria)
        options, scores, sources = load_options(args.options, criteria)
        questions = load_questions(args.questions)
        risk = load_risk(args.risk, options, questions)
        prev = load_previous(args.previous) if args.previous else None
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    a = analyse(options, criteria, raw, scores, risk, questions)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_scores(args.out_dir / "scores.csv", options, a)
    write_sens(args.out_dir / "sensitivity.csv", a)
    report = render(options, criteria, raw, desc, scores, sources, risk, questions, a, args.require_clear_winner)
    if prev is not None:
        head, sep, tail = report.partition("\n## Method\n")
        report = head + "\n" + "\n".join(changes_md(changes(options, a, prev), args.previous.name)) + sep + tail
    (args.out_dir / "vendor-report.md").write_text(report, encoding="utf-8")
    print(f"options: {len(options)}; complete: {len(a['complete'])}; "
          f"recommendation: {a['top'] if a['clear'] else 'no clear winner'}; stability {a['stability']:.1f}%")
    if args.require_clear_winner and not a["clear"]:
        print("no clear winner: " + "; ".join(a["reasons"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
