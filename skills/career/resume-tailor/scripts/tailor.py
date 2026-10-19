#!/usr/bin/env python3
"""Map JD keywords to master-résumé evidence lines — the deterministic half of the TRUTH LOCK.

    python3 -I scripts/tailor.py --jd jd.txt --master master-resume.md \
        --keyword-map keyword-map.csv --gap-list gap-list.md --bullets candidate-bullets.md

master-resume.md: every fact line is numbered `MR-Lnn | text` (layout: assets/master-resume.example.md).

What it does, deterministically:
  * extracts keywords from the JD's requirement lines — proper nouns and acronyms (SAP S/4HANA, FinOps,
    MBA), noun phrases with a known head (ERP consolidation, API gateway, vendor management), scale
    markers ($25M budget, 10+ years) — and weights each `must` or `nice` from the line's own wording;
  * looks for literal support in the master résumé: every content token of the keyword (crudely
    stemmed) on one MR line, or a scale marker that the MR meets or exceeds. No synonym guessing;
  * keyword-map.csv  — jd_keyword, present_in_master (yes/no), master_line_ids, weight;
  * gap-list.md      — keywords with no support. They go to the user, never into the résumé;
  * candidate-bullets.md — for every supported JD must-have (then nice-to-have), the supporting
    master lines quoted VERBATIM with their ids. The script rewrites nothing; the llm step does, and
    scripts/check_traceability.py proves every bullet it writes still traces.
--draft-only --final tailored-resume.md: no model step — the tailored résumé is assembled from master lines
quoted verbatim with their ids (Summary = the master's summary lines; Selected experience = the lines
that support JD keywords, must-haves first, under the master's own role headers; Skills = supported JD
keywords without figures, each citing its lines; Education = the master's education lines), so
check_traceability.py passes by construction. Labelled as a draft.
--existing tailored.md --final tailored-resume.md: a résumé you already tailored is kept verbatim and
extended — every supported JD keyword whose master lines it does not cite yet gets one verbatim, cited
bullet under "Additions for this JD" — so the trace gate checks your text and the additions together.
Exit 1 on a missing/empty file or a master résumé without MR-L ids. Stdlib only, offline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

MR_LINE_RE = re.compile(r"^\s*(MR-L\d+)\s*\|\s*(.*)$")
TBD_RESUME = "[TO BE BASELINED — owner: Candidate]"
NICE_RE = re.compile(r"nice[- ]to[- ]have|preferred|a plus|is a plus|ideally|bonus|desirable|nice to", re.I)
MUST_RE = re.compile(r"\bmust\b|\brequired\b|\brequire[sd]?\b|\bminimum\b", re.I)
LABEL_RE = re.compile(r"^(must[- ]haves?|nice[- ]to[- ]haves?|required|preferred|requirements?|qualifications?|"
                      r"responsibilities|you (?:will|have)|what you(?:'ll)? bring)\s*[:\-–]\s*", re.I)
PAREN_RE = re.compile(r"\(([^()]{2,60})\)")
MONEY_RE = re.compile(r"\$\s?(\d+(?:\.\d+)?)\s*([MBK])\b", re.I)
YEARS_RE = re.compile(r"(\d+)\s*\+?\s*years?", re.I)
HEADS = ("consolidation", "modernization", "modernisation", "migration", "management", "integration",
         "integrations", "gateway", "program", "programs", "platform", "platforms", "leadership", "governance",
         "transformation", "architecture", "engineering", "strategy", "roadmap", "optimization", "operations",
         "security", "compliance", "analytics", "automation", "delivery", "negotiation", "committee",
         "re-platform", "replatform", "remediation", "certification", "payer", "payers", "domain")
# single words that stand as keywords on their own (industries, platforms-as-words, functions)
STANDALONE = {"insurance", "healthcare", "claims", "enrollment", "manufacturing", "retail", "banking", "payer",
              "vendor", "vendors", "outsourcing", "procurement", "cybersecurity", "privacy", "audit"}
TEAM_RE = re.compile(r"team of (\d+)|(\d+)\s*\+?\s*(?:people|engineers|staff|fte|direct reports|employees)", re.I)
STOP = {"a", "an", "the", "and", "or", "of", "with", "in", "for", "to", "on", "at", "by", "is", "are", "be",
        "have", "has", "must", "required", "preferred", "experience", "strong", "proven", "demonstrated",
        "ability", "plus", "nice", "ideally", "years", "year", "more", "least", "minimum", "including",
        "across", "within", "large", "scale", "we", "you", "our", "your", "as", "that", "this", "such",
        "etc", "e.g", "eg", "ie", "i.e", "value", "role", "candidate", "team", "teams", "working", "own",
        "owned", "owning", "leading", "lead", "led", "managing", "manage", "managed", "building", "build",
        "track", "record", "hands", "deep", "solid", "relevant", "equivalent", "comparable", "similar",
        "exposure", "end", "or", "and", "related"}
GENERIC_CAPS = {"Must", "Nice", "Required", "Preferred", "Experience", "Strong", "Proven", "Ability", "We",
                "You", "Our", "The", "A", "An", "Location", "Travel", "Requirements", "Responsibilities",
                "Bachelor", "Master", "Degree", "Minimum", "Plus", "Senior", "Director", "Vice", "President",
                "Manager", "Lead", "Head", "Chief", "Reports", "Reporting", "Hybrid", "Remote", "Onsite",
                "Up", "Yes", "No", "Title", "Company", "Team", "Role", "About", "What", "Who", "How", "Led",
                "Lead", "Leading", "Managed", "Owned", "Own", "Delivered", "Built", "Drive", "Driven", "Track",
                "Demonstrated", "Deep", "Hands", "Familiarity", "Knowledge", "Understanding", "Excellent",
                "Exceptional", "Partner", "Collaborate", "Develop", "Define", "Ensure", "Oversee", "Establish",
                "Champion", "Serve", "Act", "Work", "Provide", "Support", "Maintain", "Create", "Set", "Shape",
                "Run", "Cloud", "Enterprise", "Comparable", "Must-have", "Nice-to-have"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    text = p.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        die(f"file is empty: {p}")
    return text


def stem(tok: str) -> str:
    t = tok.lower().strip("'\"“”.,;:()")
    for suf in ("ations", "ation", "ating", "ated", "ities", "ity", "ness", "ments", "ment", "ings", "ing",
                "ies", "ers", "er", "ed", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def content_tokens(text: str) -> list[str]:
    toks = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]*", text)
    return [stem(t) for t in toks if t.lower() not in STOP and len(t) > 1]


# ------------------------------------------------------------------ master résumé

def load_master(path: str) -> list[tuple[str, str]]:
    lines = []
    for raw in read(path).splitlines():
        m = MR_LINE_RE.match(raw)
        if m:
            lines.append((m.group(1), m.group(2).strip()))
    if not lines:
        die("master résumé has no `MR-Lnn | text` lines (see assets/master-resume.example.md)")
    return lines


# ------------------------------------------------------------------ JD keywords

def clean_phrase(p: str) -> str:
    p = re.sub(r"\s+", " ", p).strip(" ,;:.-–—")
    p = re.sub(r"\b(?:is )?(?:strongly )?(?:preferred|required|a plus|desirable|ideally|nice to have)\b", "", p, flags=re.I)
    return p.strip(" ,;:.-–—")


def caps_runs(clause: str) -> list[str]:
    """Runs of capitalised / acronym / versioned tokens, e.g. 'SAP S/4HANA', 'FinOps', 'MBA'."""
    out, run = [], []
    toks = clause.split()
    for i, tok in enumerate(toks):
        bare = tok.strip("“”\"'(),.;:")
        is_cap = bool(re.match(r"^[A-Z][A-Za-z0-9+#./-]*$", bare)) and bare not in GENERIC_CAPS and not (
            i == 0 and bare.lower() in STOP)
        has_inner_cap = bool(re.search(r"[a-z][A-Z]", bare)) or bool(re.search(r"[A-Z]{2}", bare)) or \
            bool(re.search(r"\d", bare))
        keep = bare and (is_cap or (has_inner_cap and bare[0].isalpha() and bare not in GENERIC_CAPS))
        nxt = toks[i + 1].lower() if i + 1 < len(toks) else ""
        verb_like = bare.istitle() and not has_inner_cap and (bare.lower().endswith(("ed", "ing"))
                                                              or nxt in STOP and nxt != "")
        if keep and not (i == 0 and verb_like):
            run.append(bare)
        else:
            if run:
                out.append(" ".join(run))
            run = []
        if tok.endswith((",", ";", ".", ")", ":")) and run:
            out.append(" ".join(run))
            run = []
    if run:
        out.append(" ".join(run))
    return [r for r in out if len(r) >= 2 and not re.fullmatch(r"\d+[%+]?", r)]


def head_phrases(clause: str) -> list[str]:
    """'cloud cost management', 'API gateway', 'ERP consolidation' — up to 3 content words + a head noun."""
    out = []
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]*", clause)
    for i, w in enumerate(words):
        wl = w.lower()
        if wl in HEADS:
            pre = []
            for prev in reversed(words[max(0, i - 3): i]):
                if prev.lower() in STOP or prev.lower() in HEADS:
                    break
                pre.insert(0, prev)
            if pre:
                out.append(" ".join(pre + [w]))
            elif wl in STANDALONE:
                out.append(w)
        elif wl in STANDALONE:
            out.append(w)
    return out


def scale_markers(line: str) -> list[tuple[str, dict]]:
    out = []
    for m in MONEY_RE.finditer(line):
        label = f"${m.group(1)}{m.group(2).upper()}" + (" budget" if re.search(r"budget|p&l|portfolio", line, re.I) else "")
        out.append((label, {"money": float(m.group(1)), "unit": m.group(2).upper()}))
    for m in YEARS_RE.finditer(line):
        out.append((f"{m.group(1)}+ years", {"years": int(m.group(1))}))
    for m in TEAM_RE.finditer(line):
        n = m.group(1) or m.group(2)
        out.append((f"team of {n}", {"team": int(n)}))
    return out


def extract_keywords(jd_text: str) -> list[dict]:
    """[{keyword, weight, line}] in JD order, deduplicated case-insensitively."""
    found, seen = [], set()
    section_nice = False
    for raw in jd_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        header = re.match(r"^(nice[- ]to[- ]haves?|preferred(?: qualifications)?|bonus|desirable)\s*:?\s*$", line, re.I)
        if header:
            section_nice = True
            continue
        if re.match(r"^(must[- ]haves?|required|requirements|responsibilities|qualifications)\s*:?\s*$", line, re.I):
            section_nice = False
            continue
        is_req = bool(re.match(r"^[-*•\d.)]+\s+", line)) or MUST_RE.search(line) or NICE_RE.search(line)
        if not is_req:
            continue
        body = re.sub(r"^[-*•\d.)]+\s+", "", line)
        body = LABEL_RE.sub("", body)
        stripped = PAREN_RE.sub(" ", body)
        weight = "nice" if (NICE_RE.search(stripped) or section_nice) and not re.search(r"\bmust\b", stripped, re.I) \
            else "must"
        cands: list[tuple[str, str]] = []
        for m in PAREN_RE.finditer(body):
            w = "nice" if NICE_RE.search(m.group(1)) else weight
            cands += [(clean_phrase(x), w) for x in re.split(r",|/(?!\d)| or ", m.group(1))]
        for clause in re.split(r",|;| and | or |/(?!\d)|\bwith\b|\bincluding\b", stripped):
            cands += [(c, weight) for c in caps_runs(clause)]
            cands += [(c, weight) for c in head_phrases(clause)]
        for label, _ in scale_markers(body):
            cands.append((label, weight))
        for c, w in cands:
            c = clean_phrase(c)
            if not c or len(c) < 2 or c.lower() in STOP:
                continue
            key = c.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append({"keyword": c, "weight": w, "line": body})
    # drop a one-word keyword that is merely a token of a longer keyword from the same line
    keep = []
    for k in found:
        longer = [o for o in found if o is not k and o["line"] == k["line"] and k["keyword"].lower() in o["keyword"].lower()
                  and len(o["keyword"]) > len(k["keyword"])]
        if longer and " " not in k["keyword"]:
            continue
        keep.append(k)
    return keep


# ------------------------------------------------------------------ matching

def money_in(text: str) -> list[tuple[float, str]]:
    return [(float(m.group(1)), m.group(2).upper()) for m in MONEY_RE.finditer(text)]


def supports(keyword: str, text: str) -> bool:
    kl, tl = keyword.lower(), text.lower()
    if re.search(r"(?<![a-z0-9])" + re.escape(kl) + r"(?![a-z0-9])", tl):
        return True
    m = re.fullmatch(r"\$(\d+(?:\.\d+)?)([MBK])(?: budget)?", keyword)
    if m:
        want, unit = float(m.group(1)), m.group(2)
        return any(u == unit and v >= want for v, u in money_in(text))
    m = re.fullmatch(r"(\d+)\+ years", keyword)
    if m:
        return any(int(y) >= int(m.group(1)) for y in YEARS_RE.findall(text))
    m = re.fullmatch(r"team of (\d+)", keyword)
    if m:
        return any(int(a or b) >= int(m.group(1)) for a, b in TEAM_RE.findall(text))
    toks = content_tokens(keyword)
    if not toks:
        return False
    ttoks = set(content_tokens(text))

    def present(t: str) -> bool:
        return t in ttoks or (len(t) >= 5 and any(t in x for x in ttoks))
    return all(present(t) for t in toks)


def map_keywords(keywords: list[dict], master: list[tuple[str, str]]) -> list[dict]:
    rows = []
    for k in keywords:
        ids = [mid for mid, text in master if supports(k["keyword"], text)]
        rows.append({"jd_keyword": k["keyword"], "present_in_master": "yes" if ids else "no",
                     "master_line_ids": ";".join(ids), "weight": k["weight"], "jd_line": k["line"]})
    return rows


# ------------------------------------------------------------------ outputs

def write_map(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["jd_keyword", "present_in_master", "master_line_ids", "weight"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_gaps(rows: list[dict], path: Path) -> None:
    gaps = [r for r in rows if r["present_in_master"] == "no"]
    lines = ["# Gap list — JD keywords with no support in the master résumé", "",
             "Rule (TRUTH LOCK): nothing on this list goes into the résumé. If the master résumé supports a "
             "keyword under another name, add the JD term to that master line first (SYNONYM rule in "
             "`references/ats-keyword-mapping.md`), then re-run. Otherwise the gap is addressed in the "
             "interview or accepted.", ""]
    if not gaps:
        lines += ["None — every extracted JD keyword has at least one supporting master line.", ""]
    else:
        lines += ["| JD keyword | Weight | JD line | Option |", "|---|---|---|---|"]
        for g in gaps:
            lines.append(f"| {g['jd_keyword']} | {g['weight']} | {g['jd_line'][:90]} | "
                         f"Add to master résumé only if true (user confirms), else omit |")
        lines.append("")
    n_must = sum(1 for g in gaps if g["weight"] == "must")
    lines += [f"Unsupported: {len(gaps)} of {len(rows)} keywords ({n_must} must-have).", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_bullets(rows: list[dict], master: list[tuple[str, str]], path: Path) -> None:
    by_id = dict(master)
    lines = ["# Candidate bullets — supporting master lines, quoted verbatim", "",
             "Each JD keyword below has literal support in the master résumé. The lines are the ONLY raw "
             "material for the tailored résumé; every tailored bullet must end with the `[MR-Lnn]` id(s) it "
             "came from, and `scripts/check_traceability.py` fails the run otherwise.", ""]
    for weight, title in (("must", "JD must-haves"), ("nice", "JD nice-to-haves")):
        sel = [r for r in rows if r["weight"] == weight and r["present_in_master"] == "yes"]
        lines += [f"## {title} with support ({len(sel)})", ""]
        if not sel:
            lines += ["(none)", ""]
        for r in sel:
            lines += [f"### {r['jd_keyword']}", ""]
            for mid in r["master_line_ids"].split(";"):
                lines.append(f"- [{mid}] {by_id[mid]}")
            lines.append("")
    unsupported = [r["jd_keyword"] for r in rows if r["present_in_master"] == "no"]
    lines += ["## Unsupported keywords (see gap-list.md)", "",
              ("- " + "\n- ".join(unsupported)) if unsupported else "(none)", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def master_layout(path: str) -> tuple[dict[str, str], dict[str, str]]:
    """id -> enclosing '## ' section title, id -> enclosing '### ' role header (or '')."""
    section, role, sec_of, role_of = "", "", {}, {}
    for raw in read(path).splitlines():
        if raw.startswith("## "):
            section, role = raw[3:].strip(), ""
        elif raw.startswith("### "):
            role = raw[4:].strip()
        m = MR_LINE_RE.match(raw)
        if m:
            sec_of[m.group(1)], role_of[m.group(1)] = section, role
    return sec_of, role_of


CITED_RE = re.compile(r"\[(MR-L\d+(?:\s*,\s*MR-L\d+)*)\]")
DRAFT_LABEL = ("<!-- Script draft: the model step was not run (draft only). Every line is a master-résumé line quoted "
               "verbatim with its id; reword it yourself, keeping the [MR-Lnn] ids. -->")


def assemble_draft(rows: list[dict], master: list[tuple[str, str]], master_path: str, jd_title: str) -> str:
    by_id = dict(master)
    sec_of, role_of = master_layout(master_path)
    L = [f"# Tailored résumé — {jd_title}", "", DRAFT_LABEL, "", "## Summary", ""]
    summary = [mid for mid, _ in master if sec_of.get(mid, "").lower().startswith("summary")]
    L += [f"- {by_id[mid]} [{mid}]" for mid in summary] or [f"- {TBD_RESUME}"]
    picked: list[str] = []
    for weight in ("must", "nice"):
        for r in rows:
            if r["weight"] == weight and r["present_in_master"] == "yes":
                for mid in r["master_line_ids"].split(";"):
                    if mid not in picked and role_of.get(mid):
                        picked.append(mid)
    L += ["", "## Selected experience", ""]
    roles = list(dict.fromkeys(role_of[m] for m, _ in master if m in picked))
    for role in roles:
        L += [f"### {role}", ""] + [f"- {by_id[m]} [{m}]" for m, _ in master if m in picked and role_of[m] == role] + [""]
    if not roles:
        L += [f"- {TBD_RESUME}", ""]
    L += ["## Skills", ""]
    skills = [r for r in rows if r["present_in_master"] == "yes" and not re.search(r"\d", r["jd_keyword"])]
    L += [f"- {r['jd_keyword']} [{', '.join(r['master_line_ids'].split(';')[:2])}]" for r in skills] or [f"- {TBD_RESUME}"]
    edu = [mid for mid, _ in master if sec_of.get(mid, "").lower().startswith("education")]
    L += ["", "## Education and certifications", ""] + ([f"- {by_id[m]} [{m}]" for m in edu] or [f"- {TBD_RESUME}"])
    return "\n".join(L) + "\n"


def extend_existing(existing: str, rows: list[dict], master: list[tuple[str, str]]) -> tuple[str, list[str]]:
    by_id = dict(master)
    cited = set()
    for m in CITED_RE.finditer(existing):
        cited |= {i.strip() for i in m.group(1).split(",")}
    adds, keys = [], []
    for weight in ("must", "nice"):
        for r in rows:
            if r["weight"] != weight or r["present_in_master"] != "yes":
                continue
            ids = r["master_line_ids"].split(";")
            if cited & set(ids):
                continue
            mid = ids[0]
            if mid not in {a[0] for a in adds}:
                adds.append((mid, r["jd_keyword"]))
            keys.append(r["jd_keyword"])
    out = existing.rstrip("\n") + "\n"
    if adds:
        out += ("\n## Additions for this JD\n\n<!-- Verbatim master lines for JD keywords your résumé does not cite yet; "
                "move each into place and reword, keeping the id. -->\n\n")
        out += "\n".join(f"- {by_id[mid]} [{mid}]" for mid, _ in adds) + "\n"
    return out, keys


def main() -> int:
    ap = argparse.ArgumentParser(description="JD keyword → master-résumé evidence map (truth-locked, no rewriting)")
    ap.add_argument("--jd", required=True, help="job description text file")
    ap.add_argument("--master", required=True, help="master résumé with MR-Lnn | line ids")
    ap.add_argument("--keyword-map", required=True, help="output CSV")
    ap.add_argument("--gap-list", required=True, help="output Markdown")
    ap.add_argument("--bullets", required=True, help="output Markdown (verbatim supporting lines)")
    ap.add_argument("--final", default="", help="tailored résumé path (written with --draft-only or --existing)")
    ap.add_argument("--draft-only", action="store_true", help="no model step: assemble --final from verbatim master lines")
    ap.add_argument("--existing", default="", help="a résumé you already tailored, to check and extend for this JD")
    a = ap.parse_args()
    jd = read(a.jd)
    master = load_master(a.master)
    keywords = extract_keywords(jd)
    if not keywords:
        die("no requirement lines found in the JD (expected bullets or lines with must/required/preferred)")
    rows = map_keywords(keywords, master)
    write_map(rows, Path(a.keyword_map))
    write_gaps(rows, Path(a.gap_list))
    write_bullets(rows, master, Path(a.bullets))
    if a.existing and a.final:
        text, missing = extend_existing(read(a.existing), rows, master)
        Path(a.final).write_text(text, encoding="utf-8")
        print(f"existing résumé kept; {len(missing)} supported JD keyword(s) it did not cite: {', '.join(missing) or 'none'}")
    elif a.draft_only and a.final:
        title = next((ln.strip() for ln in jd.splitlines() if ln.strip()), "role")[:100]
        Path(a.final).write_text(assemble_draft(rows, master, a.master, title), encoding="utf-8")
    n_yes = sum(r["present_in_master"] == "yes" for r in rows)
    print(f"{len(rows)} JD keywords: {n_yes} supported, {len(rows) - n_yes} unsupported; "
          f"{len(master)} master lines; wrote {a.keyword_map}, {a.gap_list}, {a.bullets}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
