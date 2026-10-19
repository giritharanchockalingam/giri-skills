"""Tests for ai-platform/ai-bom-license-check/scripts/aibom.py (normalisation, decisions, gate, CycloneDX shape)."""
from __future__ import annotations

import csv
import json

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/ai-platform/ai-bom-license-check/scripts/aibom.py"
SKILL = REPO_ROOT / "skills/ai-platform/ai-bom-license-check"
FIX = SKILL / "evals/fixtures"
TBD_LEGAL = "[TO BE BASELINED — owner: Legal counsel]"
HEAD = "component,type,version,license,source_url,use\n"
POLICY = "license,decision\nApache-2.0,allow\nMIT,allow\nCC-BY-NC-4.0,review\nAGPL-3.0-only,deny\nLicenseRef-Llama-3.1-Community,allow\n"


def _run(tmp_path, bom: str, policy: str | None = POLICY, *extra):
    (tmp_path / "bom.csv").write_text(HEAD + bom, encoding="utf-8")
    out = tmp_path / "out"
    args = ["--bom", str(tmp_path / "bom.csv"), "--out-dir", str(out), *extra]
    if policy is not None:
        (tmp_path / "policy.csv").write_text(policy, encoding="utf-8")
        args += ["--policy", str(tmp_path / "policy.csv")]
    res = run_script(SCRIPT, *args)
    rows = {r["component"]: r for r in csv.DictReader((out / "aibom.csv").open(encoding="utf-8"))} \
        if (out / "aibom.csv").exists() else {}
    return res, rows, out


def test_normalises_common_spellings(tmp_path):
    bom = ("a,library,1,Apache License 2.0,,internal\nb,library,1,the MIT licence,,internal\n"
           "c,library,1,\"Apache License, Version 2.0\",,internal\nd,library,1,apache-2.0,,internal\n")
    res, rows, _ = _run(tmp_path, bom)
    assert res.returncode == 0, res.stderr
    assert [rows[k]["spdx_id"] for k in "abcd"] == ["Apache-2.0", "MIT", "Apache-2.0", "Apache-2.0"]
    assert all(rows[k]["decision"] == "allow" for k in "abcd")


def test_unknown_licence_never_guessed(tmp_path):
    bom = "x,model,1,OpenRAIL-M,,internal\ny,model,1,Gemma,,internal\nz,service,1,,,internal\n"
    res, rows, _ = _run(tmp_path, bom)
    for k in "xyz":
        assert rows[k]["spdx_id"] == "unknown" and rows[k]["decision"] == "review"
    assert "Legal counsel" in rows["x"]["reason"]
    assert rows["z"]["license_raw"] == "[TO BE BASELINED — owner: Engineering lead]"


def test_noncommercial_commercial_use_denied_and_gate(tmp_path):
    bom = "nc,dataset,1,CC BY-NC 4.0,,commercial\nnc2,dataset,1,CC-BY-NC-4.0,,internal\n"
    res, rows, out = _run(tmp_path, bom)
    assert res.returncode == 1 and "nc" in res.stderr
    assert rows["nc"]["decision"] == "deny" and "conflicts" in rows["nc"]["reason"]
    assert rows["nc2"]["decision"] == "review"
    assert (out / "license-report.md").exists() and (out / "aibom.json").exists()


def test_policy_deny_and_missing_from_policy(tmp_path):
    res, rows, _ = _run(tmp_path, "g,library,1,AGPL-3.0-only,,internal\nb,library,1,BSD-3-Clause,,internal\n")
    assert res.returncode == 1
    assert rows["g"]["decision"] == "deny" and rows["b"]["decision"] == "review"
    assert "not in policy: BSD-3-Clause" in rows["b"]["reason"]


def test_llama_conditional_turns_allow_into_review(tmp_path):
    bom = "l1,model,1,Llama 3.1 Community License,,commercial\nl2,model,1,Llama 3.1 Community License,,internal\n"
    res, rows, _ = _run(tmp_path, bom)
    assert res.returncode == 0
    assert rows["l1"]["decision"] == "review" and rows["l2"]["decision"] == "allow"
    assert "commercial_use_restricted:conditional" in rows["l1"]["flags"]


def test_expressions(tmp_path):
    bom = ("o,library,1,AGPL-3.0-only OR MIT,,internal\na,library,1,MIT AND AGPL-3.0-only,,internal\n"
           "m,library,1,(MIT OR Apache-2.0) AND MIT,,internal\nw,library,1,GPL-2.0-only WITH Classpath-exception-2.0,,internal\n")
    res, rows, _ = _run(tmp_path, bom)
    assert rows["o"]["decision"] == "allow" and "MIT chosen" in rows["o"]["reason"]
    assert rows["a"]["decision"] == "deny" and "copyleft" in rows["a"]["flags"]
    assert rows["m"]["spdx_id"] == "unknown" and rows["w"]["spdx_id"] == "unknown"


