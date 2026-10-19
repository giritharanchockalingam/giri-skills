# Classification method

Answers are `yes`, `no` or blank (blank, `unknown` and `tbd` all count as unanswered). The script applies these rules in order.

| Step | Rule | Result |
|---|---|---|
| 1 | Any Art. 5 key = yes | **prohibited**. Gate fails (exit 1). Outputs are still written. |
| 2 | `annex1_safety_component` = yes | high-risk route `annex1` (Art. 6(1)) |
| 3 | Any Annex III key = yes, and `d63_profiling` = yes **or** every Art. 6(3) condition = no | high-risk route `annex3` (Art. 6(2)) |
| 4 | Annex III = yes, `d63_profiling` = no, and at least one Art. 6(3) condition = yes | Art. 6(3) derogation: not high-risk. Adds DER-6-4 (document and register). |
| 5 | Not high-risk, and any Art. 50 key = yes | **limited-transparency** |
| 6 | Otherwise | **minimal** |

## Undetermined
If a blank answer could change the tier, the tier is `undetermined`. `provisional_tier` shows where the answers so far point.

| Provisional tier | Keys that can still change it |
|---|---|
| high-risk | blank Art. 5 keys |
| limited-transparency | blank Art. 5, Annex I, Annex III and (when relevant) Art. 6(3) keys |
| minimal | all of the above plus blank Art. 50 keys |

Every unanswered key is listed under Open questions with `[TO BE BASELINED — owner: AI compliance lead]` and a "could change tier" flag. Blank keys that only affect obligations (role, placed_on_market, GPAI) are listed but do not make the tier undetermined.

## Obligations
- Rows come from `assets/obligations-catalogue.csv` (`trigger`, `applies_to_role`, `date_rule`).
- HR-FRIA (Art. 27) is listed only when the deployer answers `fria_scope` yes (Art. 27(1): bodies governed by public law, private entities providing public services, Annex III 5(b)/(c) uses); when it is blank for an Annex III deployer the report says so and the key is an open question.
- AI-LIT paraphrases Art. 4 as amended by Reg. 2026/1744 ("take measures to support the development of AI literacy").
- User text written to obligations.csv (owner, evidence) that starts with = + - @ tab or CR gets a leading `'` (CSV-injection guard).
- They are filtered by role. If the role is blank, every role's rows are listed.
- High-risk dates come from the route: Annex III 2027-12-02, Annex I 2028-08-02. When both routes apply, the earlier date is used.
- The `pom_before` rule uses `placed_on_market`. If that is blank, the date reads "X or Y [TO BE BASELINED …]".
- `--as-of` sets `in_force` to yes or no. Without it, the column reads "not assessed". The run date is never used.
- Evidence rows set `status`, `evidence` and `owner`. With no evidence row, the status is `open` and the owner is `accountable_owner`, or the TBD marker if that is blank.
