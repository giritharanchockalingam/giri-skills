# Debug method — what the runner computes and why

This skill automates the evidence-gathering phases of the vendored `systematic-debugging` method (obra/superpowers, pinned in `vendor/pins.json`): read the error completely, check recent changes, trace the call stack, then test one hypothesis at a time. Read the upstream `vendor/systematic-debugging/SKILL.md` for the method itself; this note documents only the runner's rules.

## Parsing
| Format | Frames | Error line |
|---|---|---|
| Python | `File "<path>", line N, in <func>` (traceback, most recent call last → reversed to innermost first); pytest `path.py:N: in func` | last `Type: message` line (`E   ` prefix allowed) |
| JS / TS | `at func (path:line:col)` or `at path:line:col` (already innermost first) | first `XxxError: message` line |
| Java / JVM | `at pkg.Class.method(File.java:N)` (module prefix such as `java.base/` allowed) | deepest `Caused by:` block, else the first `pkg.Type: message` |

When several formats appear, the one with the most frames wins. No error line in any format → exit 2: the runner never invents a symptom.

## In-repo frames
Third-party when the path contains `site-packages`, `dist-packages`, `node_modules`, `node:internal`, `<frozen …>`, `/lib/pythonX`, or the Java class starts with `java.`, `javax.`, `jdk.`, `sun.`, `com.sun.`, `org.junit.`, `org.opentest4j.`, `kotlin.`, `scala.`. A frame whose file appears in the diff is always in-repo.

## Diff correlation
- File overlap: the frame path ends with the diff path (or vice versa); Java frames are matched on `package/path/File.java`.
- Line overlap: the frame line lies inside a hunk of the new file (hunk range includes the diff's context lines, so "inside a changed hunk", not "on the changed line"; the changed lines are listed).
- Classification: `regression-likely` (any overlap) · `no-overlap` (diff given, nothing touched) · `no-diff`.

## Hypothesis scoring
| Score | Evidence |
|---|---|
| 3 | A stack frame sits inside a changed hunk |
| 2 | A stack frame is in a changed file, or the error type matches a known failure family at an in-repo frame |
| 1 | Weak: innermost-frame default, or environmental when nothing overlaps |

Failure families (null value, missing key/index, assertion mismatch, dependency/environment, timing, external dependency, type/contract) are generic debugging categories; each comes with a falsifying experiment, not a fix.

## The fix gate
Always written closed (`fix_allowed: false`). It opens only when a hypothesis is confirmed by its experiment and a failing automated test reproduces the defect. Three failed fixes means the design is in question, not that a fourth fix is due. `debug_log.py --validate` fails any debug.json whose gate is open without a confirmed hypothesis.
