#!/usr/bin/env python3
"""Build the governed Claude Code plugin from the Skills Factory: only published, approved versions, byte for byte.

    SF_API_KEY=sf_live_… python3 scripts/build_plugin.py                      # from the live factory
    python3 scripts/build_plugin.py --from-json snapshots.json                # offline (tests, air-gapped builds)
    python3 scripts/build_plugin.py --check                                   # exit 1 if the plugin on disk is stale

What it writes under plugins/skills-factory/ (the plugin root; .claude-plugin/plugin.json and hooks/ are maintained
by hand and only the version is bumped here):
  skills/<slug>/…        the published version's frozen files (sf_version_snapshots: the files it was reviewed and
                         approved on), verified against the factory's sha256 before anything is written
  shared/, vendor/<x>/   the repo files those skills reference by relative path, so they resolve inside the plugin
  governed.lock.json     per skill: version, published_at, manifest_hash, the factory's hash of the frozen files and
                         the hash of the files as installed; the hook checks the installed files against it

One transformation, documented and reversible: a skill's files reference the repo's shared/ and vendor/ as
`../../../shared/…` (skills/<domain>/<name>/ is three levels deep); in the plugin a skill is two levels deep
(skills/<slug>/), so those prefixes become `../../shared/…` and `../../vendor/…`. Nothing else changes.

Exit codes: 0 written (or --check: current), 1 --check: stale, 2 bad input / factory refused / hash mismatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "skills-factory"
PLUGIN_NAME = "skills-factory"
DEFAULT_FACTORY = "https://giri-skills-studio.vercel.app"
GENERATED = ("skills", "shared", "vendor", "governed.lock.json")
SLUG = re.compile(r"^[a-z0-9-]{1,80}$")
SAFE_PATH = re.compile(r"^[A-Za-z0-9._ ()\[\]@+,=~-]{1,120}(/[A-Za-z0-9._ ()\[\]@+,=~-]{1,120}){0,11}$")
REF = re.compile(r"\.\./\.\./\.\./(shared|vendor)/")
VENDOR_REF = re.compile(r"\.\./\.\./\.\./vendor/([A-Za-z0-9._-]+)")
IGNORED = ("__pycache__", ".pyc", ".DS_Store")


class BuildError(Exception):
    pass


def files_sha(files: list[dict]) -> str:
    """The factory's algorithm (studio/lib/factory/snapshot.ts snapshotSha): path NUL content NUL, sorted by path."""
    h = hashlib.sha256()
    for f in sorted(files, key=lambda x: x["path"]):
        h.update(f["path"].encode("utf-8") + b"\0" + f["content"].encode("utf-8") + b"\0")
    return h.hexdigest()


def ignored(rel: str) -> bool:
    return any(part == "__pycache__" or part.endswith(".pyc") or part == ".DS_Store" for part in rel.split("/"))


def dir_files(d: Path) -> list[dict]:
    """A directory's files as {path, content} (text), skipping interpreter caches — the hook uses the same rule."""
    out = []
    for p in sorted(d.rglob("*")):
        if p.is_file():
            rel = p.relative_to(d).as_posix()
            if not ignored(rel):
                out.append({"path": rel, "content": p.read_text(encoding="utf-8")})
    return out


def rewrite(content: str) -> str:
    return REF.sub(lambda m: f"../../{m.group(1)}/", content)


# ---------- sources ----------

