# TEST-FINDINGS — 2026-10-17 (branch `test/script-suite`)

Independent pytest suite for the skill scripts: **91 passed, 2 skipped**,
`scripts/validate.py` still reports 0 errors.

## Genuine script bugs fixed

None. The suite found no genuine script bugs. Every script honored its
documented contract: argparse `--help` exits 0, happy paths on the skill's own
example assets produce the expected columns/keys, bad or missing input exits
non-zero with a message, and no script touches the network.

## Test-expectation corrections (fixed in tests, not in scripts)

| test | observed | correction |
|---|---|---|
| `test_aiplatform_size.py::test_happy_path_json` | `cost_monthly_usd` is a breakdown dict `{"rental": {"gpu", "ops", "software", "total"}}`, not a number | assert `rental.total > 0` |
| `test_aiplatform_eval_retrieval.py::test_missing_columns` | `CSV missing columns: [...]` is printed to stderr | assert on stdout + stderr |
| `test_presales_score_inventory.py::test_validate_hard_failure` | `validation: FAILED` is printed to stderr | assert on stdout + stderr |

## Notes

- The handoff brief said "14 scripts"; the repo contains **12** (the brief's own
  enumerated list also names 12: 4 presales + 2 build + 3 ai-platform + 3 career).
  All 12 are covered, one test file each, plus `test_validator.py` and
  `test_offline.py`.
- 2 skipped: `test_docx_without_library_exits_3` and
  `test_pdf_without_library_exits_3` — python-docx and pypdf are installed in
  this environment and in CI, so the missing-library branches skip here by
  design; they execute in minimal environments without those packages.
