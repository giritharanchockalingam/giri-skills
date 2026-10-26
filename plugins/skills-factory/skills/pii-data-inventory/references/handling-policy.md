# Handling policy

The policy is owned by the Privacy officer (or DPO). This skill applies it; it never chooses a handling.

| Handling | Meaning for downstream AI use | Typical when |
|---|---|---|
| drop | Column removed before data leaves the system of record | Not needed for the use case (data minimisation) |
| tokenize | Replaced by a consistent surrogate (vault or keyed hash) so joins still work | Needed as a join key or for per-entity analysis |
| mask | Partially obscured (e.g. last 4) for display or debugging | Humans need to recognise, not use, the value |
| allow | Used in clear | Lawful basis and purpose recorded; access controlled |

## Resolution rule
A column can carry several types (e.g. `ipv4;ipv6`, or `email` found inside a `comment` column). Its handling is the **strictest** of its types: drop > tokenize > mask > allow. If any of its types is missing from the policy, the column is `[TO BE BASELINED — owner: Privacy officer]` — a partial policy never silently covers a column.

## Strict mode
`--strict` turns any TBD column into a failed run (exit 1). Use it as the gate before a sample moves to a lower-trust environment (notebook, vendor model, vector store).

## Public references (by name only)
- Data minimisation and purpose limitation: GDPR Article 5 principles.
- De-identification techniques: NIST SP 800-188 and NIST IR 8053.
- Card display: PCI DSS permits showing at most the first six and last four digits.
- LLM data leakage risk: OWASP Top 10 for LLM Applications (sensitive information disclosure).
