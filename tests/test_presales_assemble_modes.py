"""presales/proposal-writer: --draft-only final and the --existing team-draft redline."""
from __future__ import annotations

import sys

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/proposal-writer"
SCRIPT = SK / "scripts/assemble.py"
FX = SK / "evals/fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output  # noqa: E402


def assemble(tmp_path, *extra):
    p = {k: tmp_path / k for k in ("proposal.md", "ph.csv", "sources.md", "final.md", "redline.md")}
    r = run_script(SCRIPT, str(FX / "win-themes.json"), "--library", str(SK / "assets/section-library.md"),
                   "--estimate", str(FX / "estimate-memo.md"), "--out", str(p["proposal.md"]),
                   "--placeholders", str(p["ph.csv"]), "--sources", str(p["sources.md"]), "--final", str(p["final.md"]),
                   "--redline", str(p["redline.md"]), *extra)
    return r, {k: (v.read_text(encoding="utf-8") if v.exists() else None) for k, v in p.items()}


def traces(tmp_path) -> bool:
    return check_output.run_check("numbers_trace_to:sources.md", str(tmp_path / "final.md"), mode="real",
                                  cwd=str(tmp_path))["pass"]


def test_no_flags_leaves_final_to_model(tmp_path):
    r, out = assemble(tmp_path)
    assert r.returncode == 0 and out["final.md"] is None and out["redline.md"] is None


def test_draft_only_final_is_labelled_draft(tmp_path):
    r, out = assemble(tmp_path, "--draft-only")
    assert r.returncode == 0, r.stderr
    assert out["final.md"].splitlines()[2].startswith("> Script draft — the model sharpen step was not run")
    assert traces(tmp_path)


def test_existing_draft_redline(tmp_path):
    r, out = assemble(tmp_path, "--existing", str(FX / "proposal-draft.md"))
    assert r.returncode == 0, r.stderr
    red, final = out["redline.md"], out["final.md"]
    assert "| Executive summary (≤1 page) | [SHARPEN] | win theme(s) not in it: Inventory-accurate promising;" in red
    assert "| Scope and deliverables | [KEEP] | present |" in red and "| Timeline | [ADD] |" in red
    assert "figure 40% is in no input file" in red
    assert "40%" not in final and "3,100 pickup orders" in final        # 3,100 is backed by the win themes
    assert final.index("## 11. Why us") < final.index("## 7. Timeline")  # additions after the team storyline
    assert traces(tmp_path)


def test_missing_existing_fails(tmp_path):
    r, _ = assemble(tmp_path, "--existing", str(tmp_path / "nope.md"))
    assert r.returncode == 1 and "existing draft not found" in r.stderr
