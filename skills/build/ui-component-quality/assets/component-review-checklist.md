# Component review checklist (manual pass, same rules as `ui_lint.py`)

Use in a PR review or when the linter cannot run. One line per rule; mark pass / fail / n.a. with `file:line`.

| # | Check | Rule |
|---|---|---|
| 1 | Every `<img>`/`<Image>` has `alt` (empty for decorative) | UI1 |
| 2 | Every icon-only button has `aria-label`/`aria-labelledby` or sr-only text | UI2 |
| 3 | No `onClick` on `div`/`span` without `role`, `tabIndex` and a key handler — prefer `<button>` | UI3 |
| 4 | Every input/select/textarea has a programmatic label (`htmlFor`, wrapping label, `aria-label`) | UI4 |
| 5 | Async data: loading state (skeleton/spinner/`Suspense`, `aria-busy`) and an error state | UI5 |
| 6 | Lists: explicit empty state before `.map` | UI6 |
| 7 | No fixed width > 600px without a responsive variant; layout works at 320px | UI7 |
| 8 | No `dangerouslySetInnerHTML` (or sanitised + documented) | UI8 |
| 9 | ≤ 8 props, or composed from a shared props type | UI9 |
| 10 | No `style={{}}`/new objects per row inside `.map` in hot lists | UI10 |
| 11 | State never shown by colour alone — add text or an icon | UI11 |
| 12 | Browser pass (axe/Lighthouse): contrast, focus visible, target size, focus not obscured | a11y-checklist.md |
