# Flow format and generation rules

The vendored `webapp-testing` skill (anthropics/skills, pinned in `vendor/pins.json`) writes native Python Playwright scripts against a running app. This runner applies the same conventions to generated pytest-playwright tests. Read `vendor/webapp-testing/SKILL.md` for the method; this note documents the runner's contract.

## Flows JSON
| Field | Type | Rule |
|---|---|---|
| `base_url` | string | An `http(s)://` URL or a placeholder (`${BASE_URL}`, `{{BASE_URL}}`, `<…>`). At test time `BASE_URL` from the environment wins; with only a placeholder the tests skip. |
| `flows[]` | list | Non-empty. |
| `flows[].name` | string | Required, unique after slugging (it becomes `test_<slug>`). |
| `flows[].steps[]` | list | Non-empty. |
| `steps[].action` | enum | `goto`, `click`, `fill`, `expect_text`, `expect_url`. Anything else is an error. |
| `steps[].selector` | string | Required for `click`, `fill`; optional for `expect_text`; ignored (info) for `goto`, `expect_url`. |
| `steps[].value` | string | Required for `goto` (path or absolute URL), `fill`, `expect_text`, `expect_url` (substring of the URL). |

## Selector mapping
| Selector | Generated locator |
|---|---|
| `role=button[name="Save"]` | `page.get_by_role('button', name='Save')` |
| `text=Save` | `page.get_by_text('Save')` |
| `label=Email` | `page.get_by_label('Email')` |
| `placeholder=Search` | `page.get_by_placeholder('Search')` |
| `testid=cart` / `data-testid=cart` | `page.get_by_test_id('cart')` |
| anything else | `page.locator('<selector>')` + style warning |

## Warnings (do not fail the run)
| Pattern | Severity | Reason |
|---|---|---|
| `:nth-child()` / `:nth-of-type()` | warning | positional; breaks when order changes |
| XPath (`//…`, `xpath=`) | warning | tied to markup structure |
| Generated class (`.css-…`, `.sc-…`, `.jsx-123`, CSS-module hashes) | warning | changes between builds |
| CSS chain with 3+ combinators | warning | couples the test to DOM depth |
| Plain CSS | info | acceptable; role/text/label/test id survive refactors better |
| Flow not starting with `goto` | warning | depends on state left by another test |
| Flow with no `expect_*` | warning | can pass without checking anything |

## Generated code
- One function per flow, pytest-playwright `page` fixture (headless Chromium by default).
- After every `goto`: `page.wait_for_load_state("networkidle")` — the upstream skill's rule for dynamic apps.
- `expect_text` without a selector: `expect(page.get_by_text(v).first).to_be_visible()`; with a selector: `to_contain_text`.
- `expect_url`: `expect(page).to_have_url(re.compile(re.escape(v)))`.
- Values are emitted with Python `repr()`, so quotes and backslashes in flows cannot break the file.
- The module docstring carries `GENERATED, NOT EXECUTED`; `gen_tests.py --verify-compiles` checks both the banner and `compile()`.
