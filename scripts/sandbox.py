#!/usr/bin/env python3
"""Sandbox for running model-written project code (docs/HARNESS.md layer 3).

    sb = Sandbox.from_env()                                   # or Sandbox("docker", image=..., cpus=2, memory="4g")
    argv, env = sb.wrap("npm test", cwd=repo, writable=[repo, evidence_dir], network="none")
    subprocess.run(argv, env=env, ...)

    python3 scripts/sandbox.py exec --dir <repo> -- npx vitest run tests/x.test.ts     # what the reviewer is allowed to run

Backends
  docker  every command runs in `docker run --rm`: only `cwd` and the listed writable folders are writable (mounted at
          the same absolute path), the image is read-only, /tmp is a private tmpfs, `--network none` (the dependency
          install alone gets the host network, for the package registry), CPU / memory / process limits, a timeout.
          Image "hostroot" is a skeleton image (built locally on first use with `docker import`, no registry needed)
          whose /usr, /etc and /opt come read-only from the host, so the project runs on the host's own toolchain.
          Any other image name (e.g. node:22-bookworm) is used as is.
  none    runs on the host; recorded in the evidence as NOT SANDBOXED.

Postgres at localhost in DATABASE_URL is reached through its unix socket (mounted), never the network: the URL is
rewritten to postgresql://user:pass@/db?host=/var/run/postgresql.

Configuration travels in environment variables so a child process (the reviewer's sandbox exec) gets the same box:
SF_SANDBOX (docker|none), SF_SANDBOX_IMAGE, SF_SANDBOX_CPUS, SF_SANDBOX_MEMORY, SF_SANDBOX_PIDS.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

HOSTROOT_IMAGE = "sf-sandbox-hostroot:1"
HOST_RO = ("/usr", "/etc", "/opt")
PASS_ENV = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "NODE_EXTRA_CA_CERTS",
            "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CI", "NODE_ENV", "NEXT_TELEMETRY_DISABLED", "PLAYWRIGHT_BROWSERS_PATH")
PG_SOCKET_DIR = Path("/var/run/postgresql")


class SandboxError(Exception):
    pass


def pg_socket_url(url: str) -> str | None:
    """postgresql://u:p@127.0.0.1:5432/db -> postgresql://u:p@/db?host=/var/run/postgresql&port=5432 (None: not local)."""
    try:
        u = urlsplit(url)
    except ValueError:
        return None
    if u.scheme not in ("postgres", "postgresql") or (u.hostname or "") not in ("127.0.0.1", "localhost", "::1"):
        return None
    cred = u.netloc.rsplit("@", 1)[0] + "@" if "@" in u.netloc else ""
    q = dict(parse_qsl(u.query))
    q.update({"host": str(PG_SOCKET_DIR), **({"port": str(u.port)} if u.port else {})})
    return urlunsplit((u.scheme, cred, u.path, urlencode(q, safe="/"), ""))


def docker_ok() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def ensure_hostroot_image() -> None:
    if subprocess.run(["docker", "image", "inspect", HOSTROOT_IMAGE], capture_output=True).returncode == 0:
        return
    with tempfile.TemporaryDirectory() as t:
        root = Path(t) / "rootfs"
        for d in ("usr", "etc", "opt", "tmp", "proc", "sys", "dev", "root", "var/run", "home"):
            (root / d).mkdir(parents=True, exist_ok=True)
        for link, to in (("bin", "usr/bin"), ("lib", "usr/lib"), ("lib64", "usr/lib64"), ("sbin", "usr/sbin")):
            (root / link).symlink_to(to)
        (root / "tmp").chmod(0o1777)
        tar = subprocess.run(["tar", "-C", str(root), "-c", "."], capture_output=True, check=True).stdout
        r = subprocess.run(["docker", "import", "-", HOSTROOT_IMAGE], input=tar, capture_output=True)
        if r.returncode != 0:
            raise SandboxError(f"could not build the {HOSTROOT_IMAGE} image: {r.stderr.decode(errors='replace')[:300]}")


