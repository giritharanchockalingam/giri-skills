# Screening and risk method

## Screening (WP248 rev.01, EDPB-endorsed)
| Criterion | Answered by processing key(s) |
|---|---|
| C1 Evaluation or scoring | `evaluation_scoring` |
| C2 Automated decision-making with legal or similar significant effect | `automated_decision_making` |
| C3 Systematic monitoring | `systematic_monitoring` |
| C4 Sensitive or highly personal data | `special_categories`, `criminal_data`, `highly_personal_data`; a `payment_card` column in the PII inventory counts when `highly_personal_data` is blank |
| C5 Large scale | `large_scale` |
| C6 Matching or combining datasets | `combining_datasets` |
| C7 Vulnerable data subjects | `vulnerable_subjects` |
| C8 Innovative use / new technology | `new_technology` |
| C9 Prevents a right, service or contract | `prevents_rights_or_service` |

`required` is true when:
1. an Art. 35(3) case applies — (a) `evaluation_scoring` and `automated_decision_making`; (b) `large_scale` and (`special_categories` or `criminal_data`); (c) `systematic_monitoring`, `publicly_accessible_area` and `large_scale`; or
2. two or more criteria are met; or
3. met + not-answered criteria ≥ 2 (precautionary: WP248 recommends a DPIA where it is unclear).

One criterion alone can still warrant a DPIA (WP248); the controller may decide to run one anyway.

## Risk scoring (skill convention, not from the GDPR)
- `score = likelihood × severity`, each 1 (low) – 3 (high).
- Level: 1–2 low · 3–4 medium · 6–9 high.
- Residual: the value the risk owner states. Blank residual with no measure → residual = inherent level (nothing reduces it). Blank residual with a measure → TBD (owner: Data protection officer).
- PII inventory columns whose handling is blank or TBD become unscored risks owned by the Data protection officer.

## Gate and consultation
- **Gate (exit 1):** any risk whose residual is high and that has no measure — the DPIA cannot be signed off. Outputs are still written.
- **Art. 36(1) prior consultation:** flagged whenever any residual risk is high, measure or not.
- Sign-off status: `blocked` (gate) · `incomplete` (any TBD in a risk row) · `ready`.
