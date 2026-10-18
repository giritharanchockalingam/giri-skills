"""Tests for build/domain-modeling-runner/scripts/model.py."""
from __future__ import annotations

import json
import re

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/build/domain-modeling-runner/scripts/model.py"
FX = REPO_ROOT / "skills/build/domain-modeling-runner/evals/fixtures"
TBD = "[TO BE BASELINED — owner: Domain expert]"


def build(tmp_path, ents, rels, *extra):
    md, js = tmp_path / "model.md", tmp_path / "model.json"
    res = run_script(SCRIPT, "--entities", str(ents), "--relationships", str(rels), *extra,
                     "--md", str(md), "--json", str(js))
    m = json.loads(js.read_text(encoding="utf-8")) if js.exists() else None
    return res, m, (md.read_text(encoding="utf-8") if md.exists() else "")


def csv_file(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def mermaid_block(md):
    return re.search(r"```mermaid\n(.*?)```", md, re.S).group(1)


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_happy_path(tmp_path):
    res, m, md = build(tmp_path, FX / "entities.csv", FX / "relationships.csv",
                       "--glossary", str(FX / "glossary.csv"), "--title", "Course enrollment")
    assert res.returncode == 0, res.stderr
    assert m["valid"] and m["errors"] == []
    assert [e["name"] for e in m["entities"]] == ["Student", "Course", "Enrollment", "Term", "Offering"]
    ids = {e["name"]: e["identifier"] for e in m["entities"]}
    assert ids == {"Student": "student_id", "Course": "id", "Enrollment": "id", "Term": "term_id", "Offering": "id"}
    nm = m["relationships"][0]
    assert (nm["cardinality"], nm["join"]) == ("N:M", "Enrollment")
    # Enrollment is the join entity, so it is not an orphan; only glossary gaps remain
    assert m["warnings"] == ["W2 glossary term Offering: no definition",
                             "W2 glossary term Term: entity has no glossary definition"]
    block = mermaid_block(md)
    assert block.startswith("---\ntitle: Course enrollment\n---\nerDiagram")
    assert "Student 0+ to 0+ Course : \"enrolls in\"" in block
    assert "Course 1 to 0+ Offering : \"is offered as\"" in block
    assert "uuid student_id PK\n" in block                    # PK note not repeated as a comment
    assert "decimal_4_1_ credits" in block
    for o, c in ("[]", "{}", "()"):
        assert block.count(o) == block.count(c)
    # invariants: 5 identifiers + 10 required non-id attributes + 3 relationships (hand count)
    assert len(m["invariants"]) == 18
    assert "A Student–Course pair appears at most once in Enrollment (enrolls in)." in m["invariants"]
    assert "Every Offering belongs to exactly one Term (schedules)." in m["invariants"]
    gl = {g["term"]: g for g in m["glossary"]}
    assert gl["Student"]["avoid"] == ["Learner", "user", "pupil"]
    assert gl["Offering"]["definition"] == TBD and gl["Term"]["definition"] == TBD
    assert "**Student**:\nA person admitted to take courses in a term.\n_Avoid_: Learner, user, pupil" in md
    for sec in ("## Diagram", "## Entities", "## Relationships", "## Invariants", "## Glossary", "## Open questions"):
        assert sec in md
    assert run_script(SCRIPT, "--check", str(tmp_path / "model.json")).returncode == 0


def test_invalid_relationships(tmp_path):
    res, m, md = build(tmp_path, FX / "entities.csv", FX / "relationships-invalid.csv")
    assert res.returncode == 1
    codes = [e.split()[0] for e in m["errors"]]
    assert codes == ["E4", "E1", "E3"]
    assert "relationship line 4 (Course -> Instructor)" in m["errors"][1]   # real file line (comment row counted)
    assert "Instructor" not in [e["name"] for e in m["entities"]]
    assert " to " not in mermaid_block(md).split("erDiagram")[1]               # invalid relationships not drawn
    assert "Errors (must be fixed" in md
    r = run_script(SCRIPT, "--check", str(tmp_path / "model.json"))
    assert r.returncode == 1 and "validation error" in r.stderr


def test_missing_identifier_and_bad_required(tmp_path):
    ents = csv_file(tmp_path, "e.csv", "entity,attribute,type,required,notes\nNote,body,text,maybe,\nNote,body,text,yes,\n"
                                       "Tag,tag_id,int,yes,\n")
    rels = csv_file(tmp_path, "r.csv", "from,to,cardinality,name\nNote,Tag,1:N,has\n")
    res, m, _ = build(tmp_path, ents, rels)
    assert res.returncode == 1
    joined = " ".join(m["errors"])
    assert "E6 Note.body" in joined and "E5 Note: duplicate attribute 'body'" in joined
    assert "E2 Note: no identifier" in joined
    assert not any(e.startswith("E2 Tag") for e in m["errors"])           # tag_id is <entity>_id


def test_nm_join_by_entity_name_and_orphan(tmp_path):
    ents = csv_file(tmp_path, "e.csv", "entity,attribute,type,required,notes\nA,id,int,yes,\nB,id,int,yes,\n"
                                       "AB,id,int,yes,\nLonely,id,int,yes,\n")
    rels = csv_file(tmp_path, "r.csv", "from,to,cardinality,name,notes\nA,B,n:m,links,via AB rows\n")
    res, m, _ = build(tmp_path, ents, rels)
    assert res.returncode == 0, res.stderr
    assert m["relationships"][0]["join"] == "AB"
    assert m["warnings"][0].startswith("W1 orphan entity Lonely")


def test_glossary_term_not_entity(tmp_path):
    ents = csv_file(tmp_path, "e.csv", "entity,attribute,type,required,notes\nA,id,int,yes,\n")
    rels = csv_file(tmp_path, "r.csv", "from,to,cardinality,name\nA,A,1:1,replaces\n")
    gl = csv_file(tmp_path, "g.csv", "term,definition\nA,An a.\nStatus,The lifecycle state.\n")
    res, m, _ = build(tmp_path, ents, rels, "--glossary", str(gl))
    assert res.returncode == 0
    assert any(w.startswith("W3 glossary term Status") for w in m["warnings"])
    assert "A has at most one A" in m["invariants"][-1]


def test_inputs_missing_or_malformed_exit_2(tmp_path):
    rels = FX / "relationships.csv"
    assert run_script(SCRIPT, "--relationships", str(rels), "--md", str(tmp_path / "m.md")).returncode == 2
    assert run_script(SCRIPT, "--entities", str(tmp_path / "nope.csv"), "--relationships", str(rels),
                      "--md", str(tmp_path / "m.md")).returncode == 2
    bad = csv_file(tmp_path, "bad.csv", "name,field\nA,b\n")
    r = run_script(SCRIPT, "--entities", str(bad), "--relationships", str(rels), "--md", str(tmp_path / "m.md"))
    assert r.returncode == 2 and "missing column" in r.stderr
    extra = csv_file(tmp_path, "x.csv", "entity,attribute,type,required,notes\nA,amt,decimal(4,1),yes,\n")
    r = run_script(SCRIPT, "--entities", str(extra), "--relationships", str(rels), "--md", str(tmp_path / "m.md"))
    assert r.returncode == 2 and "quote values containing commas" in r.stderr
