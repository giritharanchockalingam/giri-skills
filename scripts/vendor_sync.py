#!/usr/bin/env python3
"""Vendor upstream Agent Skills into vendor/<name>/ from catalog/top-50.json, pinned by commit.

For each catalog entry: shallow-clone the repo once (cached under .vendor-cache/), resolve the
commit (pinned sha from vendor/pins.json if present, else the remote HEAD), copy the skill
directory verbatim, copy the repo LICENSE next to it, and record {name, repo, path, sha, license,
fetched} in vendor/pins.json. Never edits upstream content.

Usage:
  python3 scripts/vendor_sync.py                # sync all catalog entries at pinned shas (or HEAD)
  python3 scripts/vendor_sync.py --update       # move pins to current upstream HEAD
  python3 scripts/vendor_sync.py --only name    # one skill
  python3 scripts/vendor_sync.py --check        # exit 1 if vendor/ differs from pins (CI)
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "top-50.json"
VENDOR = ROOT / "vendor"
PINS = VENDOR / "pins.json"
CACHE = ROOT / ".vendor-cache"
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")


def sh(*cmd: str, cwd: Path | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def clone(repo: str) -> Path:
    dest = CACHE / repo.replace("/", "__")
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        sh("git", "clone", "--quiet", "--filter=blob:none", f"https://github.com/{repo}", str(dest))
    else:
        sh("git", "fetch", "--quiet", "origin", cwd=dest)
    return dest


def checkout(work: Path, sha: str) -> None:
    sh("git", "checkout", "--quiet", "--force", sha, cwd=work)


def resolve_by_name(work: Path, name: str) -> Path | None:
    """Find a SKILL.md whose directory equals `name`, or `name` minus a vendor prefix (vercel-x -> x)."""
    cands = [p.parent for p in work.rglob("SKILL.md") if ".git" not in p.parts and "node_modules" not in p.parts]
    for d in cands:
        if d.name == name:
            return d
    for d in cands:
        if name.endswith("-" + d.name) or d.name.endswith("-" + name):
            return d
    return None


def find_license(work: Path, skill_dir: Path) -> Path | None:
    for base in (skill_dir, work):
        for n in LICENSE_NAMES:
            if (base / n).is_file():
                return base / n
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="re-pin every entry to upstream HEAD")
    ap.add_argument("--only", action="append", default=[], help="limit to these skill names")
    ap.add_argument("--check", action="store_true", help="verify vendor/ matches pins; no changes")
    a = ap.parse_args()

    if not CATALOG.exists():
        sys.exit(f"missing {CATALOG}")
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    pins = json.loads(PINS.read_text(encoding="utf-8")) if PINS.exists() else {}
    VENDOR.mkdir(exist_ok=True)
    failures, done = [], 0

    for e in catalog:
        name = e["name"]
        if a.only and name not in a.only:
            continue
        if a.check:
            if name not in pins or not (VENDOR / name / "SKILL.md").exists():
                failures.append(f"{name}: not vendored"); continue
            done += 1
            continue
        try:
            work = clone(e["repo"])
            sha = pins.get(name, {}).get("sha") if not a.update else None
            if not sha:
                sha = sh("git", "rev-parse", "origin/HEAD", cwd=work)
            checkout(work, sha)
            src = work / e.get("path", "") if e.get("path") else work
            if not (src / "SKILL.md").is_file():
                src = resolve_by_name(work, name) or src
            if not (src / "SKILL.md").is_file():
                raise RuntimeError(f"no SKILL.md at {e['repo']}/{e.get('path', '')} (and no dir named like '{name}')")
            e["path"] = str(src.relative_to(work)).replace("\\", "/") if src != work else ""
            dst = VENDOR / name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"))
            lic = find_license(work, src)
            if lic:
                shutil.copyfile(lic, dst / "LICENSE.upstream")
            (dst / "UPSTREAM.md").write_text(
                f"# Upstream\n\nrepo: https://github.com/{e['repo']}\npath: {e.get('path','') or '/'}\n"
                f"commit: {sha}\nlicense: {e.get('license','?')}\nfetched: {time.strftime('%Y-%m-%d')}\n\n"
                "Vendored verbatim by scripts/vendor_sync.py — do not edit; re-run the sync to update.\n",
                encoding="utf-8")
            pins[name] = {"repo": e["repo"], "path": e.get("path", ""), "sha": sha,
                          "license": e.get("license", "?"), "fetched": time.strftime("%Y-%m-%d")}
            done += 1
            print(f"ok  {name:40s} {e['repo']}@{sha[:10]}")
        except Exception as ex:  # keep going; report at end
            failures.append(f"{name}: {ex}")
            print(f"ERR {name:40s} {ex}", file=sys.stderr)

    if not a.check:
        PINS.write_text(json.dumps(pins, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{done} vendored, {len(failures)} failed")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