def _get(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": "skills-factory-plugin-builder"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise BuildError(f"{url.split('/api/')[-1]}: HTTP {e.code} {body}") from None
    except urllib.error.URLError as e:
        raise BuildError(f"cannot reach the factory at {url}: {e.reason}") from None


def from_factory(factory: str, key: str) -> list[dict]:
    listing = _get(f"{factory}/api/v1/skills", key).get("skills", [])
    out = []
    for s in listing:
        if s.get("allowed") is False:
            continue
        out.append(_get(f"{factory}/api/v1/skills/{s['slug']}/snapshot", key))
    return out


def from_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["snapshots"] if isinstance(data, dict) else data


# ---------- build ----------

def validate(snap: dict) -> None:
    slug = snap.get("slug")
    if not isinstance(slug, str) or not SLUG.match(slug):
        raise BuildError(f"bad slug: {slug!r}")
    files = snap.get("files")
    if not isinstance(files, list) or not files:
        raise BuildError(f"{slug}: no files")
    paths = set()
    for f in files:
        rel = str((f or {}).get("path", ""))
        if not SAFE_PATH.match(rel) or any(p in ("", ".", "..") for p in rel.split("/")):
            raise BuildError(f"{slug}: unsafe file path {rel[:80]!r}")
        paths.add(rel)
    if "SKILL.md" not in paths:
        raise BuildError(f"{slug}: SKILL.md missing")
    if files_sha(files) != snap.get("sha256"):
        raise BuildError(f"{slug}: frozen files do not match the factory's hash — refusing to package them")
    if not isinstance(snap.get("version"), int) or snap["version"] < 1:
        raise BuildError(f"{slug}: bad version")


def plan(snapshots: list[dict], repo: Path = ROOT) -> dict:
    """Everything the plugin should contain, in memory: {files: {relpath: content}, lock: {...}}."""
    files: dict[str, str] = {}
    skills: dict[str, dict] = {}
    vendors: set[str] = set()
    for snap in sorted(snapshots, key=lambda s: s.get("slug", "")):
        validate(snap)
        slug = snap["slug"]
        if slug in skills:
            raise BuildError(f"{slug}: listed twice")
        installed = []
        for f in snap["files"]:
            c = rewrite(f["content"])
            vendors.update(VENDOR_REF.findall(f["content"]))
            installed.append({"path": f["path"], "content": c})
            files[f"skills/{slug}/{f['path']}"] = c
        skills[slug] = {
            "version": snap["version"], "version_id": snap.get("version_id"), "published_at": snap.get("published_at"),
            "manifest_hash": snap.get("manifest_hash"), "repo_skill": snap.get("repo_skill"),
            "factory_sha256": snap["sha256"], "installed_sha256": files_sha(installed),
        }
    references: dict[str, str] = {}
    for ref in ["shared"] + [f"vendor/{v}" for v in sorted(vendors)]:
        src = repo / ref
        if not src.is_dir():
            raise BuildError(f"referenced {ref}/ is not in the repo")
        ref_files = dir_files(src)
        for f in ref_files:
            files[f"{ref}/{f['path']}"] = f["content"]
        references[ref] = files_sha(ref_files)
    lock = {"plugin": PLUGIN_NAME, "note": "Generated by scripts/build_plugin.py from the Skills Factory's published versions. Do not edit.",
            "skills": skills, "references": references}
    return {"files": files, "lock": lock}


def lock_text(lock: dict) -> str:
    return json.dumps(lock, indent=2, sort_keys=True) + "\n"


def current(plugin: Path) -> dict[str, str]:
    """The generated part of the plugin as it is on disk."""
    out: dict[str, str] = {}
    for top in ("skills", "shared", "vendor"):
        d = plugin / top
        if d.is_dir():
            for f in dir_files(d):
                out[f"{top}/{f['path']}"] = f["content"]
    return out


def is_current(p: dict, plugin: Path) -> bool:
    lock_file = plugin / "governed.lock.json"
    return current(plugin) == p["files"] and lock_file.is_file() and lock_file.read_text(encoding="utf-8") == lock_text(p["lock"])


def bump(version: str) -> str:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version or "")
    if not m:
        return "1.0.0"
    return f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}"


def write(p: dict, plugin: Path) -> str:
    """Replace the generated part of the plugin and bump plugin.json's patch version. Returns the new version."""
    for top in ("skills", "shared", "vendor"):
        shutil.rmtree(plugin / top, ignore_errors=True)
    for rel, content in p["files"].items():
        dest = plugin.joinpath(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    (plugin / "governed.lock.json").write_text(lock_text(p["lock"]), encoding="utf-8")
    manifest_path = plugin / ".claude-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = bump(manifest.get("version", ""))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest["version"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--factory", default=os.environ.get("SF_FACTORY_URL", DEFAULT_FACTORY))
    ap.add_argument("--from-json", type=Path, help="snapshots exported from the factory (offline build)")
    ap.add_argument("--plugin", type=Path, default=PLUGIN)
    ap.add_argument("--check", action="store_true", help="only report whether the plugin on disk is current")
    a = ap.parse_args(argv)
    try:
        if a.from_json:
            snaps = from_json(a.from_json)
        else:
            key = os.environ.get("SF_API_KEY", "")
            if not key.startswith("sf_live_"):
                raise BuildError("set SF_API_KEY to a factory API key (sf_live_…)")
            snaps = from_factory(a.factory.rstrip("/"), key)
        p = plan(snaps)
    except BuildError as e:
        print(f"build_plugin: {e}", file=sys.stderr)
        return 2
    n = len(p["lock"]["skills"])
    if is_current(p, a.plugin):
        print(f"plugin current: {n} governed skills")
        return 0
    if a.check:
        print(f"plugin stale: the factory now publishes {n} skills that differ from plugins/{a.plugin.name}", file=sys.stderr)
        return 1
    version = write(p, a.plugin)
    print(f"plugin written: {n} governed skills, version {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
