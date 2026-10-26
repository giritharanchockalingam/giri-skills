#!/usr/bin/env python3
"""Static review of React/Next.js components — the checks a senior frontend engineer does before a ship.

    python3 -I scripts/ui_lint.py --target <repo> --findings findings.csv --report report.md --checklist a11y-checklist.md

Scans every .tsx/.jsx file, plus .js/.ts files that contain JSX (a JavaScript Next.js repo writes components in .js:
a file counts when it returns/arrows into a JSX tag, or imports react/next AND has a JSX tag; plain utilities are
left out, and route/middleware/instrumentation/*.config files never count, so the rules cannot misfire on them). Skips node_modules,
.next, out, dist, build, coverage, tests/**, *.test.*, *.spec.*, *.stories.*, *.d.ts. Rules:
  UI1  img-without-alt           high    <img>/<Image> with no alt attribute
  UI2  icon-button-without-name  high    <button> whose children are only elements, with no aria-label/aria-labelledby/title
  UI3  clickable-div             high    <div>/<span> with onClick but missing role, tabIndex or a key handler
  UI4  input-without-label       high    <input>/<select>/<textarea> with no <label htmlFor>, aria-label(ledby) or wrapping <label>
  UI5  no-loading-state          medium  component fetching/receiving async data that renders no loading state
  UI6  no-empty-state            medium  {list.map(…)} in JSX with no length/empty check on that list in the file
  UI7  fixed-width-over-600px    medium  inline width/minWidth > 600px, or w-[Npx]/min-w-[Npx] with N > 600 and no responsive variant
  UI8  dangerous-html            high    dangerouslySetInnerHTML
  UI9  prop-sprawl               low     a Props type with > 8 members that composes no shared type (extends/&/Pick/Omit)
  UI10 inline-style-in-map       low     style={{…}} created inside a .map( callback
  UI11 color-only-state          low     className toggling text-red/text-green with children that carry no state text or icon
Writes findings.csv (rule, file, line, snippet, severity, status), report.md (Summary, Findings, Rules) and
a11y-checklist.md (WCAG 2.2 AA items the rules cover vs. the ones only a runtime check can verify).
Exit 1 when any NEW high-severity finding exists (or on bad input), 0 otherwise. --quiet prints only the summary.

Existing repo (--baseline findings.csv from an earlier run, the recorded debt): a finding whose rule, file and
snippet match a baseline row (line numbers may move) is `known`; anything else is `new`. The gate then fails only
on new high-severity findings; known debt stays listed, and baseline rows no longer found are reported as resolved.
Without --baseline every finding is `new`. Stdlib, offline, deterministic.
"""
from __future__ import annotations

import argparse
import subprocess
import csv
import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".next", "out", "dist", "build", "coverage", ".git", "tests", "test", "__tests__", "storybook-static"}

_GIT_VISIBLE: dict = {}


