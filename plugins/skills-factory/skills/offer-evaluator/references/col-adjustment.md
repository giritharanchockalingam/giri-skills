# Relocation / Cost-of-Living Adjustment Method

## Inputs (user-supplied, always)
| Input | Example format | Source the user should cite |
|---|---|---|
| COL index per location | `Columbus OH=100, Austin TX=108` | A named COL calculator or survey, with date |
| Base location | The user's current city | — |
| Housing share (optional) | 0.35 | User's own budget; default 0.30 if the user accepts |
| State income tax (optional) | Effective % per state | User-supplied |

The skill and script carry **no built-in indices**. If the user cannot supply one, mark `[TO BE BASELINED — owner: user]` and compare nominal figures only.

## Method
1. Normalize indices to the base location: `rel_index = index_target / index_base`.
2. Adjust only recurring, location-spent dollars: `adjusted_recurring = annual_recurring / rel_index`.
3. Do not COL-adjust: sign-on, relocation, equity (portable value), 401k match (portable).
4. Optional housing-weighted variant when the user supplies a housing index separately:
   `blended = housing_share × housing_rel + (1 − housing_share) × non_housing_rel`.
5. Optional tax step when the user supplies rates: `after_tax = recurring × (1 − effective_rate)` applied to every option.
6. Report nominal and adjusted side by side; the decision matrix uses adjusted.

## Remote roles
- Remote with the user staying put: rel_index = 1.0; note any geo-pay band the company applies.
- Remote with planned move: use the destination index and flag the company's geo-pay policy as a risk.

## Relocation logistics checklist (ask, do not assume)
| Item | Ask |
|---|---|
| Relocation package | Lump sum vs. managed; gross-up; repayment clause |
| Timing | Must move by when; temporary housing covered? |
| Home sale / lease break | Covered? |
| Family | School-year timing, spouse employment support |
| Travel before move | Covered trips, cadence |

## Output table
| Option | Location | Index (source, date) | Annual recurring (nominal) | Rel index | Annual recurring (adjusted) | Delta vs current |
|---|---|---|---|---|---|---|
