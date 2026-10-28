"""scripts/visual_check.py — a browser opens the built app; an empty, unstyled or phone-broken page fails.

Found on the CAPE greenfield run: 85/85 tests and every gate passed on a page in the browser's default Times font
with no stylesheet. These tests start a real server and a real Chromium; no mocks."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "visual_check.py"
TEXT = "<h1>Guided pathway planner</h1><p>Fictional sample program and students. Pick a student to see the plan.</p>"
STYLED = ("<style>body{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1d2433}"
          "main{max-width:960px;margin:0 auto;padding:24px}h1{font-size:28px}</style><main>" + TEXT + "</main>")
WIDE = STYLED.replace("</main>", "<div style='width:1200px;height:10px;background:#c00'></div></main>")


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def static_app(tmp: Path, html: str) -> Path:
    """A real app the check can start: package.json "dev" serves index.html on $PORT."""
    app = tmp / "app"
    (app / "node_modules").mkdir(parents=True)          # "installed" — this app has no dependencies
    (app / "index.html").write_text(f"<!doctype html><html><head><meta name=viewport content='width=device-width'>"
                                    f"<title>t</title></head><body>{html}</body></html>", encoding="utf-8")
    (app / "package.json").write_text(json.dumps({"name": "t", "scripts": {"dev": f"{sys.executable} -m http.server $PORT --bind 127.0.0.1"}}),
                                      encoding="utf-8")
    return app


def check(app: Path, tmp: Path) -> tuple[int, dict]:
    r = subprocess.run([sys.executable, str(SCRIPT), "--target", str(app), "--out", str(tmp / "out"), "--timeout", "60"],
                       capture_output=True, text=True, timeout=300)
    return r.returncode, json.loads((tmp / "out" / "visual.json").read_text(encoding="utf-8"))


def test_a_styled_page_passes_with_screenshots_at_both_widths(tmp_path):
    code, res = check(static_app(tmp_path, STYLED), tmp_path)
    assert code == 0 and res["verdict"] == "pass", res["failures"]
    assert sorted(res["screenshots"]) == ["visual-home-desktop.png", "visual-home-phone.png"]
    assert all((tmp_path / "out" / s).stat().st_size > 1000 for s in res["screenshots"])


def test_an_unstyled_page_fails_even_though_it_has_content(tmp_path):
    code, res = check(static_app(tmp_path, TEXT), tmp_path)
    assert code == 1 and res["verdict"] == "fail"
    assert any("unstyled" in f for f in res["failures"]), res["failures"]


def test_a_page_that_scrolls_sideways_on_a_phone_fails(tmp_path):
    code, res = check(static_app(tmp_path, WIDE), tmp_path)
    assert code == 1 and any("(phone)" in f and "sideways" in f for f in res["failures"]), res["failures"]
    assert not any("(desktop)" in f for f in res["failures"])


def test_an_empty_page_fails(tmp_path):
    code, res = check(static_app(tmp_path, "<style>body{font-family:sans-serif}</style><div></div>"), tmp_path)
    assert code == 1 and any("empty page" in f for f in res["failures"]), res["failures"]


def test_without_installed_dependencies_it_is_not_run_and_downloads_nothing(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "package.json").write_text(json.dumps({"dependencies": {"next": "15.0.0"}, "scripts": {"dev": "next dev"}}), encoding="utf-8")
    code, res = check(app, tmp_path)
    assert code == 3 and res["verdict"] == "not_run" and "not installed" in res["start_reason"]


def test_no_web_ui_is_not_applicable_never_a_pass(tmp_path):
    app = tmp_path / "lib"
    app.mkdir()
    (app / "main.py").write_text("print(1)\n", encoding="utf-8")
    code, res = check(app, tmp_path)
    assert code == 3 and res["verdict"] == "not_applicable"


def test_routes_are_the_static_next_pages_home_first(tmp_path):
    d = load("deliver")
    for rel in ["app/page.tsx", "app/plan/page.tsx", "app/(marketing)/about/page.tsx", "app/students/[id]/page.tsx",
                "app/api/plan/route.ts", "app/_private/page.tsx"]:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("export default function P() { return null }\n", encoding="utf-8")
    assert d.Run.visual_routes(tmp_path) == ["/", "/about", "/plan"]


@pytest.mark.parametrize("font,rules,expect", [('"Times New Roman"', 40, True), ("system-ui, sans-serif", 40, False),
                                                ("system-ui, sans-serif", 0, True)])
def test_judge_unstyled_rule(font, rules, expect):
    v = load("visual_check")
    m = {"text": 500, "rules": rules, "inline": 1, "bgs": 3, "sizes": 4, "bodyFont": font, "scrollW": 390, "innerW": 390}
    assert any("unstyled" in f for f in v.judge(m, 200, "phone", [])) is expect


def test_pages_linked_from_the_home_page_are_checked_too(tmp_path):
    """Found on greenfield G2: /progress alone was "student not found"; the real page needs ?student=…"""
    app = static_app(tmp_path, STYLED.replace("</main>", "<a href='/detail.html?student=s1'>Ada</a> <a href='/detail.html?student=s2'>Bo</a></main>"))
    (app / "detail.html").write_text("<!doctype html><html><head><meta name=viewport content='width=device-width'></head><body>"
                                     + TEXT + "</body></html>", encoding="utf-8")          # the linked page is unstyled
    code, res = check(app, tmp_path)
    assert "/detail.html?student=s1" in res["routes"] and "/detail.html?student=s2" not in res["routes"], res["routes"]
    assert code == 1 and any(f.startswith("/detail.html?student=s1") and "unstyled" in f for f in res["failures"]), res["failures"]
