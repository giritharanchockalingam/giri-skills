"""Tests for presales/rfp-compliance-matrix/scripts/extract_requirements.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import run_script

SCRIPT = "skills/presales/rfp-compliance-matrix/scripts/extract_requirements.py"

RFP = """1.1 The Supplier shall provide 24/7 helpdesk support.
1.2 The system must encrypt data at rest using AES-256.
R-014 The bidder should hold ISO 27001 certification.
"""


def _rfp(tmp_path: Path, name: str = "rfp.txt", text: str = RFP) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_help_exits_zero():
    r = run_script(SCRIPT, "--help")
    assert r.returncode == 0


def test_dry_run_extracts_numbered_clauses(tmp_path):
    rfp = _rfp(tmp_path)
    r = run_script(SCRIPT, "--dry-run", str(rfp))
    assert r.returncode == 0, r.stderr
    assert "REQ-001" in r.stdout


def test_out_csv_has_expected_columns(tmp_path):
    rfp = _rfp(tmp_path)
    out = tmp_path / "requirements.csv"
    r = run_script(SCRIPT, "--out", str(out), str(rfp))
    assert r.returncode == 0, r.stderr
    assert out.exists()
    header = out.read_text(encoding="utf-8").splitlines()[0]
    for col in ("req_id", "section", "text", "source_file"):
        assert col in header


def test_missing_file(tmp_path):
    r = run_script(SCRIPT, "--dry-run", str(tmp_path / "nope.txt"))
    assert r.returncode == 2


def test_unsupported_suffix(tmp_path):
    rfp = _rfp(tmp_path, name="rfp.xyz")
    r = run_script(SCRIPT, "--dry-run", str(rfp))
    assert r.returncode == 2


try:
    import docx  # noqa: F401

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import pypdf  # noqa: F401

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


@pytest.mark.skipif(not HAS_DOCX, reason="python-docx not installed")
def test_docx_input(tmp_path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("2.1 The Supplier shall deliver monthly service reports.")
    p = tmp_path / "rfp.docx"
    doc.save(p)
    r = run_script(SCRIPT, "--dry-run", str(p))
    assert r.returncode == 0, r.stderr
    assert "REQ-001" in r.stdout


@pytest.mark.skipif(HAS_DOCX, reason="python-docx is installed")
def test_docx_without_library_exits_3(tmp_path):
    p = tmp_path / "rfp.docx"
    p.write_bytes(b"not a real docx")
    r = run_script(SCRIPT, "--dry-run", str(p))
    assert r.returncode == 3
    assert "python-docx" in r.stderr


@pytest.mark.skipif(HAS_PYPDF, reason="pypdf is installed")
def test_pdf_without_library_exits_3(tmp_path):
    p = tmp_path / "rfp.pdf"
    p.write_bytes(b"not a real pdf")
    r = run_script(SCRIPT, "--dry-run", str(p))
    assert r.returncode == 3
    assert "pypdf" in r.stderr
