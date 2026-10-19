"""build/product-spec-prd: --draft-only final and the --existing PRD redline."""
from __future__ import annotations

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/build/product-spec-prd"
SCRIPT = SK / "scripts/prd.py"
FX = SK / "evals/fixtures"


def prd(tmp_path, *extra, brief=FX / "brief.json"):
    paths = {k: tmp_path / f"{k}.md" for k in ("PRD", "final", "redline")}
    r = run_script(SCRIPT, str(brief), "--out", str(paths["PRD"]), "--final", str(paths["final"]),
                   "--redline", str(paths["redline"]), *extra)
    return r, {k: (p.read_text(encoding="utf-8") if p.exists() else None) for k, p in paths.items()}


def test_without_flags_final_is_left_to_the_model(tmp_path):
    r, out = prd(tmp_path)
    assert r.returncode == 0 and out["PRD"] and out["final"] is None and out["redline"] is None


def test_draft_only_writes_labelled_final(tmp_path):
    r, out = prd(tmp_path, "--draft-only")
    assert r.returncode == 0, r.stderr
    assert out["final"].splitlines()[2].startswith("> Script draft — the model sharpen step was not run")
    assert out["final"].replace(out["final"].splitlines()[2] + "\n\n", "", 1) == out["PRD"]


def test_existing_prd_redline(tmp_path):
    r, out = prd(tmp_path, "--existing", str(FX / "prd-existing.md"))
    assert r.returncode == 0, r.stderr
    red = out["redline"]
    for row in ("| Problem | [KEEP] |", "| Goals | [SHARPEN] | no goal names a measurable target |",
                "| Non-goals | [SHARPEN] | 1 non-goal(s);", "| Metrics | [SHARPEN] | metrics have no baseline |",
                "| Open questions | [SHARPEN] | open questions have no owner |",
                "| Phases | [ADD] | missing — added from the brief |",
                "| Risks | [ADD] | missing — write it (the brief does not cover it) |",
                "| Metrics | [TBD] | figure 35% is not in the brief"):
        assert row in red, row
    final = out["final"]
    assert "Make exporting invoices easy for admins" in final            # existing text kept verbatim
    assert "[TO BE BASELINED — owner: Product owner — source for 35%]" in final
    assert final.index("## Problem") < final.index("## Phases")          # additions go after the storyline
    assert "| v1 | CSV export of the current filter" in final


def test_figures_in_the_brief_are_sourced(tmp_path):
    existing = tmp_path / "e.md"
    existing.write_text("# PRD\n\n## Goals\n- Reach 40% of active tenants\n\n## Metrics\n- baseline 0, target 40%\n",
                        encoding="utf-8")
    _, out = prd(tmp_path, "--existing", str(existing))
    assert "[TBD]" not in out["redline"] and "every figure traces to the brief" in out["redline"]
    assert "| Goals | [KEEP] |" in out["redline"]


def test_existing_overrides_draft_only_and_missing_file_fails(tmp_path):
    r, out = prd(tmp_path, "--draft-only", "--existing", str(FX / "prd-existing.md"))
    assert r.returncode == 0 and "Redlined against brief.json" in out["final"]
    r, _ = prd(tmp_path, "--existing", str(tmp_path / "nope.md"))
    assert r.returncode == 1 and "existing PRD not found" in r.stderr
