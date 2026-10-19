"""Roles and talent pools (scripts/talent.py): templates are valid against the real library and agents."""
from __future__ import annotations

import json
import sys

from conftest import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import talent  # noqa: E402

SKILLS = talent.skill_stages()
PLAYBOOKS = talent.playbook_skills()
ROLES = talent.load_dir(REPO_ROOT / "roles")
POOLS = talent.load_dir(REPO_ROOT / "pools")


def test_shipped_roles_and_pools_are_valid_and_every_skill_has_a_role():
    assert ROLES and POOLS
    assert talent.validate_all() == []


def test_role_rules_catch_missing_skills_and_out_of_scope_playbooks():
    bad = {"name": "Bad Name", "title": "", "description": "x", "skills": ["presales/effort-estimator", "nope/none", "nope/none"],
           "playbooks": ["presales-pursuit", "ghost"]}
    p = "\n".join(talent.validate_role(bad, SKILLS, PLAYBOOKS))
    for expected in ("lowercase slug", "missing 'title'", "listed twice", "skill nope/none does not exist",
                     "playbook ghost does not exist", "presales-pursuit uses skills this role does not have"):
        assert expected in p, expected


def test_removing_a_skill_from_a_role_unstaffs_the_pool_playbook():
    roles = json.loads(json.dumps(ROLES))
    roles["presales-solution-architect"]["skills"].remove("presales/effort-estimator")
    p = talent.validate_pool(POOLS["presales-bid-team"], roles, PLAYBOOKS)
    assert any("no member can staff: presales/effort-estimator" in x for x in p)
    assert talent.validate_role(roles["presales-solution-architect"], SKILLS, PLAYBOOKS) == [
        "playbook estimate-and-value uses skills this role does not have: presales/effort-estimator"]


def test_pool_staffing_follows_team_order_and_repeated_roles_get_distinct_names():
    members = [{"role": "ai-strategist"}, {"role": "ai-strategist"}, {"role": "ai-risk-release-lead", "label": "Risk"}]
    assert [talent.member_key(m, i, members) for i, m in enumerate(members)] == ["ai-strategist", "ai-strategist#2", "Risk"]
    keyed = [(talent.member_key(m, i, members), ROLES[m["role"]]["skills"]) for i, m in enumerate(members)]
    assert dict(talent.staff(["ai-platform/ai-governance-risk", "ai-platform/ai-release-plan"], keyed)) == {
        "ai-platform/ai-governance-risk": "ai-strategist", "ai-platform/ai-release-plan": "Risk"}   # no stages: team order
    # with stages the specialist wins: the risk lead has more govern skills than the strategist
    assert dict(talent.staff(["ai-platform/ai-governance-risk"], keyed, SKILLS)) == {"ai-platform/ai-governance-risk": "Risk"}


def test_coverage_reports_real_gaps():
    stages = [s["id"] for s in json.loads((REPO_ROOT / "shared" / "adlc-stages.json").read_text())["stages"]]
    cov = talent.coverage(POOLS["ai-delivery-pod"], ROLES, SKILLS, stages)
    assert cov["evaluate"] == ["ai-quality-red-team"]
    assert cov["operate"] == []                      # the templated pod stops at the release decision
    pod = json.loads(json.dumps(POOLS["ai-delivery-pod"]))
    pod["members"].append({"role": "ai-ops-sre"})
    assert talent.coverage(pod, ROLES, SKILLS, stages)["operate"] == ["ai-ops-sre"]


def test_cli_exit_codes(tmp_path, monkeypatch):
    assert talent.main([]) == 0


def test_cards_cover_every_skill_and_flag_missing_ones(tmp_path):
    import json as _json
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "skill-cards.json").write_text(_json.dumps({"cards": {"a/x": "One line", "a/ghost": "x", "a/long": " ".join(["w"] * 13)}}))
    probs = talent.validate_cards({"a/x": "build", "a/y": "build", "a/long": "build"}, tmp_path)
    assert "skill a/y has no card in shared/skill-cards.json" in probs
    assert "skill-cards: a/ghost is not a skill" in probs
    assert "skill-cards: a/long is over 12 words" in probs
    assert not [p for p in probs if "a/x" in p]
