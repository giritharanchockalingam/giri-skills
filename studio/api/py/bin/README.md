# Vendored git for the hosted runtime

`git` here is put first on `PATH` by `api/py/run.py` so skills that read git facts (for example
`build/handoff-and-thread-close`) run in the portal the same way they run locally. The Vercel Python
runtime has no git of its own.

| | |
|---|---|
| Version | git 2.53.0 (GitHub Desktop dugite-native v2.53.0-4, ubuntu-x64) |
| Source archive | https://github.com/desktop/dugite-native/releases/download/v2.53.0-4/dugite-native-v2.53.0-4098283-ubuntu-x64.tar.gz |
| Archive sha256 | `cca76aa31ad9e835e771ee7f55b73934777fbd8d16757a10d307ba06de860901` (the pin dugite 3.2.3 publishes) |
| Binary sha256 | `74ea93260192ffae64e47c70c9fc54c8ca3609fcc746dc6518e1d92a54951fd4` (checked by tests/test_factory_runtime.py) |
| Links against | libc, libz only |
| Licence | GPL-2.0; source: https://github.com/git/git/tree/v2.53.0 and https://github.com/desktop/dugite-native |

Only `bin/git` is kept: init, add, commit, log, show, diff, status and rev-parse are built in. Network
transports, credential helpers and hooks are not shipped. To refresh: change the pin in
`scripts/vendor-git.sh`, run it from `studio/`, update the two hashes above and in the test, commit.