def git_ignored(root: Path, rel: Path) -> bool:
    """True for a file git ignores in a repository: build output under any name (a custom distDir such as `bo11/`,
    `.next-*`), caches, local env files. Found on a real repo where 1,500 findings came from a build folder the fixed
    SKIP_DIRS list did not name. Outside a git repository nothing is filtered beyond SKIP_DIRS."""
    key = str(root.resolve())
    if key not in _GIT_VISIBLE:
        try:
            # only when `root` IS a repository's top level: a tree exported inside another repository (the delivery
            # pipeline's <out>/postchange-repo under giri-skills/runs/, which giri-skills ignores) must not inherit
            # that repository's ignore rules — found live: every file of the export read as ignored, 0 files linted
            top = subprocess.run(["git", "-C", key, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30)
            if top.returncode != 0 or Path(top.stdout.strip()).resolve() != Path(key):
                _GIT_VISIBLE[key] = None
                return False
            r = subprocess.run(["git", "-C", key, "ls-files", "-co", "--exclude-standard", "-z"],
                               capture_output=True, text=True, timeout=120)
            _GIT_VISIBLE[key] = (set(r.stdout.split("\0")) - {""}) if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            _GIT_VISIBLE[key] = None
    visible = _GIT_VISIBLE[key]
    return visible is not None and rel.as_posix() not in visible

SKIP_SUFFIXES = tuple(f".{kind}.{ext}" for kind in ("test", "spec", "stories") for ext in ("tsx", "jsx", "js", "ts", "mjs", "cjs")) + (".d.ts",)
JSX_EXTS = {".tsx", ".jsx"}          # always component files
MAYBE_JSX_EXTS = {".js", ".ts"}      # component files only when they contain JSX (JavaScript Next.js repos)
EXTS = JSX_EXTS | MAYBE_JSX_EXTS
# Next.js files that are never components, whatever they contain (route handlers, middleware, instrumentation, configs).
NEVER_COMPONENT_STEMS = {"route", "middleware", "instrumentation"}
# Conservative JSX detection for .js/.ts: `return (<Tag`, `return <Tag`, `=> <Tag`, `=> (<Tag`, `return (<>` ...
JSX_RETURN = re.compile(r"(?:\breturn|=>)\s*\(?\s*<(?:>|[A-Za-z][\w.-]*(?:[\s/>]|$))")
# ... or a react/next import together with a JSX-looking tag (component tag, or a lower-case tag with a prop).
REACT_IMPORT = re.compile(r"""(?:\bfrom\s*|\brequire\s*\(\s*)["'](?:react|react-dom(?:/[\w/-]+)?|next/[\w/-]+)["']""")
JSX_TAG = re.compile(r"""<[A-Z][\w.]*(?:\s[^<>]*)?/?>|<[a-z][\w-]*\s+[\w-]+\s*=\s*(?:\{|["'])""")
PX_LIMIT = 600
PROP_LIMIT = 8

RULES = {
    "UI1": ("img-without-alt", "high", "Every image needs an alt attribute (empty alt for decorative images) — WCAG 1.1.1"),
    "UI2": ("icon-button-without-name", "high", "An icon-only button needs an accessible name: aria-label, aria-labelledby or visible/sr-only text — WCAG 4.1.2"),
    "UI3": ("clickable-div", "high", "A div/span with onClick needs role, tabIndex and a key handler, or should be a <button> — WCAG 2.1.1, 4.1.2"),
    "UI4": ("input-without-label", "high", "Every form control needs a programmatic label: <label htmlFor>, aria-label(ledby) or a wrapping <label> — WCAG 1.3.1, 3.3.2"),
    "UI5": ("no-loading-state", "medium", "A component that fetches or receives async data renders a loading state (skeleton, spinner, aria-busy or Suspense)"),
    "UI6": ("no-empty-state", "medium", "A list rendered with .map checks for an empty list and shows an empty state"),
    "UI7": (f"fixed-width-over-{PX_LIMIT}px", "medium", f"No hard-coded width > {PX_LIMIT}px without a responsive variant — content must reflow — WCAG 1.4.10"),
    "UI8": ("dangerous-html", "high", "dangerouslySetInnerHTML renders unsanitised HTML (XSS); render data as JSX or sanitise and document why"),
    "UI9": ("prop-sprawl", "low", f"A component with > {PROP_LIMIT} props composes a shared props type (extends/&/Pick/Omit) or is split"),
    "UI10": ("inline-style-in-map", "low", "style={{…}} inside a .map callback allocates a new object per row per render; hoist it or use classes"),
    "UI11": ("color-only-state", "low", "State shown by colour alone (text-red/text-green toggle) needs text or an icon as well — WCAG 1.4.1"),
}

# WCAG 2.2 success criteria (W3C Recommendation, 5 October 2023; see references/sources.md).
WCAG_COVERED = [
    ("1.1.1", "Non-text Content", "A", "UI1", "img/Image without alt"),
    ("1.3.1", "Info and Relationships", "A", "UI4", "form control without a programmatic label"),
    ("3.3.2", "Labels or Instructions", "A", "UI4", "form control without a label"),
    ("2.1.1", "Keyboard", "A", "UI3", "click handler on a div/span with no key handler / tabIndex"),
    ("4.1.2", "Name, Role, Value", "A", "UI2, UI3", "icon-only button without a name; clickable div without a role"),
    ("1.4.1", "Use of Color", "A", "UI11", "text-red/text-green toggle with no text or icon (conservative)"),
    ("1.4.10", "Reflow", "AA", "UI7", f"hard-coded width > {PX_LIMIT}px with no responsive variant (partial: only inline/Tailwind widths)"),
    ("4.1.3", "Status Messages", "AA", "UI5", "loading state exists (partial: the rule cannot verify a live region announces it)"),
]
WCAG_NOT_STATIC = [
    ("1.4.3", "Contrast (Minimum)", "AA", "computed colours; run axe/Lighthouse in the browser"),
    ("1.4.11", "Non-text Contrast", "AA", "rendered UI component and focus-indicator contrast"),
    ("1.4.13", "Content on Hover or Focus", "AA", "hover/focus behaviour (dismissable, hoverable, persistent)"),
    ("1.3.5", "Identify Input Purpose", "AA", "autocomplete tokens on user-data fields need the form's purpose"),
    ("2.4.3", "Focus Order", "A", "actual tab sequence of the rendered page"),
    ("2.4.6", "Headings and Labels", "AA", "whether headings and labels describe their content"),
    ("2.4.7", "Focus Visible", "AA", "rendered focus indicator"),
    ("2.4.11", "Focus Not Obscured (Minimum)", "AA", "sticky headers/overlays covering the focused element at runtime"),
    ("2.5.7", "Dragging Movements", "AA", "single-pointer alternative for drag interactions"),
    ("2.5.8", "Target Size (Minimum)", "AA", "rendered 24×24 CSS px target size and spacing"),
    ("3.3.7", "Redundant Entry", "A", "whether a multi-step process re-asks for data"),
    ("3.3.8", "Accessible Authentication (Minimum)", "AA", "the login flow's cognitive tests"),
]

TAG_OPEN = re.compile(r"<(img|Image|button|div|span|input|select|textarea|td|p|li|a)\b")
ATTR_ALT = re.compile(r"\balt\s*=")
ATTR_SPREAD = re.compile(r"\{\s*\.\.\.")
ATTR_NAME = re.compile(r"\b(aria-label|aria-labelledby|title)\s*=")
ATTR_ONCLICK = re.compile(r"\bonClick\s*=")
ATTR_ROLE = re.compile(r"\brole\s*=")
ATTR_TABINDEX = re.compile(r"\btabIndex\s*=")
ATTR_KEY = re.compile(r"\bonKey(Down|Up|Press)\s*=")
# a template-literal id/htmlFor ({`move-${c.id}`}) pairs by its exact template text — found on a real UI run where
# <label htmlFor={`move-${c.id}`}> + <select id={`move-${c.id}`}> was flagged UI4 (unlabelled) though it is labelled
ATTR_ID = re.compile(r"""\bid\s*=\s*(?:["']([^"']+)["']|\{\s*([\w.]+)\s*\}|\{\s*`([^`]+)`\s*\})""")
ATTR_TYPE = re.compile(r"""\btype\s*=\s*["'](hidden|submit|button|reset|image)["']""")
HTML_FOR = re.compile(r"""\bhtmlFor\s*=\s*(?:["']([^"']+)["']|\{\s*([\w.]+)\s*\}|\{\s*`([^`]+)`\s*\})""")
ARIA_LABELLED = re.compile(r"\baria-label(ledby)?\s*=")
DANGEROUS = re.compile(r"\bdangerouslySetInnerHTML\b")
ASYNC_HOOK = re.compile(r"\b(useQuery|useInfiniteQuery|useSWR|useSWRInfinite)\s*\(")
USE_EFFECT = re.compile(r"\buseEffect\s*\(")
FETCH_CALL = re.compile(r"\bfetch\s*\(|\baxios\b")
LOADING_PROP = re.compile(r"\b(isLoading|loading)\s*\??\s*:\s*boolean\b")
LOADING_RENDER = re.compile(
    r"\b(?:isLoading|isPending|isFetching|isValidating|loading|isInitialLoading)\b\s*(?:\?|&&|\)|\|\||===)"
    r"|\bif\s*\(\s*!?\s*(?:isLoading|isPending|isFetching|loading)\b"
    r"|<(?:Skeleton|Spinner|Loader|Loading|Suspense)\b|\baria-busy\b|\bfallback\s*=|status\s*===\s*['\"](?:pending|loading)['\"]")
JSX_MAP = re.compile(r"\{\s*([A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)*)\s*\??\.map\s*\(")
MAP_CALL = re.compile(r"\.map\s*\(")
INLINE_STYLE = re.compile(r"\bstyle\s*=\s*\{\{")
STYLE_WIDTH = re.compile(r"\b(?:min-?[Ww]idth|width)\s*:\s*['\"]?(\d+)(?:px)?['\"]?\s*[,}]")
STYLE_FLUID = re.compile(r"\bmaxWidth\s*:\s*['\"](?:100%|100vw)['\"]|\bwidth\s*:\s*['\"](?:100%|auto)['\"]")
CLASS_W = re.compile(r"(?<![\w:-])(?:min-)?w-\[(\d+)px\]")
CLASS_FLUID = re.compile(r"(?<![\w-])(?:w-full|max-w-full|w-auto|w-screen|(?:sm|md|lg|xl|2xl):(?:w-|max-w-|min-w-))")
CLASSNAME_ATTR = re.compile(r"\bclassName\s*=\s*(?:\"[^\"]*\"|'[^']*'|\{)")
PROPS_DECL = re.compile(r"^[ \t]*(?:export\s+)?(?:interface\s+(\w*Props)\b([^{]*)\{|type\s+(\w*Props)\b\s*=\s*([^{]*)\{)", re.M)
PROP_MEMBER = re.compile(r"^\s*(?:readonly\s+)?[\w$]+\??\s*:")
COMPOSED = re.compile(r"\bextends\b|&|\bPick<|\bOmit<|\bComponentProps|\bHTMLAttributes|\bPropsWithChildren")
COLOR_PAIR = (re.compile(r"\btext-green-\d+"), re.compile(r"\btext-red-\d+"))
STATE_TEXT = re.compile(r"\?[^:}]*:|&&|<svg\b|<\w*Icon\b|sr-only|aria-|\btitle\s*=")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def contains_jsx(text: str) -> bool:
    """True when a .js/.ts file is a React component file (see module docstring); false for plain utilities."""
    if JSX_RETURN.search(text):
        return True
    return bool(REACT_IMPORT.search(text) and JSX_TAG.search(text))


def source_files(root: Path):
    """(path, relpath, text) for every component file: .tsx/.jsx always, .js/.ts only when they contain JSX."""
    for p in sorted(root.rglob("*")):
        if p.suffix not in EXTS or not p.is_file() or p.name.endswith(SKIP_SUFFIXES):
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]) or git_ignored(root, rel):
            continue
        if p.suffix in MAYBE_JSX_EXTS and (p.stem in NEVER_COMPONENT_STEMS or p.stem.endswith(".config")):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix in MAYBE_JSX_EXTS and not contains_jsx(text):
            continue
        yield p, rel.as_posix(), text


