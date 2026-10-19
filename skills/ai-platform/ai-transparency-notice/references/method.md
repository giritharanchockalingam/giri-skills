# Method: notice, system card, checklist

## Notice
- Built only from `assets/notice-sentences.csv`. A row with `when=always` is always used; `when=<fact>=yes` rows are used only when that fact is `yes`.
- `{placeholders}` are filled from facts. A missing fact becomes `[TO BE BASELINED — owner: Product owner]`; the notice is still written. With `--strict` any such gap exits 1.
- Facts are written as phrases that complete the template sentence (see `assets/facts-template.csv` notes). Rewrite a fact in plainer words if the grade is above `max_grade`; do not edit `notice.md` by hand.
- Grade above `max_grade` (default 8) exits 1 with every output written.

## System card
Sections: Overview, Intended use, Not intended for, Data, Model, Human oversight, Limitations, Contact, Change log. Every row shows the fact's value and the `source` column from the facts CSV. Missing facts are TBD for the Product owner. The classification line reads `tier` (or `risk_tier`/`classification`/`category`) and `basis` (or `reasons`/`rationale`) from the optional `classification.json` written by `ai-platform/eu-ai-act-classifier`; other fields are ignored. Without it the line is TBD for the Compliance lead.

## Disclosure checklist (`assets/art50-duties.csv`)
| Column | Rule |
|---|---|
| applies | trigger fact `yes` → yes, `no` → no, missing → TBD (Product owner). The Art. 50(5) row applies when any other row applies |
| provided | `notice:<id>` evidence → yes when that notice sentence is present with no TBD; fact evidence → yes when the fact is filled; Art. 50(5) → `partial` when `notice_placement` is filled and the grade is within max (other accessibility requirements are not assessed), else no; `n/a` when the duty does not apply |
| status | provided · partial · missing (applies, not provided) · to confirm (applies is TBD) · not applicable |
| owner | role from the duty catalog: Product owner, Engineering lead, Privacy officer, Content lead |

The checklist never says "compliant". Exemptions (obvious from context, assistive editing, law enforcement, artistic works) are not assessed; see sources.md.
