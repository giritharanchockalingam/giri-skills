#!/usr/bin/env python3
"""AI transparency notice, system card and Art. 50 disclosure checklist from a system's facts.

The user-facing notice is assembled only from the sentence templates in
assets/notice-sentences.csv, so every sentence traces to a fact. Its reading grade is the
Flesch-Kincaid grade computed here (syllable heuristic in references/readability.md); a
grade above --max-grade (default 8) fails the run. The disclosure checklist evaluates the
duties in assets/art50-duties.csv (EU AI Act Art. 50) as applies / provided / missing. It
never claims compliance.

Usage:
  python3 -I transparency_notice.py --facts facts.csv [--classification classification.json] \
      [--max-grade 8] [--strict] [--published-notice current-notice.md] --out-dir OUT
  python3 -I transparency_notice.py --verify OUT/notice.md      # re-grade and compare with transparency.json

Inputs:
  facts           kv-CSV key,value[,source,notes] (layout: assets/facts-template.csv).
  classification  optional classification.json from ai-platform/eu-ai-act-classifier; reads
                  tier (or risk_tier/classification/category) and basis (or reasons/rationale).
  max_grade       reading-grade ceiling for the notice (default 8).
  strict          exit 1 when a fact the notice needs is missing.
  published_notice  optional: the notice users see today (Markdown or text, any author). It is
                  redlined sentence by sentence against the new notice: unchanged, changed (token
                  Jaccard >= 0.5 to one published sentence), added, and removed. A removed sentence is
                  a published claim the current facts no longer support; the redline says to withdraw
                  or re-source it, never to keep it silently.
Missing facts -> [TO BE BASELINED — owner: Product owner].

Outputs (in --out-dir): notice.md, system-card.md, disclosure-checklist.csv, transparency.json,
and notice-redline.md when --published-notice is given.
Exit codes: 0 written and grade within max · 1 grade above max, or --strict with notice facts
missing — outputs still written · 2 missing/invalid input.
Stdlib only; no network; writes only inside --out-dir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TBD = "[TO BE BASELINED — owner: Product owner]"
TBD_COMPLIANCE = "[TO BE BASELINED — owner: Compliance lead]"
YES_NO = ("generates_synthetic_content", "emotion_recognition", "biometric_categorisation", "interacts_directly",
          "deep_fake", "public_interest_text")
CARD_FACTS = ("system_name", "provider", "purpose", "model", "data_sources", "human_oversight", "known_limitations",
              "intended_users", "not_intended_for", "contact", "generates_synthetic_content", "emotion_recognition",
              "biometric_categorisation", "last_updated")
DEFAULT_MAX_GRADE = 8.0
PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
WORD_RE = re.compile(r"[^\s]+")
SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")


class InputError(Exception):
    """Missing or invalid input -> exit 2."""


# ------------------------------------------------------------------ input
def read_rows(path: Path, what: str) -> tuple[list[dict], list[str]]:
    if not path or not Path(path).is_file():
        raise InputError(f"{what} file not found: {path}")
    lines = [ln for ln in Path(path).read_text(encoding="utf-8-sig").splitlines() if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None} for r in reader]
    return rows, [(c or "").strip() for c in (reader.fieldnames or [])]


def load_facts(path: Path) -> dict[str, dict]:
    rows, cols = read_rows(path, "facts")
    if "key" not in cols or "value" not in cols:
        raise InputError("facts CSV needs columns key,value[,source,notes]")
    facts = {}
    for r in rows:
        k, v = r.get("key", ""), r.get("value", "")
        if not k or not v:
            continue
        if k in YES_NO:
            if v.lower() not in ("yes", "no"):
                raise InputError(f"fact {k} must be yes or no, got {v!r}")
            v = v.lower()
        facts[k] = {"value": v, "source": r.get("source", "")}
    if not facts:
        raise InputError("facts CSV has no filled facts")
    return facts


def load_classification(path: Path | None) -> dict | None:
    if path is None:
        return None
    if not Path(path).is_file():
        raise InputError(f"classification file not found: {path}")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputError(f"classification is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise InputError("classification JSON must be an object")

    def pick(keys):
        for k in keys:
            if k in data and data[k] not in (None, "", []):
                v = data[k]
                if isinstance(v, list):
                    return "; ".join(str(x) if not isinstance(x, dict) else json.dumps(x, sort_keys=True) for x in v)
                if isinstance(v, dict):
                    return json.dumps(v, sort_keys=True, ensure_ascii=False)
                return str(v)
        return None

    return {"tier": pick(("tier", "risk_tier", "classification", "category")),
            "basis": pick(("basis", "reasons", "rationale")), "file": Path(path).name}


def load_templates() -> list[dict]:
    rows, cols = read_rows(ASSETS / "notice-sentences.csv", "notice templates")
    return rows


def load_duties() -> list[dict]:
    rows, cols = read_rows(ASSETS / "art50-duties.csv", "Art. 50 duties")
    return rows


# ------------------------------------------------------------------ readability
def syllables(word: str) -> int:
    """Vowel-group heuristic (references/readability.md)."""
    if any(ch.isdigit() for ch in word) or "@" in word or "://" in word or "www." in word.lower():
        return 1
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    n = len(re.findall(r"[aeiouy]+", w))
    if n > 1 and w.endswith("e") and not w.endswith(("le", "ee", "ye")):
        n -= 1
    return max(1, n)


def readability(text: str) -> dict:
    text = text.replace(TBD, "unknown")
    words = [w for w in WORD_RE.findall(text) if re.search(r"[A-Za-z0-9]", w)]
    sentences = max(1, len(SENTENCE_END_RE.findall(text)))
    syl = sum(syllables(w) for w in words)
    nw = len(words)
    grade = 0.39 * (nw / sentences) + 11.8 * (syl / nw) - 15.59 if nw else 0.0
    return {"grade": round(grade, 1), "word_count": nw, "sentence_count": sentences, "syllable_count": syl}


# ------------------------------------------------------------------ build
def fv(facts: dict, k: str) -> str | None:
    return facts[k]["value"] if k in facts else None


def build(facts: dict, classification: dict | None, max_grade: float, strict: bool) -> dict:
    sentences, notice_missing = [], []
    for t in load_templates():
        when = t["when"]
        if when != "always":
            k, _, want = when.partition("=")
            if fv(facts, k) != want:
                continue
        missing = [p for p in PLACEHOLDER_RE.findall(t["template"]) if p not in facts]
        text = PLACEHOLDER_RE.sub(lambda m: fv(facts, m.group(1)) or TBD, t["template"])
        notice_missing += [m for m in missing if m not in notice_missing]
        sentences.append({"id": t["id"], "text": text, "complete": not missing})
    body = " ".join(s["text"] for s in sentences)
    read = readability(body)
    grade_ok = read["grade"] <= max_grade

    by_id = {s["id"]: s for s in sentences}
    checklist = []
    duties = load_duties()
    applies_by_fact = {}
    for d in duties:
        if d["applies_when"] == "any":
            continue
        v = fv(facts, d["applies_when"])
        applies_by_fact[d["id"]] = "yes" if v == "yes" else "no" if v == "no" else TBD
    for d in duties:
        if d["applies_when"] == "any":
            vals = list(applies_by_fact.values())
            applies = "yes" if "yes" in vals else (TBD if TBD in vals else "no")
        else:
            applies = applies_by_fact[d["id"]]
        ev = d["evidence"]
        if ev.startswith("notice:"):
            s = by_id.get(ev.split(":", 1)[1])
            provided = "yes" if s and s["complete"] else "no"
            evidence = f"notice.md sentence '{s['id']}'" if s and s["complete"] else "no complete notice sentence"
        elif ev == "placement+grade":
            place = fv(facts, "notice_placement")
            provided = "partial" if place and grade_ok else "no"
            evidence = (f"placement: {place or 'not stated'}; reading grade {read['grade']} vs max {max_grade:g}; "
                        "other accessibility requirements not assessed")
        else:
            val = fv(facts, ev)
            provided = "yes" if val else "no"
            evidence = f"{ev}: {val}" if val else f"{ev} not stated"
        if applies == "no":
            status, provided = "not applicable", "n/a"
            evidence = "duty does not apply: " + (f"{d['applies_when']}=no" if d["applies_when"] != "any"
                                                  else "no other duty applies")
        elif applies == TBD:
            status = "to confirm"
        else:
            status = {"yes": "provided", "partial": "partial", "no": "missing"}[provided]
        checklist.append({"duty": d["duty"], "article": d["article"], "addressee": d["addressee"],
                          "applies": applies, "provided": provided, "status": status, "evidence": evidence,
                          "owner": d["owner"]})

    all_keys = [r["key"] for r in read_rows(ASSETS / "facts-template.csv", "facts template")[0]]
    # evidence facts only matter when their trigger fact is not "no"
    conditional = {"content_marking": "generates_synthetic_content", "deep_fake_label": "deep_fake",
                   "public_interest_text_label": "public_interest_text"}
    missing_facts = [k for k in all_keys if k not in facts and fv(facts, conditional.get(k, "")) != "no"]
    counts = {s: sum(1 for c in checklist if c["status"] == s)
              for s in ("provided", "partial", "missing", "to confirm", "not applicable")}
    return {"facts": facts, "classification": classification, "sentences": sentences, "readability": read,
            "max_grade": max_grade, "grade_ok": grade_ok, "notice_missing": notice_missing,
            "missing_facts": missing_facts, "checklist": checklist, "counts": counts, "strict": strict}


# ------------------------------------------------------------------ redline
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+")
CHANGED_MIN_SIMILARITY = 0.5


def split_sentences(body: str) -> list[str]:
    return [s.strip() for s in SPLIT_RE.split(body) if s.strip()]


def load_published(path: Path) -> list[str]:
    if not Path(path).is_file():
        raise InputError(f"published notice file not found: {path}")
    text = COMMENT_RE.sub("", Path(path).read_text(encoding="utf-8-sig"))
    sentences = split_sentences(notice_body(text))
    if not sentences:
        raise InputError("published notice has no sentences")
    return sentences


def _tokens(s: str) -> set[str]:
    """Lower-case words; every number counts as the same token, so a new date or figure reads as a change."""
    return {"<num>" if tok.isdigit() else tok for tok in TOKEN_RE.findall(s.lower())}


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def redline(published: list[str], new: list[str]) -> list[dict]:
    """Rows in new-notice order (removed rows last): status unchanged | changed | added | removed."""
    pairs: dict[int, tuple[int, float]] = {}
    used: set[int] = set()
    for i, s in enumerate(new):  # exact matches first
        j = next((j for j, p in enumerate(published) if j not in used and p == s), None)
        if j is not None:
            pairs[i] = (j, 1.0)
            used.add(j)
    cands = sorted(((similarity(s, p), i, j) for i, s in enumerate(new) if i not in pairs
                    for j, p in enumerate(published) if j not in used), key=lambda x: (-x[0], x[1], x[2]))
    for sim, i, j in cands:  # then best one-to-one near matches
        if sim < CHANGED_MIN_SIMILARITY:
            break
        if i in pairs or j in used:
            continue
        pairs[i] = (j, sim)
        used.add(j)
    rows = []
    for i, s in enumerate(new):
        if i in pairs:
            j, sim = pairs[i]
            rows.append({"status": "unchanged" if published[j] == s else "changed", "published": published[j], "new": s,
                         "similarity": round(sim, 2)})
        else:
            rows.append({"status": "added", "published": "", "new": s, "similarity": 0.0})
    rows += [{"status": "removed", "published": p, "new": "", "similarity": 0.0}
             for j, p in enumerate(published) if j not in used]
    return rows


def redline_md(res: dict, source: str) -> str:
    rl, k = res["redline"], res["redline_counts"]
    pub = res["published_readability"]
    L = [f"# Notice redline: {fv(res['facts'], 'system_name') or TBD}", "",
         "## Summary", "",
         f"- Published notice: `{source}` — {pub['word_count']} words, grade {pub['grade']}.",
         f"- New notice: {res['readability']['word_count']} words, grade {res['readability']['grade']} "
         f"(max {res['max_grade']:g}).",
         f"- Sentences: {k['unchanged']} unchanged, {k['changed']} changed, {k['added']} added, {k['removed']} removed.",
         "", "## Redline", "", "| Status | Published | New |", "|---|---|---|"]
    L += [f"| {r['status']} | {md_cell(r['published']) or '—'} | {md_cell(r['new']) or '—'} |" for r in rl]
    L += ["", "## Removed claims", ""]
    removed = [r["published"] for r in rl if r["status"] == "removed"]
    if removed:
        L += [f"- \"{md_cell(s)}\" — no current fact supports this sentence: withdraw it from the published notice, "
              f"or add the fact (with its source) to the facts file and re-run. Owner: Product owner." for s in removed]
    else:
        L.append("None: every published sentence is still supported by a current fact.")
    L += ["", "Every new sentence comes from a fact in the facts file; this redline does not claim compliance.", ""]
    return "\n".join(L)


# ------------------------------------------------------------------ render
def notice_md(res: dict) -> str:
    lines = ["# About this AI assistant", ""]
    lines += [s["text"] for s in res["sentences"]]
    return "\n".join(lines) + "\n"


def notice_body(text: str) -> str:
    return " ".join(ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#"))


def md_cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def card_md(res: dict) -> str:
    f = res["facts"]

    def row(label, key):
        if key in f:
            return f"| {label} | {md_cell(f[key]['value'])} | {md_cell(f[key]['source']) or '—'} |"
        return f"| {label} | {TBD} | — |"

    def table(items):
        return ["| Fact | Value | Source |", "|---|---|---|"] + [row(a, b) for a, b in items] + [""]

    name = fv(f, "system_name") or TBD
    L = [f"# System card: {name}", ""]
    L += ["## Overview", ""]
    L += table([("System name", "system_name"), ("Provider", "provider"),
                ("Purpose", "purpose"), ("Intended users", "intended_users")])
    c = res["classification"]
    if c is None:
        L.append(f"- EU AI Act classification: {TBD_COMPLIANCE} (run `ai-platform/eu-ai-act-classifier`).")
    else:
        L.append(f"- EU AI Act classification (from `{c['file']}`): tier {c['tier'] or 'not stated in file'}; "
                 f"basis: {c['basis'] or 'not stated in file'}.")
    L.append("")
    L += ["## Intended use", ""] + table([("Purpose", "purpose"), ("Intended users", "intended_users")])
    L += ["## Not intended for", ""] + table([("Not intended for", "not_intended_for")])
    L += ["## Data", ""] + table([("Data sources", "data_sources")])
    L += ["## Model", ""] + table([("Model", "model"), ("Generates synthetic content", "generates_synthetic_content")])
    L += ["## Human oversight", ""] + table([("Human oversight", "human_oversight")])
    L += ["## Limitations", ""] + table([("Known limitations", "known_limitations"),
                                         ("Emotion recognition", "emotion_recognition"),
                                         ("Biometric categorisation", "biometric_categorisation")])
    L += ["## Contact", ""] + table([("Contact", "contact")])
    r = res["readability"]
    k = res["counts"]
    L += ["## Change log", ""] + table([("Facts last updated", "last_updated")])
    L.append(f"- User notice: {r['word_count']} words, {r['sentence_count']} sentences, Flesch-Kincaid grade "
             f"{r['grade']} (max {res['max_grade']:g}){'' if res['grade_ok'] else ' — ABOVE MAX, rewrite the facts in plainer words'}.")
    L.append(f"- Disclosure checklist (EU AI Act Art. 50): {k['provided']} provided, {k['partial']} partial, "
             f"{k['missing']} missing, {k['to confirm']} to confirm, {k['not applicable']} not applicable.")
    if res.get("redline_counts"):
        rk = res["redline_counts"]
        L.append(f"- Published notice redlined: {rk['unchanged']} unchanged, {rk['changed']} changed, {rk['added']} added, "
                 f"{rk['removed']} removed sentence(s); see notice-redline.md.")
    if res["missing_facts"]:
        L.append(f"- Facts not supplied: {', '.join(res['missing_facts'])} — {TBD}.")
    else:
        L.append("- Facts not supplied: none.")
    L.append("")
    L.append("This card records the facts supplied and their sources. It is not a legal determination and does not "
             "claim compliance with any law.")
    L.append("")
    return "\n".join(L)


def checklist_csv(res: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["duty", "article", "addressee", "applies", "provided", "status", "evidence", "owner"])
    for c in res["checklist"]:
        w.writerow([c["duty"], c["article"], c["addressee"], c["applies"], c["provided"], c["status"], c["evidence"],
                    c["owner"]])
    return buf.getvalue()


def summary_json(res: dict) -> dict:
    r = res["readability"]
    return {
        "system_name": fv(res["facts"], "system_name"),
        "grade": r["grade"], "max_grade": res["max_grade"], "grade_ok": res["grade_ok"],
        "word_count": r["word_count"], "sentence_count": r["sentence_count"], "syllable_count": r["syllable_count"],
        "notice_sentences": [s["id"] for s in res["sentences"]],
        "notice_missing_facts": res["notice_missing"], "missing_facts": res["missing_facts"],
        "checklist": res["counts"], "classification": res["classification"], "strict": res["strict"],
        "note": "Not a legal determination; does not claim compliance.",
        **({"redline": res["redline_counts"]} if res.get("redline_counts") else {}),
    }


# ------------------------------------------------------------------ modes
def verify(notice_path: Path) -> int:
    notice_path = Path(notice_path)
    tj = notice_path.parent / "transparency.json"
    if not notice_path.is_file() or not tj.is_file():
        print(f"verify FAILED: need {notice_path.name} and transparency.json in {notice_path.parent}")
        return 1
    data = json.loads(tj.read_text(encoding="utf-8"))
    r = readability(notice_body(notice_path.read_text(encoding="utf-8")))
    diffs = [k for k in ("grade", "word_count", "sentence_count", "syllable_count") if r[k] != data.get(k)]
    if (r["grade"] <= data.get("max_grade", DEFAULT_MAX_GRADE)) != data.get("grade_ok"):
        diffs.append("grade_ok")
    if diffs:
        print(f"verify FAILED: {', '.join(diffs)} differ between notice.md and transparency.json")
        return 1
    print(f"verify ok: grade {r['grade']}, {r['word_count']} words")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--facts", type=Path)
    ap.add_argument("--classification", type=Path)
    ap.add_argument("--max-grade", type=str)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--published-notice", type=Path, help="the notice users see today, to redline")
    ap.add_argument("--verify", type=Path, help="notice.md to re-grade against transparency.json beside it")
    args = ap.parse_args(argv)
    if args.verify:
        return verify(args.verify)
    try:
        if not args.facts or not args.out_dir:
            raise InputError("--facts and --out-dir are required")
        max_grade = DEFAULT_MAX_GRADE
        if args.max_grade not in (None, ""):
            try:
                max_grade = float(args.max_grade)
            except ValueError:
                raise InputError(f"--max-grade must be a number, got {args.max_grade!r}")
            if max_grade <= 0:
                raise InputError("--max-grade must be above 0")
        res = build(load_facts(args.facts), load_classification(args.classification), max_grade, args.strict)
        if args.published_notice:
            published = load_published(args.published_notice)
            res["redline"] = redline(published, split_sentences(" ".join(s["text"] for s in res["sentences"])))
            res["redline_counts"] = {s: sum(1 for r in res["redline"] if r["status"] == s)
                                     for s in ("unchanged", "changed", "added", "removed")}
            res["published_readability"] = readability(" ".join(published))
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "notice.md").write_text(notice_md(res), encoding="utf-8")
    (out / "system-card.md").write_text(card_md(res), encoding="utf-8")
    (out / "disclosure-checklist.csv").write_text(checklist_csv(res), encoding="utf-8")
    (out / "transparency.json").write_text(json.dumps(summary_json(res), indent=2, sort_keys=True, ensure_ascii=False)
                                           + "\n", encoding="utf-8")
    if res.get("redline"):
        (out / "notice-redline.md").write_text(redline_md(res, args.published_notice.name), encoding="utf-8")
    code = 0
    if not res["grade_ok"]:
        print(f"gate FAILED: notice reading grade {res['readability']['grade']} above max {max_grade:g}", file=sys.stderr)
        code = 1
    if strict_fail := (args.strict and res["notice_missing"]):
        print(f"strict: notice facts missing: {', '.join(res['notice_missing'])}", file=sys.stderr)
        code = 1
    if code == 0 and not strict_fail:
        print(f"notice written: grade {res['readability']['grade']}, {res['readability']['word_count']} words; "
              f"checklist {res['counts']['missing']} missing")
    return code


if __name__ == "__main__":
    sys.exit(main())
