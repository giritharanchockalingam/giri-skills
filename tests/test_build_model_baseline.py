"""Brownfield ("existing") path of build/domain-modeling-runner: --baseline diff and migration impact."""
from __future__ import annotations

import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/domain-modeling-runner/scripts/model.py"
FX = REPO_ROOT / "skills/build/domain-modeling-runner/evals/fixtures"


def build(tmp_path, ents, rels, *extra):
    md, js = tmp_path / "model.md", tmp_path / "model.json"
    res = run_script(SCRIPT, "--entities", str(ents), "--relationships", str(rels), *extra,
                     "--md", str(md), "--json", str(js))
    m = json.loads(js.read_text(encoding="utf-8")) if js.exists() else None
    return res, m, (md.read_text(encoding="utf-8") if md.exists() else "")


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_fixture_baseline_changes_and_impact(tmp_path):
    res, m, md = build(tmp_path, FX / "entities.csv", FX / "relationships.csv",
                       "--baseline", str(FX / "model-current.json"))
    assert res.returncode == 0, res.stderr
    ch = m["changes"]
    assert ch["entities_added"] == ["Term", "Offering"] and ch["entities_removed"] == ["Section"]
    assert ch["attributes_added"] == [{"entity": "Enrollment", "attribute": "status", "required": True}]
    assert ch["attributes_removed"] == [{"entity": "Enrollment", "attribute": "grade"}]
    assert ch["attributes_changed"] == [{"entity": "Course", "attribute": "credits", "field": "type",
                                         "from": "integer", "to": "decimal(4,1)"}]
    assert ch["relationships_removed"] == ["Course 1:N Section (is split into)"]
    assert len(ch["migration_impact"]) == 4
    assert "## Changes vs current model" in md and "| Entities removed | Section |" in md
    assert run_script(SCRIPT, "--check", str(tmp_path / "model.json")).returncode == 0


def test_same_model_as_baseline_has_no_changes(tmp_path):
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    build(base_dir, FX / "entities.csv", FX / "relationships.csv")
    res, m, md = build(tmp_path, FX / "entities.csv", FX / "relationships.csv",
                       "--baseline", str(base_dir / "model.json"))
    ch = m["changes"]
    assert res.returncode == 0
    assert not any(ch[k] for k in ch if k != "baseline")
    assert "- none: the change is additive and optional" in md


def test_cardinality_and_required_changes_flagged(tmp_path):
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    e1 = write(tmp_path, "e1.csv", "entity,attribute,type,required,notes\nA,id,uuid,yes,\nA,name,string,no,\nB,id,uuid,yes,\n")
    r1 = write(tmp_path, "r1.csv", "from,to,cardinality,name,notes\nA,B,1:1,has,\n")
    build(base_dir, e1, r1)
    e2 = write(tmp_path, "e2.csv", "entity,attribute,type,required,notes\nA,id,uuid,yes,\nA,name,string,yes,\nB,id,uuid,yes,\n")
    r2 = write(tmp_path, "r2.csv", "from,to,cardinality,name,notes\nA,B,1:N,has,\n")
    _, m, _ = build(tmp_path, e2, r2, "--baseline", str(base_dir / "model.json"))
    impact = m["changes"]["migration_impact"]
    assert any("A.name becomes required" in x for x in impact)
    assert any("cardinality 1:1 -> 1:N" in x for x in impact)


def test_optional_attribute_added_is_not_an_impact(tmp_path):
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    e1 = write(tmp_path, "e1.csv", "entity,attribute,type,required,notes\nA,id,uuid,yes,\n")
    r = write(tmp_path, "r.csv", "from,to,cardinality,name,notes\n")
    build(base_dir, e1, r)
    e2 = write(tmp_path, "e2.csv", "entity,attribute,type,required,notes\nA,id,uuid,yes,\nA,note,string,no,\n")
    _, m, _ = build(tmp_path, e2, r, "--baseline", str(base_dir / "model.json"))
    assert m["changes"]["attributes_added"][0]["attribute"] == "note"
    assert m["changes"]["migration_impact"] == []


def test_bad_baseline_exits_2(tmp_path):
    bad = write(tmp_path, "bad.json", '{"title": "not a model"}')
    res, _, _ = build(tmp_path, FX / "entities.csv", FX / "relationships.csv", "--baseline", str(bad))
    assert res.returncode == 2 and "not a model.json" in res.stderr
    res, _, _ = build(tmp_path, FX / "entities.csv", FX / "relationships.csv", "--baseline", str(tmp_path / "nope.json"))
    assert res.returncode == 2 and "not found" in res.stderr
