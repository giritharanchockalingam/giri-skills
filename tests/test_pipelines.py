"""scripts/validate_pipelines.py — the shipped templates pass; every broken shape fails with a clear message."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import REPO_ROOT, run_script

SCRIPT = "scripts/validate_pipelines.py"
PIPELINES = sorted((REPO_ROOT / "pipelines").glob("*.json"))


def load(name: str) -> dict:
    return json.loads((REPO_ROOT / "pipelines" / f"{name}.json").read_text(encoding="utf-8"))


def validate(spec: dict, tmp_path: Path, name: str = "feature-delivery") -> tuple[int, str]:
    f = tmp_path / f"{name}.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    r = run_script(SCRIPT, str(f))
    return r.returncode, r.stdout + r.stderr


def stage(spec: dict, sid: str) -> dict:
    return next(s for s in spec["stages"] if s["id"] == sid)


def step(spec: dict, sid: str, tid: str) -> dict:
    return next(t for t in stage(spec, sid)["steps"] if t["id"] == tid)


def test_shipped_templates_pass():
    r = run_script(SCRIPT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"Checked {len(PIPELINES)} pipeline(s), 0 errors" in r.stdout
    assert {p.stem for p in PIPELINES} >= {"feature-delivery", "greenfield-app"}


def test_repo_validator_counts_pipelines():
    r = run_script("scripts/validate.py")
    assert r.returncode == 0, r.stdout
    assert f"+ {len(PIPELINES)} pipelines, 0 errors" in r.stdout


def test_every_stage_role_owns_its_stage_and_skills():
    roles = {p.stem: json.loads(p.read_text()) for p in (REPO_ROOT / "roles").glob("*.json")}
    for p in PIPELINES:
        for s in json.loads(p.read_text())["stages"]:
            role = roles[s["role"]]
            assert s["adlc_stage"] in role["stages"], f"{p.name}: {s['role']} must list {s['adlc_stage']}"
            for t in s["steps"]:
                if t["kind"] == "skill":
                    assert t["skill"] in role["skills"], f"{p.name}: {s['role']} lacks {t['skill']}"


def test_duplicate_stage_id_fails(tmp_path):
    spec = load("feature-delivery")
    spec["stages"][1]["id"] = spec["stages"][0]["id"]
    code, out = validate(spec, tmp_path)
    assert code == 1 and "duplicate stage id" in out


def test_unknown_adlc_stage_fails(tmp_path):
    spec = load("feature-delivery")
    stage(spec, "build")["adlc_stage"] = "shipping"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "adlc_stage 'shipping' not in shared/adlc-stages.json" in out


def test_role_must_exist_and_own_the_stage(tmp_path):
    spec = load("feature-delivery")
    stage(spec, "evaluate")["role"] = "nobody"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "role 'nobody' does not exist" in out
    spec = load("feature-delivery")
    stage(spec, "evaluate")["role"] = "ai-product-manager"   # exists, owns requirements only
    code, out = validate(spec, tmp_path)
    assert code == 1 and "does not own stage 'evaluate'" in out


def test_role_must_have_every_skill_the_stage_runs(tmp_path):
    spec = load("feature-delivery")
    step(spec, "build", "conventions")["skill"] = "build/safe-fix"   # exists, but the role has it; use a presales one
    step(spec, "build", "conventions")["skill"] = "presales/sow-drafter"
    step(spec, "build", "conventions")["inputs"] = {}
    code, out = validate(spec, tmp_path)
    assert code == 1 and "role 'full-stack-engineer' does not have skill 'presales/sow-drafter'" in out


def test_unknown_skill_fails(tmp_path):
    spec = load("feature-delivery")
    step(spec, "evaluate", "perf")["skill"] = "build/does-not-exist"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "skill 'build/does-not-exist' is not an agent skill" in out


def test_skill_step_must_use_declared_inputs_and_supply_required_ones(tmp_path):
    spec = load("feature-delivery")
    step(spec, "evaluate", "perf")["inputs"] = {"repo_root": "$repo"}
    code, out = validate(spec, tmp_path)
    assert code == 1
    assert "declares no input 'repo_root'" in out
    assert "required input 'target' of skill 'build/perf-review-runner' is not supplied" in out


def test_steps_reference_must_point_to_an_earlier_step(tmp_path):
    spec = load("feature-delivery")
    step(spec, "requirements", "prd")["inputs"]["brief"] = "$steps.plan:plan.md"   # plan runs later
    code, out = validate(spec, tmp_path)
    assert code == 1 and "references step 'plan', which is not an earlier step" in out


def test_steps_reference_must_name_a_declared_output(tmp_path):
    spec = load("feature-delivery")
    step(spec, "evaluate", "review")["inputs"]["diff"] = "$steps.code:changes.patch"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "step 'code' does not declare output 'changes.patch'" in out
    assert "diff.patch" in out   # the message lists what it does declare


def test_input_reference_must_be_declared(tmp_path):
    spec = load("feature-delivery")
    step(spec, "requirements", "brief")["inputs"]["request"] = "$in.ticket"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "$in.ticket is not a declared pipeline input" in out


def test_profile_reference_keys_are_checked(tmp_path):
    spec = load("feature-delivery")
    step(spec, "evaluate", "perf")["inputs"]["baseline"] = "$profile.baselines.lighthouse"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "unknown baseline check $profile.baselines.lighthouse" in out


def test_gate_kinds_and_shapes(tmp_path):
    spec = load("feature-delivery")
    stage(spec, "build")["gate"] = {"kind": "vibes"}
    code, out = validate(spec, tmp_path)
    assert code == 1 and "gate kind 'vibes' not in" in out
    spec = load("feature-delivery")
    stage(spec, "requirements")["gate"] = {"kind": "output", "step": "prd", "file": "prd.md", "check": "sections:[\"x\"]"}
    code, out = validate(spec, tmp_path)
    assert code == 1 and "output gate file 'prd.md' is not an output step 'prd' declares" in out
    spec = load("feature-delivery")
    stage(spec, "requirements")["gate"]["check"] = "exit:0"      # run-level check is not a file check
    code, out = validate(spec, tmp_path)
    assert code == 1 and "not a file-level check" in out
    spec = load("feature-delivery")
    stage(spec, "architecture")["gate"] = {"kind": "approval", "step": "plan"}
    code, out = validate(spec, tmp_path)
    assert code == 1 and "approval gate must name an approval step" in out
    spec = load("feature-delivery")
    stage(spec, "evaluate")["gate"] = {"kind": "all", "of": []}
    code, out = validate(spec, tmp_path)
    assert code == 1 and "needs a non-empty `of` list" in out


def test_inputs_must_be_typed(tmp_path):
    spec = load("feature-delivery")
    spec["inputs"][0]["type"] = "repository"
    del spec["inputs"][1]["required"]
    code, out = validate(spec, tmp_path)
    assert code == 1
    assert "type 'repository' not in" in out and "`required` must be true or false" in out


def test_compose_step_must_name_a_known_derivation_and_its_outputs(tmp_path):
    spec = load("feature-delivery")
    step(spec, "build", "feature")["derive"] = "feature-from-thin-air"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "unknown derivation 'feature-from-thin-air'" in out


def test_approval_role_must_be_the_stage_role(tmp_path):
    spec = load("feature-delivery")
    step(spec, "architecture", "plan-approval")["role"] = "ai-product-manager"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "approval role 'ai-product-manager' must be the stage's role 'ai-solution-architect'" in out


def test_name_must_match_file(tmp_path):
    spec = load("feature-delivery")
    code, out = validate(spec, tmp_path, name="other-name")
    assert code == 1 and "must match the file name 'other-name'" in out