def test_no_policy_every_decision_tbd(tmp_path):
    res, rows, out = _run(tmp_path, "a,library,1,MIT,,internal\nb,dataset,1,CC0-1.0,,commercial\n", None)
    assert res.returncode == 0 and all(r["decision"] == TBD_LEGAL for r in rows.values())
    md = (out / "license-report.md").read_text()
    assert "[TO BE BASELINED]" not in md and "No licence policy supplied" in md


def test_cyclonedx_shape(tmp_path):
    bom = ("m,model,1,Apache-2.0,https://example.com/m,internal\nd,dataset,2,CC-BY-NC-4.0,,internal\n"
           "s,service,v1,Vendor terms,,internal\nl,library,,MIT OR Apache-2.0,,internal\n")
    res, _, out = _run(tmp_path, bom, POLICY, "--system", "Fictional System")
    doc = json.loads((out / "aibom.json").read_text())
    assert doc["bomFormat"] == "CycloneDX" and doc["specVersion"] == "1.6" and doc["version"] == 1
    assert doc["metadata"]["component"]["name"] == "Fictional System"
    types = {c["name"]: c["type"] for c in doc["components"]}
    assert types == {"m": "machine-learning-model", "d": "data", "l": "library"}
    assert [s["name"] for s in doc["services"]] == ["s"]
    comp = {c["name"]: c for c in doc["components"]}
    assert comp["m"]["licenses"] == [{"license": {"id": "Apache-2.0", "acknowledgement": "declared"}}]
    assert comp["l"]["licenses"] == [{"expression": "MIT OR Apache-2.0", "acknowledgement": "declared"}]
    assert "version" not in comp["l"]
    assert doc["services"][0]["licenses"] == [{"license": {"name": "Vendor terms", "acknowledgement": "declared"}}]
    assert comp["m"]["externalReferences"] == [{"type": "website", "url": "https://example.com/m"}]


def test_invalid_inputs_exit_2(tmp_path):
    assert _run(tmp_path, "a,plugin,1,MIT,,internal\n")[0].returncode == 2
    assert _run(tmp_path, "a,library,1,MIT,,resale\n")[0].returncode == 2
    assert _run(tmp_path, "a,library,1,MIT,,internal\na,library,1,MIT,,internal\n")[0].returncode == 2
    assert _run(tmp_path, "a,library,1,MIT,,internal\n", "license,decision\nMIT,maybe\n")[0].returncode == 2
    res = _run(tmp_path, "a,library,1,MIT,,internal\n", "license,decision\nAcme EULA,allow\n")[0]
    assert res.returncode == 2 and "catalog" in res.stderr
    assert run_script(SCRIPT, "--out-dir", str(tmp_path / "o")).returncode == 2
    (tmp_path / "bad.csv").write_text("name,licence\nx,MIT\n", encoding="utf-8")
    assert run_script(SCRIPT, "--bom", str(tmp_path / "bad.csv"), "--out-dir", str(tmp_path / "o")).returncode == 2


def test_fixture_deterministic_and_verify(tmp_path):
    outs = []
    for n in ("a", "b"):
        out = tmp_path / n
        res = run_script(SCRIPT, "--bom", str(FIX / "bom.csv"), "--policy", str(FIX / "policy.csv"),
                         "--system", "Northwind Billing Assistant", "--out-dir", str(out))
        assert res.returncode == 0, res.stderr
        outs.append({f: (out / f).read_bytes() for f in ("aibom.csv", "aibom.json", "license-report.md")})
    assert outs[0] == outs[1]
    assert run_script(SCRIPT, "--verify", str(tmp_path / "a" / "aibom.json")).returncode == 0
    p = tmp_path / "a" / "aibom.json"
    p.write_text(p.read_text().replace('"machine-learning-model"', '"model"'), encoding="utf-8")
    bad = run_script(SCRIPT, "--verify", str(p))
    assert bad.returncode == 1 and "enum" in bad.stderr


def test_catalog_ids_and_sources():
    rows = [ln for ln in (SKILL / "assets/license-catalog.csv").read_text(encoding="utf-8").splitlines()
            if not ln.startswith("#")]
    cat = list(csv.DictReader(rows))
    ids = {r["spdx_id"] for r in cat}
    for need in ("Apache-2.0", "MIT", "BSD-3-Clause", "GPL-3.0-only", "AGPL-3.0-only", "CC-BY-4.0",
                 "CC-BY-NC-4.0", "CC-BY-SA-4.0", "LicenseRef-Llama-3.1-Community", "LicenseRef-Gemma-Terms-of-Use",
                 "LicenseRef-CreativeML-OpenRAIL-M"):
        assert need in ids
    for r in cat:
        assert r["source_url"].startswith("https://")
        assert r["commercial_use_restricted"] in ("yes", "no", "conditional")
        assert all(r[f] in ("yes", "no") for f in ("copyleft", "attribution_required", "use_based_restrictions"))
