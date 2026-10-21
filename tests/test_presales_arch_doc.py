"""Tests for presales/solution-architecture-doc/scripts/arch_doc.py."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from conftest import REPO_ROOT, run_script

SCRIPT = "skills/presales/solution-architecture-doc/scripts/arch_doc.py"
FX = REPO_ROOT / "skills/presales/solution-architecture-doc/evals/fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_output  # noqa: E402


def run(tmp_path, comp):
    md, nfr = tmp_path / "arch.md", tmp_path / "nfr.csv"
    return run_script(SCRIPT, str(comp), "--out", str(md), "--nfr", str(nfr)), md, nfr


def test_help_exits_zero():
    assert run_script(SCRIPT, "--help").returncode == 0


def test_fixture_doc(tmp_path):
    r, md, nfr = run(tmp_path, FX / "components.json")
    assert r.returncode == 0, r.stderr
    text = md.read_text(encoding="utf-8")
    assert text.count("```mermaid") == 2
    assert check_output.run_check("mermaid_parses", str(md))["pass"]
    assert 'SYS["Order Hub"]' in text and 'erp -->|batch file: inventory positions| SYS' in text
    assert "gw -->|INT-001 sync REST| orders" in text and 'subgraph Order_Hub["Order Hub"]' in text
    assert "### event" in text and "| INT-004 | Event backbone | Warehouse management | connector |" in text
    assert "| 2 | INT-004, INT-005 | batch file, event |" in text
    assert "| ADR-005 | API gateway on Apigee X |" in text
    rows = list(csv.DictReader(nfr.open(encoding="utf-8")))
    assert [r_["category"] for r_ in rows] == ["Availability", "Performance", "Recoverability", "Security"]
    assert rows[0]["target"] == "99.9% monthly" and rows[1]["target"] == "[TO BE BASELINED — owner: Solution architect]"
    assert "| Wave for INT-006 |" in text                               # missing wave surfaced


def test_thin_components_parse_and_mark_tbd(tmp_path):
    r, md, nfr = run(tmp_path, FX / "components-thin.json")
    assert r.returncode == 0, r.stderr
    assert check_output.run_check("mermaid_parses", str(md))["pass"]
    rows = list(csv.DictReader(nfr.open(encoding="utf-8")))
    assert all(r_["target"].startswith("[TO BE BASELINED") for r_ in rows)


def test_labels_are_mermaid_safe(tmp_path):
    comp = tmp_path / "c.json"
    comp.write_text(json.dumps({"system": "Sys (v2) [beta]", "containers": [{"id": "a", "name": "A {core}", "tech": "x(y)"}],
                                "integrations": []}), encoding="utf-8")
    r, md, _ = run(tmp_path, comp)
    assert r.returncode == 0, r.stderr
    assert check_output.run_check("mermaid_parses", str(md))["pass"]


def test_bad_input_exits_1(tmp_path):
    assert run(tmp_path, tmp_path / "missing.json")[0].returncode == 1
    for bad in ('{nope', '{"system": "x"}', '{"system": "x", "containers": [{"id": "a", "name": "A"}, {"id": "a", "name": "B"}]}',
                '{"system": "x", "containers": [{"id": "a", "name": "A"}], "integrations": [{"from": "a", "to": "zzz"}]}'):
        p = tmp_path / "b.json"
        p.write_text(bad, encoding="utf-8")
        assert run(tmp_path, p)[0].returncode == 1, bad


# ───────── v0.3: partner-grade deliverables ─────────
GOLDEN = REPO_ROOT / "skills/presales/solution-architecture-doc/evals/golden/agent-happy-path"


def run_full(tmp_path, comp, client="Northwind"):
    out = tmp_path / "o"
    r = run_script(SCRIPT, str(comp), "--out", str(out / "architecture.md"), "--nfr", str(out / "nfr.csv"), "--client", client,
                   "--svg-dir", str(out / "diagrams"), "--drawio", str(out / "architecture.drawio"),
                   "--html", str(out / "architecture.html"), "--adr-dir", str(out / "adr"))
    return r, out


def test_try_example_reproduces_the_reviewed_golden_output_exactly(tmp_path):
    """Try Example must give the reviewed deliverable, byte for byte: same input, same documents and pictures."""
    r, out = run_full(tmp_path, FX / "northwind-order-hub.json")
    assert r.returncode == 0, r.stderr
    golden = sorted(p.relative_to(GOLDEN) for p in GOLDEN.rglob("*") if p.is_file())
    made = sorted(p.relative_to(out) for p in out.rglob("*") if p.is_file())
    assert made == golden
    for rel in golden:
        assert (out / rel).read_bytes() == (GOLDEN / rel).read_bytes(), f"{rel} differs from the reviewed golden output"


def test_diagrams_are_valid_files_people_can_open(tmp_path):
    import xml.etree.ElementTree as ET
    r, out = run_full(tmp_path, FX / "northwind-order-hub.json")
    assert r.returncode == 0, r.stderr
    for v in ("context", "container", "deployment"):
        root = ET.parse(out / "diagrams" / f"{v}.svg").getroot()
        assert root.tag.endswith("svg") and root.get("viewBox")
    mx = ET.parse(out / "architecture.drawio").getroot()
    assert mx.tag == "mxfile" and len(mx.findall("diagram")) == 3
    cont = (out / "diagrams/container.svg").read_text(encoding="utf-8")
    for name in ("API gateway", "Order service", "Event backbone", "Order store", "Warehouse management", "Store POS", "INT-005 batch file"):
        assert name in cont, name
    html = (out / "architecture.html").read_text(encoding="utf-8")
    assert html.count("<figure>") == 3 and "<script" not in html.lower()


def test_decisions_are_scored_not_asserted(tmp_path):
    r, out = run_full(tmp_path, FX / "northwind-order-hub.json")
    text = (out / "architecture.md").read_text(encoding="utf-8")
    # weighted score = Σ(weight × score) ÷ Σweights: (35·5 + 25·3 + 20·4 + 20·3) / 100 = 3.9
    assert "| Kafka (managed) **(chosen)** | 5 | 3 | 4 | 3 | 3.9 |" in text
    assert "| Cloud Pub/Sub | 2 | 5 | 4 | 4 | 3.55 |" in text
    assert "Recommended: event backbone for order events on **Kafka (managed)** (ADR-001)" in text
    assert "API entry point for stores and partners on **Apigee X** (ADR-003)" in text     # acronyms keep their capitals
    adr = (out / "adr/ADR-001-event-backbone-for-order-events.md").read_text(encoding="utf-8")
    for h in ("## Context", "## Options considered", "## Decision", "## Consequences"):
        assert h in adr


def test_a_choice_below_the_top_score_is_flagged(tmp_path):
    comp = json.loads((FX / "northwind-order-hub.json").read_text(encoding="utf-8"))
    comp["decisions"][0]["chosen"] = "IBM MQ"
    p = tmp_path / "c.json"
    p.write_text(json.dumps(comp), encoding="utf-8")
    r, out = run_full(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert "The chosen option is not the top weighted score (Kafka (managed))" in (out / "architecture.md").read_text(encoding="utf-8")


def test_risks_rated_and_gaps_become_open_items_not_inventions(tmp_path):
    r, out = run_full(tmp_path, FX / "northwind-order-hub.json")
    text = (out / "architecture.md").read_text(encoding="utf-8")
    assert "| Nightly SAP inventory file makes intraday promises inaccurate | 4 | 4 | 16 (high) |" in text
    tbd = "[TO BE BASELINED — owner: Solution architect]"
    assert f"| Store POS upgrade dates are not known | 3 | 3 | 9 (medium) | {tbd} | {tbd} |" in text
    for item in ("Owner for risk: Store POS upgrade dates are not known", "Control for: Payment data", "Wave for INT-006",
                 "NFR target: Performance — Order create p95 latency"):
        assert item in text, item
    assert "6 items still need a baseline or an owner" in text


def test_every_value_in_the_document_comes_from_the_input(tmp_path):
    """No number appears that the input did not state, except computed scores/ratings and counts of the input's own lists."""
    import re
    r, out = run_full(tmp_path, FX / "northwind-order-hub.json")
    src = (FX / "northwind-order-hub.json").read_text(encoding="utf-8")
    text = (out / "architecture.md").read_text(encoding="utf-8")
    computed = {"3.9", "3.55", "2.8", "4.7", "3.2", "3.0", "4.6", "2.3", "16", "15", "10", "9", "8", "14", "1", "2", "3", "4", "5", "6"}
    for num in set(re.findall(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w.])", text)):
        assert num in src or num in computed, f"number {num} is not in the input"
