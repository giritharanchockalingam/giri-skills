# Readability: Flesch–Kincaid grade as computed by the script

`grade = 0.39 × (words ÷ sentences) + 11.8 × (syllables ÷ words) − 15.59`, rounded to one decimal (formula: sources.md S5).

## What is counted
- **Text graded**: the notice body (every non-heading line of `notice.md`, joined). A `[TO BE BASELINED …]` marker is graded as the single word "unknown".
- **Words**: whitespace-separated tokens containing at least one letter or digit.
- **Sentences**: runs of `.`, `!` or `?` followed by whitespace or the end of text (minimum 1). A dot inside `help@northwind.example` or `2026-09-30` does not end a sentence; `Questions?` does.
- **Syllables (heuristic)**: lower-case letters only; count groups of consecutive vowels `a e i o u y`; subtract one for a final silent `e` (not `-le`, `-ee`, `-ye`) when the word has more than one group; minimum 1. Tokens with a digit, `@`, `://` or `www.` count as one syllable.

## Limits of the heuristic
- English only. It miscounts some words (e.g. `created` → 2, true 3; `area` → 2, true 3; `queue` → 1, correct) — typically within ±1 syllable per long word, which moves the grade by a few tenths on a 100-word notice.
- Very short texts swing widely: one long word in a 20-word notice can move the grade by more than 1.
- Grade is a proxy. It does not test plain-language quality, layout, contrast, screen-reader support or translation; Article 50(5) accessibility requirements are therefore marked `partial` at best.
- `--verify notice.md` re-grades the written notice and checks it against `transparency.json`.
