"""Harness layer 3: the sandbox for model-written project code (docs/HARNESS.md).

Unit tests check the docker command the box is built from; integration tests run real containers and are skipped,
with the reason, where no docker daemon is reachable."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import sandbox as sbx  # noqa: E402

DOCKER = sbx.docker_ok()
needs_docker = pytest.mark.skipif(not DOCKER, reason="no docker daemon reachable: integration tests of the box skipped")


def test_none_runs_on_the_host_and_says_so(tmp_path):
    sb = sbx.Sandbox("none")
    argv, _ = sb.wrap("echo hi", tmp_path)
    assert argv == ["bash", "-c", "echo hi"] and sb.describe().startswith("NOT SANDBOXED")


def test_docker_command_isolates_network_filesystem_and_resources(tmp_path, monkeypatch):
    sb = sbx.Sandbox("docker", image="node:22", cpus="1", memory="1g", pids="128")
    monkeypatch.setattr(sb, "prepare", lambda: None)
    argv, _ = sb.wrap("npm test", tmp_path, writable=[tmp_path / "ev"], readonly=[REPO / "scripts"])
    s = " ".join(argv)
    assert argv[:3] == ["docker", "run", "--rm"] and "--network none" in s and "--read-only" in s
    assert "--cpus 1" in s and "--memory 1g" in s and "--pids-limit 128" in s and "no-new-privileges" in s
    assert f"{tmp_path.resolve()}:{tmp_path.resolve()}" in s and f"{(tmp_path / 'ev').resolve()}:{(tmp_path / 'ev').resolve()}" in s
    assert f"{(REPO / 'scripts').resolve()}:{(REPO / 'scripts').resolve()}:ro" in s
    assert argv[-4:-1] == ["node:22", "bash", "-c"] and argv[-1].endswith("npm test")


def test_only_the_install_gets_a_network(tmp_path, monkeypatch):
    sb = sbx.Sandbox("docker", image="node:22")
    monkeypatch.setattr(sb, "prepare", lambda: None)
    assert "--network host" in " ".join(sb.wrap("npm ci", tmp_path, network="host")[0])
    assert "--network none" in " ".join(sb.wrap("npm test", tmp_path)[0])


def test_local_postgres_is_reached_through_its_socket_not_the_network():
    assert sbx.pg_socket_url("postgresql://u:p@127.0.0.1:5432/db") == "postgresql://u:p@/db?host=/var/run/postgresql&port=5432"
    assert sbx.pg_socket_url("postgresql://u:p@db.example.com:5432/db") is None
    assert sbx.pg_socket_url("mysql://u@127.0.0.1/db") is None


def test_an_unreachable_daemon_is_an_error_not_a_silent_fallback(tmp_path):
    env = {**os.environ, "DOCKER_HOST": "unix:///nonexistent/docker.sock", "SF_SANDBOX": "docker"}
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "sandbox.py"), "exec", "--dir", str(tmp_path), "--", "true"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 2 and "docker daemon is not reachable" in r.stderr


@needs_docker
def test_box_blocks_network_and_system_writes_and_keeps_project_writes(tmp_path):
    env = {**os.environ, "SF_SANDBOX": "docker"}
    script = "touch /usr/x 2>/dev/null && echo USR-WRITABLE; (getent hosts example.com >/dev/null && echo NET-OPEN) || echo net-blocked; echo hi > made.txt"
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "sandbox.py"), "exec", "--dir", str(tmp_path), "--", "bash", "-c", script],
                       capture_output=True, text=True, env=env, timeout=180)
    assert "USR-WRITABLE" not in r.stdout and "NET-OPEN" not in r.stdout and "net-blocked" in r.stdout, r.stdout + r.stderr
    assert (tmp_path / "made.txt").read_text() == "hi\n"


@needs_docker
def test_box_enforces_the_timeout_and_removes_the_container(tmp_path):
    env = {**os.environ, "SF_SANDBOX": "docker"}
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "sandbox.py"), "exec", "--dir", str(tmp_path), "--timeout", "5",
                        "--", "sleep", "60"], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 124
    left = subprocess.run(["docker", "ps", "-q", "--filter", "name=sf-sbx-"], capture_output=True, text=True).stdout.strip()
    assert left == "", "the container outlived its timeout"
