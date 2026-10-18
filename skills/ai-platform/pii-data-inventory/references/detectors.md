# Detectors

All detectors are deterministic (regex + checksum + stdlib parsers). Cells are trimmed; empty cells are skipped and excluded from the match-rate denominator.

| Type | Rule | Scope | Masked example format |
|---|---|---|---|
| email | `local@domain.tld` | whole cell, or embedded in free text | `j***@e***.com` (first char of local part and first domain label, keep TLD) |
| phone | E.164 (`+` and 8–15 digits after removing separators) or NANP 10-digit with optional `+1`/`1` and `( ) . - space` separators | whole cell | `***-***-0142` (last 4) |
| ssn | `ddd-dd-dddd`, structurally valid: area ≠ 000, 666, 900–999; group ≠ 00; serial ≠ 0000 | whole cell, or embedded in free text | `***-**-6789` (last 4) |
| payment_card | 13–19 digits (spaces/dashes allowed) passing the Luhn checksum | whole cell | `**** 1111` (last 4, as PCI DSS display rules permit) |
| ipv4 / ipv6 | stdlib `ipaddress.ip_address` parses the cell | whole cell | `192.***.***.***`, `2001:****:…` |
| dob | ISO `YYYY-MM-DD` or `MM/DD/YYYY` date in a column whose name contains `dob` or `birth` | whole cell | `****-**-**` |

Precedence inside one cell: an SSN match suppresses card and phone; a card match suppresses phone.

## Column-name hints
Tokens are split on non-alphanumerics and camelCase.
- `name`: token `name` (or firstname/lastname/fullname/surname/givenname), unless the column also names a thing (product, file, host, company, sku, …) or is `username`.
- `address`: token `address`/`street`, unless qualified as ip/email/mac/web/url.
- `ssn`, `email`/`mail`, `phone`/`mobile`/`tel`.
A hint adds the type with basis `name-hint` and match rate from value detectors only. Hints are heuristics: a human confirms or dismisses them.

## Known false positives / negatives
- 13–19 digit identifiers pass Luhn about 1 time in 10 → may show as payment_card. Check the column's meaning.
- Any 10-digit number shaped like NANP shows as phone.
- Version strings like `1.2.3.4` parse as IPv4.
- Not detected: names/addresses in free text, non-US national IDs, health/biometric data, quasi-identifiers (ZIP + birth date + gender).
- SSNs in invalid ranges (000/666/9xx) are not flagged by value; an `ssn` column-name hint still flags the column.

## Leak check
`scan_pii.py --leak-check <report> --data <sample>` re-runs every detector over the sample and fails (exit 1) if any matched raw text appears verbatim in the report. Both outputs are checked on every run.