def line_no(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def tag_end(text: str, start: int) -> int:
    """Index just past the `>` closing the JSX opening tag at `start`, skipping {…} expressions and quoted strings."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "\"'`" and depth == 0:
            j = text.find(c, i + 1)
            i = (j if j >= 0 else n) + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif c == ">" and depth == 0:
            return i + 1
        i += 1
    return n


def matched(text: str, start: int, open_ch: str, close_ch: str) -> str:
    """The `open … close` block starting at the first open_ch at/after start (bracket-matched)."""
    s = text.find(open_ch, start)
    if s < 0:
        return ""
    depth = 0
    for i in range(s, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return text[s:i + 1]
    return text[s:]


def children_of(text: str, open_end: int, name: str) -> str:
    """Children text of the element whose opening tag ends at open_end (next matching `</name>`; nesting-aware)."""
    depth, i, n = 1, open_end, len(text)
    opener, closer = re.compile(rf"<{name}\b[^>]*?(?<!/)>"), f"</{name}>"
    while i < n:
        nxt_close = text.find(closer, i)
        if nxt_close < 0:
            return text[open_end:]
        m = opener.search(text, i, nxt_close)
        if m:
            depth += 1
            i = m.end()
            continue
        depth -= 1
        if depth == 0:
            return text[open_end:nxt_close]
        i = nxt_close + len(closer)
    return text[open_end:]


def strip_tags(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "<":
            i = tag_end(s, i)
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def is_self_closing(tag: str) -> bool:
    return tag.rstrip().endswith("/>")


def has_jsx(text: str) -> bool:
    return "</" in text or "/>" in text


def lint_file(text: str, rel: str) -> list[dict]:
    out, lines = [], text.splitlines()
    seen = set()

    def add(rule: str, ln: int) -> None:
        if (rule, ln) in seen:
            return
        seen.add((rule, ln))
        name, sev, _ = RULES[rule]
        out.append({"rule": rule, "file": rel, "line": ln, "snippet": lines[ln - 1].strip()[:120], "severity": sev})

    html_for = {v1 or v2 or v3 for v1, v2, v3 in HTML_FOR.findall(text)}
    labelled_ids = set(re.findall(r"""\baria-labelledby\s*=\s*["']([^"']+)["']""", text))

    for m in TAG_OPEN.finditer(text):
        name, start = m.group(1), m.start()
        end = tag_end(text, start)
        tag = text[start:end]
        ln = line_no(text, start)
        spread = bool(ATTR_SPREAD.search(tag))
        if name in ("img", "Image"):
            if not ATTR_ALT.search(tag) and not spread:
                add("UI1", ln)
        elif name == "button":
            if not ATTR_NAME.search(tag) and not spread and not is_self_closing(tag):
                kids = children_of(text, end, "button")
                if not strip_tags(kids).strip():
                    add("UI2", ln)
        elif name in ("div", "span"):
            if ATTR_ONCLICK.search(tag) and not spread and not (
                    ATTR_ROLE.search(tag) and ATTR_TABINDEX.search(tag) and ATTR_KEY.search(tag)):
                add("UI3", ln)
        elif name in ("input", "select", "textarea"):
            if spread or ATTR_TYPE.search(tag) or ARIA_LABELLED.search(tag) or ATTR_NAME.search(tag):
                continue
            idm = ATTR_ID.search(tag)
            ident = (idm.group(1) or idm.group(2) or idm.group(3)) if idm else None
            if ident and ident in html_for:
                continue
            before = text[:start]
            if before.count("<label") - before.count("</label>") > 0:
                continue
            add("UI4", ln)
        if name in ("div", "span", "td", "p", "li", "a") and not is_self_closing(tag):
            cm = CLASSNAME_ATTR.search(tag)
            if cm:
                cls = matched(tag, cm.start(), "{", "}") if cm.group(0).endswith("{") else cm.group(0)
                cls_end = (tag.find("{", cm.start()) if cm.group(0).endswith("{") else cm.start()) + len(cls)
                rest = tag[:cm.start()] + tag[cls_end:]
                if COLOR_PAIR[0].search(cls) and COLOR_PAIR[1].search(cls) and not re.search(r"\baria-|\btitle\s*=", rest):
                    kids = children_of(text, end, name)
                    if kids.strip() and not STATE_TEXT.search(kids):
                        add("UI11", ln)

    for m in DANGEROUS.finditer(text):
        add("UI8", line_no(text, m.start()))

    if has_jsx(text):
        async_signal = ASYNC_HOOK.search(text) or (USE_EFFECT.search(text) and FETCH_CALL.search(text)) or LOADING_PROP.search(text)
        if async_signal and not LOADING_RENDER.search(text):
            add("UI5", line_no(text, async_signal.start()))

        for m in JSX_MAP.finditer(text):
            expr = m.group(1)
            last = expr.split(".")[-1].lstrip("?")
            if last.isupper() or re.search(rf"\b(?:const|let|var)\s+{re.escape(last)}\s*(?::[^=]+)?=\s*\[", text):
                continue
            parts = [re.escape(p) for p in expr.replace("?.", ".").split(".")]
            base = r"\??\.".join(parts)
            if re.search(rf"\b{base}\s*\??\.length\b|!\s*{base}\b(?!\.map)|\b{base}\.(?:some|every)\(|isEmpty\(\s*{base}\s*\)", text):
                continue
            add("UI6", line_no(text, m.start()))

    for m in INLINE_STYLE.finditer(text):
        block = matched(text, m.start(), "{", "}")
        if STYLE_FLUID.search(block):
            continue
        for wm in STYLE_WIDTH.finditer(block):
            if int(wm.group(1)) > PX_LIMIT:
                add("UI7", line_no(text, m.start() + wm.start()))
    for m in CLASSNAME_ATTR.finditer(text):
        braced = m.group(0).endswith("{")
        cls_start = text.find("{", m.start()) if braced else m.start()
        cls = matched(text, cls_start, "{", "}") if braced else m.group(0)
        if CLASS_FLUID.search(cls):
            continue
        for wm in CLASS_W.finditer(cls):
            if int(wm.group(1)) > PX_LIMIT:
                add("UI7", line_no(text, cls_start + wm.start()))

    for m in PROPS_DECL.finditer(text):
        head = m.group(2) or m.group(4) or ""
        block = matched(text, m.end() - 1, "{", "}")
        after = text[m.end() - 1 + len(block):m.end() - 1 + len(block) + 40]
        if COMPOSED.search(head) or after.lstrip().startswith("&") or COMPOSED.search(after.split("\n")[0]):
            continue
        members = sum(1 for ln_ in block.splitlines()[1:-1] if PROP_MEMBER.match(ln_))
        if members > PROP_LIMIT:
            add("UI9", line_no(text, m.start()))

    for m in MAP_CALL.finditer(text):
        call = matched(text, m.end() - 1, "(", ")")
        for sm in INLINE_STYLE.finditer(call):
            add("UI10", line_no(text, m.end() - 1 + sm.start()))

    return out


def norm_snippet(s: str) -> str:
    """One form for both sides of a baseline match: a snippet is cut at a fixed width AFTER stripping, so a live
    one can end in whitespace (`m.id, `) while the CSV round-trip strips it — strip and collapse internal runs."""
    return " ".join(str(s or "").split())


def load_baseline(path: Path) -> list[tuple[str, str, str]]:
    if not path.is_file():
        die(f"baseline not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in ("rule", "file", "snippet") if c not in (reader.fieldnames or [])]
        if missing:
            die(f"baseline lacks column(s) {missing} (expected a findings.csv from this script)")
        return [((r.get("rule") or "").strip(), (r.get("file") or "").strip(), (r.get("snippet") or "").strip())
                for r in reader if (r.get("rule") or "").strip() and not (r.get("rule") or "").startswith("#")]


def apply_baseline(findings: list[dict], baseline: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Mark each finding known/new (one baseline row matches one finding); return the unmatched (resolved) rows."""
    pool = [(r, fl, norm_snippet(s)) for r, fl, s in baseline]
    for f in findings:
        key = (f["rule"], f["file"], norm_snippet(f["snippet"]))
        if key in pool:
            pool.remove(key)
            f["status"] = "known"
        else:
            f["status"] = "new"
    return pool


def write_report(path: Path, findings: list[dict], n_files: int, target: Path,
                 resolved: list[tuple[str, str, str]] | None) -> None:
    by_rule: dict[str, list[dict]] = {}
    for f in findings:
        by_rule.setdefault(f["rule"], []).append(f)
    high = sum(1 for f in findings if f["severity"] == "high")
    medium = sum(1 for f in findings if f["severity"] == "medium")
    low = len(findings) - high - medium
    new_high = sum(1 for f in findings if f["severity"] == "high" and f["status"] == "new")
    based = resolved is not None
    head = f"**{len(findings)} finding(s) in {n_files} component file(s): {high} high, {medium} medium, {low} low"
    if based:
        known = sum(1 for f in findings if f["status"] == "known")
        head += f"; {len(findings) - known} new, {known} known from the baseline, {len(resolved)} resolved"
    gate = ("Gate: FAIL (new high-severity findings)." if new_high else
            "Gate: PASS (no new high-severity findings; known debt listed below)." if high else "Gate: PASS.") if based \
        else ("Gate: FAIL (high-severity findings)." if high else "Gate: PASS.")
    lines = [f"# UI component quality — {target.name}", "", head + ".** " + gate, "",
             "Static review of React component files (.tsx/.jsx, and .js/.ts containing JSX): accessibility, loading/empty states, responsive layout, reusability. "
             "It reads source only — see a11y-checklist.md for the WCAG items that need a browser run.", "",
             "## Summary", "", "| Rule | Name | Severity | Count |", "|---|---|---|---|"]
    for rule, (name, sev, _) in RULES.items():
        lines.append(f"| {rule} | {name} | {sev} | {len(by_rule.get(rule, []))} |")
    lines += ["", "## Findings", "", "| Rule | File:line | Severity | Status | Snippet |", "|---|---|---|---|---|"]
    for f in findings:
        snippet = f["snippet"].replace("|", "\\|")
        lines.append(f"| {f['rule']} | `{f['file']}:{f['line']}` | {f['severity']} | {f['status']} | `{snippet}` |")
    if not findings:
        lines.append("| — | — | — | — | no findings |")
    if based:
        lines += ["", "## Baseline", "",
                  "Known findings are recorded debt: fix them in their own PRs and re-record the baseline. Resolved since the baseline:", ""]
        lines += [f"- {r} `{f_}` — {s_}" for r, f_, s_ in resolved] or ["- none"]
    lines += ["", "## Rules", ""]
    for rule, (name, sev, why) in RULES.items():
        lines.append(f"- **{rule} {name}** ({sev}) — {why}")
    lines += ["", "Limits: source-only heuristics (no render, no DOM, no network); contrast, focus, target size and "
              "live-region behaviour need a browser check (`webapp-testing-runner`)."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checklist(path: Path, findings: list[dict], target: Path) -> None:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["rule"]] = counts.get(f["rule"], 0) + 1
    lines = [f"# WCAG 2.2 AA checklist — {target.name}", "",
             "WCAG 2.2 (W3C Recommendation, 5 October 2023). Levels A and AA only. "
             "Sources and the date verified: `references/sources.md`.", "",
             "## Covered by the rules (static)", "",
             "| SC | Title | Level | Rule(s) | What the rule checks | This run |", "|---|---|---|---|---|---|"]
    for sc, title, level, rules, what in WCAG_COVERED:
        n = sum(counts.get(r.strip(), 0) for r in rules.split(","))
        status = f"{n} finding(s)" if n else "no findings"
        lines.append(f"| {sc} | {title} | {level} | {rules} | {what} | {status} |")
    lines += ["", "UI8 (dangerouslySetInnerHTML) is a security check, not a WCAG criterion; UI6, UI9 and UI10 are "
              "quality rules outside WCAG.", "",
              "## Not checkable statically (needs a rendered page)", "",
              "| SC | Title | Level | Why static analysis cannot decide it |", "|---|---|---|---|"]
    for sc, title, level, why in WCAG_NOT_STATIC:
        lines.append(f"| {sc} | {title} | {level} | {why} |")
    lines += ["", "Run these with axe-core / Lighthouse in an e2e flow (`webapp-testing-runner`) before sign-off. "
              "Passing every rule above is necessary, not sufficient, for WCAG 2.2 AA."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Static UI component quality review for React/Next.js (.tsx/.jsx, and .js/.ts files containing JSX)")
    ap.add_argument("--target", required=True, help="repo root or components directory")
    ap.add_argument("--findings", default="findings.csv")
    ap.add_argument("--report", default="report.md")
    ap.add_argument("--checklist", default="a11y-checklist.md")
    ap.add_argument("--quiet", action="store_true", help="print only the summary line")
    ap.add_argument("--baseline", default="", help="findings.csv from an earlier run: known debt that does not gate")
    a = ap.parse_args()
    target = Path(a.target)
    if not target.is_dir():
        die(f"target is not a directory: {target}")
    findings, n_files = [], 0
    for _p, rel, text in source_files(target):
        n_files += 1
        findings += lint_file(text, rel)
    if n_files == 0:
        die(f"no React component files under {target} (looked for .tsx/.jsx, and .js/.ts files containing JSX)")
    findings.sort(key=lambda f: (f["file"], f["line"], f["rule"]))
    resolved = apply_baseline(findings, load_baseline(Path(a.baseline))) if a.baseline else None
    if resolved is None:
        for f in findings:
            f["status"] = "new"
    fp, rp, cp = Path(a.findings), Path(a.report), Path(a.checklist)
    for p in (fp, rp, cp):
        p.parent.mkdir(parents=True, exist_ok=True)
    with fp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["rule", "file", "line", "snippet", "severity", "status"])
        w.writeheader()
        w.writerows(findings)
    write_report(rp, findings, n_files, target, resolved)
    write_checklist(cp, findings, target)
    high = [f for f in findings if f["severity"] == "high" and f["status"] == "new"]
    if not a.quiet:
        for f in findings:
            print(f"{f['severity']:6} {f['rule']:4} {f['file']}:{f['line']}  {f['snippet']}"
                  + ("  (known)" if f["status"] == "known" else ""))
    print(f"{len(findings)} finding(s) in {n_files} file(s); {len(high)} {'new ' if resolved is not None else ''}high -> {fp}, {rp}, {cp}")
    if high:
        print(f"gate: FAIL — {len(high)} {'new ' if resolved is not None else ''}high-severity finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