class Sandbox:
    def __init__(self, mode: str = "none", image: str = "hostroot", cpus: str = "2", memory: str = "4g", pids: str = "1024"):
        if mode not in ("none", "docker"):
            raise SandboxError(f"unknown sandbox {mode!r} (docker or none)")
        self.mode, self.image, self.cpus, self.memory, self.pids = mode, image, str(cpus), str(memory), str(pids)
        self._ready = False

    @classmethod
    def from_env(cls) -> "Sandbox":
        e = os.environ
        return cls(e.get("SF_SANDBOX", "none"), e.get("SF_SANDBOX_IMAGE", "hostroot"), e.get("SF_SANDBOX_CPUS", "2"),
                   e.get("SF_SANDBOX_MEMORY", "4g"), e.get("SF_SANDBOX_PIDS", "1024"))

    def env_vars(self) -> dict:
        return {"SF_SANDBOX": self.mode, "SF_SANDBOX_IMAGE": self.image, "SF_SANDBOX_CPUS": self.cpus,
                "SF_SANDBOX_MEMORY": self.memory, "SF_SANDBOX_PIDS": self.pids}

    def describe(self) -> str:
        if self.mode == "none":
            return "NOT SANDBOXED: project code ran on the host"
        return (f"sandboxed in docker ({'host toolchain, read-only' if self.image == 'hostroot' else self.image}; network none "
                f"except the dependency install; {self.cpus} CPU, {self.memory} memory, {self.pids} processes; only the project "
                f"and its evidence folder writable)")

    def prepare(self) -> None:
        if self.mode != "docker" or self._ready:
            return
        if not docker_ok():
            raise SandboxError("--sandbox docker: the docker daemon is not reachable (start Docker, or run with --sandbox none, "
                               "which the evidence records as NOT SANDBOXED)")
        if self.image == "hostroot":
            ensure_hostroot_image()
        self._ready = True

    def wrap(self, cmd: str, cwd: Path, writable: list[Path] | None = None, network: str = "none",
             env: dict | None = None, readonly: list[Path] | None = None) -> tuple[list[str], dict]:
        """(argv, env) to pass to subprocess.run. `cmd` is a shell command line, run in `cwd`."""
        base_env = {**os.environ, **(env or {})}
        if self.mode == "none":
            return ["bash", "-c", cmd], base_env
        self.prepare()
        cwd = Path(cwd).resolve()
        tag = "".join(ch for ch in os.environ.get("SF_SANDBOX_TAG", "") if ch.isalnum())[:20]
        self.last_name = f"sf-sbx-{tag + '-' if tag else ''}{uuid.uuid4().hex[:12]}"
        argv = ["docker", "run", "--rm", "-i", "--name", self.last_name, *([] if self.image == "hostroot" else ["--init"]), "--network", "host" if network == "host" else "none",
                "--cpus", self.cpus, "--memory", self.memory, "--pids-limit", self.pids, "--shm-size", "1g",
                "--read-only", "--tmpfs", "/tmp:exec,size=2g", "--tmpfs", "/home:exec,size=2g",
                "--security-opt", "no-new-privileges", "-w", str(cwd)]
        mounts = {str(cwd)}
        for w in writable or []:
            mounts.add(str(Path(w).resolve()))
        for m in sorted(mounts):
            Path(m).mkdir(parents=True, exist_ok=True)
            argv += ["-v", f"{m}:{m}"]
        for ro in readonly or []:
            r = str(Path(ro).resolve())
            if Path(r).exists() and r not in mounts:
                argv += ["-v", f"{r}:{r}:ro"]
        if self.image == "hostroot":
            for ro in HOST_RO:
                if Path(ro).is_dir() and not any(m == ro or m.startswith(ro + "/") for m in mounts):
                    argv += ["-v", f"{ro}:{ro}:ro"]
            browsers = Path(base_env.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / ".cache" / "ms-playwright")
            if browsers.is_dir():
                argv += ["-v", f"{browsers}:{browsers}:ro", "-e", f"PLAYWRIGHT_BROWSERS_PATH={browsers}"]
        inner = {"HOME": "/home/sandbox", "PATH": base_env.get("PATH", "/usr/bin:/bin"), "CI": base_env.get("CI", "1")}
        for k in PASS_ENV:
            if base_env.get(k):
                inner[k] = base_env[k]
        for k in ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
            f = base_env.get(k)
            if f and Path(f).is_file() and not f.startswith(HOST_RO):
                argv += ["-v", f"{f}:{f}:ro"]
        db = base_env.get("DATABASE_URL", "")
        sock = pg_socket_url(db) if db else None
        if sock and PG_SOCKET_DIR.is_dir():
            argv += ["-v", f"{PG_SOCKET_DIR}:{PG_SOCKET_DIR}"]
            inner["DATABASE_URL"] = sock
        elif db:
            inner["DATABASE_URL"] = db
        for k, v in (env or {}).items():
            if k not in ("PATH", "HOME"):
                inner[k] = v
        for k, v in sorted(inner.items()):
            argv += ["-e", f"{k}={v}"]
        argv += [HOSTROOT_IMAGE if self.image == "hostroot" else self.image, "bash", "-c", f"mkdir -p $HOME && {cmd}"]
        return argv, base_env


def kill(argv: list[str]) -> None:
    """Stop the container a wrapped command started (a timeout kills the docker client, not the container)."""
    if "--name" in argv:
        subprocess.run(["docker", "kill", argv[argv.index("--name") + 1]], capture_output=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run one command in the configured sandbox (SF_SANDBOX*)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("exec")
    ex.add_argument("--dir", type=Path, required=True, help="working folder (the only writable one besides /tmp)")
    ex.add_argument("--timeout", type=float, default=600)
    ex.add_argument("--ro", type=Path, action="append", default=[], help="extra folder visible read-only (repeatable)")
    ex.add_argument("--rw", type=Path, action="append", default=[], help="extra writable folder (repeatable)")
    ex.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    rest = a.rest[1:] if a.rest[:1] == ["--"] else a.rest
    if not rest:
        ap.error("give the command after --")
    try:
        argv2, env = Sandbox.from_env().wrap(shlex.join(rest) if len(rest) > 1 else rest[0], a.dir, writable=a.rw, readonly=a.ro)
    except SandboxError as e:
        print(f"sandbox: {e}", file=sys.stderr)
        return 2
    log = os.environ.get("SF_SANDBOX_LOG")
    t0, code = time.time(), 124
    try:
        code = subprocess.run(argv2, env=env, timeout=a.timeout).returncode
        return code
    except subprocess.TimeoutExpired:
        kill(argv2)
        print(f"sandbox: timed out after {a.timeout:.0f}s", file=sys.stderr)
        return 124
    finally:
        if log:                                 # the acceptance gate counts what the reviewer actually ran
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"cmd": rest, "exit": code, "seconds": round(time.time() - t0, 1)}) + "\n")


if __name__ == "__main__":
    sys.exit(main())
