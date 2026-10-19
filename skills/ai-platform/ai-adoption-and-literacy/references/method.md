# Method

## Exposure levels
| Exposure | Who | Typical need |
|---|---|---|
| none | Staff who do not use the AI system but work near it | Awareness |
| user | Uses AI outputs in daily tasks | Safe use, prompting, checking outputs |
| operator | Runs, monitors or supports the AI system | Monitoring, incidents, escalation |
| builder | Designs, builds, evaluates or changes the system | Evaluation, guardrails, data protection |
| overseer | Accountable for decisions the system supports; can override or stop it | Human oversight, risk and accountability |

## Proficiency (0-3)
0 none · 1 basic (has used AI tools) · 2 working (uses or runs AI in role with confidence) · 3 advanced (can teach others). Assessed by the manager or a short self-assessment; record which.

## Rules
1. Required when `exposure ∈ audience` and `level > proficiency`.
2. Always required when `exposure ∈ mandatory_for` (default catalog: AIL-06 human oversight for overseers).
3. Hours per person = Σ module hours; role hours = headcount × hours per person; seats per module = Σ headcount.
4. Training load per business unit is mapped to its wave; no wave → `[TO BE BASELINED — owner: Change lead]`.
5. Gate (`--strict`): exit 1 when an operator or overseer role has no module, or the catalog has no overseer-mandatory module while overseers exist.

## KPIs
Five adoption KPIs are always listed with a definition and data source (skill design). Targets are never defaulted: each comes from `targets` or is `[TO BE BASELINED — owner: Change lead]`.

## Limits
Proficiency is an estimate. Hours exclude travel, backfill and refresher cycles. The default catalog is this skill's own design, not a regulatory syllabus.
