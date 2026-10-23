"""scripts/validate_pipelines.py — the shipped templates pass; every broken shape fails with a clear message."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import REPO_ROOT, run_script

SCRIPT = "scripts/validate_pipelines.py"
PIPELINES = sorted((REPO_ROOT / "pipelines").glob("*.json")) + sorted((REPO_ROOT / "pipelines" / "composed").glob("*.json"))   # composed/ as the validator counts it


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


def test_agent_step_produces_and_text_file_modifiers(tmp_path):
    """The files step: an agent step with `produces: ["files.txt"]`; later steps read it with #csv / #lines."""
    spec = load("feature-delivery")
    files = step(spec, "build", "files")
    assert files["kind"] == "agent" and files["produces"] == ["files.txt"]
    assert step(spec, "build", "tests")["inputs"]["files"] == "$steps.files:files.txt#csv"
    assert step(spec, "build", "code")["inputs"]["files"] == "$steps.files:files.txt"
    assert "$steps.files:files.txt" in stage(spec, "build")["evidence"]
    assert validate(spec, tmp_path)[0] == 0
    spec = load("feature-delivery")
    step(spec, "build", "tests")["inputs"]["files"] = "$steps.files:files.txt#lines"
    assert validate(spec, tmp_path)[0] == 0
    spec = load("feature-delivery")
    step(spec, "build", "tests")["inputs"]["files"] = "$steps.files:files.txt#files"       # a json key path on a text file
    code, out = validate(spec, tmp_path)
    assert code == 1 and "'#files' on a text file must be one of #csv, #lines" in out
    spec = load("feature-delivery")
    step(spec, "build", "tests")["inputs"]["files"] = "$steps.feature:feature.json#csv"      # a text modifier on a json file
    code, out = validate(spec, tmp_path)
    assert code == 1 and "'#csv' joins the lines of a text file, not a .json file" in out
    spec = load("feature-delivery")
    step(spec, "build", "files")["produces"] = []
    code, out = validate(spec, tmp_path)
    assert code == 1 and "`produces` must be a non-empty list of file names" in out
    spec = load("feature-delivery")
    step(spec, "build", "files")["produces"] = ["plan.md"]
    code, out = validate(spec, tmp_path)
    assert code == 1 and "`produces` ['plan.md'] is not something the executor can ask a builder for" in out
    spec = load("feature-delivery")
    del step(spec, "build", "files")["produces"]                                            # a plain agent step declares diff.patch, not files.txt
    code, out = validate(spec, tmp_path)
    assert code == 1 and "step 'files' does not declare output 'files.txt'" in out and "diff.patch" in out


def test_plan_refine_step_produces_the_refined_plan_and_the_gate_checks_it(tmp_path):
    """The architecture stage: plan (scaffold) → plan-refine (agent, produces plan.md + tasks.csv) → plan-approval; the
    gate is `all` of the tasks.csv checks and the approval; the build stage reads the refined plan."""
    for name in ("feature-delivery", "greenfield-app"):
        spec = load(name)
        refine = step(spec, "architecture", "plan-refine")
        assert refine["kind"] == "agent" and refine["produces"] == ["plan.md", "tasks.csv"]
        assert refine["inputs"] == {"plan": "$steps.plan:plan.md", "tasks": "$steps.plan:tasks.csv", "prd": "$steps.prd-refine:prd-final.md", "request": "$in.request", "target": "$repo"}
        assert [t["id"] for t in stage(spec, "architecture")["steps"]] == ["spec", "plan", "plan-refine", "plan-approval"]
        gate = stage(spec, "architecture")["gate"]
        assert gate["kind"] == "all" and gate["of"][-1] == {"kind": "approval", "step": "plan-approval"}
        assert [g["check"] for g in gate["of"][:-1]] == ["csv_rows:files!empty", "csv_rows:acceptance!empty", "csv_rows:files!tbd", "csv_rows:acceptance!tbd", "csv_rows:test!tbd"]
        assert all(g["step"] == "plan-refine" and g["file"] == "tasks.csv" for g in gate["of"][:-1])
        for tid in ("feature", "files", "code"):
            assert step(spec, "build", tid)["inputs"]["plan"] == "$steps.plan-refine:plan.md", (name, tid)
        assert step(spec, "build", "files")["inputs"]["tasks"] == "$steps.plan-refine:tasks.csv"
        assert "$steps.plan-refine:tasks.csv" in stage(spec, "architecture")["evidence"] and "$steps.plan:tasks.csv" in stage(spec, "architecture")["evidence"]
        assert validate(spec, tmp_path, name=name)[0] == 0
    spec = load("feature-delivery")
    step(spec, "architecture", "plan-refine")["produces"] = ["tasks.csv"]                  # the two files go together
    code, out = validate(spec, tmp_path)
    assert code == 1 and "`produces` ['tasks.csv'] is not something the executor can ask a builder for" in out and "['plan.md', 'tasks.csv']" in out
    spec = load("feature-delivery")
    stage(spec, "architecture")["gate"]["of"][2]["check"] = "csv_rows:files!filled"           # not a check the vocabulary has
    code, out = validate(spec, tmp_path)
    assert code == 0                                                                        # the name is csv_rows: vocabulary-valid; the predicate is judged at run time
    stage(spec, "architecture")["gate"]["of"][2]["check"] = "rows_tbd:files"
    code, out = validate(spec, tmp_path)
    assert code == 1 and "not a file-level check" in out


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
    stage(spec, "requirements")["gate"]["of"][0]["check"] = "exit:0"      # run-level check is not a file check
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


