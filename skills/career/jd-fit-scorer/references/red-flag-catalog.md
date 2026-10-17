# Red-Flag Catalog

Penalties subtract from the 100-point total. Detection phrases are case-insensitive. The script applies them; judgement may waive a flag with a stated reason.

| # | Flag | Penalty | Detection phrases / signals | Why it matters at exec level |
|---|---|---|---|---|
| R1 | Title inflation | −10 | "Senior Director" but reports to a Director/Manager; team size ≤5; no budget mentioned | Comp band and scope will not match the title |
| R2 | Hands-on contradiction | −8 | "hands-on coding", "player-coach", "write production code" in a VP/Sr Dir JD | Signals under-resourced team or IC role in disguise |
| R3 | Kitchen-sink requirements | −6 | ≥4 unrelated platform stacks listed as required; "expert in" ≥8 technologies | Unrealistic profile; likely an internal candidate or a confused hiring manager |
| R4 | Unstated compensation in pay-transparency state | −3 | No salary band where law requires (CA, CO, NY, WA, IL, etc.) | Compliance laxity; expect low anchor |
| R5 | Vague scope | −5 | No team size, no budget, no reporting line, "wear many hats" | Role is undefined; 90-day plan impossible |
| R6 | Perpetual urgency | −5 | "fast-paced", "thrive under pressure", "hit the ground running", "24/7" | Burnout and turnover signal |
| R7 | Reposting churn | −5 | User reports JD reposted ≥3 times in 6 months, or multiple identical listings | Hiring freeze, rejected offers, or internal politics |
| R8 | Travel mismatch | −8 (hard if > user max + 15) | "travel up to X%" above user's stated maximum | Logistics; may be hard constraint |
| R9 | Clearance required now | hard NO-GO | "active TS/SCI", "must currently hold" | Cannot be met until clearance is granted |
| R10 | Contract / interim disguised as FTE | −6 | "contract-to-hire", "6-month engagement", "1099" | Different risk profile than stated |
| R11 | Industry in decline for the user's goals | −4 | User's stated avoid-list industries | Strategic fit |
| R12 | Excessive onsite for distant city | −6 | "5 days onsite" + city outside user's list, no relocation | Logistics |
| R13 | Missing leadership competencies | −4 | JD lists only technical skills; no mention of people, budget, strategy | Role is senior IC with a leadership title |
| R14 | Layoff / restructuring context | −3 | "backfill after reorg", "rebuild the team", recent public layoffs | Higher risk; may also be opportunity. Flag, don't block |

## Waiver rule
A flag may be waived only with a sentence of evidence (e.g., "R2 waived: recruiter confirmed no coding expectation, 2026-10-01"). Record waivers in the output.
