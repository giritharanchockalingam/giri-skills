"""Offline guarantee: no script may depend on network access."""
from __future__ import annotations

import re

import pytest

from conftest import REPO_ROOT, SCRIPTS

# repo-level tooling is held to the same offline rule
SCRIPTS = {**SCRIPTS, "run_skill": "scripts/run_skill.py", "check_output": "scripts/check_output.py",
           "skillmeta": "scripts/skillmeta.py"}

NETWORK_IMPORT = re.compile(
    r"^\s*(import|from)\s+"
    r"(socket|urllib|requests|httpx|http\.client|ssl|websocket|aiohttp|urllib3)\b",
    re.MULTILINE,
)
NETWORK_CALLS = ("urlopen(", "urlretrieve(", "socket.create_connection(")


@pytest.mark.parametrize("name,rel", sorted(SCRIPTS.items()))
def test_no_network_imports(name, rel):
    src = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert not NETWORK_IMPORT.search(src), f"{rel} imports a networking module"


@pytest.mark.parametrize("name,rel", sorted(SCRIPTS.items()))
def test_no_network_calls(name, rel):
    src = (REPO_ROOT / rel).read_text(encoding="utf-8")
    for token in NETWORK_CALLS:
        assert token not in src, f"{rel} references {token}"
