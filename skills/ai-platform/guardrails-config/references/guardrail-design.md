# Guardrail design — deterministic first layer

## Rule types and precedence
`guard.evaluate` checks, in order, and any block wins:

| Order | Rule | Applies to | Action | Catches | Misses |
|---|---|---|---|---|---|
| 1 | Length (`LEN-IN`, `LEN-OUT`) | in / out | block | context stuffing, runaway outputs | short attacks |
| 2 | Injection markers (`INJ-nnn`) | in | block | known override phrases, incl. case, spacing, line-break and zero-width variants | paraphrase, translation, encoding |
| 3 | Blocked topics (`TOPIC-nnn`) | in + out | block | exact phrases from the policy | synonyms, implied requests |
| 4 | Tool allowlist (`TOOL-DENY`) | tool calls | block | any tool not listed (default deny) | misuse of an allowed tool's arguments |
| 5 | PII action block (`PII-<TYPE>`) | in + out | block | patterned identifiers | names, addresses, free-text identifiers |
| 6 | PII action mask | in + out | mask (token such as `[EMAIL]`) | same as above | same as above |
| 7 | Otherwise | — | allow | — | — |

Reasons list rule ids only, never the matched text, so logs can be kept without re-exposing PII.

## PII detectors (built into `scripts/guard.py`, copied into guardrails.json)
| Type | Rule | Detection |
|---|---|---|
| card | `PII-CARD` | 13–19 digits with optional spaces/dashes and a valid Luhn checksum (a digit run that fails Luhn is not a card) |
| ssn | `PII-SSN` | US SSN pattern NNN-NN-NNNN; area 000, 666 and 9xx, group 00 and serial 0000 excluded |
| email | `PII-EMAIL` | local@domain.tld pattern |
| phone | `PII-PHONE` | NANP forms such as (612) 555-0199, 612-555-0199, +1 612 555 0142; or +country code with separated groups |

Detectors run in that order and an earlier detector claims overlapping text, so a card number is never also masked as a phone.

## Writing the policy
- Blocked topics: short, specific phrases; one concept per entry. Review hits weekly at first.
- PII: `mask` keeps the conversation useful; `block` where even a masked request should not proceed (payment cards in chat); `allow` only with a documented reason. A type left out is reported as to be baselined (owner: Data protection officer).
- Length limits from the product's real maximum prompt and answer sizes, not a guess.
- Tool allowlist: name every tool the agent may call; anything else is denied.
- Extra injection markers: phrases seen in red-team runs or production logs.

## Testing
Cover, per rule type, at least one allow, one block or mask, and an evasion variant. Use reserved or documented fictional values only: example.com addresses, 555-01xx phone numbers, payment-network test card numbers, never-issued SSNs. Never put real customer data in a test file.

## Deployment pattern
1. Input: `evaluate(rules, user_text, "in")` before the model sees it; on block, return a refusal message; on mask, send `output_text`.
2. Retrieved documents and tool results: run the same input check before adding them to the prompt (indirect injection).
3. Tool call: `evaluate(rules, "", "in", tool=name)` before executing.
4. Output: `evaluate(rules, model_text, "out")` before the user sees it.
5. Log decision and reasons (rule ids) to observability; alert on block-rate spikes.

## Standards (by name)
- OWASP Top 10 for LLM Applications — LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM06 Excessive Agency.
- NIST AI Risk Management Framework (AI RMF 1.0) — MANAGE function: risk treatments implemented and monitored.
- PCI DSS — payment card data should not be stored or echoed; block or mask card numbers.
