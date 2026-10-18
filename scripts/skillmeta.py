#!/usr/bin/env python3
"""Minimal SKILL.md frontmatter parser (stdlib only, no pyyaml).

Parses the YAML subset this repo uses:
  * scalars (quoted or bare; true/false/null and integers are converted,
    everything else stays a string, so `version: 0.2.0` is "0.2.0")
  * nested block maps (2-space indent)
  * block lists of scalars (`- item`)
  * lists of flow maps  (`- {k: v, k2: [a, b]}`)
  * block maps inside list items (`- key: v` followed by indented keys)
  * flow lists (`[a, b, name:[x, y]]`) and flow maps (`{a: 1, b: "x"}`)

Anything outside that subset is parsed as a plain string; nothing raises.

API:
    parse_frontmatter(text) -> dict          # {} when no frontmatter
    load_skill(path)        -> dict           # name, description, metadata, body, dir, path
    agent_block(skill)      -> dict | None    # skill["metadata"].get("agent")
    version_tuple("0.2.0")  -> (0, 2, 0)
"""
from __future__ import annotations

from pathlib import Path

_SCALARS = {"true": True, "false": False, "null": None, "~": None}


# ------------------------------------------------------------------ scalars

def scalar(raw: str):
    s = raw.strip()
    if not s:
        return ""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if s[0] == '"' else inner
    low = s.lower()
    if low in _SCALARS:
        return _SCALARS[low]
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except ValueError:
            return s
    return s


# ------------------------------------------------------------------ flow syntax

def _split_top_level(s: str, sep: str = ",") -> list[str]:
    """Split on `sep` outside quotes and outside nested [] / {}."""
    parts, depth, quote, buf = [], 0, None, []
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf)
    if tail.strip() or parts:
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def _split_key(item: str):
    """Split `key: value` at the first top-level `: ` (colon-space) or trailing colon."""
    depth, quote = 0, None
    for i, ch in enumerate(item):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            nxt = item[i + 1:i + 2]
            if nxt in ("", " ", "\t"):
                return item[:i].strip(), item[i + 1:].strip()
    return None, item


def parse_flow(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        return [parse_flow(p) for p in _split_top_level(s[1:-1])]
    if s.startswith("{") and s.endswith("}"):
        out = {}
        for item in _split_top_level(s[1:-1]):
            k, v = _split_key(item)
            if k is None:
                out[scalar(item)] = None
            else:
                out[scalar(k)] = parse_flow(v)
        return out
    return scalar(s)


# ------------------------------------------------------------------ block syntax

def _lines(text: str):
    out = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        out.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    return out


def _parse_block(lines, i, indent):
    """Parse the block starting at lines[i] whose indent is `indent`."""
    if i >= len(lines):
        return None, i
    if lines[i][1].startswith("- ") or lines[i][1] == "-":
        return _parse_list(lines, i, indent)
    return _parse_map(lines, i, indent)


def _value_after_key(lines, i, indent, value: str):
    """Value for `key: value` at lines[i]; nested block if value is empty."""
    if value == "":
        if i + 1 < len(lines) and lines[i + 1][0] > indent:
            return _parse_block(lines, i + 1, lines[i + 1][0])
        if i + 1 < len(lines) and lines[i + 1][0] == indent and lines[i + 1][1].startswith("- "):
            # YAML allows a list at the same indent as its parent key
            return _parse_list(lines, i + 1, indent)
        return None, i + 1
    if value[0] in "[{":
        return parse_flow(value), i + 1
    return scalar(value), i + 1


def _parse_map(lines, i, indent):
    out = {}
    while i < len(lines):
        ind, content = lines[i]
        if ind < indent:
            break
        if ind > indent:  # stray deeper line; skip
            i += 1
            continue
        if content.startswith("- "):
            break
        k, v = _split_key(content)
        if k is None:
            i += 1
            continue
        out[k], i = _value_after_key(lines, i, indent, v)
    return out, i


def _parse_list(lines, i, indent):
    out = []
    while i < len(lines):
        ind, content = lines[i]
        if ind != indent or not (content.startswith("- ") or content == "-"):
            break
        rest = content[2:].strip() if content != "-" else ""
        if rest == "":
            val, i = _parse_block(lines, i + 1, lines[i + 1][0]) if i + 1 < len(lines) else (None, i + 1)
            out.append(val)
            continue
        if rest[0] in "[{":
            out.append(parse_flow(rest))
            i += 1
            continue
        k, v = _split_key(rest)
        if k is not None:
            # block map whose first key sits on the "- " line
            item_indent = indent + 2
            item = {}
            item[k], i = _value_after_key(lines, i, item_indent, v)
            if i < len(lines) and lines[i][0] == item_indent and not lines[i][1].startswith("- "):
                more, i = _parse_map(lines, i, item_indent)
                item.update(more)
            out.append(item)
            continue
        out.append(scalar(rest))
        i += 1
    return out, i


def parse_yaml_subset(text: str):
    lines = _lines(text)
    if not lines:
        return {}
    val, _ = _parse_block(lines, 0, lines[0][0])
    return val if isinstance(val, dict) else {"_": val}


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    return parse_yaml_subset(text[4:end])


def split_frontmatter(text: str):
    """Return (frontmatter_text, body_text); frontmatter_text is '' when absent."""
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---", 4)
    if end == -1:
        return "", text
    body_start = text.find("\n", end + 1)
    return text[4:end], text[body_start + 1:] if body_start != -1 else ""


# ------------------------------------------------------------------ skills

def load_skill(path) -> dict:
    """Load a SKILL.md (or its directory). Returns name, description, metadata, body, dir, path."""
    p = Path(path)
    if p.is_dir():
        p = p / "SKILL.md"
    text = p.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    _, body = split_frontmatter(text)
    meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    return {
        "name": str(fm.get("name", "") or ""),
        "description": str(fm.get("description", "") or ""),
        "metadata": meta,
        "frontmatter": fm,
        "body": body,
        "dir": p.parent,
        "path": p,
    }


def agent_block(skill: dict):
    a = skill.get("metadata", {}).get("agent")
    return a if isinstance(a, dict) else None


def version_tuple(v) -> tuple:
    out = []
    for part in str(v or "0").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


if __name__ == "__main__":  # quick manual check: python3 scripts/skillmeta.py skills/x/y
    import json
    import sys
    for arg in sys.argv[1:]:
        s = load_skill(arg)
        print(json.dumps({k: v for k, v in s.items() if k not in ("body", "dir", "path")},
                         indent=2, default=str))
