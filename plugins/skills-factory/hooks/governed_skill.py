#!/usr/bin/env python3
"""PreToolUse hook (matcher: Skill) of the skills-factory plugin. Stdlib only; never needs the network to decide.

Before Claude Code loads one of this plugin's skills:
  1. hash the skill's installed files (interpreter caches ignored) and compare with governed.lock.json, the hash the
     factory published for the approved version;
  2. changed → block the load (exit 2: Claude Code shows the reason to Claude and the person) — a skill edited after
     approval is no longer the approved skill; not in the lock at all → block too (fail closed); intact → allow;
  3. report the load to the factory (POST /api/v1/uses) when an API key is configured: best effort, 3-second limit,
     never changes the decision. The session id is sent hashed, never raw.

Skills from other plugins or the person's own ~/.claude/skills are not this hook's business: exit 0, no output.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

PLUGIN_NAME = "skills-factory"


def files_sha(d: Path) -> str:
    """Same algorithm as scripts/build_plugin.py files_sha over the same file set (caches ignored)."""
    h = hashlib.sha256()
    for p in sorted((p for p in d.rglob("*") if p.is_file()), key=lambda p: p.relative_to(d).as_posix()):
        rel = p.relative_to(d).as_posix()
        if any(part == "__pycache__" or part.endswith(".pyc") or part == ".DS_Store" for part in rel.split("/")):
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return "unreadable"
        h.update(rel.encode("utf-8") + b"\0" + content.encode("utf-8") + b"\0")
    return h.hexdigest()


def skill_slug(tool_input: dict) -> str | None:
    """`skills-factory:<slug>` (how Claude Code names a plugin skill) → slug; anything else → None."""
    name = str((tool_input or {}).get("skill", ""))
    prefix = PLUGIN_NAME + ":"
    return name[len(prefix):] if name.startswith(prefix) else None


def decide(root: Path, slug: str) -> tuple[str, dict | None]:
    """('verified' | 'modified' | 'unknown', lock entry)."""
    try:
        lock = json.loads((root / "governed.lock.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unknown", None
    entry = (lock.get("skills") or {}).get(slug)
    d = root / "skills" / slug
    if not entry or not d.is_dir():
        return "unknown", entry
    return ("verified" if files_sha(d) == entry.get("installed_sha256") else "modified"), entry


def report(slug: str, entry: dict, event: str, integrity: str, session: str) -> None:
    key = os.environ.get("CLAUDE_PLUGIN_OPTION_API_KEY", "").strip()
    if not key.startswith("sf_live_"):
        return
    url = (os.environ.get("CLAUDE_PLUGIN_OPTION_FACTORY_URL", "").strip() or "https://giri-skills-studio.vercel.app").rstrip("/")
    if not url.startswith("https://"):
        return
    body = {"slug": slug, "version": entry.get("version"), "sha256": entry.get("factory_sha256"), "event": event, "integrity": integrity}
    if session:
        body["session"] = hashlib.sha256(session.encode("utf-8")).hexdigest()[:32]
    req = urllib.request.Request(f"{url}/api/v1/uses", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "skills-factory-plugin"})
    try:
        urllib.request.urlopen(req, timeout=3).close()
    except Exception:  # reporting is best effort: an offline laptop still gets the integrity check
        pass


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if event.get("tool_name") != "Skill":
        return 0
    slug = skill_slug(event.get("tool_input") or {})
    if not slug:
        return 0
    root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
    integrity, entry = decide(root, slug)
    if integrity == "modified":
        if entry:
            report(slug, entry, "blocked", integrity, str(event.get("session_id", "")))
        print(f"Skills Factory: '{slug}' v{entry.get('version') if entry else '?'} was changed after it was approved, so it is "
              f"not the approved skill and will not load. Reinstall the plugin (/plugin → skills-factory → update) to "
              f"restore the approved files.", file=sys.stderr)
        return 2
    if integrity == "unknown":   # fail closed: a skill in this plugin's name that the lock does not vouch for
        print(f"Skills Factory: '{slug}' is not in this plugin's approved list (governed.lock.json), so it will not "
              f"load. Reinstall the plugin (/plugin → skills-factory → update).", file=sys.stderr)
        return 2
    report(slug, entry, "loaded", integrity, str(event.get("session_id", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
