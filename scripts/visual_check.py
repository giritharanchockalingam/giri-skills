#!/usr/bin/env python3
"""Visual check: start the built web app, look at it in a real browser, fail when a person would say "that's broken".

    python3 scripts/visual_check.py --target <repo> --out <dir> [--route / --route /plan] [--start-cmd CMD] [--timeout 180]

Why it exists: on the CAPE greenfield run every test passed (85/85) and every gate passed, and the page was plain
black-on-white HTML with no styling at all. Unit tests and linters never open the page. This does.

What it does, per route × viewport (desktop 1440×900, phone 390×844) — the given routes plus same-site pages linked
from the pages it opens (breadth-first, one per path + query-parameter names, at most 8 pages; found on greenfield G2: /progress alone was a
"student not found" page and the dashboard behind /progress?student=… was never seen):
  - loads the page in Chromium (Playwright), full-page screenshot to <out>/visual-<route>-<viewport>.png
  - FAILS on: HTTP status >= 400 or no response; an empty page (< 40 characters of visible text); an UNSTYLED page
    (no stylesheet rules reach it, or the body is still in the browser's default serif font — form controls carry
    default backgrounds, so colour counts alone missed the CAPE v1 plan page);
    horizontal scrolling at phone width; an uncaught JavaScript error
  - WARNS (does not fail) on console errors, which dev servers emit for many harmless reasons
It never judges taste. It catches the cases where a reviewer would reject the page in the first five seconds.

How the app starts: a Next.js app with its own node_modules/.bin/next dev, a Vite app with its own vite, otherwise the
package.json "dev" (or "start") script with PORT set. --start-cmd overrides; `{port}` in it is replaced. Nothing is ever
downloaded: without installed dependencies the verdict is not_run (exit 3), recorded as NOT RUN, never as a pass.

Writes <out>/visual.json: {applicable, verdict, start_cmd, url, checks: [...], failures: [...], warnings: [...], screenshots}.
Exit codes: 0 pass, 1 fail, 3 not applicable (no web UI found — recorded as such, never as a pass), 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VIEWPORTS = {"desktop": (1440, 900), "phone": (390, 844)}
MIN_TEXT = 40
MAX_PAGES = 8          # the given routes plus pages linked from opened pages (breadth-first), one per path + query-parameter names
LINKS_JS = "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"

PROBE_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  let rules = 0;
  for (const sh of Array.from(document.styleSheets)) { try { rules += sh.cssRules.length; } catch (e) { rules += 1; } }
  const inline = document.querySelectorAll('[style]').length;
  const els = Array.from(document.body ? document.body.querySelectorAll('*') : []).filter(vis).slice(0, 2000);
  const bgs = new Set(), sizes = new Set(), fonts = new Set(), colors = new Set();
  const add = el => { const s = getComputedStyle(el);
    if (s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== 'transparent') bgs.add(s.backgroundColor);
    sizes.add(s.fontSize); fonts.add(s.fontFamily); colors.add(s.color); };
  if (document.body) add(document.body);
  els.forEach(add);
  const bodyFont = document.body ? getComputedStyle(document.body).fontFamily : '';
  return { text: (document.body ? document.body.innerText : '').trim().length, rules, inline,
           bgs: bgs.size, sizes: sizes.size, fonts: fonts.size, colors: colors.size, bodyFont,
           scrollW: document.documentElement.scrollWidth, innerW: window.innerWidth, title: document.title };
}"""


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def package(target: Path) -> dict | None:
    p = target / "package.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def start_command(target: Path, port: int, override: str | None) -> tuple[str | None, str]:
    """(command, reason). command None means there is no web UI to look at."""
    if override:
        return override.replace("{port}", str(port)), "--start-cmd"
    pkg = package(target)
    if pkg is None:
        return None, "no package.json: not a web app this check knows how to start"
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    scripts = pkg.get("scripts") or {}
    if ("next" in deps or "vite" in deps or scripts) and not (target / "node_modules").is_dir():
        return None, "NOT_RUN: the app's dependencies are not installed (node_modules missing); nothing is downloaded here"
    if "next" in deps:
        return (f"./node_modules/.bin/next dev -p {port}", "Next.js app") if (target / "node_modules/.bin/next").exists() else \
               (None, "NOT_RUN: next is a dependency but node_modules/.bin/next is missing")
    if "vite" in deps:
        return (f"./node_modules/.bin/vite --port {port} --strictPort", "Vite app") if (target / "node_modules/.bin/vite").exists() else \
               (None, "NOT_RUN: vite is a dependency but node_modules/.bin/vite is missing")
    for name in ("dev", "start"):
        if name in scripts and not re.search(r"\b(node|tsx|ts-node)\b.*\b(worker|sync|server)\b", scripts[name]):
            return f"npm run {name}", f'package.json "{name}" script (PORT={port})'
    return None, "package.json has no Next.js, Vite, dev or start script: no web UI to look at"


def wait_up(url: str, proc: subprocess.Popen, timeout: float) -> str | None:
    """None once the server answers; otherwise the reason it never did."""
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            return f"the app exited with code {proc.returncode} before answering"
        try:
            with urllib.request.urlopen(url, timeout=10):
                return None
        except urllib.error.HTTPError:
            return None                      # it answered; the per-page check judges the status
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    return f"no answer from {url} within {int(timeout)} s"


