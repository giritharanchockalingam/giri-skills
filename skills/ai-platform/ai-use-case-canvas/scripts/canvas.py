#!/usr/bin/env python3
"""Fill the one-page AI use-case canvas, score it and make the build/buy/partner call from answers.json.

    python3 -I scripts/canvas.py answers.json --out-dir runs/x [--template assets/use-case-canvas.md]

answers.json (every key optional except `name`; blanks become `[TO BE BASELINED — owner: <owner>]`):
  name, owner (default owner for unknowns), raised_by
  problem_user, decision                                   boxes 1-2 (strings)
  current_process: {volume, time_per_unit, error_cost}     box 3
  capability:      {pattern, autonomy}                     box 4  autonomy: suggest|draft|act with approval|act
  data:            {sources, owner, access, sensitivity, freshness}   box 5
  feasibility:     {known_pattern, integrations_exist, team_available, eval_definable}  box 6 (y/n)
  value:           {type, mechanism, estimate, baseline_signed_by}    box 7
  risks:           {tier, top_risks: [..]}                 box 8
  scores:          {value|feasibility|data_readiness|risk: {score: 1-5, evidence}}
  build_buy:       {<factor>: {favors: build|buy|partner, note}}  factors from references/build-buy-factors.md:
                   differentiation, data_sensitivity, product_fit, team_capability, time_to_value,
                   cost_at_scale, control_roadmap, lock_in_exit, compliance_evidence, integration_depth
  next_step:       {step, owner, by}

Rules: priority = V x F x D / R only when all four scores exist. Verdict per references/canvas-definition.md
(Proceed to design / Proceed after data readiness / Park / Stop); unscored -> TBD. Build/buy/partner = the
option favored by most stated factors, citing them; a tie or fewer than two factors -> TBD; a missing or
<= 2 data-readiness score -> "wait" (data readiness first), whatever the factors say.

Writes canvas.md (template filled; <= 60 lines), decision.md, score.json. Exit 1 on missing/invalid JSON,
a score outside 1-5, an unknown factor or an unknown `favors` value. Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
AXES = ["value", "feasibility", "data_readiness", "risk"]
FACTORS = ["differentiation", "data_sensitivity", "product_fit", "team_capability", "time_to_value",
           "cost_at_scale", "control_roadmap", "lock_in_exit", "compliance_evidence", "integration_depth"]
OPTIONS = ("build", "buy", "partner")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{p.name}: invalid JSON: {e}")
    if not isinstance(d, dict) or not str(d.get("name", "")).strip():
        die(f"{p.name}: expected an object with at least `name`")
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="answers.json -> canvas.md + decision.md + score.json")
    ap.add_argument("answers")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--template", default=str(SKILL / "assets" / "use-case-canvas.md"))
    a = ap.parse_args()
    d = load(a.answers)
    owner = str(d.get("owner") or "___")
    tbd = f"[TO BE BASELINED — owner: {owner}]"

    def g(section, key=None):
        v = d.get(section) if key is None else (d.get(section) or {}).get(key) if isinstance(d.get(section), dict) else None
        if isinstance(v, list):
            v = "; ".join(str(x) for x in v)
        v = "" if v is None else str(v).strip()
        return v or tbd

    # ---- scores
    scores, evidence = {}, {}
    for ax in AXES:
        s = (d.get("scores") or {}).get(ax)
        if s is None:
            continue
        val, ev = (s.get("score"), s.get("evidence", "")) if isinstance(s, dict) else (s, "")
        if val in ("", None):
            continue
        if not (isinstance(val, int) and not isinstance(val, bool) and 1 <= val <= 5):
            die(f"scores.{ax}: score must be an integer 1-5, got {val!r}")
        scores[ax] = val
        evidence[ax] = str(ev).strip()
    missing = [ax for ax in AXES if ax not in scores]
    priority = round(scores["value"] * scores["feasibility"] * scores["data_readiness"] / scores["risk"], 2) \
        if not missing else None

    # ---- verdict
    user_ok = bool(str(d.get("problem_user", "")).strip()) and bool(str(d.get("decision", "")).strip())
    owner_ok = str((d.get("value") or {}).get("baseline_signed_by", "")).strip() != ""
    if not user_ok:
        verdict, why = "Stop", "no identifiable user or decision (boxes 1-2 blank)"
    elif missing:
        verdict, why = "TBD", f"unscored axis/axes: {', '.join(missing)} — score before deciding"
    else:
        v, f, dr, r = (scores[x] for x in AXES)
        if r == 5:
            verdict, why = "Stop", "R = 5 without a stated mitigation path"
        elif v >= 3 and f >= 3 and dr >= 3 and r <= 3 and owner_ok:
            verdict, why = "Proceed to design", "V>=3, F>=3, D>=3, R<=3, baseline owner named"
        elif v >= 3 and f >= 3 and dr >= 3 and r <= 3:
            verdict, why = "Park", "scores pass but nobody owns the baseline — park until an owner exists"
        elif v >= 3 and f >= 3 and dr <= 2:
            verdict, why = "Proceed after data readiness", "V>=3, F>=3 but D<=2 — next step is a data task"
        elif v <= 2 or f <= 2:
            verdict, why = "Park", "V<=2 or F<=2 now; set a revisit trigger"
        else:
            verdict, why = "Park", "R = 4 — mitigation plan and tier review before design"

    # ---- build / buy / partner
    votes = {o: [] for o in OPTIONS}
    bb = d.get("build_buy") or {}
    for factor, spec in bb.items():
        if factor not in FACTORS:
            die(f"build_buy: unknown factor {factor!r}; allowed: {FACTORS}")
        fav = (spec.get("favors") if isinstance(spec, dict) else spec)
        fav = str(fav or "").strip().lower()
        if fav not in OPTIONS:
            die(f"build_buy.{factor}: favors must be one of {OPTIONS}, got {fav!r}")
        votes[fav].append((factor, (spec.get("note", "") if isinstance(spec, dict) else "") or ""))
    d_score = scores.get("data_readiness")
    ranked = sorted(OPTIONS, key=lambda o: -len(votes[o]))
    if d_score is None:
        decision, dwhy = "wait", "data readiness is unscored — decide build/buy only after the data box is baselined"
    elif d_score <= 2:
        decision, dwhy = "wait", f"data readiness = {d_score}: fund the data task first; revisit build/buy after"
    elif sum(len(v) for v in votes.values()) < 2:
        decision, dwhy = "TBD", "fewer than two factors stated — the decision must cite two factors"
    elif len(votes[ranked[0]]) == len(votes[ranked[1]]):
        decision, dwhy = "TBD", f"tie between {ranked[0]} and {ranked[1]} on stated factors — resolve with the sponsor"
    else:
        decision = ranked[0]
        top = votes[decision][:2]
        dwhy = f"{len(votes[decision])} of {sum(len(v) for v in votes.values())} factors favor {decision}; strongest: " \
               + "; ".join(f"{f_}" + (f" ({n})" if n else "") for f_, n in top)

    # ---- canvas.md from the template
    tp = Path(a.template)
    if not tp.is_file():
        die(f"template not found: {tp}")
    ns = d.get("next_step") or {}
    t = tp.read_text(encoding="utf-8")
    t = t.replace("**Next 30-day step:** <concrete step> — owner: <name> — by: <date>",
                  f"**Next 30-day step:** {ns.get('step') or tbd} — owner: {ns.get('owner') or owner} — by: {ns.get('by') or tbd}")
    t = t.replace("<name>", str(d["name"])).replace("<date>", datetime.date.today().isoformat())
    t = t.replace("**Verdict:** <Proceed to design | Proceed after data readiness | Park | Stop>",
                  f"**Verdict:** {verdict} — {why}")
    fz = d.get("feasibility") or {}
    rows = {
        "Problem and user": g("problem_user"),
        "Decision or task affected": g("decision"),
        "Current process and baseline": f"Volume: {g('current_process', 'volume')}; time/unit: {g('current_process', 'time_per_unit')}; error/cost: {g('current_process', 'error_cost')}",
        "Proposed AI capability": f"Pattern: {g('capability', 'pattern')}; autonomy: {g('capability', 'autonomy')}",
        "Data": f"Sources: {g('data', 'sources')}; owner: {g('data', 'owner')}; access: {g('data', 'access')}; sensitivity: {g('data', 'sensitivity')}; freshness: {g('data', 'freshness')}",
        "Feasibility": "; ".join(f"{k.replace('_', ' ')}: {fz.get(k) or tbd}" for k in ("known_pattern", "integrations_exist", "team_available", "eval_definable")),
        "Value hypothesis": f"Type: {g('value', 'type')}; mechanism: {g('value', 'mechanism')}; estimate: {g('value', 'estimate')}; baseline signed by: {g('value', 'baseline_signed_by')}",
        "Risks and tier": f"Tier: {g('risks', 'tier')}; top risks: {g('risks', 'top_risks')}",
        "Build / buy / partner": f"Decision: {decision}; factors: {dwhy}; exit trigger: {g('build_buy_exit_trigger')}",
    }
    out_lines = []
    for ln in t.splitlines():
        cells = [c.strip() for c in ln.strip("|").split("|")] if ln.startswith("| ") else []
        if len(cells) == 3 and cells[1] in rows:
            ln = f"| {cells[0]} | {cells[1]} | {rows[cells[1]]} |"
        elif len(cells) == 3 and cells[0] in ("Value", "Feasibility", "Data readiness", "Risk") and cells[1] == "":
            ax = cells[0].lower().replace(" ", "_")
            ln = f"| {cells[0]} | {scores.get(ax, tbd)} | {evidence.get(ax) or tbd} |"
        elif ln.startswith("| Priority (V×F×D÷R) |"):
            ln = f"| Priority (V×F×D÷R) | {priority if priority is not None else tbd} | {'all four axes scored' if priority is not None else 'unscored: ' + ', '.join(missing)} |"
        elif ln.startswith("Hand-off:"):
            tier = str((d.get("risks") or {}).get("tier", "")).lower()
            hand = ("ai-governance-risk" if tier in ("medium", "high") else
                    "agent-architecture | rag-pipeline-design" if verdict == "Proceed to design" else "none")
            ln = f"Hand-off: {hand}"
        out_lines.append(ln)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "canvas.md").write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    L = [f"# Build / buy / partner — {d['name']}", "", f"**Decision:** {decision} — {dwhy}.", "",
         "## Factors stated", "| Factor | Favors | Note |", "|---|---|---|"]
    L += [f"| {f_} | {o} | {n} |" for o in OPTIONS for f_, n in votes[o]] or [f"| none stated | | {tbd} |"]
    L += ["", "## Factors not stated", ", ".join(f_ for f_ in FACTORS if f_ not in bb) or "none", "",
          "## Verdict", f"{verdict} — {why}", "", f"Exit / revisit trigger: {g('build_buy_exit_trigger')}"]
    (out / "decision.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out / "score.json").write_text(json.dumps({
        "name": d["name"], "scores": scores, "evidence": evidence, "missing_axes": missing, "priority": priority,
        "verdict": verdict, "verdict_reason": why, "decision": decision, "decision_reason": dwhy,
        "factors": {o: [f_ for f_, _ in votes[o]] for o in OPTIONS}}, indent=2) + "\n", encoding="utf-8")
    print(f"canvas: verdict={verdict}; decision={decision}; priority={priority} -> {out}")
    return 0


if __name__ == "__main__":
    main()
