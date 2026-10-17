# Total Compensation Components

| Component | How to value | Notes |
|---|---|---|
| Base salary | As stated | Annual |
| Target bonus | base × target % | Show target; note the historical payout % if the user has it (ask) |
| Sign-on bonus | As stated, year 1 only | Note clawback period |
| Equity (RSU) | user-stated grant value ÷ vesting years, per year within horizon | Private company: use user's stated valuation; flag illiquidity |
| Equity (options) | user-stated (strike, FMV, count); value only if the user supplies a number | Otherwise `[TO BE BASELINED — owner: user]` |
| Retention / LTI | annualized over vesting period | Often exec-level; ask |
| 401k / pension match | base × match % (cap per plan) | User supplies plan terms |
| Health premiums | employer-paid annual amount if known; else difference in employee cost vs. current | Not a hardcoded value |
| PTO | (days − current days) × daily base rate | Only if the user wants it counted |
| Relocation | lump sum or covered costs, year 1 | Note tax gross-up status |
| Car / phone / stipends | annual stated | |
| Deferred comp / ESPP | only if the user quantifies | |

## Calculations
```
year1_cash      = base + bonus_target + sign_on + relocation
annual_recurring = base + bonus_target + equity_per_year + retirement_match + benefits_value + stipends
annualized_total = annual_recurring + (sign_on + relocation) / horizon_years
```
Show all three. Negotiation targets `annual_recurring`; the decision considers `annualized_total`.

## What not to do
- Do not assume bonus pays at target; ask for payout history or label as target.
- Do not value equity at a hoped-for price.
- Do not net taxes unless the user supplies state rates; if they do, apply the same method to every option.
- Do not count "unlimited PTO" as a number.

## Executive-level items to ask about
Severance terms, change-of-control, non-compete scope, bonus proration in year 1, review timing (6 vs 12 months), title and reporting line in writing, budget and headcount commitments, relocation timing flexibility.
