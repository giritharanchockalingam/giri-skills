#!/usr/bin/env bash
# Refresh the git binary the hosted runtime (api/py/run.py) puts on PATH for skills that read git facts
# (e.g. build/handoff-and-thread-close). Source: GitHub Desktop's dugite-native build, pinned by URL and sha256
# (the same pin dugite publishes in script/embedded-git.json). Only bin/git is kept: the commands skills use
# (init, add, commit, log, show, diff, status, rev-parse) are built in. Run from studio/; commit the result.
set -euo pipefail
URL="https://github.com/desktop/dugite-native/releases/download/v2.53.0-4/dugite-native-v2.53.0-4098283-ubuntu-x64.tar.gz"
SHA256="cca76aa31ad9e835e771ee7f55b73934777fbd8d16757a10d307ba06de860901"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/git.tgz" "$URL"
echo "$SHA256  $tmp/git.tgz" | sha256sum -c -
tar -xzf "$tmp/git.tgz" -C "$tmp" ./bin/git
install -m 0755 "$tmp/bin/git" api/py/bin/git
sha256sum api/py/bin/git
api/py/bin/git --version
