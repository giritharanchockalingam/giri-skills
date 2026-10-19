#!/usr/bin/env python3
"""Conversation-layer design check: intents + real utterances -> routing, intent quality, spec.

Routes every utterance to its best intent with a TF-IDF cosine over each intent's
description + examples (references/method.md). A best score below CONFIDENCE_THRESHOLD
(0.25) routes to `fallback` (uncovered). With expected_intent labels it computes accuracy,
per-intent precision/recall and confusion pairs. Intent pairs whose example sets have a
TF-IDF cosine at or above CONFUSABLE_THRESHOLD (0.40) are flagged as confusable.

Usage:
  python3 -I conversation_design.py --intents intents.csv --utterances utterances.csv \
      [--persona persona.csv] [--min-accuracy 0.8] --out-dir OUT
  python3 -I conversation_design.py --verify OUT/routing.csv --intents intents.csv --utterances utterances.csv
  python3 -I conversation_design.py --leak-check OUT/conversation-spec.md --utterances utterances.csv

Inputs:
  intents     CSV intent,description,examples,response_type,handoff,owner. examples are
              pipe-separated; response_type answer|action|handoff|clarify; handoff yes|no.
  utterances  CSV utterance[,expected_intent]. expected_intent is an intent name, `fallback`
              (out of scope on purpose) or blank (unlabelled).
  persona     kv-CSV key,value[,source,notes]: name, tone, reading_level, escalation_channel,
              disallowed_topics. Missing keys -> [TO BE BASELINED — owner: Conversation designer].
  min_accuracy  optional gate 0-1 on labelled accuracy.

Outputs (in --out-dir): routing.csv, intent-quality.csv, conversation-spec.md.
Utterances are user text: outputs never contain more than the first 80 characters of one.
Exit codes: 0 written (and gate met when set) · 1 accuracy below --min-accuracy (or no labels to
measure it) — outputs still written · 2 missing/invalid input.
Stdlib only; no network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import re
import sys
from pathlib import Path

CONFIDENCE_THRESHOLD = 0.25   # best cosine below this -> fallback (uncovered)
CONFUSABLE_THRESHOLD = 0.40   # example-set cosine at/above this -> confusable pair
MIN_EXAMPLES = 5              # skill design guideline: fewer examples -> thin intent (gap)
MAX_ECHO = 80                 # never echo more than this many characters of an utterance
FALLBACK = "fallback"
TBD = "[TO BE BASELINED — owner: Conversation designer]"
RESPONSE_TYPES = ("answer", "action", "clarify", "handoff")
PERSONA_KEYS = ("name", "tone", "reading_level", "escalation_channel", "disallowed_topics")
STOPWORDS = frozenset(
    "a an the and or but if of to in on at for from by with about as is are was were be been "
    "am do does did i me my we our you your it its this that these those there here can could "
    "would should will just so please hi hello hey".split()
)
TOKEN_RE = re.compile(r"[a-z0-9]+")


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


# ------------------------------------------------------------------ input
def read_csv(path: Path, what: str) -> list[dict]:
    if not path or not Path(path).is_file():
        raise InputError(f"{what} file not found: {path}")
    text = Path(path).read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None} for r in reader]
    return rows, [(c or "").strip() for c in (reader.fieldnames or [])]


def load_intents(path: Path) -> list[dict]:
    rows, cols = read_csv(path, "intents")
    need = ("intent", "description", "examples", "response_type", "handoff", "owner")
    miss = [c for c in need if c not in cols]
    if miss:
        raise InputError(f"intents CSV missing column(s): {', '.join(miss)} (need {','.join(need)})")
    if not rows:
        raise InputError("intents CSV has no intent rows")
    out, seen = [], set()
    for i, r in enumerate(rows, start=2):
        name = r["intent"]
        if not name:
            raise InputError(f"intents line {i}: intent name is blank")
        if name.lower() == FALLBACK:
            raise InputError(f"intents line {i}: '{FALLBACK}' is reserved for uncovered utterances")
        if name in seen:
            raise InputError(f"intents line {i}: duplicate intent {name!r}")
        seen.add(name)
        rt = r["response_type"].lower()
        if rt not in RESPONSE_TYPES:
            raise InputError(f"intents line {i}: response_type {r['response_type']!r} not in {'|'.join(RESPONSE_TYPES)}")
        ho = r["handoff"].lower()
        if ho not in ("yes", "no"):
            raise InputError(f"intents line {i}: handoff {r['handoff']!r} must be yes or no")
        examples = [e.strip() for e in r["examples"].split("|") if e.strip()]
        out.append({"intent": name, "description": r["description"], "examples": examples,
                    "response_type": rt, "handoff": ho, "owner": r["owner"] or TBD})
    return out


def load_utterances(path: Path, intent_names: set[str]) -> list[dict]:
    rows, cols = read_csv(path, "utterances")
    if "utterance" not in cols:
        raise InputError("utterances CSV needs an 'utterance' column")
    out = []
    for i, r in enumerate(rows, start=2):
        if not r.get("utterance"):
            continue
        exp = r.get("expected_intent", "")
        if exp and exp != FALLBACK and exp not in intent_names:
            raise InputError(f"utterances line {i}: expected_intent {exp!r} is not an intent or '{FALLBACK}'")
        out.append({"utterance": r["utterance"], "expected": exp})
    if not out:
        raise InputError("utterances CSV has no non-empty utterances")
    return out


def load_persona(path: Path | None) -> dict[str, dict]:
    if not path:
        return {}
    rows, cols = read_csv(path, "persona")
    if "key" not in cols or "value" not in cols:
        raise InputError("persona CSV needs columns key,value[,source,notes]")
    return {r["key"]: {"value": r["value"], "source": r.get("source", "")}
            for r in rows if r.get("key") and r.get("value")}


# ------------------------------------------------------------------ TF-IDF
def tokens(text: str) -> list[str]:
    out = []
    for t in TOKEN_RE.findall(text.lower()):
        if t in STOPWORDS or len(t) < 2:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]  # light plural folding: bills -> bill
        out.append(t)
    return out


def idf_table(docs: list[list[str]]) -> dict[str, float]:
    n = len(docs)
    df: dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    return {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}


def vector(toks: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf: dict[str, int] = {}
    for t in toks:
        if t in idf:
            tf[t] = tf.get(t, 0) + 1
    v = {t: c * idf[t] for t, c in tf.items()}
    norm = math.sqrt(sum(x * x for x in v.values()))
    return {t: x / norm for t, x in v.items()} if norm else {}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def echo(text: str) -> str:
    """User text as it may appear in outputs: at most MAX_ECHO characters, single line."""
    t = " ".join(text.split())
    return t if len(t) <= MAX_ECHO else t[:MAX_ECHO] + "…"


# ------------------------------------------------------------------ analysis
def analyse(intents: list[dict], utterances: list[dict], persona: dict, min_accuracy: float | None) -> dict:
    docs = [tokens(it["description"] + " " + " ".join(it["examples"])) for it in intents]
    idf = idf_table(docs)
    ivecs = [vector(d, idf) for d in docs]
    names = [it["intent"] for it in intents]

    routing = []
    for u in utterances:
        uv = vector(tokens(u["utterance"]), idf)
        scored = sorted(((round(cosine(uv, iv), 6), n) for iv, n in zip(ivecs, names)), key=lambda x: (-x[0], x[1]))
        best_score, best = scored[0] if scored else (0.0, FALLBACK)
        pred = best if best_score >= CONFIDENCE_THRESHOLD else FALLBACK
        correct = "" if not u["expected"] else ("yes" if pred == u["expected"] else "no")
        routing.append({"utterance": u["utterance"], "predicted_intent": pred, "score": best_score,
                        "nearest_intent": best, "expected_intent": u["expected"], "correct": correct})

    labelled = [r for r in routing if r["expected_intent"]]
    n_correct = sum(1 for r in labelled if r["correct"] == "yes")
    accuracy = (n_correct / len(labelled)) if labelled else None
    covered = sum(1 for r in routing if r["predicted_intent"] != FALLBACK)

    # confusable intents: cosine between example-set vectors (examples only)
    evecs = [vector(tokens(" ".join(it["examples"])), idf) for it in intents]
    confusable: dict[str, list[tuple[str, float]]] = {n: [] for n in names}
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            s = round(cosine(evecs[i], evecs[j]), 6)
            if s >= CONFUSABLE_THRESHOLD:
                confusable[names[i]].append((names[j], s))
                confusable[names[j]].append((names[i], s))
                pairs.append((names[i], names[j], s))
    pairs.sort(key=lambda p: (-p[2], p[0], p[1]))

    quality = []
    for it in intents:
        n = it["intent"]
        tp = sum(1 for r in labelled if r["expected_intent"] == n and r["predicted_intent"] == n)
        pred_n = sum(1 for r in labelled if r["predicted_intent"] == n)
        exp_n = sum(1 for r in labelled if r["expected_intent"] == n)
        quality.append({
            "intent": n, "examples": len(it["examples"]),
            "precision": (tp / pred_n) if pred_n else None, "recall": (tp / exp_n) if exp_n else None,
            "confusable_with": ";".join(c for c, _ in sorted(confusable[n], key=lambda x: (-x[1], x[0]))),
            "response_type": it["response_type"], "handoff": it["handoff"], "owner": it["owner"],
            "routed": sum(1 for r in routing if r["predicted_intent"] == n), "labelled": exp_n,
        })

    confusion: dict[tuple[str, str], int] = {}
    for r in labelled:
        if r["correct"] == "no":
            k = (r["expected_intent"], r["predicted_intent"])
            confusion[k] = confusion.get(k, 0) + 1
    confusion_pairs = sorted(confusion.items(), key=lambda kv: (-kv[1], kv[0]))

    gate = None
    if min_accuracy is not None:
        gate = {"min_accuracy": min_accuracy, "met": accuracy is not None and accuracy >= min_accuracy}
    return {"routing": routing, "quality": quality, "pairs": pairs, "confusion": confusion_pairs,
            "labelled": len(labelled), "correct": n_correct, "accuracy": accuracy, "covered": covered,
            "total": len(routing), "intents": intents, "persona": persona, "gate": gate}


# ------------------------------------------------------------------ rendering
def f3(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def pct(num: int, den: int) -> str:
    return f"{num}/{den} ({100.0 * num / den:.1f}%)" if den else "0/0"


def routing_csv(res: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["utterance", "predicted_intent", "score", "expected_intent", "correct", "nearest_intent"])
    for r in res["routing"]:
        w.writerow([echo(r["utterance"]), r["predicted_intent"], f"{r['score']:.3f}", r["expected_intent"],
                    r["correct"], r["nearest_intent"]])
    return buf.getvalue()


def quality_csv(res: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["intent", "examples", "precision", "recall", "confusable_with", "response_type", "handoff",
                "routed", "labelled", "owner"])
    for q in res["quality"]:
        w.writerow([q["intent"], q["examples"], f3(q["precision"]), f3(q["recall"]), q["confusable_with"] or "none",
                    q["response_type"], q["handoff"], q["routed"], q["labelled"], q["owner"]])
    return buf.getvalue()


def md_cell(s: str) -> str:
    return str(s).replace("|", "\\|")


def mermaid_label(s: str) -> str:
    return re.sub(r"[\[\]{}()\"<>|#;]", " ", s).strip() or "unnamed"


def mermaid(res: dict, channel: str) -> list[str]:
    groups = {rt: [it["intent"] for it in res["intents"] if it["response_type"] == rt] for rt in RESPONSE_TYPES}
    lines = ["```mermaid", "flowchart TD",
             '  U(["User message"]) --> R{"Best intent score >= ' + f"{CONFIDENCE_THRESHOLD:.2f}" + '?"}']
    labels = {"answer": "Answer", "action": "Action", "clarify": "Clarify", "handoff": "Hand-off intents"}
    for rt in RESPONSE_TYPES:
        if groups[rt]:
            names = ", ".join(mermaid_label(n) for n in groups[rt])
            lines.append(f'  R -->|yes| {rt.upper()}["{labels[rt]}: {names}"]')
    lines.append('  R -->|no| FB["Fallback: rephrase prompt"]')
    lines.append('  FB -->|matched| R')
    lines.append(f'  FB -->|still unmatched| H["Human hand-off: {mermaid_label(channel)}"]')
    if groups["handoff"]:
        lines.append("  HANDOFF --> H")
    if groups["clarify"]:
        lines.append("  CLARIFY -->|answer given| R")
    lines.append("```")
    return lines


def spec_md(res: dict) -> str:
    persona, intents = res["persona"], res["intents"]
    L: list[str] = []
    total, covered = res["total"], res["covered"]
    acc = res["accuracy"]
    L.append("# Conversation spec")
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append(f"- Intents: {len(intents)}. Utterances routed: {total}.")
    L.append(f"- Coverage: {pct(covered, total)} reach an intent at score >= {CONFIDENCE_THRESHOLD:.2f}; "
             f"{total - covered} go to fallback.")
    if acc is None:
        L.append("- Accuracy: not measured (no expected_intent labels).")
    else:
        L.append(f"- Accuracy: {pct(res['correct'], res['labelled'])} of labelled utterances routed correctly.")
    L.append(f"- Confusable intent pairs (example cosine >= {CONFUSABLE_THRESHOLD:.2f}): {len(res['pairs'])}.")
    if res["gate"]:
        g = res["gate"]
        if g["met"]:
            L.append(f"- Gate: accuracy {f3(acc)} meets min_accuracy {g['min_accuracy']:.3f}.")
        elif acc is None:
            L.append(f"- Gate: FAILED — min_accuracy {g['min_accuracy']:.3f} set but no labels to measure it (exit 1).")
        else:
            L.append(f"- Gate: FAILED — accuracy {f3(acc)} is below min_accuracy {g['min_accuracy']:.3f} (exit 1).")
    else:
        L.append("- Gate: none set (no min_accuracy).")
    L.append("")
    L.append("## Persona")
    L.append("")
    L.append("| Key | Value | Source |")
    L.append("|---|---|---|")
    for k in PERSONA_KEYS:
        p = persona.get(k)
        L.append(f"| {k} | {md_cell(p['value']) if p else TBD} | {md_cell(p['source']) if p and p['source'] else '—'} |")
    L.append("")
    L.append("## Intents")
    L.append("")
    L.append("| Intent | Response type | Hand-off | Examples | Routed | Precision | Recall | Confusable with | Owner |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for q in res["quality"]:
        L.append(f"| {md_cell(q['intent'])} | {q['response_type']} | {q['handoff']} | {q['examples']} | {q['routed']} | "
                 f"{f3(q['precision'])} | {f3(q['recall'])} | {md_cell(q['confusable_with']) or 'none'} | {md_cell(q['owner'])} |")
    L.append("")
    L.append("## Fallback and hand-off")
    L.append("")
    channel = persona["escalation_channel"]["value"] if "escalation_channel" in persona else TBD
    handoff_intents = [it["intent"] for it in intents if it["handoff"] == "yes"]
    L.append(f"- Fallback: any utterance whose best intent score is below {CONFIDENCE_THRESHOLD:.2f} gets a rephrase "
             "prompt; a second miss goes to a person.")
    L.append(f"- Escalation channel: {channel}.")
    L.append(f"- Intents that hand off to a person: {', '.join(handoff_intents) if handoff_intents else 'none'}.")
    if "disallowed_topics" in persona:
        L.append(f"- Disallowed topics (decline and route to fallback): {persona['disallowed_topics']['value']}.")
    else:
        L.append(f"- Disallowed topics: {TBD}.")
    L.append("")
    L.extend(mermaid(res, channel if "escalation_channel" in persona else "channel to be baselined"))
    L.append("")
    L.append("## Coverage")
    L.append("")
    L.append(f"Covered {pct(covered, total)}. Uncovered utterances (first {MAX_ECHO} characters only):")
    L.append("")
    uncovered = [r for r in res["routing"] if r["predicted_intent"] == FALLBACK]
    if uncovered:
        L.append("| Utterance | Nearest intent | Score | Expected |")
        L.append("|---|---|---|---|")
        for r in uncovered:
            L.append(f"| {md_cell(echo(r['utterance']))} | {r['nearest_intent']} | {r['score']:.3f} | "
                     f"{r['expected_intent'] or '—'} |")
    else:
        L.append("None: every utterance reached an intent.")
    L.append("")
    if res["confusion"]:
        L.append("Confusion pairs (expected → predicted, labelled utterances):")
        L.append("")
        L.append("| Expected | Predicted | Count |")
        L.append("|---|---|---|")
        for (e, p), c in res["confusion"]:
            L.append(f"| {e} | {p} | {c} |")
        L.append("")
    L.append("## Gaps")
    L.append("")
    gaps = []
    for q in res["quality"]:
        if q["examples"] < MIN_EXAMPLES:
            gaps.append(f"Thin intent `{q['intent']}`: {q['examples']} example(s), guideline is {MIN_EXAMPLES} "
                        f"(owner: {q['owner']}).")
        if q["routed"] == 0:
            gaps.append(f"No utterance routed to `{q['intent']}`: check it is needed or add real phrasings "
                        f"(owner: {q['owner']}).")
        if q["recall"] is not None and q["recall"] < 1.0:
            gaps.append(f"`{q['intent']}` recall {f3(q['recall'])}: add the missed phrasings as examples "
                        f"(owner: {q['owner']}).")
        if q["precision"] is not None and q["precision"] < 1.0:
            gaps.append(f"`{q['intent']}` precision {f3(q['precision'])}: other requests route here; tighten its "
                        f"examples or add the missing intent (owner: {q['owner']}).")
    for a, b, s in res["pairs"]:
        gaps.append(f"Confusable: `{a}` and `{b}` (example cosine {s:.3f}); sharpen examples or merge "
                    "(owner: Conversation designer).")
    for it in intents:
        if it["response_type"] == "handoff" and it["handoff"] != "yes":
            gaps.append(f"`{it['intent']}` has response_type handoff but handoff=no (owner: {it['owner']}).")
    if not handoff_intents:
        gaps.append("No intent hands off to a person; only fallback reaches one (owner: Conversation designer).")
    n_unc = total - covered
    if n_unc:
        gaps.append(f"{n_unc} uncovered utterance(s): add intents or examples, or confirm they are out of scope "
                    "(owner: Conversation designer).")
    missing_p = [k for k in PERSONA_KEYS if k not in persona]
    if missing_p:
        gaps.append(f"Persona keys missing: {', '.join(missing_p)} — {TBD}.")
    L.extend([f"- {g}" for g in gaps] if gaps else ["None found."])
    L.append("")
    L.append("## Method")
    L.append("")
    L.append(f"- Routing: TF-IDF cosine between the utterance and each intent's description + examples "
             f"(smoothed IDF over intent documents, L2-normalised term counts, stopwords removed, light plural "
             f"folding). Best score below {CONFIDENCE_THRESHOLD:.2f} → `fallback`. Ties break by intent name.")
    L.append(f"- Confusable: TF-IDF cosine between two intents' example sets >= {CONFUSABLE_THRESHOLD:.2f}.")
    L.append("- Precision = correct / routed-to-intent; recall = correct / labelled-as-intent; labelled rows only.")
    L.append(f"- Coverage = utterances routed to an intent / all utterances. Utterances are echoed to {MAX_ECHO} "
             "characters at most.")
    L.append("- Limits: lexical matching only (no synonyms or embeddings); a production NLU model will score "
             "differently. Results describe this utterance sample, not all future traffic.")
    L.append("")
    return "\n".join(L)


# ------------------------------------------------------------------ modes
def verify(routing_path: Path, intents_path: Path, utt_path: Path) -> int:
    intents = load_intents(intents_path)
    utt = load_utterances(utt_path, {i["intent"] for i in intents})
    expected = routing_csv(analyse(intents, utt, {}, None))
    actual = Path(routing_path).read_text(encoding="utf-8") if Path(routing_path).is_file() else ""
    if actual != expected:
        print(f"verify FAILED: {routing_path} does not match a fresh routing of the inputs")
        return 1
    print(f"verify ok: {len(utt)} routings reproduce")
    return 0


def leak_check(path: Path, utt_path: Path) -> int:
    rows, cols = read_csv(utt_path, "utterances")
    text = " ".join(Path(path).read_text(encoding="utf-8").split())
    leaks = 0
    for r in rows:
        u = " ".join(r.get("utterance", "").split())
        if len(u) > MAX_ECHO and u[:MAX_ECHO + 1] in text:
            leaks += 1
    if leaks:
        print(f"leak-check FAILED: {leaks} utterance(s) echoed beyond {MAX_ECHO} characters in {path}")
        return 1
    print(f"leak-check ok: no utterance echoed beyond {MAX_ECHO} characters")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--intents", type=Path)
    ap.add_argument("--utterances", type=Path)
    ap.add_argument("--persona", type=Path)
    ap.add_argument("--min-accuracy", type=str)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--verify", type=Path, help="routing.csv to re-derive from --intents/--utterances")
    ap.add_argument("--leak-check", type=Path, help="output file to check against --utterances")
    args = ap.parse_args(argv)
    try:
        if args.leak_check:
            if not args.utterances:
                raise InputError("--leak-check needs --utterances")
            return leak_check(args.leak_check, args.utterances)
        if not args.intents or not args.utterances:
            raise InputError("--intents and --utterances are required")
        if args.verify:
            return verify(args.verify, args.intents, args.utterances)
        if not args.out_dir:
            raise InputError("--out-dir is required")
        min_acc = None
        if args.min_accuracy not in (None, ""):
            try:
                min_acc = float(args.min_accuracy)
            except ValueError:
                raise InputError(f"--min-accuracy must be a number 0-1, got {args.min_accuracy!r}")
            if not 0.0 <= min_acc <= 1.0:
                raise InputError(f"--min-accuracy must be between 0 and 1, got {min_acc}")
        intents = load_intents(args.intents)
        utt = load_utterances(args.utterances, {i["intent"] for i in intents})
        res = analyse(intents, utt, load_persona(args.persona), min_acc)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "routing.csv").write_text(routing_csv(res), encoding="utf-8")
    (out / "intent-quality.csv").write_text(quality_csv(res), encoding="utf-8")
    (out / "conversation-spec.md").write_text(spec_md(res), encoding="utf-8")
    acc = "n/a" if res["accuracy"] is None else f"{res['accuracy']:.3f}"
    if res["gate"] and not res["gate"]["met"]:
        print(f"gate FAILED: accuracy {acc} below min_accuracy {res['gate']['min_accuracy']:.3f}", file=sys.stderr)
        return 1
    print(f"conversation spec written: coverage {res['covered']}/{res['total']}, accuracy {acc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