# ---------------------------------------------------------------- .github/workflows/delivery.yml (the GitHub executor)

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "delivery.yml"
WORKFLOW_INPUTS = ["run_id", "pipeline", "mode", "repo", "ref", "request", "callback"]   # = studio workflowInputs()


def test_delivery_workflow_declares_the_portal_contract_parser_free():
    """No YAML parser: the dispatch inputs, the secrets, the executor call and the evidence upload must all be there."""
    text = WORKFLOW.read_text(encoding="utf-8")
    inputs_block = text.split("workflow_dispatch:", 1)[1].split("\nconcurrency:", 1)[0]
    declared = [ln.split(":", 1)[0].strip() for ln in inputs_block.splitlines() if ln.startswith("      ") and not ln.startswith("       ") and ":" in ln]
    assert declared == WORKFLOW_INPUTS
    for name in WORKFLOW_INPUTS:
        assert f"inputs.{name}" in text, name
    for secret in ("DELIVERY_TOKEN", "ANTHROPIC_API_KEY", "SF_API_KEY"):
        assert f"secrets.{secret}" in text, secret
    assert "concurrency:" in text and "delivery-${{ inputs.run_id }}" in text
    assert "repository: ${{ inputs.repo }}" in text and "ref: ${{ inputs.ref }}" in text and "path: target" in text
    assert "npm i -g @anthropic-ai/claude-code" in text
    assert "scripts/deliver.py --pipeline" in text and "--repo target" in text and "--builder claude-code" in text
    assert "--provider anthropic" in text and "--out delivery-out" in text and '--run "$RUN_ID" --portal "$CALLBACK"' in text
    assert "GH_TOKEN: ${{ secrets.DELIVERY_TOKEN }}" in text and "SF_API_KEY: ${{ secrets.SF_API_KEY }}" in text
    assert "actions/upload-artifact@v4" in text and "delivery-out/evidence" in text and "if: always()" in text
    assert "EVIDENCE.md" in text and "GITHUB_STEP_SUMMARY" in text
    # no workflow input is interpolated inside a run: script (injection): they reach the shell through env
    run_blocks = [b for b in text.split("run: |")[1:]]
    assert not any("${{ inputs." in b.split("\n      - ")[0] for b in run_blocks)


def test_delivery_workflow_parses_when_pyyaml_is_available():
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = d.get("on", d.get(True))
    assert list(on["workflow_dispatch"]["inputs"]) == WORKFLOW_INPUTS
    assert all(i["type"] == "string" for i in on["workflow_dispatch"]["inputs"].values())
    steps = d["jobs"]["deliver"]["steps"]
    assert any(s.get("uses", "").startswith("actions/setup-python") for s in steps)
    assert any(s.get("uses", "").startswith("actions/setup-node") for s in steps)
    assert d["concurrency"]["group"] == "delivery-${{ inputs.run_id }}"


def test_prd_refine_step_is_the_product_managers_stop_and_the_gate_refuses_template_stories():
    """First greenfield run: a request with no brief produced a template PRD that the requirements gate waved
    through. Now prd → prd-refine (agent, produces prd-final.md) and the gate needs the stories filled."""
    for name in ("feature-delivery", "greenfield-app"):
        spec = load(name)
        refine = step(spec, "requirements", "prd-refine")
        assert refine["kind"] == "agent" and refine["produces"] == ["prd-final.md"]
        assert refine["inputs"]["prd"] == "$steps.prd:prd-final.md" and refine["inputs"]["request"] == "$in.request"
        gate = stage(spec, "requirements")["gate"]
        assert gate["kind"] == "all" and [g["check"] for g in gate["of"]] == ['sections:["Acceptance criteria"]', 'section_filled:"user stories"']
        assert all(g["step"] == "prd-refine" and g["file"] == "prd-final.md" for g in gate["of"])
        # everything downstream reads the refined PRD, never the draft
        assert step(spec, "architecture", "spec")["inputs"]["prd"] == "$steps.prd-refine:prd-final.md"
        assert step(spec, "evaluate", "review")["inputs"]["spec"] == "$steps.prd-refine:prd-final.md"
