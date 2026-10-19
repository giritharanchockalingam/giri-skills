"""career/resume-tailor: --draft-only assembly and --existing extension, both gated by check_traceability.py."""
from __future__ import annotations

from conftest import REPO_ROOT, run_script

SK = REPO_ROOT / "skills/career/resume-tailor"
FX = SK / "evals/fixtures"


def tailor(tmp_path, *extra):
    r = run_script(SK / "scripts/tailor.py", "--jd", str(FX / "jd.txt"), "--master", str(FX / "master-resume.md"),
                   "--keyword-map", str(tmp_path / "k.csv"), "--gap-list", str(tmp_path / "g.md"),
                   "--bullets", str(tmp_path / "b.md"), "--final", str(tmp_path / "t.md"), *extra)
    t = tmp_path / "t.md"
    return r, (t.read_text(encoding="utf-8") if t.exists() else None)


def trace(tmp_path, resume):
    return run_script(SK / "scripts/check_traceability.py", "--resume", str(resume), "--master",
                      str(FX / "master-resume.md"), "--out", str(tmp_path / "tr.csv"))


def test_final_only_with_a_flag(tmp_path):
    r, text = tailor(tmp_path)
    assert r.returncode == 0 and text is None


def test_draft_assembly_traces(tmp_path):
    r, text = tailor(tmp_path, "--draft-only")
    assert r.returncode == 0, r.stderr
    for h in ("## Summary", "## Selected experience", "## Skills", "## Education and certifications"):
        assert h in text
    assert "### Lakeshore Health Plans — Senior Director, Enterprise Platforms" in text
    gaps = (tmp_path / "g.md").read_text(encoding="utf-8")
    assert "Script draft" in text
    assert trace(tmp_path, tmp_path / "t.md").returncode == 0
    assert "$25M" not in text and "team of 80" not in text              # unsupported scale keywords stay out
    assert "Unsupported:" in gaps


def test_existing_kept_and_extended(tmp_path):
    r, text = tailor(tmp_path, "--existing", str(FX / "tailored-previous.md"))
    assert r.returncode == 0, r.stderr
    original = (FX / "tailored-previous.md").read_text(encoding="utf-8")
    assert text.startswith(original.rstrip("\n"))
    adds = text.split("## Additions for this JD", 1)[1]
    assert "[MR-L13]" in adds and "[MR-L16]" in adds and "[MR-L14]" not in adds   # already-cited lines not repeated
    assert trace(tmp_path, tmp_path / "t.md").returncode == 0


def test_existing_with_everything_cited_adds_nothing(tmp_path):
    first = tmp_path / "first"
    first.mkdir()
    tailor(first, "--draft-only")
    r, text = tailor(tmp_path, "--existing", str(first / "t.md"))
    assert r.returncode == 0 and "## Additions for this JD" not in text


def test_uncited_existing_fails_the_gate(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("# CV\n\n## Summary\n\n- Led a 500-person org.\n", encoding="utf-8")
    r, _ = tailor(tmp_path, "--existing", str(bad))
    assert r.returncode == 0
    assert trace(tmp_path, tmp_path / "t.md").returncode == 1
