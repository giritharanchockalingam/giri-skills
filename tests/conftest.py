"""Shared fixtures for the giri-skills script test suite.

Every script is invoked via subprocess as [sys.executable, "-I", path, ...]
and never imported (the scripts are not packages).
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# skill key -> script path relative to the repo root (25 scripts total).
SCRIPTS = {
    "score_matrix": "skills/presales/rfp-compliance-matrix/scripts/score_matrix.py",
    "tco": "skills/presales/integration-migration-assessor/scripts/tco.py",
    "build_golden": "skills/ai-platform/llm-eval-harness/scripts/build_golden.py",
    "brief_skeleton": "skills/presales/client-research-brief/scripts/brief_skeleton.py",
    "extract_requirements": "skills/presales/rfp-compliance-matrix/scripts/extract_requirements.py",
    "estimate": "skills/presales/effort-estimator/scripts/estimate.py",
    "score_inventory": "skills/presales/integration-migration-assessor/scripts/score_inventory.py",
    "scaffold": "skills/build/project-bootstrap/scripts/scaffold.py",
    "rls_lint": "skills/build/supabase-schema-rls/scripts/rls_lint.py",
    "run_evals": "skills/ai-platform/llm-eval-harness/scripts/run_evals.py",
    "eval_retrieval": "skills/ai-platform/rag-pipeline-design/scripts/eval_retrieval.py",
    "size": "skills/ai-platform/infra-gpu-sizing/scripts/size.py",
    "score": "skills/career/jd-fit-scorer/scripts/score.py",
    "tracker": "skills/career/application-tracker/scripts/tracker.py",
    "compare": "skills/career/offer-evaluator/scripts/compare.py",
    # phases 1-2: presales skills turned into agents
    "value_model": "skills/presales/value-case-builder/scripts/value_model.py",
    "assemble": "skills/presales/proposal-writer/scripts/assemble.py",
    "sow_from_proposal": "skills/presales/sow-drafter/scripts/sow_from_proposal.py",
    "build_pack": "skills/presales/discovery-interview/scripts/build_pack.py",
    "synthesize": "skills/presales/discovery-interview/scripts/synthesize.py",
    "arch_doc": "skills/presales/solution-architecture-doc/scripts/arch_doc.py",
    "redline": "skills/presales/exec-deck-redline/scripts/redline.py",
    "battle_card": "skills/presales/competitive-positioning/scripts/battle_card.py",
    "account_plan": "skills/presales/account-plan/scripts/account_plan.py",
    "orals": "skills/presales/orals-prep/scripts/orals.py",
}


def run_script(
    script: str | Path,
    *args: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a repo script in a subprocess with `python -I`. Never import it."""
    path = script if isinstance(script, Path) else REPO_ROOT / script
    cmd = [sys.executable, "-I", str(path), *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None)


@pytest.fixture()
def run() -> Callable[..., subprocess.CompletedProcess]:
    return run_script


@pytest.fixture()
def repo_root() -> Path:
    return REPO_ROOT


def copy_asset(asset_rel: str, dest_dir: Path) -> Path:
    """Copy one repo asset (example input) into a tmp dir; return the copy."""
    src = REPO_ROOT / asset_rel
    dest = dest_dir / src.name
    shutil.copy(src, dest)
    return dest


@pytest.fixture()
def examples(tmp_path) -> dict[str, Path]:
    """Copies of every skill's assets/*.example.* file, keyed by filename."""
    out: dict[str, Path] = {}
    target = tmp_path / "examples"
    target.mkdir()
    for src in sorted(REPO_ROOT.rglob("assets/*.example.*")):
        dest = target / src.name
        shutil.copy(src, dest)
        out[src.name] = dest
    return out


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail fast if any in-process test code tries to open a network socket.

    (Scripts themselves run in subprocesses; test_offline.py additionally
    scans their sources for networking imports.)
    """

    def _blocked(*args, **kwargs):
        raise RuntimeError("network access is blocked in tests")

    monkeypatch.setattr(socket, "socket", _blocked)