def judge(m: dict, status: int | None, viewport: str, page_errors: list[str]) -> list[str]:
    fails = []
    if status is None or status >= 400:
        fails.append(f"HTTP {status if status is not None else 'no response'}")
    if m["text"] < MIN_TEXT:
        fails.append(f"empty page ({m['text']} characters of visible text)")
    default_font = re.match(r'^\s*"?(Times New Roman|Times|serif)"?\s*(,|$)', m["bodyFont"] or "", re.I) is not None
    if m["rules"] == 0 and m["inline"] < 5:
        fails.append(f"unstyled: no stylesheet reaches the page (0 CSS rules, {m['inline']} inline style(s))")
    elif default_font:
        fails.append(f"unstyled: the page uses the browser's default font ({m['bodyFont']}); no design system reached it")
    if viewport == "phone" and m["scrollW"] > m["innerW"] + 1:
        fails.append(f"scrolls sideways on a phone: content is {m['scrollW']} px wide in a {m['innerW']} px screen")
    for e in page_errors[:3]:
        fails.append(f"uncaught JavaScript error: {e[:200]}")
    return fails


def slug(route: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", route.lower()).strip("-") or "home"


def run(target: Path, out: Path, routes: list[str], override: str | None, timeout: float) -> int:
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    cmd, reason = start_command(target, port, override)
    result: dict = {"applicable": cmd is not None, "start_cmd": cmd, "start_reason": reason, "routes": list(routes),
                    "checks": [], "failures": [], "warnings": [], "screenshots": []}

    def finish(verdict: str, code: int) -> int:
        result["verdict"] = verdict
        (out / "visual.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"visual check: {verdict.upper()}" + (f" — {'; '.join(result['failures'][:4])}" if result["failures"] else "")
              + (f" ({reason})" if verdict in ("not_applicable", "not_run") else ""))
        return code

    if cmd is None:
        if reason.startswith("NOT_RUN: "):
            result["start_reason"] = reason = reason[len("NOT_RUN: "):]
            return finish("not_run", 3)
        return finish("not_applicable", 3)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["failures"].append("python playwright is not installed")
        return finish("error", 2)
    base = f"http://127.0.0.1:{port}"
    result["url"] = base
    log = open(out / "visual-server.log", "w", encoding="utf-8")
    env = {**os.environ, "PORT": str(port), "BROWSER": "none", "NEXT_TELEMETRY_DISABLED": "1", "CI": "1"}
    proc = subprocess.Popen(cmd, shell=True, cwd=str(target), stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    try:
        why = wait_up(base + routes[0], proc, timeout)
        if why:
            result["failures"].append(f"the app did not start: {why} (log: visual-server.log)")
            return finish("fail", 1)
        from urllib.parse import urlsplit, parse_qsl
        def key(r: str) -> tuple:
            u = urlsplit(r)
            return (u.path.rstrip("/") or "/", tuple(sorted(k for k, _ in parse_qsl(u.query))))
        queue, seen = list(routes), {key(r) for r in routes}
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            while queue:
                route = queue.pop(0)
                for vp, (w, h) in VIEWPORTS.items():
                    page = browser.new_page(viewport={"width": w, "height": h})
                    console, errors = [], []
                    page.on("console", lambda msg, c=console: c.append(msg.text) if msg.type == "error" else None)
                    page.on("pageerror", lambda exc, e=errors: e.append(str(exc)))
                    status = None
                    try:
                        resp = page.goto(base + route, wait_until="networkidle", timeout=int(timeout * 1000))
                        status = resp.status if resp else None
                    except Exception as exc:              # noqa: BLE001 — a page that never loads is a finding
                        errors.append(f"navigation: {str(exc).splitlines()[0][:200]}")
                    page.wait_for_timeout(500)
                    shot = out / f"visual-{slug(route)}-{vp}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    m = page.evaluate(PROBE_JS)
                    if vp == "desktop" and len(seen) < MAX_PAGES:     # follow links: /progress alone showed only "not found"
                        for href in page.evaluate(LINKS_JS):
                            u = urlsplit(href)
                            if f"{u.scheme}://{u.netloc}" != base or u.path.startswith(("/api/", "/_next/")):
                                continue
                            r = u.path + (f"?{u.query}" if u.query else "")
                            if key(r) not in seen and len(seen) < MAX_PAGES:
                                seen.add(key(r))
                                queue.append(r)
                    fails = judge(m, status, vp, errors)
                    if route not in result["routes"]:
                        result["routes"].append(route)
                    result["checks"].append({"route": route, "viewport": vp, "status": status, "metrics": m,
                                             "failures": fails, "console_errors": console[:5], "screenshot": shot.name})
                    result["screenshots"].append(shot.name)
                    result["failures"] += [f"{route} ({vp}): {f}" for f in fails]
                    result["warnings"] += [f"{route} ({vp}) console: {c[:160]}" for c in console[:3]]
                    page.close()
            browser.close()
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=15)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        log.close()
    return finish("fail" if result["failures"] else "pass", 1 if result["failures"] else 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--route", action="append", dest="routes", help="path to look at (repeatable; default /)")
    ap.add_argument("--start-cmd", help="command that starts the app; {port} is replaced")
    ap.add_argument("--timeout", type=float, default=180, help="seconds to wait for the app and for each page")
    a = ap.parse_args(argv)
    return run(a.target.resolve(), a.out.resolve(), a.routes or ["/"], a.start_cmd, a.timeout)


if __name__ == "__main__":
    sys.exit(main())
