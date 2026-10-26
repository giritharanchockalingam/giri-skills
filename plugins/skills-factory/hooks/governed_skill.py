#!/usr/bin/env python3
"""PreToolUse hook (matchers: Skill, Bash) of the skills-factory plugin. Stdlib only; never needs the network to decide.

Before Claude Code loads one of this plugin's skills, or runs a shell command that uses its files (Claude often runs a
skill's scripts straight from the plugin folder without loading the skill):
  1. hash the skill's installed files (interpreter caches ignored) and compare with governed.lock.json, the hash the
     factory published for the approved version;
  2. changed → block the load (exit 2: Claude Code shows the reason to Claude and the person) — a skill edited after
     approval is no longer the approved skill; not in the lock at all → block too (fail closed); intact → allow;
  3. report the load to the factory (POST /api/v1/uses): best effort, 3-second limit, never changes the decision. The
     session id is sent hashed, never raw. When the use is not reported (no API key — said once per session — or the
     factory refused or was unreachable) the person is told why, so a missing record is never silent.

A skill counts as one use per session however many times it is loaded or its scripts run.
Skills from other plugins, the person's own ~/.claude/skills and unrelated commands: exit 0, no output.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
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


SCRIPT_PATH = re.compile(r"skills-factory/[^/\\s'\"]+/skills/([a-z0-9-]{1,80})/")


def bash_slugs(tool_input: dict, root: Path) -> list[str]:
    """Governed skills a shell command runs files from: this plugin's installed path (any version) + /skills/<slug>/.
    Claude often runs a skill's scripts straight from the plugin cache without loading the skill first."""
    cmd = str((tool_input or {}).get("command", ""))
    found = set(SCRIPT_PATH.findall(cmd))
    marker = f"{root.as_posix().rstrip('/')}/skills/"
    for part in cmd.split(marker)[1:]:
        m = re.match(r"([a-z0-9-]{1,80})/", part)
        if m:
            found.add(m.group(1))
    return sorted(found)


def first_in_session(slug: str, session: str) -> bool:
    """True the first time a skill is used in a session (a load and its later script runs are one use)."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
    if not (data and session):
        return True
    flag = Path(data) / "used" / f"{hashlib.sha256(session.encode('utf-8')).hexdigest()[:16]}-{slug}"
    if flag.exists():
        return False
    try:
        flag.parent.mkdir(parents=True, exist_ok=True); flag.touch()
    except OSError:
        pass
    return True


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


def report(slug: str, entry: dict, event: str, integrity: str, session: str) -> str:
    """'reported', 'no_key', or 'failed: <reason>'. Never raises: the decision never depends on the network."""
    key = os.environ.get("CLAUDE_PLUGIN_OPTION_API_KEY", "").strip()
    if not key.startswith("sf_live_"):
        return "no_key"
    url = (os.environ.get("CLAUDE_PLUGIN_OPTION_FACTORY_URL", "").strip() or "https://giri-skills-studio.vercel.app").rstrip("/")
    if not url.startswith("https://"):
        return "failed: the factory URL must start with https://"
    body = {"slug": slug, "version": entry.get("version"), "sha256": entry.get("factory_sha256"), "event": event, "integrity": integrity}
    if session:
        body["session"] = hashlib.sha256(session.encode("utf-8")).hexdigest()[:32]
    req = urllib.request.Request(f"{url}/api/v1/uses", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "skills-factory-plugin"})
    try:
        urllib.request.urlopen(req, timeout=3).close()
        return "reported"
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        return f"failed: HTTP {e.code}{' ' + msg[:160] if msg else ''}"
    except Exception as e:   # offline, DNS, timeout: the integrity check still applied
        return f"failed: {type(e).__name__}"


def notice(status: str, session: str) -> str | None:
    """What to tell the person about reporting: a missing key once per session, every failure."""
    if status == "reported":
        return None
    if status == "no_key":
        data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
        if data and session:
            flag = Path(data) / "told" / hashlib.sha256(session.encode("utf-8")).hexdigest()[:16]
            if flag.exists():
                return None
            try:
                flag.parent.mkdir(parents=True, exist_ok=True); flag.touch()
            except OSError:
                pass
        return ("Skills Factory: skill checked against its approved version, but this use was not reported because no "
                "API key is set. Run /plugin configure skills-factory@giri-skills and add your sf_live_ key.")
    return f"Skills Factory: skill checked against its approved version, but reporting the use {status}."


def check(root: Path, slug: str, session: str, how: str) -> tuple[int, str | None, str | None]:
    """(exit code, stderr reason, systemMessage) for one governed skill about to be used."""
    integrity, entry = decide(root, slug)
    if integrity == "modified":
        if entry:
            report(slug, entry, "blocked", integrity, session)
        return 2, (f"Skills Factory: '{slug}' v{entry.get('version') if entry else '?'} was changed after it was approved, so "
                   f"it is not the approved skill and will not {how}. Reinstall the plugin (/plugin → skills-factory → "
                   f"update) to restore the approved files."), None
    if integrity == "unknown":   # fail closed: a skill in this plugin's name that the lock does not vouch for
        return 2, (f"Skills Factory: '{slug}' is not in this plugin's approved list (governed.lock.json), so it will not "
                   f"{how}. Reinstall the plugin (/plugin → skills-factory → update)."), None
    if not first_in_session(slug, session):
        return 0, None, None
    return 0, None, notice(report(slug, entry, "loaded", integrity, session), session)


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
    tool, tool_input = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "Skill":
        slugs, how = [s for s in [skill_slug(tool_input)] if s], "load"
    elif tool == "Bash":
        slugs, how = bash_slugs(tool_input, root), "run"
    else:
        return 0
    session = str(event.get("session_id", ""))
    messages = []
    for slug in slugs:
        code, reason, msg = check(root, slug, session, how)
        if code:
            print(reason, file=sys.stderr)
            return code
        if msg:
            messages.append(msg)
    if messages:
        print(json.dumps({"systemMessage": " ".join(dict.fromkeys(messages))}))   # shown to the person; nothing blocked
    return 0


if __name__ == "__main__":
    sys.exit(main())
