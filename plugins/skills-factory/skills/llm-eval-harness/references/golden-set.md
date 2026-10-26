# Golden Set Construction

A golden set is the contract for "good enough". It is versioned, owned, and grows with every production failure.

## Layout (`assets/golden-set.csv`)
| Column | Meaning |
|---|---|
| id | Stable id (`GS-0001`) |
| category | Task slice (e.g., `refund_policy`, `tool_choice`, `abstain`, `safety`) |
| difficulty | easy / medium / hard / adversarial |
| input | The exact input to the system (JSON string for structured inputs) |
| expected | Reference output when one exists (exact match / JSON) |
| must_contain | `||`-separated keywords or `re:` regexes that a passing output contains |
| must_not_contain | `||`-separated keywords or `re:` regexes that must be absent (safety, leakage, hallucination markers) |
| expected_json_valid | `true` when the output must parse as JSON |
| weight | 1 default; higher for business-critical cases |
| source | `log`, `sme`, `incident-<id>`, `synthetic` |
| notes | Why this case exists |

## Coverage rules
| Rule | Target |
|---|---|
| Size | ≥ 30 to start; 100–300 for a production feature; grow with incidents |
| Real vs synthetic | ≥ 70% from logs/SMEs; synthetic labeled and reported separately |
| Difficulty mix | ~40% easy, 40% medium, 20% hard/adversarial (assumption) |
| Categories | Every user-visible task slice; every tool (for agents); abstention cases; out-of-scope; safety/injection |
| Negatives | Cases where the correct behavior is to refuse, ask, or say "not covered" |
| Edge cases | Empty input, very long input, non-English, ambiguous, conflicting instructions |
| Regression cases | One case per fixed production defect, tagged `incident-<id>` |

## Sourcing
1. Export recent production/pilot inputs; de-identify PII; sample stratified by category.
2. SMEs write expected outputs or acceptance notes; two reviewers for high-risk categories; disagreements resolved and recorded.
3. Convert acceptance notes into `must_contain` / `must_not_contain` so the deterministic scorer can run on every commit.
4. Reserve a held-out slice (≈20%) that prompt authors do not see, to detect overfitting the prompt to the set.

## Maintenance
| Event | Action |
|---|---|
| Production failure | Add case within the fix PR |
| Prompt/model change | Run full set; update baseline |
| Quarterly | Review stale cases; re-sample from logs; rebalance categories |
| Judge rubric change | Re-score baseline; do not compare across rubric versions |

## Anti-patterns
- Cases written by the prompt author only (confirmation bias).
- Expected outputs that are one of many valid phrasings scored by exact match — use keywords/regex or a judge.
- A set that never fails — it is not measuring anything.
