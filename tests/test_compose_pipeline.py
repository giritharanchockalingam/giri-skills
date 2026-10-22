"""scripts/compose_pipeline.py — composition when no template fits (docs/DELIVERY-PIPELINES.md).

Composed for the JS/AWS fixture = the feature-delivery template's stages and steps; a Python profile drops the stages
whose skills do not fit, with notes, and never wires a skill that does not fit; unknown kinds are a clear error; the
result is deterministic, validates with validate_pipelines.py and dry-runs with deliver.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, run_script
from test_deliver import RUN_UUID, StubPortal, portal_env

SCRIPT = "scripts/compose_pipeline.py"
FIX = REPO_ROOT / "tests" / "fixtures"
JS_AWS_REPO = FIX / "delivery-repo"                       # js · nextjs · vitest · playwright · AWS workflow
PY_REPO = FIX / "stack-profile" / "python-repo"            # python · fastapi · pytest
TS_REPO = FIX / "stack-profile" / "ts-vercel-supabase"     # ts · nextjs · supabase · vercel
KINDS = json.loads((REPO_ROOT / "shared" / "request-kinds.json").read_text(encoding="utf-8"))
TEMPLATE = json.loads((REPO_ROOT / "pipelines" / "feature-delivery.json").read_text(encoding="utf-8"))


def profile(repo: Path, tmp_path: Path) -> Path:
    out = tmp_path / f"{repo.name}-profile.json"
    r = run_script("scripts/stack_profile.py", str(repo), "--json", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    return out


def compose(tmp_path: Path, *args: str, name: str = "composed") -> tuple[subprocess.CompletedProcess, dict | None]:
    out = tmp_path / f"{name}.json"
    r = run_script(SCRIPT, *args, "--out", str(out))
    return r, (json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None)


def shape(spec: dict) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """(stage id, role, [(step id, skill-or-kind)]) — what a pipeline runs."""
    return [(s["id"], s["role"], [(t["id"], t.get("skill") or t.get("derive") or t["kind"]) for t in s["steps"]]) for s in spec["stages"]]


def skills_in(spec: dict) -> set[str]:
    return {t["skill"] for s in spec["stages"] for t in s["steps"] if t["kind"] == "skill"}


@pytest.fixture(scope="module")
def js_aws(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("jsaws")
    r, spec = compose(tmp, "--profile", str(profile(JS_AWS_REPO, tmp)), "--request-kind", "feature", name="feature-js-aws")
    assert r.returncode == 0, r.stdout + r.stderr
    return tmp, spec


# ---------------------------------------------------------------- the JS/AWS fixture = the template
def test_js_aws_feature_equals_the_feature_delivery_template(js_aws):
    _, spec = js_aws
    assert shape(spec) == shape(TEMPLATE)
    assert spec["stages"] == TEMPLATE["stages"]          # same wiring, gates and evidence, step for step
    assert spec["fits"] == {"stacks": ["github-actions", "nextjs", "react", "tests"], "request_kinds": ["feature"]}
    assert spec["mode"] == "brownfield" and spec["name"] == "feature-js-aws"
    assert spec["composed"]["notes"] == []


def test_composed_pipeline_passes_the_validator(js_aws):
    tmp, _ = js_aws
    r = run_script("scripts/validate_pipelines.py", str(tmp / "feature-js-aws.json"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 pipeline(s), 0 errors" in r.stdout


def test_composed_pipeline_dry_runs_with_deliver(js_aws, tmp_path):
    tmp, _ = js_aws
    out = tmp_path / "run"
    r = run_script("scripts/deliver.py", str(tmp / "feature-js-aws.json"), "--repo", str(JS_AWS_REPO), "--request", "Export orders as CSV",
                   "--brief", str(FIX / "delivery-build" / "brief.json"), "--out", str(out), "--provider", "dry", "--dry",
                   "--builder", "manual", "--patch", str(FIX / "delivery-build" / "diff.patch"), "--approve-all")
    assert r.returncode == 0, r.stdout + r.stderr
    rj = json.loads((out / "run.json").read_text())
    assert rj["pipeline"] == "feature-js-aws" and rj["status"] == "passed"
    assert [s["id"] for s in rj["stages"]] == ["requirements", "architecture", "build", "evaluate", "deploy", "operate"]


def test_deterministic(js_aws, tmp_path):
    tmp, spec = js_aws
    r, again = compose(tmp_path, "--profile", str(profile(JS_AWS_REPO, tmp_path)), "--request-kind", "feature", name="feature-js-aws")
    assert r.returncode == 0 and again == spec
    text1 = (tmp / "feature-js-aws.json").read_text(encoding="utf-8")
    text2 = (tmp_path / "feature-js-aws.json").read_text(encoding="utf-8")
    assert text1 == text2


# ---------------------------------------------------------------- fits decide; nothing unfit is wired
def test_python_profile_drops_stages_with_notes_and_wires_no_unfit_skill(tmp_path):
    r, spec = compose(tmp_path, "--profile", str(profile(PY_REPO, tmp_path)), "--request-kind", "feature", name="py-feature")
    assert r.returncode == 0, r.stdout + r.stderr
    assert [s["id"] for s in spec["stages"]] == ["requirements", "architecture", "operate"]
    notes = spec["composed"]["notes"]
    assert [n.split(":")[0] for n in notes] == ["stage build dropped", "stage evaluate dropped", "stage deploy dropped"]
    assert all("python" in n for n in notes)
    assert "Notes:" in spec["description"]
    for skill in skills_in(spec):            # every wired skill fits python (or fits anything)
        fits = fits_of(skill)
        assert fits is None or "any" in fits["stacks"] or "python" in fits["stacks"], skill
    assert skills_in(spec).isdisjoint({"build/nextjs-enterprise-conventions", "build/perf-review-runner", "build/ui-component-quality",
                                       "build/ci-cd-vercel-github", "build/test-strategy-tdd", "build/observability-setup"})
    assert run_script("scripts/validate_pipelines.py", str(tmp_path / "py-feature.json")).returncode == 0


def fits_of(skill: str) -> dict | None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import skillmeta
    return skillmeta.load_skill(REPO_ROOT / "skills" / skill)["metadata"].get("fits")


def test_explain_prints_the_decision_table(tmp_path):
    out = tmp_path / "py-feature.json"
    r = run_script(SCRIPT, "--profile", str(profile(PY_REPO, tmp_path)), "--request-kind", "feature", "--out", str(out), "--explain")
    assert r.returncode == 0, r.stderr
    assert "stage" in r.stdout and "| decision |" in r.stdout
    assert "build/nextjs-enterprise-conventions" in r.stdout and "rejected" in r.stdout
    assert "stack: fits nextjs; the repository has python, tests" in r.stdout
    assert "note: stage build dropped" in r.stdout
    assert "needs step(s) code: code (build stage, absent or dropped)" in r.stdout      # evaluate's review needs the diff


def test_fix_kind_skips_definition_and_plan_and_builds_from_the_composed_spec(tmp_path):
    r, spec = compose(tmp_path, "--profile", str(profile(JS_AWS_REPO, tmp_path)), "--request-kind", "fix", name="fix-js")
    assert r.returncode == 0, r.stdout + r.stderr
    assert [s["id"] for s in spec["stages"]] == ["build", "evaluate", "deploy", "operate"]
    build = spec["stages"][0]
    assert [t["id"] for t in build["steps"]] == ["brief", "spec", "files", "code", "conventions"]   # compose steps carried in
    files = next(t for t in build["steps"] if t["id"] == "files")
    assert files["produces"] == ["files.txt"] and files["inputs"] == {"plan": "$steps.spec:spec.md", "target": "$repo"}   # no tasks.csv: the builder names the files
    code = next(t for t in build["steps"] if t["id"] == "code")
    assert code["inputs"] == {"plan": "$steps.spec:spec.md", "files": "$steps.files:files.txt", "target": "$repo"}   # no plan.md: the spec is the plan
    assert "build/test-strategy-tdd" not in skills_in(spec)                                   # needs feature.md from the plan
    assert "build/spec-to-plan" not in skills_in(spec) and "build/product-spec-prd" not in skills_in(spec)
    assert "spec" not in next(t for t in spec["stages"][1]["steps"] if t["id"] == "review")["inputs"]   # prd absent: optional input dropped
    assert run_script("scripts/validate_pipelines.py", str(tmp_path / "fix-js.json")).returncode == 0


def test_hardening_adds_observability_and_carries_the_brief_into_architecture(tmp_path):
    r, spec = compose(tmp_path, "--profile", str(profile(TS_REPO, tmp_path)), "--request-kind", "hardening", name="harden-ts")
    assert r.returncode == 0, r.stdout + r.stderr
    assert [s["id"] for s in spec["stages"]] == ["architecture", "build", "evaluate", "deploy", "operate"]
    assert [t["id"] for t in spec["stages"][0]["steps"]] == ["brief", "spec", "plan", "plan-approval"]
    assert [t["id"] for t in spec["stages"][3]["steps"]] == ["observe", "ci", "pr"]
    assert spec["fits"]["stacks"] == ["nextjs", "react", "supabase", "tests", "typescript", "vercel"]
    assert run_script("scripts/validate_pipelines.py", str(tmp_path / "harden-ts.json")).returncode == 0


def test_greenfield_bootstraps_first_and_reads_the_profile_after(tmp_path):
    r, spec = compose(tmp_path, "--stacks", "nextjs,supabase,vercel", "--request-kind", "greenfield", name="new-shop")
    assert r.returncode == 0, r.stdout + r.stderr
    assert spec["mode"] == "greenfield" and spec["stack_profile"]["after"] == "bootstrap"
    assert [s["id"] for s in spec["stages"]] == ["bootstrap", "requirements", "architecture", "build", "evaluate", "deploy", "operate"]
    assert spec["stages"][0]["steps"][0]["skill"] == "build/project-bootstrap" and spec["stages"][0]["adlc_stage"] == "build"
    assert {i["name"] for i in spec["inputs"]} == {"repo", "name", "request", "brief"}
    assert run_script("scripts/validate_pipelines.py", str(tmp_path / "new-shop.json")).returncode == 0


def test_new_app_is_an_alias_of_greenfield(tmp_path):
    _, a = compose(tmp_path, "--stacks", "nextjs", "--request-kind", "new-app", name="a")
    _, b = compose(tmp_path, "--stacks", "nextjs", "--request-kind", "greenfield", name="a")
    assert a == b and a["fits"]["request_kinds"] == ["greenfield"]


def test_stages_override_and_mode_override(tmp_path):
    r, spec = compose(tmp_path, "--profile", str(profile(JS_AWS_REPO, tmp_path)), "--request-kind", "feature", "--stages", "build,operate", name="short")
    assert r.returncode == 0, r.stderr
    assert [s["id"] for s in spec["stages"]] == ["build", "operate"]
    # greenfield mode asks for a bootstrap stage; project-bootstrap fits the greenfield kind only, so for a feature it is dropped, not forced
    r, spec = compose(tmp_path, "--stacks", "nextjs", "--request-kind", "feature", "--mode", "greenfield", name="gf-feature")
    assert r.returncode == 0 and spec["mode"] == "greenfield" and spec["stages"][0]["id"] == "requirements"
    assert spec["composed"]["notes"][0].startswith("stage bootstrap dropped") and "after" not in spec["stack_profile"]


# ---------------------------------------------------------------- errors are clear
def test_unknown_request_kind_is_a_clear_error(tmp_path):
    r, spec = compose(tmp_path, "--stacks", "nextjs", "--request-kind", "refactor")
    assert r.returncode == 2 and spec is None
    assert "unknown request kind 'refactor'" in r.stderr
    assert "feature, fix, greenfield, hardening, migration, new-app" in r.stderr


def test_unknown_stack_and_unknown_stage_are_clear_errors(tmp_path):
    r, _ = compose(tmp_path, "--stacks", "cobol", "--request-kind", "feature")
    assert r.returncode == 2 and "unknown stack id(s) ['cobol']" in r.stderr
    r, _ = compose(tmp_path, "--stacks", "nextjs", "--request-kind", "feature", "--stages", "build,shipping")
    assert r.returncode == 2 and "unknown stage(s) ['shipping']" in r.stderr
    r = run_script(SCRIPT, "--request-kind", "feature")
    assert r.returncode == 2 and "exactly one of --profile or --stacks" in r.stderr


def test_nothing_composable_exits_1_with_the_reason(tmp_path):
    r, spec = compose(tmp_path, "--profile", str(profile(PY_REPO, tmp_path)), "--request-kind", "fix", "--stages", "build,evaluate")
    assert r.returncode == 1 and spec is None
    assert "nothing composed" in r.stderr and "stage build dropped" in r.stderr


# ---------------------------------------------------------------- the catalog agrees with itself
def test_request_kinds_file_names_known_stages_and_detect_signal_ids():
    stages = {s["id"] for s in json.loads((REPO_ROOT / "shared" / "adlc-stages.json").read_text())["stages"]}
    for k in KINDS["kinds"]:
        assert k.get("alias_of") or set(k["stages"]) <= stages, k["id"]
        assert k["description"]
    detect = (REPO_ROOT / "studio" / "lib" / "github" / "detect.ts").read_text(encoding="utf-8")
    for sid in KINDS["stacks"]:
        assert sid == "any" or f'add("{sid}",' in detect, f"stack id {sid} is not a detect.ts signal"


def test_every_build_skill_declares_fits_the_validator_accepts():
    for md in sorted((REPO_ROOT / "skills" / "build").glob("*/SKILL.md")):
        fits = fits_of(f"build/{md.parent.name}")
        assert fits and set(fits) == {"stacks", "request_kinds"}, md
        assert set(fits["stacks"]) <= set(KINDS["stacks"]) and set(fits["request_kinds"]) <= {k["id"] for k in KINDS["kinds"]}
    r = run_script("scripts/validate.py")
    assert r.returncode == 0, r.stdout


# ---------------------------------------------------------------- the executor finds a composed pipeline
def test_deliver_loads_a_pipeline_from_pipelines_composed_by_name(tmp_path, monkeypatch):
    composed = REPO_ROOT / "pipelines" / "composed"
    r, spec = compose(tmp_path, "--profile", str(profile(JS_AWS_REPO, tmp_path)), "--request-kind", "fix", name="t-fix-js")
    assert r.returncode == 0
    target = composed / "t-fix-js.json"
    try:
        composed.mkdir(exist_ok=True)
        target.write_text(json.dumps(spec), encoding="utf-8")
        out = tmp_path / "run"
        r = run_script("scripts/deliver.py", "t-fix-js", "--repo", str(JS_AWS_REPO), "--request", "Fix the export", "--out", str(out),
                       "--provider", "dry", "--dry", "--builder", "manual", "--patch", str(FIX / "delivery-build" / "diff.patch"),
                       "--files", str(FIX / "delivery-build" / "files.txt"))      # a fix has no tasks.csv: the builder names the files
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads((out / "run.json").read_text())["pipeline"] == "t-fix-js"
    finally:
        target.unlink(missing_ok=True)
        if not any(composed.iterdir()):
            composed.rmdir()
    r = run_script("scripts/deliver.py", "t-fix-js", "--repo", str(JS_AWS_REPO), "--request", "x", "--out", str(tmp_path / "none"), "--dry")
    assert r.returncode != 0 and "pipeline not found: t-fix-js" in r.stderr and "pipelines/composed/" in r.stderr


def test_deliver_in_portal_mode_reads_the_composed_pipeline_from_the_run(tmp_path, monkeypatch):
    """The portal stores a composed pipeline on the run (pipeline_spec, 0024); `deliver.py --pipeline <its name> --run … --portal …`
    — the command the portal prints — fetches it, saves it as <out>/pipeline.json and runs it."""
    portal_env(monkeypatch)
    r, spec = compose(tmp_path, "--profile", str(profile(JS_AWS_REPO, tmp_path)), "--request-kind", "fix", name="composed-fix-portal")
    assert r.returncode == 0
    stub = StubPortal(pipeline_spec=spec)
    try:
        out = tmp_path / "run"
        r = run_script("scripts/deliver.py", "--pipeline", "composed-fix-portal", "--repo", str(JS_AWS_REPO), "--request", "Fix the export",
                       "--out", str(out), "--provider", "dry", "--dry", "--builder", "manual", "--patch", str(FIX / "delivery-build" / "diff.patch"),
                       "--files", str(FIX / "delivery-build" / "files.txt"), "--run", RUN_UUID, "--portal", stub.url)
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads((out / "pipeline.json").read_text()) == spec
        rj = json.loads((out / "run.json").read_text())
        assert rj["pipeline"] == "composed-fix-portal" and [s["id"] for s in rj["stages"]] == ["build", "evaluate", "deploy", "operate"]
        assert stub.gets >= 1 and [p["id"] for p in stub.posts][:1] == ["build"]
        # the portal holds a different pipeline: refused, nothing run
        other = StubPortal(pipeline_spec={**spec, "name": "something-else"})
        try:
            r = run_script("scripts/deliver.py", "--pipeline", "composed-fix-portal", "--repo", str(JS_AWS_REPO), "--request", "x",
                           "--out", str(tmp_path / "run2"), "--dry", "--run", RUN_UUID, "--portal", other.url)
            assert r.returncode != 0 and "pipeline not found: composed-fix-portal" in r.stderr
        finally:
            other.close()
    finally:
        stub.close()
