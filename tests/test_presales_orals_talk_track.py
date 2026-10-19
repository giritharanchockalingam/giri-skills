"""presales/orals-prep: --talk-track check of the team's existing talk track."""
from __future__ import annotations

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/presales/orals-prep"
SCRIPT = SK / "scripts/orals.py"
FX = SK / "evals/fixtures"


def orals(tmp_path, *extra, speakers="Giri,Priya,Alex"):
    paths = {k: tmp_path / f"{k}" for k in ("script.md", "registry.csv", "questions.md", "check.md")}
    r = run_script(SCRIPT, str(FX / "proposal.md"), "--minutes", "60", "--speakers", speakers,
                   "--script", str(paths["script.md"]), "--registry", str(paths["registry.csv"]),
                   "--questions", str(paths["questions.md"]), "--check", str(paths["check.md"]), *extra)
    return r, {k: (p.read_text(encoding="utf-8") if p.exists() else None) for k, p in paths.items()}


def test_track_figures_speakers_and_airtime(tmp_path):
    r, out = orals(tmp_path, "--talk-track", str(FX / "talk-track.md"))
    assert r.returncode == 0, r.stderr
    chk = out["check.md"]
    assert "| 7 | Alex | $2.1M |" in chk
    assert "6.2%" not in chk.split("## Airtime")[0] and "| 118 |" not in chk
    assert "- Sam: has lines in the track but is not in --speakers" in chk
    assert "| Priya | 24.5 |" in chk


def test_script_unchanged_by_track(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _, out_a = orals(a)
    _, out_b = orals(b, "--talk-track", str(FX / "talk-track.md"))
    assert out_a["script.md"] == out_b["script.md"] and out_a["check.md"] is None


def test_long_track_is_over(tmp_path):
    track = tmp_path / "t.md"
    track.write_text("**Giri:** " + " ".join(["word"] * 1500) + "\n", encoding="utf-8")
    r, out = orals(tmp_path, "--talk-track", str(track))
    assert r.returncode == 0
    assert "| Giri | 8.0 | 10.0 | over — cut |" in out["check.md"]
    assert "| Priya | 24.5 | 0.0 | no lines in the track |" in out["check.md"]
    assert "every figure traces to the proposal" in out["check.md"]


def test_missing_track_fails(tmp_path):
    r, _ = orals(tmp_path, "--talk-track", str(tmp_path / "none.md"))
    assert r.returncode == 1 and "talk track not found" in r.stderr
