# Method

1. **Normalise.** Each `license` string is lower-cased, "licence" → "license", and stripped of everything but letters, digits, `.` and `+`; it is then looked up against every catalog row's `spdx_id`, `name` and `aliases`. No match → `unknown` (never guessed).
2. **Expressions.** `A OR B`: each part resolved; the part with the best policy decision is chosen (allow < TBD < review < deny), ties to the first. `A AND B`: the strictest decision; flags are the union. Parentheses, `WITH`, or a mix of AND and OR → `unknown`.
3. **Decide.** Policy decision for the id; id not in the policy → `review`; no policy at all → `[TO BE BASELINED — owner: Legal counsel]`; unknown licence → `review` (TBD when no policy).
4. **Use rules.** `use` commercial or redistribution with `commercial_use_restricted=yes` → `deny`. With `conditional` (Llama MAU clause) an `allow` becomes `review`.
5. **Gate.** Any `deny` → exit 1; all outputs are still written.
6. **Obligations.** Catalog obligations are listed for every component that is not denied; unknown licences get a Legal-counsel TBD.

Policy rows must name a catalog id (SPDX or LicenseRef, or an alias); an unrecognised policy licence stops the run (exit 2) so the policy cannot silently miss.

Flags: `commercial_use_restricted` (yes/no/conditional), `copyleft`, `attribution_required`, `use_based_restrictions`, `redistribution_prohibited` (a `redistribution` use of such a licence is denied). They summarise the licence for triage; Legal counsel reads the licence itself.
