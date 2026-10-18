# Review rules — what the runner flags and why

The vendored `code-review` method (mattpocock/skills, pinned in `vendor/pins.json`) reviews a change on two axes, Standards and Spec, and keeps them separate. This runner automates only the mechanical part of the Standards axis. Read `vendor/code-review/SKILL.md` for the method; this note documents the detectors.

## Scope
- Only **added** lines are scanned (`+` lines of the new file). Context and removed lines never produce findings.
- Line numbers are new-file line numbers from the hunk headers.

## Detectors
| Rule | Severity | Flags | Common false positive → what to do |
|---|---|---|---|
| CR-SECRET | blocking | AWS key ids, GitHub/Slack/Stripe/Google tokens, private-key blocks, JWTs, `password/secret/token/api_key = "<literal>"`, high-entropy string literals (`--entropy` bits/char, `--min-secret-len`) | Test fixtures with fake keys, hashes → keep fakes obviously fake or override severity for the fixture path via a team rule |
| CR-EVAL | blocking | `eval(`, `exec(`, `new Function(` (not `.exec(` method calls) | Sandboxed expression engines → document and override |
| CR-TLS | blocking | `verify=False`, `rejectUnauthorized: false`, `CERT_NONE`, `NODE_TLS_REJECT_UNAUTHORIZED=0`, `InsecureSkipVerify: true`, `curl -k`, trust-all verifiers | Local-only dev tooling → still fix; use a local CA |
| CR-SQL-CONCAT | blocking | SQL text (`select … from`, `insert into`, `update … set`, `delete from`) built with `+`, f-strings, `${}`, `%` or `.format()` | Identifiers from a fixed allow-list → document; values must be bound parameters |
| CR-SWALLOW | warning | `except:` / `except Exception:` followed by `pass`/`...`, empty `catch {}`, `catch (Exception e) {}` | Deliberate best-effort cleanup → log at debug level instead of silence |
| CR-DEBUG | warning | `console.log/debug/trace`, `debugger`, `print(` in non-test `.py`, `pdb`, `breakpoint()`, `System.out.println`, `printStackTrace()` | CLI scripts whose job is to print → override for that path |
| CR-TODO | info | TODO/FIXME/XXX/HACK without `(owner)`, `@owner`, `[ABC-123]` or `(#123)` | — |
| CR-DUP | info | the same 3 consecutive non-trivial added lines appear twice | Generated code → ignore; it is a labelled judgement call, like the upstream smell baseline |
| CR-NO-TESTS | warning | code files changed and no test file changed | Pure refactors with existing coverage → say so in the PR |

Test files: `tests/`, `__tests__/`, `spec/`, `test_*.py`, `*_test.py|go`, `*.test|spec.[jt]sx?`, `*Test.java`. Debug detectors skip test files.

## Severities and the gate
`blocking` fails the run (`review.py --gate review.json` exits 1). `warning` and `info` are reported under Non-blocking (missing tests under Tests). Team rules may raise or lower any built-in severity; the change is recorded in `review.json` → `rules.overrides`.

## Thresholds are parameters
The entropy threshold, minimum literal length and the large-change label are CLI options with documented defaults, not facts about your codebase. Tune them per repository and record the values (they are echoed in `review.json`).
