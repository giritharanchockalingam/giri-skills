# Severity matrix (the skill's default)

This is **the skill's default matrix**, used only when no `matrix` input is supplied; the runbook
then states "the skill's default matrix". It is a starting point, not an industry standard —
replace it with your organisation's incident policy by passing your own CSV in the same layout.

Machine copy: `references/severity-matrix.default.csv` (`rule_id,conditions,severity,reason`).

## Method
1. Missing `data_exposed` / `regulated_data` / `users_affected` are **unknown**.
2. Every row is evaluated; a row fires when all of its `;`-joined clauses hold.
3. Severity = the most severe fired row (SEV1 > SEV2 > SEV3 > SEV4). All fired rows are listed as the reasoning.
4. Numeric clauses (`users_affected>=100`) never fire on unknown; unknown is handled by explicit rows (D02, D03, D12) so **unknown escalates**.
5. A matrix where no row fires is invalid (exit 1): keep a baseline row with `always`.

## Default rows
| Rule | Conditions | Severity | Reason |
|---|---|---|---|
| D01 | data_exposed=yes; regulated_data=yes | SEV1 | Regulated data confirmed exposed |
| D02 | data_exposed=yes; regulated_data=unknown | SEV1 | Exposure confirmed, regulated status unknown — unknown escalates |
| D03 | data_exposed=unknown; regulated_data in yes/unknown | SEV2 | Exposure not ruled out, regulated data possible |
| D04 | data_exposed=yes | SEV2 | Data exposed (non-regulated) |
| D05 | category=data-leak | SEV2 | Data-leak category |
| D06 | category=harmful-output | SEV2 | Harmful output reached users |
| D07 | users_affected>=1000 | SEV2 | Broad blast radius |
| D08 | category=prompt-injection | SEV3 | Escalates via the data rows if data is touched |
| D09 | category=outage | SEV3 | Service unavailable or degraded |
| D10 | category=hallucination | SEV3 | Incorrect output reached users |
| D11 | users_affected>=100 | SEV3 | Material blast radius |
| D12 | users_affected=unknown | SEV3 | Blast radius unknown — unknown escalates |
| D13 | always | SEV4 | Baseline |

## Communications rule
- Internal: always.
- Customer: unless `users_affected = 0`.
- Regulator: only when `regulated_data` is `yes` or `unknown` (unknown escalates). Legal / privacy
  confirms the applicable obligations and deadlines (e.g. GDPR Article 33); the skill sets none.

## Related public practice (by name)
- NIST SP 800-61 (Computer Security Incident Handling Guide) — contain, eradicate, recover lifecycle.
- OWASP Top 10 for LLM Applications (2025) — category mapping in each playbook.
- NIST AI RMF 1.0, *Manage* function — incident response for AI systems.
